"""
3DCity Generator Script for Blender
Generates 3D city models from OpenStreetMap data with terrain elevation.

Usage:
  blender --background --python generator.py -- --min-lat 48.8566 --max-lat 48.8666 --min-lon 2.3522 --max-lon 2.3622
  Or run in Blender without arguments to use the UI panel
"""

import bpy
import sys
import argparse
import os
import json
import math
import time
from pathlib import Path

# Try to import required libraries
try:
    import requests
    from requests.exceptions import RequestException, Timeout, ConnectionError, HTTPError
except ImportError:
    print("ERROR: requests library not found. Please install with: pip install requests")
    sys.exit(1)

try:
    import numpy as np
except ImportError:
    print("ERROR: numpy library not found. Please install with: pip install numpy")
    sys.exit(1)


class CityGenerator:
    """Main class for generating 3D city models"""
    
    def __init__(self, min_lat, max_lat, min_lon, max_lon):
        self.min_lat = min_lat
        self.max_lat = max_lat
        self.min_lon = min_lon
        self.max_lon = max_lon
        self.center_lat = (min_lat + max_lat) / 2
        self.center_lon = (min_lon + max_lon) / 2
        
        # Configuration for downloads
        self.max_retries = 3
        self.initial_timeout = 30
        self.backoff_factor = 2
        
        # Configuration for sequential processing with rate limiting
        # No multithreading to avoid 429 errors
        self.request_delay = 0.2  # 200ms delay between requests (5 requests per second)
        
        # List of public Overpass API servers for fallback
        # When one server fails, we try the next one
        self.overpass_servers = [
            "https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.openstreetmap.ru/api/interpreter",
        ]
        
        # Track errors and warnings during generation
        self.errors = []
        self.warnings = []
        
        # Store elevation data for 3D relief roads
        self.elevation_data = None
        self.elevation_grid_size = None
        
        # Create export directory if it doesn't exist
        self.export_dir = Path("export")
        self.export_dir.mkdir(exist_ok=True)
        
        # Enable required Blender addons
        self._enable_export_addons()
        
        print(f"Initialized CityGenerator for area:")
        print(f"  Latitude: {min_lat} to {max_lat}")
        print(f"  Longitude: {min_lon} to {max_lon}")
    
    def _enable_export_addons(self):
        """Enable export addons for various file formats"""
        addons_to_enable = [
            'io_scene_fbx',  # Autodesk FBX format (widely supported)
        ]
        
        for addon in addons_to_enable:
            try:
                if addon not in bpy.context.preferences.addons:
                    bpy.ops.preferences.addon_enable(module=addon)
                    print(f"Enabled addon: {addon}")
            except Exception as e:
                print(f"Could not enable addon {addon}: {e}")
    
    def _retry_request(self, request_func, operation_name, *args, **kwargs):
        """
        Retry a request with exponential backoff.
        Sequential processing with delays to avoid rate limiting.
        
        Args:
            request_func: Function to call (e.g., requests.get or requests.post)
            operation_name: Name of the operation for logging
            *args, **kwargs: Arguments to pass to request_func
            
        Returns:
            Response object or None if all retries failed
        """
        for attempt in range(self.max_retries):
            try:
                # Apply delay to avoid 429 errors (sequential processing)
                if attempt == 0:
                    time.sleep(self.request_delay)
                
                timeout = self.initial_timeout * (self.backoff_factor ** attempt)
                kwargs['timeout'] = timeout
                
                if attempt > 0:
                    wait_time = self.backoff_factor ** (attempt - 1)
                    print(f"Retrying {operation_name} (attempt {attempt + 1}/{self.max_retries}) after {wait_time}s wait...")
                    time.sleep(wait_time)
                
                response = request_func(*args, **kwargs)
                response.raise_for_status()
                return response
                
            except Timeout:
                error_msg = f"{operation_name}: Request timed out after {timeout}s"
                print(f"WARNING: {error_msg}")
                if attempt == self.max_retries - 1:
                    self.errors.append(error_msg)
                    
            except ConnectionError as e:
                error_msg = f"{operation_name}: Connection error - {str(e)}"
                print(f"WARNING: {error_msg}")
                if attempt == self.max_retries - 1:
                    self.errors.append(error_msg)
                    
            except HTTPError as e:
                error_msg = f"{operation_name}: HTTP error {e.response.status_code} - {str(e)}"
                print(f"WARNING: {error_msg}")
                
                # Special handling for 429 (Rate Limiting)
                if e.response.status_code == 429:
                    if attempt < self.max_retries - 1:
                        # Wait longer for rate limit errors
                        rate_limit_wait = 10 * (attempt + 1)  # 10s, 20s, 30s...
                        print(f"Rate limit (429) detected. Waiting {rate_limit_wait}s before retry...")
                        time.sleep(rate_limit_wait)
                        continue
                    else:
                        self.errors.append(f"{error_msg} - Rate limit exceeded after all retries")
                        return None
                
                # Don't retry on client errors (4xx) except for rate limiting
                if e.response.status_code < 500 and e.response.status_code != 429:
                    self.errors.append(error_msg)
                    return None
                
                # For 504 Gateway Timeout, use longer wait times
                if e.response.status_code == 504 and attempt < self.max_retries - 1:
                    extra_wait = 5  # Add 5 extra seconds for gateway timeouts
                    wait_time = (self.backoff_factor ** attempt) + extra_wait
                    print(f"Gateway timeout detected. Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue  # Skip the normal wait at the top of the loop
                
                if attempt == self.max_retries - 1:
                    self.errors.append(error_msg)
                    
            except RequestException as e:
                error_msg = f"{operation_name}: Request failed - {str(e)}"
                print(f"WARNING: {error_msg}")
                if attempt == self.max_retries - 1:
                    self.errors.append(error_msg)
                    
            except Exception as e:
                error_msg = f"{operation_name}: Unexpected error - {str(e)}"
                print(f"ERROR: {error_msg}")
                self.errors.append(error_msg)
                return None
        
        return None
    
    def clear_scene(self):
        """Clear all objects from the scene"""
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        print("Scene cleared")
    
    def lat_lon_to_meters(self, lat, lon):
        """Convert lat/lon to local meters relative to center"""
        # Approximate conversion (good enough for small areas)
        lat_diff = lat - self.center_lat
        lon_diff = lon - self.center_lon
        
        # 1 degree latitude ≈ 111,320 meters
        # 1 degree longitude ≈ 111,320 * cos(latitude) meters
        y = lat_diff * 111320
        x = lon_diff * 111320 * math.cos(math.radians(self.center_lat))
        
        return x, y
    
    def download_osm_data(self):
        """Download OpenStreetMap data for the specified area with robust error handling
        
        This method tries multiple Overpass API servers for increased reliability.
        If one server fails (e.g., 504 Gateway Timeout), it automatically tries the next one.
        """
        print("Downloading OSM data...")
        
        # Overpass API query
        overpass_query = f"""
        [out:json][timeout:60];
        (
          way["building"]({self.min_lat},{self.min_lon},{self.max_lat},{self.max_lon});
          way["highway"]({self.min_lat},{self.min_lon},{self.max_lat},{self.max_lon});
          way["waterway"]({self.min_lat},{self.min_lon},{self.max_lat},{self.max_lon});
          way["natural"="water"]({self.min_lat},{self.min_lon},{self.max_lat},{self.max_lon});
          node["natural"="tree"]({self.min_lat},{self.min_lon},{self.max_lat},{self.max_lon});
          way["natural"="tree_row"]({self.min_lat},{self.min_lon},{self.max_lat},{self.max_lon});
        );
        out body;
        >;
        out skel qt;
        """
        
        # Try each Overpass API server in turn
        last_error = None
        for server_index, overpass_url in enumerate(self.overpass_servers, 1):
            print(f"Trying Overpass API server {server_index}/{len(self.overpass_servers)}: {overpass_url}")
            
            response = self._retry_request(
                requests.post,
                f"OSM data download from server {server_index}",
                overpass_url,
                data={'data': overpass_query}
            )
            
            if response is not None:
                # Success! Parse and return the data
                try:
                    data = response.json()
                    elements_count = len(data.get('elements', []))
                    
                    if elements_count == 0:
                        warning_msg = "OSM data download succeeded but returned 0 elements. The area may not have any mapped features."
                        print(f"WARNING: {warning_msg}")
                        self.warnings.append(warning_msg)
                    else:
                        print(f"Successfully downloaded {elements_count} OSM elements from server {server_index}")
                    
                    return data
                    
                except json.JSONDecodeError as e:
                    error_msg = f"Failed to parse OSM data JSON response from server {server_index}: {str(e)}"
                    print(f"ERROR: {error_msg}")
                    last_error = error_msg
                    # Try next server
                    continue
                except Exception as e:
                    error_msg = f"Unexpected error processing OSM data from server {server_index}: {str(e)}"
                    print(f"ERROR: {error_msg}")
                    last_error = error_msg
                    # Try next server
                    continue
            else:
                # This server failed after retries, try next one
                print(f"Server {server_index} failed after all retries, trying next server...")
                last_error = f"Server {server_index} ({overpass_url}) failed after all retries"
        
        # All servers failed
        warning_msg = f"Failed to download OSM data from all {len(self.overpass_servers)} servers. Using empty dataset."
        if last_error:
            warning_msg += f" Last error: {last_error}"
        print(f"WARNING: {warning_msg}")
        self.warnings.append(warning_msg)
        return {'elements': []}
    
    def _fetch_elevation_point(self, lat, lon, i, j):
        """
        Fetch elevation data for a single point.
        
        Args:
            lat: Latitude of the point
            lon: Longitude of the point
            i: Row index
            j: Column index
            
        Returns:
            tuple: (i, j, elevation, success)
        """
        url = f"https://api.open-elevation.com/api/v1/lookup?locations={lat},{lon}"
        
        response = self._retry_request(
            requests.get,
            f"Terrain elevation point ({i},{j})",
            url
        )
        
        if response is not None:
            try:
                data = response.json()
                if 'results' in data and len(data['results']) > 0:
                    elevation = data['results'][0]['elevation']
                    return (i, j, elevation, True)
                else:
                    return (i, j, 0, False)
            except (json.JSONDecodeError, KeyError, IndexError):
                return (i, j, 0, False)
        else:
            return (i, j, 0, False)
    
    def download_terrain_data(self):
        """Download terrain elevation data with 50cm resolution using sequential processing"""
        print("Downloading terrain data...")
        
        # Calculate grid size for 50cm (0.5m) resolution
        # Calculate area dimensions in meters
        lat_meters = (self.max_lat - self.min_lat) * 111320
        lon_meters = (self.max_lon - self.min_lon) * 111320 * math.cos(math.radians(self.center_lat))
        
        # Calculate grid size for 0.5m resolution (capped at 100 for API limits)
        grid_size_lat = min(int(lat_meters / 0.5), 100)
        grid_size_lon = min(int(lon_meters / 0.5), 100)
        grid_size = max(grid_size_lat, grid_size_lon, 20)  # Minimum 20 for quality
        
        lat_step = (self.max_lat - self.min_lat) / grid_size
        lon_step = (self.max_lon - self.min_lon) / grid_size
        
        total_points = (grid_size + 1) * (grid_size + 1)
        
        print(f"Fetching elevation data for {total_points} grid points sequentially...")
        print(f"Estimated time: {total_points * self.request_delay / 60:.1f} minutes")
        
        try:
            # Initialize elevation data array with zeros
            elevation_data = np.zeros((grid_size + 1, grid_size + 1))
            
            # Sequential counters
            successful_downloads = 0
            failed_downloads = 0
            points_processed = 0
            first_failure_logged = False
            
            # Process points sequentially
            for i in range(grid_size + 1):
                for j in range(grid_size + 1):
                    lat = self.min_lat + i * lat_step
                    lon = self.min_lon + j * lon_step
                    
                    # Fetch elevation for this point
                    i_result, j_result, elevation, success = self._fetch_elevation_point(lat, lon, i, j)
                    
                    # Update elevation data
                    elevation_data[i_result, j_result] = elevation
                    
                    # Update counters
                    if success:
                        successful_downloads += 1
                    else:
                        failed_downloads += 1
                        if not first_failure_logged:
                            warning_msg = f"Invalid elevation data format at point ({i},{j})"
                            self.warnings.append(warning_msg)
                            first_failure_logged = True
                    
                    points_processed += 1
                    
                    # Progress reporting every 10%
                    if points_processed % max(1, total_points // 10) == 0:
                        progress = (points_processed / total_points) * 100
                        print(f"Progress: {progress:.0f}% ({points_processed}/{total_points} points)")
            
            # Summary
            print(f"Terrain data download complete:")
            print(f"  Grid size: {elevation_data.shape}")
            print(f"  Successful: {successful_downloads}/{total_points} points")
            
            if failed_downloads > 0:
                warning_msg = f"Failed to download elevation for {failed_downloads}/{total_points} points (using 0m elevation as fallback)"
                print(f"WARNING: {warning_msg}")
                self.warnings.append(warning_msg)
            
            # Validate that we got some real elevation data
            if elevation_data.max() == 0 and elevation_data.min() == 0:
                warning_msg = "All elevation data is 0. Terrain will be flat. This may indicate API failures."
                print(f"WARNING: {warning_msg}")
                self.warnings.append(warning_msg)
            
            # Store elevation data and grid size for 3D relief roads
            self.elevation_data = elevation_data
            self.elevation_grid_size = grid_size
            
            return elevation_data
            
        except Exception as e:
            error_msg = f"Critical error during terrain data download: {str(e)}"
            print(f"ERROR: {error_msg}")
            self.errors.append(error_msg)
            print("Using flat terrain as fallback")
            fallback_data = np.zeros((grid_size + 1, grid_size + 1))
            self.elevation_data = fallback_data
            self.elevation_grid_size = grid_size
            return fallback_data
    
    def create_terrain(self, elevation_data):
        """Create terrain mesh from elevation data"""
        print("Creating terrain...")
        
        rows, cols = elevation_data.shape
        vertices = []
        faces = []
        
        # Create vertices
        for i in range(rows):
            for j in range(cols):
                lat = self.min_lat + (i / (rows - 1)) * (self.max_lat - self.min_lat)
                lon = self.min_lon + (j / (cols - 1)) * (self.max_lon - self.min_lon)
                x, y = self.lat_lon_to_meters(lat, lon)
                z = elevation_data[i, j] * 0.1  # Scale down elevation
                vertices.append((x, y, z))
        
        # Create faces
        for i in range(rows - 1):
            for j in range(cols - 1):
                v1 = i * cols + j
                v2 = i * cols + j + 1
                v3 = (i + 1) * cols + j + 1
                v4 = (i + 1) * cols + j
                faces.append((v1, v2, v3, v4))
        
        # Create mesh
        mesh = bpy.data.meshes.new("Terrain")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        
        # Create object
        terrain_obj = bpy.data.objects.new("Terrain", mesh)
        bpy.context.collection.objects.link(terrain_obj)
        
        # Add detailed terrain material with high-quality grass texture
        material = bpy.data.materials.new(name="DetailedTerrainMaterial")
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        
        # Clear default nodes
        nodes.clear()
        
        # Output
        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (800, 0)
        
        # Main BSDF
        bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
        bsdf.location = (500, 0)
        bsdf.inputs['Roughness'].default_value = 0.95
        bsdf.inputs['Specular IOR Level'].default_value = 0.3
        
        # === GRASS BLADE DETAIL ===
        # High-frequency noise for grass blades
        grass_detail = nodes.new(type='ShaderNodeTexNoise')
        grass_detail.location = (-1000, 300)
        grass_detail.inputs['Scale'].default_value = 150.0  # Very high detail
        grass_detail.inputs['Detail'].default_value = 15.0
        grass_detail.inputs['Roughness'].default_value = 0.7
        
        # === GRASS PATCHES ===
        # Medium-frequency noise for grass color patches
        grass_patches = nodes.new(type='ShaderNodeTexNoise')
        grass_patches.location = (-1000, 0)
        grass_patches.inputs['Scale'].default_value = 25.0
        grass_patches.inputs['Detail'].default_value = 10.0
        grass_patches.inputs['Roughness'].default_value = 0.5
        
        # === DIRT/BARE PATCHES ===
        # Voronoi for organic dirt patches
        voronoi = nodes.new(type='ShaderNodeTexVoronoi')
        voronoi.location = (-1000, -300)
        voronoi.inputs['Scale'].default_value = 5.0
        voronoi.voronoi_dimensions = '3D'
        voronoi.feature = 'F1'
        
        # === GRASS COLOR VARIATION ===
        # Create rich grass color with multiple shades
        grass_color_ramp = nodes.new(type='ShaderNodeValToRGB')
        grass_color_ramp.location = (-600, 200)
        # Add more color stops for variation
        grass_color_ramp.color_ramp.elements[0].position = 0.0
        grass_color_ramp.color_ramp.elements[0].color = (0.08, 0.2, 0.05, 1.0)  # Very dark green
        grass_color_ramp.color_ramp.elements[1].position = 0.3
        grass_color_ramp.color_ramp.elements[1].color = (0.15, 0.35, 0.1, 1.0)  # Dark green
        grass_color_ramp.color_ramp.elements.new(0.6)
        grass_color_ramp.color_ramp.elements[2].color = (0.25, 0.5, 0.15, 1.0)  # Medium green
        grass_color_ramp.color_ramp.elements.new(0.9)
        grass_color_ramp.color_ramp.elements[3].color = (0.4, 0.6, 0.2, 1.0)  # Light green
        
        # === DIRT COLOR ===
        dirt_color_ramp = nodes.new(type='ShaderNodeValToRGB')
        dirt_color_ramp.location = (-600, -300)
        dirt_color_ramp.color_ramp.elements[0].color = (0.3, 0.2, 0.1, 1.0)  # Dark dirt
        dirt_color_ramp.color_ramp.elements[1].color = (0.45, 0.35, 0.2, 1.0)  # Light dirt
        
        # === MIX GRASS DETAIL INTO COLOR ===
        mix_grass_detail = nodes.new(type='ShaderNodeMixRGB')
        mix_grass_detail.location = (-400, 100)
        mix_grass_detail.blend_type = 'OVERLAY'
        mix_grass_detail.inputs['Fac'].default_value = 0.4
        
        # === MIX GRASS WITH DIRT ===
        mix_grass_dirt = nodes.new(type='ShaderNodeMixRGB')
        mix_grass_dirt.location = (-200, 0)
        mix_grass_dirt.blend_type = 'MIX'
        
        # === BUMP MAPPING FOR TERRAIN ===
        # Combine multiple noise layers for terrain bumps
        bump = nodes.new(type='ShaderNodeBump')
        bump.location = (200, -300)
        bump.inputs['Strength'].default_value = 0.5
        bump.inputs['Distance'].default_value = 0.05
        
        # Mix noise for bump height
        bump_mix = nodes.new(type='ShaderNodeMixRGB')
        bump_mix.location = (-100, -300)
        bump_mix.blend_type = 'ADD'
        bump_mix.inputs['Fac'].default_value = 0.5
        
        # Texture coordinates
        tex_coord = nodes.new(type='ShaderNodeTexCoord')
        tex_coord.location = (-1200, 0)
        
        # === CONNECT NODES ===
        # Texture coordinates
        links.new(tex_coord.outputs['Generated'], grass_detail.inputs['Vector'])
        links.new(tex_coord.outputs['Generated'], grass_patches.inputs['Vector'])
        links.new(tex_coord.outputs['Generated'], voronoi.inputs['Vector'])
        
        # Grass color with detail
        links.new(grass_patches.outputs['Fac'], grass_color_ramp.inputs['Fac'])
        links.new(grass_color_ramp.outputs['Color'], mix_grass_detail.inputs['Color1'])
        links.new(grass_detail.outputs['Fac'], mix_grass_detail.inputs['Color2'])
        
        # Dirt color
        links.new(voronoi.outputs['Distance'], dirt_color_ramp.inputs['Fac'])
        
        # Mix grass with dirt
        links.new(mix_grass_detail.outputs['Color'], mix_grass_dirt.inputs['Color1'])
        links.new(dirt_color_ramp.outputs['Color'], mix_grass_dirt.inputs['Color2'])
        links.new(voronoi.outputs['Distance'], mix_grass_dirt.inputs['Fac'])
        
        # Bump mapping
        links.new(grass_detail.outputs['Fac'], bump_mix.inputs['Color1'])
        links.new(grass_patches.outputs['Fac'], bump_mix.inputs['Color2'])
        links.new(bump_mix.outputs['Color'], bump.inputs['Height'])
        links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
        
        # Final color
        links.new(mix_grass_dirt.outputs['Color'], bsdf.inputs['Base Color'])
        
        # Output
        links.new(bsdf.outputs['BSDF'], output_node.inputs['Surface'])
        
        terrain_obj.data.materials.append(material)
        
        print(f"Created terrain with {len(vertices)} vertices and {len(faces)} faces")
        return terrain_obj
    
    def get_elevation_at_xy(self, x, y):
        """
        Get the elevation at a specific (x, y) coordinate by interpolating from elevation data.
        Returns elevation in meters (scaled by 0.1 like the terrain).
        
        Args:
            x, y: Coordinates in meters from the center
        
        Returns:
            float: Elevation at the given coordinate (scaled by 0.1)
        """
        if self.elevation_data is None or self.elevation_grid_size is None:
            return 0.0  # Return flat if no elevation data
        
        # Convert x, y back to lat, lon
        lat_diff = y / 111320
        lon_diff = x / (111320 * math.cos(math.radians(self.center_lat)))
        lat = self.center_lat + lat_diff
        lon = self.center_lon + lon_diff
        
        # Clamp to bounds
        lat = max(self.min_lat, min(self.max_lat, lat))
        lon = max(self.min_lon, min(self.max_lon, lon))
        
        # Convert to grid coordinates
        grid_size = self.elevation_grid_size
        lat_norm = (lat - self.min_lat) / (self.max_lat - self.min_lat)
        lon_norm = (lon - self.min_lon) / (self.max_lon - self.min_lon)
        
        # Get grid indices (continuous)
        i_float = lat_norm * grid_size
        j_float = lon_norm * grid_size
        
        # Get surrounding grid points
        i = int(i_float)
        j = int(j_float)
        i = max(0, min(grid_size - 1, i))
        j = max(0, min(grid_size - 1, j))
        
        # Bilinear interpolation
        i_frac = i_float - i
        j_frac = j_float - j
        
        # Get four corner elevations
        e00 = self.elevation_data[i, j]
        e10 = self.elevation_data[min(i + 1, grid_size), j]
        e01 = self.elevation_data[i, min(j + 1, grid_size)]
        e11 = self.elevation_data[min(i + 1, grid_size), min(j + 1, grid_size)]
        
        # Interpolate
        e0 = e00 * (1 - j_frac) + e01 * j_frac
        e1 = e10 * (1 - j_frac) + e11 * j_frac
        elevation = e0 * (1 - i_frac) + e1 * i_frac
        
        # Scale by 0.1 like the terrain
        return elevation * 0.1
    
    def create_buildings(self, osm_data):
        """Create building meshes from OSM data"""
        print("Creating buildings...")
        
        # Parse nodes
        nodes = {}
        for element in osm_data.get('elements', []):
            if element['type'] == 'node':
                nodes[element['id']] = element
        
        building_count = 0
        for element in osm_data.get('elements', []):
            if element['type'] == 'way' and 'building' in element.get('tags', {}):
                node_ids = element['nodes']
                
                # Get coordinates
                coords = []
                for node_id in node_ids:
                    if node_id in nodes:
                        node = nodes[node_id]
                        lat = node['lat']
                        lon = node['lon']
                        x, y = self.lat_lon_to_meters(lat, lon)
                        coords.append((x, y))
                
                if len(coords) < 3:
                    continue
                
                # Get building height
                tags = element.get('tags', {})
                height = float(tags.get('height', tags.get('building:levels', 3))) * 3
                if 'height' not in tags:
                    height = height  # levels * 3 meters per level
                
                # Create building
                self.create_building_mesh(coords, height)
                building_count += 1
        
        print(f"Created {building_count} buildings")
    
    def create_building_mesh(self, coords, height):
        """Create a single building mesh with detailed facade and roof"""
        import random
        vertices = []
        faces = []
        uvs = []
        
        # Bottom vertices
        for x, y in coords[:-1]:  # Exclude last coord if it's same as first
            vertices.append((x, y, 0))
        
        n = len(vertices)
        
        # Top vertices
        for x, y in coords[:-1]:
            vertices.append((x, y, height))
        
        # Bottom face
        bottom_face = list(range(n))
        faces.append(bottom_face)
        
        # Top face (roof)
        top_face = list(range(n, 2 * n))
        top_face.reverse()
        faces.append(top_face)
        
        # Side faces (walls)
        for i in range(n):
            next_i = (i + 1) % n
            face = [i, next_i, next_i + n, i + n]
            faces.append(face)
        
        # Create mesh
        mesh = bpy.data.meshes.new("Building")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        
        # Create UV map for proper texture mapping
        uv_layer = mesh.uv_layers.new(name="UVMap")
        
        # Create object
        building_obj = bpy.data.objects.new("Building", mesh)
        bpy.context.collection.objects.link(building_obj)
        
        # Add detailed facade material (for walls)
        facade_material = self._create_detailed_facade_material()
        building_obj.data.materials.append(facade_material)
        
        # Add roof material 
        roof_material = self._create_roof_material()
        building_obj.data.materials.append(roof_material)
        
        # Assign materials to faces (roof gets different material)
        for i, face in enumerate(mesh.polygons):
            if i == 1:  # Top face is the roof
                face.material_index = 1
            else:  # All other faces get facade material
                face.material_index = 0
    
    def _create_detailed_facade_material(self):
        """Create a highly detailed building facade material with windows, bricks, and variation"""
        import random
        
        material = bpy.data.materials.new(name="DetailedFacadeMaterial")
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        
        # Clear default nodes
        nodes.clear()
        
        # Output node
        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (800, 0)
        
        # Main BSDF
        bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
        bsdf.location = (500, 0)
        bsdf.inputs['Roughness'].default_value = 0.7
        
        # === WINDOW PATTERN ===
        # Create a grid pattern for windows using brick texture
        window_tex = nodes.new(type='ShaderNodeTexBrick')
        window_tex.location = (-800, 400)
        window_tex.inputs['Scale'].default_value = 3.0  # Window density
        window_tex.inputs['Mortar Size'].default_value = 0.15  # Window frame size
        window_tex.inputs['Mortar Smooth'].default_value = 0.0
        window_tex.inputs['Bias'].default_value = 0.0
        
        # Window color ramp (creates dark windows vs lighter walls)
        window_ramp = nodes.new(type='ShaderNodeValToRGB')
        window_ramp.location = (-600, 400)
        window_ramp.color_ramp.elements[0].position = 0.3
        window_ramp.color_ramp.elements[0].color = (0.05, 0.1, 0.15, 1.0)  # Dark blue-ish windows
        window_ramp.color_ramp.elements[1].position = 0.7
        window_ramp.color_ramp.elements[1].color = (0.7, 0.65, 0.6, 1.0)  # Light wall color
        
        # === BRICK/WALL TEXTURE ===
        # Add brick texture for wall detail
        brick_tex = nodes.new(type='ShaderNodeTexBrick')
        brick_tex.location = (-800, 100)
        brick_tex.inputs['Scale'].default_value = 8.0  # Brick density
        brick_tex.inputs['Mortar Size'].default_value = 0.02  # Mortar lines
        brick_tex.inputs['Mortar Smooth'].default_value = 0.1
        brick_tex.inputs['Color1'].default_value = (0.6, 0.4, 0.3, 1.0)  # Brick color
        brick_tex.inputs['Color2'].default_value = (0.65, 0.45, 0.35, 1.0)  # Slight variation
        
        # Brick color output
        brick_color_ramp = nodes.new(type='ShaderNodeValToRGB')
        brick_color_ramp.location = (-600, 100)
        brick_color_ramp.color_ramp.elements[0].color = (0.55, 0.4, 0.3, 1.0)  # Darker brick
        brick_color_ramp.color_ramp.elements[1].color = (0.7, 0.55, 0.45, 1.0)  # Lighter brick
        
        # === WALL DETAIL NOISE ===
        # Add noise for weathering and variation
        detail_noise = nodes.new(type='ShaderNodeTexNoise')
        detail_noise.location = (-800, -200)
        detail_noise.inputs['Scale'].default_value = 15.0
        detail_noise.inputs['Detail'].default_value = 10.0
        detail_noise.inputs['Roughness'].default_value = 0.6
        
        # === MIX BRICK TEXTURE WITH WALL BASE ===
        mix_brick_noise = nodes.new(type='ShaderNodeMixRGB')
        mix_brick_noise.location = (-400, 0)
        mix_brick_noise.blend_type = 'MULTIPLY'
        mix_brick_noise.inputs['Fac'].default_value = 0.3
        
        # === COMBINE WINDOWS WITH WALLS ===
        mix_windows = nodes.new(type='ShaderNodeMixRGB')
        mix_windows.location = (-200, 200)
        mix_windows.blend_type = 'MIX'
        mix_windows.inputs['Fac'].default_value = 1.0
        
        # === BUMP MAPPING FOR DEPTH ===
        # Create bump map for brick depth
        bump_node = nodes.new(type='ShaderNodeBump')
        bump_node.location = (200, -200)
        bump_node.inputs['Strength'].default_value = 0.3
        bump_node.inputs['Distance'].default_value = 0.1
        
        # Connect brick texture to bump for wall depth
        links.new(brick_tex.outputs['Fac'], bump_node.inputs['Height'])
        
        # === TEXTURE COORDINATE ===
        tex_coord = nodes.new(type='ShaderNodeTexCoord')
        tex_coord.location = (-1000, 0)
        
        # Use generated coordinates for better mapping
        links.new(tex_coord.outputs['Generated'], window_tex.inputs['Vector'])
        links.new(tex_coord.outputs['Generated'], brick_tex.inputs['Vector'])
        links.new(tex_coord.outputs['Generated'], detail_noise.inputs['Vector'])
        
        # === CONNECT NODES ===
        # Window pattern
        links.new(window_tex.outputs['Fac'], window_ramp.inputs['Fac'])
        
        # Brick texture
        links.new(brick_tex.outputs['Fac'], brick_color_ramp.inputs['Fac'])
        
        # Mix brick with noise for variation
        links.new(brick_color_ramp.outputs['Color'], mix_brick_noise.inputs['Color1'])
        links.new(detail_noise.outputs['Fac'], mix_brick_noise.inputs['Color2'])
        
        # Combine windows with textured walls
        links.new(window_ramp.outputs['Color'], mix_windows.inputs['Color1'])
        links.new(mix_brick_noise.outputs['Color'], mix_windows.inputs['Color2'])
        links.new(window_tex.outputs['Fac'], mix_windows.inputs['Fac'])
        
        # Final color to BSDF
        links.new(mix_windows.outputs['Color'], bsdf.inputs['Base Color'])
        
        # Bump mapping to normal
        links.new(bump_node.outputs['Normal'], bsdf.inputs['Normal'])
        
        # Output
        links.new(bsdf.outputs['BSDF'], output_node.inputs['Surface'])
        
        return material
    
    def _create_roof_material(self):
        """Create a detailed roof material with tiles"""
        material = bpy.data.materials.new(name="RoofMaterial")
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        
        # Clear default nodes
        nodes.clear()
        
        # Output
        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (600, 0)
        
        # BSDF
        bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
        bsdf.location = (400, 0)
        bsdf.inputs['Roughness'].default_value = 0.6
        
        # Roof tile texture using brick texture
        tile_tex = nodes.new(type='ShaderNodeTexBrick')
        tile_tex.location = (-600, 0)
        tile_tex.inputs['Scale'].default_value = 12.0  # Tile density
        tile_tex.inputs['Mortar Size'].default_value = 0.03
        tile_tex.inputs['Row Height'].default_value = 0.3
        tile_tex.inputs['Color1'].default_value = (0.35, 0.15, 0.1, 1.0)  # Dark red tile
        tile_tex.inputs['Color2'].default_value = (0.4, 0.2, 0.12, 1.0)  # Lighter red tile
        
        # Color variation
        color_ramp = nodes.new(type='ShaderNodeValToRGB')
        color_ramp.location = (-400, 0)
        color_ramp.color_ramp.elements[0].color = (0.3, 0.15, 0.1, 1.0)
        color_ramp.color_ramp.elements[1].color = (0.45, 0.25, 0.15, 1.0)
        
        # Weathering noise
        noise = nodes.new(type='ShaderNodeTexNoise')
        noise.location = (-600, -200)
        noise.inputs['Scale'].default_value = 20.0
        noise.inputs['Detail'].default_value = 8.0
        
        # Mix tile with noise
        mix_noise = nodes.new(type='ShaderNodeMixRGB')
        mix_noise.location = (-200, 0)
        mix_noise.blend_type = 'MULTIPLY'
        mix_noise.inputs['Fac'].default_value = 0.2
        
        # Bump for tile depth
        bump = nodes.new(type='ShaderNodeBump')
        bump.location = (100, -200)
        bump.inputs['Strength'].default_value = 0.4
        
        # Texture coordinates
        tex_coord = nodes.new(type='ShaderNodeTexCoord')
        tex_coord.location = (-800, 0)
        
        # Connect nodes
        links.new(tex_coord.outputs['Generated'], tile_tex.inputs['Vector'])
        links.new(tex_coord.outputs['Generated'], noise.inputs['Vector'])
        links.new(tile_tex.outputs['Color'], color_ramp.inputs['Fac'])
        links.new(color_ramp.outputs['Color'], mix_noise.inputs['Color1'])
        links.new(noise.outputs['Fac'], mix_noise.inputs['Color2'])
        links.new(mix_noise.outputs['Color'], bsdf.inputs['Base Color'])
        links.new(tile_tex.outputs['Fac'], bump.inputs['Height'])
        links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
        links.new(bsdf.outputs['BSDF'], output_node.inputs['Surface'])
        
        return material
    
    def create_streets(self, osm_data):
        """Create street meshes from OSM data"""
        print("Creating streets...")
        
        # Parse nodes
        nodes = {}
        for element in osm_data.get('elements', []):
            if element['type'] == 'node':
                nodes[element['id']] = element
        
        street_count = 0
        for element in osm_data.get('elements', []):
            if element['type'] == 'way' and 'highway' in element.get('tags', {}):
                node_ids = element['nodes']
                
                # Get coordinates
                coords = []
                for node_id in node_ids:
                    if node_id in nodes:
                        node = nodes[node_id]
                        lat = node['lat']
                        lon = node['lon']
                        x, y = self.lat_lon_to_meters(lat, lon)
                        coords.append((x, y))
                
                if len(coords) < 2:
                    continue
                
                # Get street width
                tags = element.get('tags', {})
                highway_type = tags['highway']
                width = 3.0  # Default
                if highway_type in ['motorway', 'trunk']:
                    width = 10.0
                elif highway_type in ['primary', 'secondary']:
                    width = 6.0
                elif highway_type in ['tertiary', 'residential']:
                    width = 4.0
                
                # Create street and sidewalks
                self.create_street_mesh(coords, width, highway_type)
                street_count += 1
        
        print(f"Created {street_count} streets")
    
    def create_street_mesh(self, coords, width, highway_type):
        """Create a single street mesh with sidewalks"""
        vertices = []
        faces = []
        
        half_width = width / 2
        
        # Create vertices along the path
        for i, (x, y) in enumerate(coords):
            if i == 0:
                # First segment
                dx = coords[1][0] - coords[0][0]
                dy = coords[1][1] - coords[0][1]
            elif i == len(coords) - 1:
                # Last segment
                dx = coords[-1][0] - coords[-2][0]
                dy = coords[-1][1] - coords[-2][1]
            else:
                # Middle segments - average direction
                dx1 = coords[i][0] - coords[i-1][0]
                dy1 = coords[i][1] - coords[i-1][1]
                dx2 = coords[i+1][0] - coords[i][0]
                dy2 = coords[i+1][1] - coords[i][1]
                dx = (dx1 + dx2) / 2
                dy = (dy1 + dy2) / 2
            
            # Perpendicular direction
            length = math.sqrt(dx*dx + dy*dy)
            if length > 0:
                px = -dy / length * half_width
                py = dx / length * half_width
            else:
                px = py = 0
            
            # Get elevation at this point for 3D relief
            z = self.get_elevation_at_xy(x, y)
            # Add small offset to place road slightly above terrain
            z += 0.05
            
            # Left and right vertices with terrain elevation
            vertices.append((x + px, y + py, z))
            vertices.append((x - px, y - py, z))
        
        # Create faces
        for i in range(len(coords) - 1):
            v1 = i * 2
            v2 = i * 2 + 1
            v3 = (i + 1) * 2 + 1
            v4 = (i + 1) * 2
            faces.append((v1, v2, v3, v4))
        
        # Create mesh
        mesh = bpy.data.meshes.new("Street")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        
        # Create object
        street_obj = bpy.data.objects.new("Street", mesh)
        bpy.context.collection.objects.link(street_obj)
        
        # Add detailed asphalt material with road markings
        material = bpy.data.materials.new(name="DetailedStreetMaterial")
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        
        # Clear default nodes
        nodes.clear()
        
        # Output
        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (1000, 0)
        
        # Main BSDF
        bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
        bsdf.location = (700, 0)
        bsdf.inputs['Roughness'].default_value = 0.65
        bsdf.inputs['Specular IOR Level'].default_value = 0.4
        
        # === ASPHALT TEXTURE ===
        # Fine grain noise for asphalt texture
        asphalt_fine = nodes.new(type='ShaderNodeTexNoise')
        asphalt_fine.location = (-1000, 300)
        asphalt_fine.inputs['Scale'].default_value = 100.0  # Very fine grain
        asphalt_fine.inputs['Detail'].default_value = 15.0
        asphalt_fine.inputs['Roughness'].default_value = 0.6
        
        # Medium noise for asphalt patches
        asphalt_patches = nodes.new(type='ShaderNodeTexNoise')
        asphalt_patches.location = (-1000, 0)
        asphalt_patches.inputs['Scale'].default_value = 30.0
        asphalt_patches.inputs['Detail'].default_value = 8.0
        asphalt_patches.inputs['Roughness'].default_value = 0.5
        
        # Cracks and wear using Voronoi
        cracks = nodes.new(type='ShaderNodeTexVoronoi')
        cracks.location = (-1000, -300)
        cracks.inputs['Scale'].default_value = 15.0
        cracks.feature = 'DISTANCE_TO_EDGE'
        
        # === ASPHALT COLOR ===
        asphalt_color_ramp = nodes.new(type='ShaderNodeValToRGB')
        asphalt_color_ramp.location = (-600, 100)
        asphalt_color_ramp.color_ramp.elements[0].position = 0.0
        asphalt_color_ramp.color_ramp.elements[0].color = (0.08, 0.08, 0.08, 1.0)  # Very dark
        asphalt_color_ramp.color_ramp.elements[1].position = 0.5
        asphalt_color_ramp.color_ramp.elements[1].color = (0.15, 0.15, 0.15, 1.0)  # Dark gray
        asphalt_color_ramp.color_ramp.elements.new(0.8)
        asphalt_color_ramp.color_ramp.elements[2].color = (0.22, 0.22, 0.22, 1.0)  # Medium gray
        
        # === LANE MARKINGS ===
        # Create white lane markings using wave texture
        lane_marks = nodes.new(type='ShaderNodeTexWave')
        lane_marks.location = (-800, -600)
        lane_marks.wave_type = 'BANDS'
        lane_marks.bands_direction = 'X'  # Lines along road
        lane_marks.inputs['Scale'].default_value = 0.5
        lane_marks.inputs['Distortion'].default_value = 0.0
        
        # Lane mark color (white)
        lane_ramp = nodes.new(type='ShaderNodeValToRGB')
        lane_ramp.location = (-600, -600)
        lane_ramp.color_ramp.elements[0].position = 0.48
        lane_ramp.color_ramp.elements[0].color = (0.12, 0.12, 0.12, 1.0)  # Asphalt (no marking)
        lane_ramp.color_ramp.elements[1].position = 0.52
        lane_ramp.color_ramp.elements[1].color = (0.9, 0.9, 0.85, 1.0)  # White/yellow marking
        
        # === MIX ASPHALT LAYERS ===
        # Combine fine and medium asphalt texture
        mix_asphalt = nodes.new(type='ShaderNodeMixRGB')
        mix_asphalt.location = (-400, 100)
        mix_asphalt.blend_type = 'OVERLAY'
        mix_asphalt.inputs['Fac'].default_value = 0.6
        
        # Add cracks to asphalt
        mix_cracks = nodes.new(type='ShaderNodeMixRGB')
        mix_cracks.location = (-200, 0)
        mix_cracks.blend_type = 'MULTIPLY'
        mix_cracks.inputs['Fac'].default_value = 0.3
        
        # Add lane markings
        mix_lanes = nodes.new(type='ShaderNodeMixRGB')
        mix_lanes.location = (0, -200)
        mix_lanes.blend_type = 'MIX'
        mix_lanes.inputs['Fac'].default_value = 0.3
        
        # === BUMP MAPPING ===
        bump = nodes.new(type='ShaderNodeBump')
        bump.location = (400, -400)
        bump.inputs['Strength'].default_value = 0.3
        bump.inputs['Distance'].default_value = 0.02
        
        # Bump height from cracks
        bump_height = nodes.new(type='ShaderNodeMixRGB')
        bump_height.location = (200, -400)
        bump_height.blend_type = 'ADD'
        bump_height.inputs['Fac'].default_value = 0.5
        
        # Texture coordinates
        tex_coord = nodes.new(type='ShaderNodeTexCoord')
        tex_coord.location = (-1200, 0)
        
        # === CONNECT NODES ===
        # Texture coordinates
        links.new(tex_coord.outputs['Generated'], asphalt_fine.inputs['Vector'])
        links.new(tex_coord.outputs['Generated'], asphalt_patches.inputs['Vector'])
        links.new(tex_coord.outputs['Generated'], cracks.inputs['Vector'])
        links.new(tex_coord.outputs['UV'], lane_marks.inputs['Vector'])  # UV for lane marks
        
        # Asphalt color
        links.new(asphalt_patches.outputs['Fac'], asphalt_color_ramp.inputs['Fac'])
        
        # Mix asphalt layers
        links.new(asphalt_color_ramp.outputs['Color'], mix_asphalt.inputs['Color1'])
        links.new(asphalt_fine.outputs['Fac'], mix_asphalt.inputs['Color2'])
        
        # Add cracks
        links.new(mix_asphalt.outputs['Color'], mix_cracks.inputs['Color1'])
        links.new(cracks.outputs['Distance'], mix_cracks.inputs['Color2'])
        
        # Lane markings
        links.new(lane_marks.outputs['Fac'], lane_ramp.inputs['Fac'])
        links.new(mix_cracks.outputs['Color'], mix_lanes.inputs['Color1'])
        links.new(lane_ramp.outputs['Color'], mix_lanes.inputs['Color2'])
        
        # Bump mapping
        links.new(asphalt_fine.outputs['Fac'], bump_height.inputs['Color1'])
        links.new(cracks.outputs['Distance'], bump_height.inputs['Color2'])
        links.new(bump_height.outputs['Color'], bump.inputs['Height'])
        links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
        
        # Final color
        links.new(mix_lanes.outputs['Color'], bsdf.inputs['Base Color'])
        
        # Output
        links.new(bsdf.outputs['BSDF'], output_node.inputs['Surface'])
        
        street_obj.data.materials.append(material)
        
        # Create sidewalks for non-motorway roads
        if highway_type not in ['motorway', 'trunk', 'motorway_link', 'trunk_link']:
            self.create_sidewalk_mesh(coords, width)
    
    def create_sidewalk_mesh(self, coords, street_width):
        """Create sidewalks on both sides of the street"""
        sidewalk_width = 1.5  # 1.5 meters wide sidewalks
        sidewalk_offset = street_width / 2 + sidewalk_width / 2
        
        # Create left and right sidewalks
        for side in [-1, 1]:  # -1 for left, 1 for right
            vertices = []
            faces = []
            
            half_width = sidewalk_width / 2
            
            # Create vertices along the path
            for i, (x, y) in enumerate(coords):
                if i == 0:
                    # First segment
                    dx = coords[1][0] - coords[0][0]
                    dy = coords[1][1] - coords[0][1]
                elif i == len(coords) - 1:
                    # Last segment
                    dx = coords[-1][0] - coords[-2][0]
                    dy = coords[-1][1] - coords[-2][1]
                else:
                    # Middle segments - average direction
                    dx1 = coords[i][0] - coords[i-1][0]
                    dy1 = coords[i][1] - coords[i-1][1]
                    dx2 = coords[i+1][0] - coords[i][0]
                    dy2 = coords[i+1][1] - coords[i][1]
                    dx = (dx1 + dx2) / 2
                    dy = (dy1 + dy2) / 2
                
                # Perpendicular direction
                length = math.sqrt(dx*dx + dy*dy)
                if length > 0:
                    px = -dy / length
                    py = dx / length
                else:
                    px = py = 0
                
                # Offset for this side
                offset_x = px * sidewalk_offset * side
                offset_y = py * sidewalk_offset * side
                
                # Get elevation at center point
                z = self.get_elevation_at_xy(x, y)
                # Sidewalks slightly higher than road
                z += 0.1
                
                # Inner and outer vertices
                inner_x = x + offset_x - px * half_width * side
                inner_y = y + offset_y - py * half_width * side
                outer_x = x + offset_x + px * half_width * side
                outer_y = y + offset_y + py * half_width * side
                
                vertices.append((inner_x, inner_y, z))
                vertices.append((outer_x, outer_y, z))
            
            # Create faces
            for i in range(len(coords) - 1):
                v1 = i * 2
                v2 = i * 2 + 1
                v3 = (i + 1) * 2 + 1
                v4 = (i + 1) * 2
                faces.append((v1, v2, v3, v4))
            
            # Create mesh
            mesh = bpy.data.meshes.new("Sidewalk")
            mesh.from_pydata(vertices, [], faces)
            mesh.update()
            
            # Create object
            sidewalk_obj = bpy.data.objects.new("Sidewalk", mesh)
            bpy.context.collection.objects.link(sidewalk_obj)
            
            # Add detailed concrete sidewalk material
            material = bpy.data.materials.new(name="DetailedSidewalkMaterial")
            material.use_nodes = True
            nodes = material.node_tree.nodes
            links = material.node_tree.links
            
            # Clear default nodes
            nodes.clear()
            
            # Output
            output_node = nodes.new(type='ShaderNodeOutputMaterial')
            output_node.location = (800, 0)
            
            # BSDF
            bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
            bsdf.location = (500, 0)
            bsdf.inputs['Roughness'].default_value = 0.9
            
            # === CONCRETE TILES ===
            # Use brick texture for concrete tile pattern
            tiles = nodes.new(type='ShaderNodeTexBrick')
            tiles.location = (-800, 200)
            tiles.inputs['Scale'].default_value = 4.0
            tiles.inputs['Mortar Size'].default_value = 0.05
            tiles.inputs['Mortar Smooth'].default_value = 0.1
            tiles.inputs['Color1'].default_value = (0.55, 0.55, 0.55, 1.0)
            tiles.inputs['Color2'].default_value = (0.6, 0.6, 0.6, 1.0)
            
            # === CONCRETE DETAIL ===
            # Fine noise for concrete grain
            concrete_detail = nodes.new(type='ShaderNodeTexNoise')
            concrete_detail.location = (-800, -100)
            concrete_detail.inputs['Scale'].default_value = 80.0
            concrete_detail.inputs['Detail'].default_value = 12.0
            concrete_detail.inputs['Roughness'].default_value = 0.6
            
            # Larger weathering patterns
            weathering = nodes.new(type='ShaderNodeTexNoise')
            weathering.location = (-800, -400)
            weathering.inputs['Scale'].default_value = 15.0
            weathering.inputs['Detail'].default_value = 8.0
            
            # === COLOR RAMPS ===
            # Tile color variation
            tile_ramp = nodes.new(type='ShaderNodeValToRGB')
            tile_ramp.location = (-600, 200)
            tile_ramp.color_ramp.elements[0].color = (0.48, 0.48, 0.48, 1.0)  # Darker concrete
            tile_ramp.color_ramp.elements[1].color = (0.68, 0.68, 0.68, 1.0)  # Lighter concrete
            
            # Weathering color
            weather_ramp = nodes.new(type='ShaderNodeValToRGB')
            weather_ramp.location = (-600, -400)
            weather_ramp.color_ramp.elements[0].color = (0.4, 0.4, 0.4, 1.0)  # Dark stains
            weather_ramp.color_ramp.elements[1].color = (0.7, 0.7, 0.7, 1.0)  # Clean areas
            
            # === MIX LAYERS ===
            # Add concrete detail to tiles
            mix_detail = nodes.new(type='ShaderNodeMixRGB')
            mix_detail.location = (-400, 100)
            mix_detail.blend_type = 'OVERLAY'
            mix_detail.inputs['Fac'].default_value = 0.4
            
            # Add weathering
            mix_weather = nodes.new(type='ShaderNodeMixRGB')
            mix_weather.location = (-200, 0)
            mix_weather.blend_type = 'MULTIPLY'
            mix_weather.inputs['Fac'].default_value = 0.3
            
            # === BUMP MAPPING ===
            bump = nodes.new(type='ShaderNodeBump')
            bump.location = (200, -300)
            bump.inputs['Strength'].default_value = 0.35
            bump.inputs['Distance'].default_value = 0.03
            
            # Combine bumps from tiles and detail
            bump_mix = nodes.new(type='ShaderNodeMixRGB')
            bump_mix.location = (0, -300)
            bump_mix.blend_type = 'ADD'
            bump_mix.inputs['Fac'].default_value = 0.5
            
            # Texture coordinates
            tex_coord = nodes.new(type='ShaderNodeTexCoord')
            tex_coord.location = (-1000, 0)
            
            # === CONNECT NODES ===
            links.new(tex_coord.outputs['Generated'], tiles.inputs['Vector'])
            links.new(tex_coord.outputs['Generated'], concrete_detail.inputs['Vector'])
            links.new(tex_coord.outputs['Generated'], weathering.inputs['Vector'])
            
            # Tile color
            links.new(tiles.outputs['Fac'], tile_ramp.inputs['Fac'])
            
            # Mix detail with tiles
            links.new(tile_ramp.outputs['Color'], mix_detail.inputs['Color1'])
            links.new(concrete_detail.outputs['Fac'], mix_detail.inputs['Color2'])
            
            # Add weathering
            links.new(weathering.outputs['Fac'], weather_ramp.inputs['Fac'])
            links.new(mix_detail.outputs['Color'], mix_weather.inputs['Color1'])
            links.new(weather_ramp.outputs['Color'], mix_weather.inputs['Color2'])
            
            # Bump mapping
            links.new(tiles.outputs['Fac'], bump_mix.inputs['Color1'])
            links.new(concrete_detail.outputs['Fac'], bump_mix.inputs['Color2'])
            links.new(bump_mix.outputs['Color'], bump.inputs['Height'])
            links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
            
            # Final color
            links.new(mix_weather.outputs['Color'], bsdf.inputs['Base Color'])
            
            # Output
            links.new(bsdf.outputs['BSDF'], output_node.inputs['Surface'])
            
            sidewalk_obj.data.materials.append(material)
    
    def create_water(self, osm_data):
        """Create water body meshes from OSM data"""
        print("Creating water bodies...")
        
        # Parse nodes
        nodes = {}
        for element in osm_data.get('elements', []):
            if element['type'] == 'node':
                nodes[element['id']] = element
        
        water_count = 0
        for element in osm_data.get('elements', []):
            tags = element.get('tags', {})
            is_water = ('waterway' in tags or 
                       tags.get('natural') == 'water')
            
            if element['type'] == 'way' and is_water:
                node_ids = element['nodes']
                
                # Get coordinates
                coords = []
                for node_id in node_ids:
                    if node_id in nodes:
                        node = nodes[node_id]
                        lat = node['lat']
                        lon = node['lon']
                        x, y = self.lat_lon_to_meters(lat, lon)
                        coords.append((x, y))
                
                if len(coords) < 3:
                    continue
                
                # Create water body
                self.create_water_mesh(coords)
                water_count += 1
        
        print(f"Created {water_count} water bodies")
    
    def create_water_mesh(self, coords):
        """Create a single water body mesh"""
        vertices = []
        faces = []
        
        # Create vertices
        for x, y in coords[:-1]:  # Exclude last coord if it's same as first
            vertices.append((x, y, 0.05))
        
        # Create face (assuming polygon is convex or using simple triangulation)
        if len(vertices) >= 3:
            # Simple fan triangulation
            for i in range(1, len(vertices) - 1):
                faces.append((0, i, i + 1))
        
        # Create mesh
        mesh = bpy.data.meshes.new("Water")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        
        # Create object
        water_obj = bpy.data.objects.new("Water", mesh)
        bpy.context.collection.objects.link(water_obj)
        
        # Add realistic water material
        material = bpy.data.materials.new(name="DetailedWaterMaterial")
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        
        # Clear default nodes
        nodes.clear()
        
        # Output
        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (800, 0)
        
        # Main BSDF
        bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
        bsdf.location = (500, 0)
        bsdf.inputs['Base Color'].default_value = (0.1, 0.3, 0.5, 1.0)  # Deep blue
        bsdf.inputs['Metallic'].default_value = 0.0
        bsdf.inputs['Roughness'].default_value = 0.05  # Very smooth
        bsdf.inputs['IOR'].default_value = 1.333  # Water IOR
        bsdf.inputs['Transmission Weight'].default_value = 0.5  # Semi-transparent
        bsdf.inputs['Specular IOR Level'].default_value = 0.5
        
        # === WATER RIPPLES ===
        # Wave texture for water ripples
        waves1 = nodes.new(type='ShaderNodeTexWave')
        waves1.location = (-800, 200)
        waves1.wave_type = 'BANDS'
        waves1.inputs['Scale'].default_value = 5.0
        waves1.inputs['Distortion'].default_value = 2.0
        waves1.inputs['Detail'].default_value = 8.0
        waves1.inputs['Detail Scale'].default_value = 3.0
        
        # Second wave layer for complexity
        waves2 = nodes.new(type='ShaderNodeTexWave')
        waves2.location = (-800, -100)
        waves2.wave_type = 'RINGS'
        waves2.inputs['Scale'].default_value = 8.0
        waves2.inputs['Distortion'].default_value = 3.0
        waves2.inputs['Detail'].default_value = 6.0
        
        # Noise for water movement
        noise = nodes.new(type='ShaderNodeTexNoise')
        noise.location = (-800, -400)
        noise.inputs['Scale'].default_value = 12.0
        noise.inputs['Detail'].default_value = 10.0
        
        # === COLOR VARIATION ===
        # Depth-based color variation
        color_ramp = nodes.new(type='ShaderNodeValToRGB')
        color_ramp.location = (-400, -400)
        color_ramp.color_ramp.elements[0].color = (0.05, 0.15, 0.25, 1.0)  # Deep water
        color_ramp.color_ramp.elements[1].color = (0.2, 0.4, 0.6, 1.0)  # Shallow water
        
        # === MIX WAVES ===
        mix_waves = nodes.new(type='ShaderNodeMixRGB')
        mix_waves.location = (-600, 0)
        mix_waves.blend_type = 'ADD'
        mix_waves.inputs['Fac'].default_value = 0.5
        
        # === BUMP MAPPING ===
        # Create water surface bumps
        bump = nodes.new(type='ShaderNodeBump')
        bump.location = (200, -200)
        bump.inputs['Strength'].default_value = 0.4
        bump.inputs['Distance'].default_value = 0.1
        
        # Combine wave patterns for bump
        bump_mix = nodes.new(type='ShaderNodeMixRGB')
        bump_mix.location = (-200, -100)
        bump_mix.blend_type = 'ADD'
        bump_mix.inputs['Fac'].default_value = 0.5
        
        # Mix color variation
        mix_color = nodes.new(type='ShaderNodeMixRGB')
        mix_color.location = (-200, 300)
        mix_color.blend_type = 'MIX'
        mix_color.inputs['Fac'].default_value = 0.3
        mix_color.inputs['Color1'].default_value = (0.1, 0.3, 0.5, 1.0)
        
        # Texture coordinates
        tex_coord = nodes.new(type='ShaderNodeTexCoord')
        tex_coord.location = (-1000, 0)
        
        # === CONNECT NODES ===
        links.new(tex_coord.outputs['Generated'], waves1.inputs['Vector'])
        links.new(tex_coord.outputs['Generated'], waves2.inputs['Vector'])
        links.new(tex_coord.outputs['Generated'], noise.inputs['Vector'])
        
        # Mix waves
        links.new(waves1.outputs['Color'], mix_waves.inputs['Color1'])
        links.new(waves2.outputs['Color'], mix_waves.inputs['Color2'])
        
        # Color variation
        links.new(noise.outputs['Fac'], color_ramp.inputs['Fac'])
        links.new(color_ramp.outputs['Color'], mix_color.inputs['Color2'])
        
        # Bump mapping
        links.new(waves1.outputs['Color'], bump_mix.inputs['Color1'])
        links.new(waves2.outputs['Color'], bump_mix.inputs['Color2'])
        links.new(bump_mix.outputs['Color'], bump.inputs['Height'])
        links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
        
        # Final color
        links.new(mix_color.outputs['Color'], bsdf.inputs['Base Color'])
        
        # Output
        links.new(bsdf.outputs['BSDF'], output_node.inputs['Surface'])
        
        water_obj.data.materials.append(material)
    
    def create_trees(self, osm_data):
        """Create tree objects from OSM data"""
        print("Creating trees...")
        
        # Parse nodes to find individual trees
        tree_count = 0
        for element in osm_data.get('elements', []):
            if element['type'] == 'node' and element.get('tags', {}).get('natural') == 'tree':
                lat = element['lat']
                lon = element['lon']
                x, y = self.lat_lon_to_meters(lat, lon)
                
                # Create tree
                self.create_tree_mesh(x, y)
                tree_count += 1
        
        # Parse ways for tree rows
        nodes = {}
        for element in osm_data.get('elements', []):
            if element['type'] == 'node':
                nodes[element['id']] = element
        
        for element in osm_data.get('elements', []):
            if element['type'] == 'way' and element.get('tags', {}).get('natural') == 'tree_row':
                node_ids = element['nodes']
                
                # Get coordinates for the tree row
                for node_id in node_ids[::2]:  # Place trees every other node
                    if node_id in nodes:
                        node = nodes[node_id]
                        lat = node['lat']
                        lon = node['lon']
                        x, y = self.lat_lon_to_meters(lat, lon)
                        
                        # Create tree
                        self.create_tree_mesh(x, y)
                        tree_count += 1
        
        print(f"Created {tree_count} trees")
    
    def create_tree_mesh(self, x, y):
        """Create a simple tree mesh (trunk + canopy)"""
        # Tree dimensions
        trunk_radius = 0.3
        trunk_height = 2.0
        canopy_radius = 2.0
        canopy_height = 3.0
        
        # Create trunk (cylinder approximation)
        trunk_vertices = []
        trunk_faces = []
        segments = 6
        
        # Bottom circle
        for i in range(segments):
            angle = 2 * math.pi * i / segments
            px = x + trunk_radius * math.cos(angle)
            py = y + trunk_radius * math.sin(angle)
            trunk_vertices.append((px, py, 0.3))
        
        # Top circle
        for i in range(segments):
            angle = 2 * math.pi * i / segments
            px = x + trunk_radius * math.cos(angle)
            py = y + trunk_radius * math.sin(angle)
            trunk_vertices.append((px, py, trunk_height))
        
        # Side faces
        for i in range(segments):
            next_i = (i + 1) % segments
            face = [i, next_i, next_i + segments, i + segments]
            trunk_faces.append(face)
        
        # Create trunk mesh
        trunk_mesh = bpy.data.meshes.new("TreeTrunk")
        trunk_mesh.from_pydata(trunk_vertices, [], trunk_faces)
        trunk_mesh.update()
        
        trunk_obj = bpy.data.objects.new("TreeTrunk", trunk_mesh)
        bpy.context.collection.objects.link(trunk_obj)
        
        # Add detailed trunk material with bark texture
        trunk_material = bpy.data.materials.new(name="DetailedTrunkMaterial")
        trunk_material.use_nodes = True
        nodes = trunk_material.node_tree.nodes
        links = trunk_material.node_tree.links
        nodes.clear()
        
        # Output
        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (600, 0)
        
        # BSDF
        bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
        bsdf.location = (400, 0)
        bsdf.inputs['Roughness'].default_value = 0.95
        
        # Bark texture using noise
        bark_noise1 = nodes.new(type='ShaderNodeTexNoise')
        bark_noise1.location = (-800, 200)
        bark_noise1.inputs['Scale'].default_value = 25.0
        bark_noise1.inputs['Detail'].default_value = 15.0
        bark_noise1.inputs['Roughness'].default_value = 0.7
        
        # Vertical bark lines using wave
        bark_lines = nodes.new(type='ShaderNodeTexWave')
        bark_lines.location = (-800, -100)
        bark_lines.wave_type = 'BANDS'
        bark_lines.bands_direction = 'Z'  # Vertical
        bark_lines.inputs['Scale'].default_value = 15.0
        bark_lines.inputs['Distortion'].default_value = 5.0
        
        # Color ramp for bark
        bark_color = nodes.new(type='ShaderNodeValToRGB')
        bark_color.location = (-400, 100)
        bark_color.color_ramp.elements[0].color = (0.2, 0.12, 0.06, 1.0)  # Dark brown
        bark_color.color_ramp.elements[1].color = (0.35, 0.22, 0.12, 1.0)  # Light brown
        
        # Mix bark layers
        mix_bark = nodes.new(type='ShaderNodeMixRGB')
        mix_bark.location = (-600, 0)
        mix_bark.blend_type = 'MULTIPLY'
        mix_bark.inputs['Fac'].default_value = 0.6
        
        # Bump for bark texture
        bump = nodes.new(type='ShaderNodeBump')
        bump.location = (100, -200)
        bump.inputs['Strength'].default_value = 0.5
        
        # Texture coordinates
        tex_coord = nodes.new(type='ShaderNodeTexCoord')
        tex_coord.location = (-1000, 0)
        
        # Connect nodes
        links.new(tex_coord.outputs['Generated'], bark_noise1.inputs['Vector'])
        links.new(tex_coord.outputs['Generated'], bark_lines.inputs['Vector'])
        links.new(bark_noise1.outputs['Fac'], mix_bark.inputs['Color1'])
        links.new(bark_lines.outputs['Fac'], mix_bark.inputs['Color2'])
        links.new(mix_bark.outputs['Color'], bark_color.inputs['Fac'])
        links.new(bark_color.outputs['Color'], bsdf.inputs['Base Color'])
        links.new(bark_noise1.outputs['Fac'], bump.inputs['Height'])
        links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
        links.new(bsdf.outputs['BSDF'], output_node.inputs['Surface'])
        
        trunk_obj.data.materials.append(trunk_material)
        
        # Create canopy (ico sphere approximation)
        canopy_vertices = []
        canopy_faces = []
        segments_h = 8
        segments_v = 6
        
        for i in range(segments_v):
            theta = math.pi * i / (segments_v - 1)
            for j in range(segments_h):
                phi = 2 * math.pi * j / segments_h
                
                px = x + canopy_radius * math.sin(theta) * math.cos(phi)
                py = y + canopy_radius * math.sin(theta) * math.sin(phi)
                pz = trunk_height + canopy_height/2 + canopy_radius * math.cos(theta)
                
                canopy_vertices.append((px, py, pz))
        
        # Create faces
        for i in range(segments_v - 1):
            for j in range(segments_h):
                next_j = (j + 1) % segments_h
                v1 = i * segments_h + j
                v2 = i * segments_h + next_j
                v3 = (i + 1) * segments_h + next_j
                v4 = (i + 1) * segments_h + j
                canopy_faces.append((v1, v2, v3, v4))
        
        # Create canopy mesh
        canopy_mesh = bpy.data.meshes.new("TreeCanopy")
        canopy_mesh.from_pydata(canopy_vertices, [], canopy_faces)
        canopy_mesh.update()
        
        canopy_obj = bpy.data.objects.new("TreeCanopy", canopy_mesh)
        bpy.context.collection.objects.link(canopy_obj)
        
        # Add detailed foliage material
        canopy_material = bpy.data.materials.new(name="DetailedCanopyMaterial")
        canopy_material.use_nodes = True
        nodes = canopy_material.node_tree.nodes
        links = canopy_material.node_tree.links
        nodes.clear()
        
        # Output
        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (800, 0)
        
        # BSDF
        bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
        bsdf.location = (500, 0)
        bsdf.inputs['Roughness'].default_value = 0.85
        bsdf.inputs['Subsurface Weight'].default_value = 0.1  # Slight subsurface for leaves
        # Note: In Blender 4.x+, subsurface color is derived from Base Color automatically
        
        # === LEAF CLUSTERS ===
        # High-detail noise for individual leaves
        leaf_detail = nodes.new(type='ShaderNodeTexNoise')
        leaf_detail.location = (-800, 300)
        leaf_detail.inputs['Scale'].default_value = 80.0
        leaf_detail.inputs['Detail'].default_value = 15.0
        leaf_detail.inputs['Roughness'].default_value = 0.6
        
        # Larger foliage clusters
        foliage_clusters = nodes.new(type='ShaderNodeTexNoise')
        foliage_clusters.location = (-800, 0)
        foliage_clusters.inputs['Scale'].default_value = 20.0
        foliage_clusters.inputs['Detail'].default_value = 10.0
        
        # Voronoi for organic leaf distribution
        voronoi = nodes.new(type='ShaderNodeTexVoronoi')
        voronoi.location = (-800, -300)
        voronoi.inputs['Scale'].default_value = 15.0
        voronoi.feature = 'F1'
        
        # === COLOR VARIATION ===
        # Multiple shades of green
        leaf_color_ramp = nodes.new(type='ShaderNodeValToRGB')
        leaf_color_ramp.location = (-400, 200)
        leaf_color_ramp.color_ramp.elements[0].position = 0.0
        leaf_color_ramp.color_ramp.elements[0].color = (0.05, 0.2, 0.03, 1.0)  # Very dark green
        leaf_color_ramp.color_ramp.elements[1].position = 0.3
        leaf_color_ramp.color_ramp.elements[1].color = (0.15, 0.35, 0.08, 1.0)  # Dark green
        leaf_color_ramp.color_ramp.elements.new(0.6)
        leaf_color_ramp.color_ramp.elements[2].color = (0.2, 0.5, 0.15, 1.0)  # Medium green
        leaf_color_ramp.color_ramp.elements.new(0.9)
        leaf_color_ramp.color_ramp.elements[3].color = (0.3, 0.6, 0.2, 1.0)  # Light green
        
        # === MIX LAYERS ===
        # Combine leaf detail with clusters
        mix_detail = nodes.new(type='ShaderNodeMixRGB')
        mix_detail.location = (-600, 100)
        mix_detail.blend_type = 'OVERLAY'
        mix_detail.inputs['Fac'].default_value = 0.5
        
        # Add voronoi pattern
        mix_voronoi = nodes.new(type='ShaderNodeMixRGB')
        mix_voronoi.location = (-400, -100)
        mix_voronoi.blend_type = 'MULTIPLY'
        mix_voronoi.inputs['Fac'].default_value = 0.3
        
        # === BUMP MAPPING ===
        bump = nodes.new(type='ShaderNodeBump')
        bump.location = (200, -300)
        bump.inputs['Strength'].default_value = 0.4
        
        # Texture coordinates
        tex_coord = nodes.new(type='ShaderNodeTexCoord')
        tex_coord.location = (-1000, 0)
        
        # === CONNECT NODES ===
        links.new(tex_coord.outputs['Generated'], leaf_detail.inputs['Vector'])
        links.new(tex_coord.outputs['Generated'], foliage_clusters.inputs['Vector'])
        links.new(tex_coord.outputs['Generated'], voronoi.inputs['Vector'])
        
        # Mix foliage layers
        links.new(foliage_clusters.outputs['Fac'], mix_detail.inputs['Color1'])
        links.new(leaf_detail.outputs['Fac'], mix_detail.inputs['Color2'])
        
        # Add voronoi
        links.new(mix_detail.outputs['Color'], mix_voronoi.inputs['Color1'])
        links.new(voronoi.outputs['Distance'], mix_voronoi.inputs['Color2'])
        
        # Color
        links.new(mix_voronoi.outputs['Color'], leaf_color_ramp.inputs['Fac'])
        links.new(leaf_color_ramp.outputs['Color'], bsdf.inputs['Base Color'])
        
        # Bump
        links.new(leaf_detail.outputs['Fac'], bump.inputs['Height'])
        links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
        
        # Output
        links.new(bsdf.outputs['BSDF'], output_node.inputs['Surface'])
        
        canopy_obj.data.materials.append(canopy_material)
    
    def export_to_3ds(self, filename="city_model.3ds"):
        """Export the scene to supported formats (FBX, OBJ, or Blender)
        
        Note: Despite the function name, .3ds format is deprecated in Blender 4.0+.
        This function now exports to FBX as the primary format.
        The filename parameter is automatically converted to the appropriate extension.
        """
        print("Exporting scene...")
        
        # Select all objects
        bpy.ops.object.select_all(action='SELECT')
        
        # Note: .3ds format is deprecated in Blender 4.0+
        # We'll export to FBX as the primary format, with OBJ and Blender as fallbacks
        
        # Try FBX export (most widely supported)
        try:
            fbx_path = self.export_dir / filename.replace('.3ds', '.fbx')
            print(f"FBX export starting... '{fbx_path}'")
            bpy.ops.export_scene.fbx(
                filepath=str(fbx_path),
                use_selection=True
            )
            print(f"Successfully exported to FBX format: {fbx_path}")
            return True
        except Exception as e:
            print(f"FBX export failed: {e}")
        
        # Try OBJ export (Blender 3.2+ uses wm.obj_export)
        try:
            obj_path = self.export_dir / filename.replace('.3ds', '.obj')
            print(f"OBJ export starting... '{obj_path}'")
            # Try new API first (Blender 3.2+)
            try:
                bpy.ops.wm.obj_export(
                    filepath=str(obj_path),
                    export_selected_objects=True
                )
                print(f"Successfully exported to OBJ format: {obj_path}")
                return True
            except AttributeError:
                # Fall back to legacy API
                bpy.ops.export_scene.obj(
                    filepath=str(obj_path),
                    use_selection=True
                )
                print(f"Successfully exported to OBJ format (legacy API): {obj_path}")
                return True
        except Exception as e:
            print(f"OBJ export failed: {e}")
        
        # Try native Blender format as last resort
        try:
            blend_path = self.export_dir / filename.replace('.3ds', '.blend')
            print(f"Blender format export starting... '{blend_path}'")
            bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
            print(f"Successfully exported to Blender format: {blend_path}")
            return True
        except Exception as e:
            print(f"Blender format export failed: {e}")
        
        print("ERROR: All export formats failed!")
        print("Please check Blender version and file permissions")
        return False
    
    def generate(self):
        """Main generation method"""
        print("\n" + "="*50)
        print("Starting 3D City Generation")
        print("="*50 + "\n")
        
        # Clear scene
        self.clear_scene()
        
        # Download data
        osm_data = self.download_osm_data()
        terrain_data = self.download_terrain_data()
        
        # Generate scene
        self.create_terrain(terrain_data)
        self.create_buildings(osm_data)
        self.create_streets(osm_data)
        self.create_water(osm_data)
        self.create_trees(osm_data)
        
        # Export
        self.export_to_3ds()
        
        # Print summary
        print("\n" + "="*50)
        print("3D City Generation Complete!")
        print("="*50)
        
        # Report errors and warnings
        if self.warnings:
            print(f"\n⚠ WARNINGS ({len(self.warnings)}):")
            for i, warning in enumerate(self.warnings, 1):
                print(f"  {i}. {warning}")
        
        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for i, error in enumerate(self.errors, 1):
                print(f"  {i}. {error}")
            print("\nNote: Generation continued despite errors. Some features may be missing or incomplete.")
        
        if not self.errors and not self.warnings:
            print("\n✅ Generation completed successfully with no errors or warnings!")
        
        print("="*50 + "\n")


# Blender UI Panel for manual coordinate entry
class CITYGEN_PT_Panel(bpy.types.Panel):
    """Creates a Panel in the 3D View"""
    bl_label = "3D City Generator"
    bl_idname = "CITYGEN_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "3D City"
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        layout.label(text="Coordinate Selection:")
        
        box = layout.box()
        box.prop(scene, "citygen_min_lat")
        box.prop(scene, "citygen_max_lat")
        box.prop(scene, "citygen_min_lon")
        box.prop(scene, "citygen_max_lon")
        
        layout.operator("citygen.generate")


class CITYGEN_OT_Generate(bpy.types.Operator):
    """Generate 3D City from coordinates"""
    bl_idname = "citygen.generate"
    bl_label = "Generate City"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        scene = context.scene
        
        # Get coordinates from scene properties
        min_lat = scene.citygen_min_lat
        max_lat = scene.citygen_max_lat
        min_lon = scene.citygen_min_lon
        max_lon = scene.citygen_max_lon
        
        # Validate coordinates
        if min_lat >= max_lat or min_lon >= max_lon:
            self.report({'ERROR'}, "Invalid coordinates: min must be less than max")
            return {'CANCELLED'}
        
        # Generate city
        try:
            generator = CityGenerator(min_lat, max_lat, min_lon, max_lon)
            generator.generate()
            self.report({'INFO'}, "City generation complete!")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Generation failed: {str(e)}")
            return {'CANCELLED'}


def register_ui():
    """Register Blender UI components"""
    # Register properties
    bpy.types.Scene.citygen_min_lat = bpy.props.FloatProperty(
        name="Min Latitude",
        description="Minimum latitude",
        default=48.8566,
        min=-90,
        max=90
    )
    bpy.types.Scene.citygen_max_lat = bpy.props.FloatProperty(
        name="Max Latitude",
        description="Maximum latitude",
        default=48.8666,
        min=-90,
        max=90
    )
    bpy.types.Scene.citygen_min_lon = bpy.props.FloatProperty(
        name="Min Longitude",
        description="Minimum longitude",
        default=2.3522,
        min=-180,
        max=180
    )
    bpy.types.Scene.citygen_max_lon = bpy.props.FloatProperty(
        name="Max Longitude",
        description="Maximum longitude",
        default=2.3622,
        min=-180,
        max=180
    )
    
    # Register classes
    bpy.utils.register_class(CITYGEN_PT_Panel)
    bpy.utils.register_class(CITYGEN_OT_Generate)
    
    print("3D City Generator UI registered")


def unregister_ui():
    """Unregister Blender UI components"""
    try:
        bpy.utils.unregister_class(CITYGEN_PT_Panel)
        bpy.utils.unregister_class(CITYGEN_OT_Generate)
        
        del bpy.types.Scene.citygen_min_lat
        del bpy.types.Scene.citygen_max_lat
        del bpy.types.Scene.citygen_min_lon
        del bpy.types.Scene.citygen_max_lon
    except:
        pass


def parse_command_line_args():
    """Parse command line arguments when running in background mode"""
    # Check if we're running in background mode with arguments
    if '--' in sys.argv:
        argv = sys.argv[sys.argv.index('--') + 1:]
        
        parser = argparse.ArgumentParser(description='3D City Generator')
        parser.add_argument('--min-lat', type=float, help='Minimum latitude')
        parser.add_argument('--max-lat', type=float, help='Maximum latitude')
        parser.add_argument('--min-lon', type=float, help='Minimum longitude')
        parser.add_argument('--max-lon', type=float, help='Maximum longitude')
        
        args = parser.parse_args(argv)
        
        # Check if all coordinates are provided
        if all([args.min_lat, args.max_lat, args.min_lon, args.max_lon]):
            return args
    
    return None


def main():
    """Main entry point"""
    # Try to parse command line arguments
    args = parse_command_line_args()
    
    if args:
        # Command line mode - generate immediately
        print("Running in command-line mode")
        generator = CityGenerator(
            args.min_lat,
            args.max_lat,
            args.min_lon,
            args.max_lon
        )
        generator.generate()
    else:
        # UI mode - register the panel
        print("Running in UI mode - registering panel")
        register_ui()
        print("3D City Generator panel available in the 3D View sidebar (press N)")


if __name__ == "__main__":
    main()
