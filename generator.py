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
from pathlib import Path

# Try to import required libraries
try:
    import requests
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
        """Download OpenStreetMap data for the specified area"""
        print("Downloading OSM data...")
        
        # Overpass API query
        overpass_url = "http://overpass-api.de/api/interpreter"
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
        
        try:
            response = requests.post(overpass_url, data={'data': overpass_query}, timeout=120)
            response.raise_for_status()
            data = response.json()
            print(f"Downloaded {len(data.get('elements', []))} OSM elements")
            return data
        except Exception as e:
            print(f"Error downloading OSM data: {e}")
            return {'elements': []}
    
    def download_terrain_data(self):
        """Download terrain elevation data with 50cm resolution"""
        print("Downloading terrain data...")
        
        # Use Open-Elevation API for terrain data
        # For a real implementation, you might want to use SRTM or other elevation services
        
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
        
        elevation_data = []
        
        try:
            # Sample elevation at grid points
            for i in range(grid_size + 1):
                row = []
                for j in range(grid_size + 1):
                    lat = self.min_lat + i * lat_step
                    lon = self.min_lon + j * lon_step
                    
                    # For this demo, we'll use a simple API call
                    # In production, batch these requests
                    url = f"https://api.open-elevation.com/api/v1/lookup?locations={lat},{lon}"
                    
                    try:
                        response = requests.get(url, timeout=10)
                        if response.status_code == 200:
                            data = response.json()
                            elevation = data['results'][0]['elevation']
                        else:
                            elevation = 0
                    except:
                        elevation = 0
                    
                    row.append(elevation)
                row_data = np.array(row)
                elevation_data.append(row_data)
            
            elevation_array = np.array(elevation_data)
            print(f"Downloaded terrain data: {elevation_array.shape}")
            return elevation_array
            
        except Exception as e:
            print(f"Error downloading terrain data: {e}")
            print("Using flat terrain as fallback")
            return np.zeros((grid_size + 1, grid_size + 1))
    
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
        
        # Add material with grass texture
        material = bpy.data.materials.new(name="TerrainMaterial")
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        
        # Clear default nodes
        nodes.clear()
        
        # Create nodes for grass texture
        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (400, 0)
        
        bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
        bsdf.location = (100, 0)
        bsdf.inputs['Roughness'].default_value = 0.9
        
        # Add noise texture for grass variation
        noise1 = nodes.new(type='ShaderNodeTexNoise')
        noise1.location = (-600, 100)
        noise1.inputs['Scale'].default_value = 15.0
        noise1.inputs['Detail'].default_value = 10.0
        
        # Color ramp for grass colors
        color_ramp = nodes.new(type='ShaderNodeValToRGB')
        color_ramp.location = (-300, 0)
        color_ramp.color_ramp.elements[0].color = (0.15, 0.3, 0.1, 1.0)  # Dark green
        color_ramp.color_ramp.elements[1].color = (0.4, 0.6, 0.2, 1.0)  # Light green
        
        # Connect nodes
        links.new(noise1.outputs['Fac'], color_ramp.inputs['Fac'])
        links.new(color_ramp.outputs['Color'], bsdf.inputs['Base Color'])
        links.new(bsdf.outputs['BSDF'], output_node.inputs['Surface'])
        
        terrain_obj.data.materials.append(material)
        
        print(f"Created terrain with {len(vertices)} vertices and {len(faces)} faces")
        return terrain_obj
    
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
        """Create a single building mesh"""
        vertices = []
        faces = []
        
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
        
        # Top face
        top_face = list(range(n, 2 * n))
        top_face.reverse()
        faces.append(top_face)
        
        # Side faces
        for i in range(n):
            next_i = (i + 1) % n
            face = [i, next_i, next_i + n, i + n]
            faces.append(face)
        
        # Create mesh
        mesh = bpy.data.meshes.new("Building")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        
        # Create object
        building_obj = bpy.data.objects.new("Building", mesh)
        bpy.context.collection.objects.link(building_obj)
        
        # Add material with improved texture
        material = bpy.data.materials.new(name="BuildingMaterial")
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        
        # Clear default nodes
        nodes.clear()
        
        # Create nodes for a brick/concrete texture
        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (300, 0)
        
        bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
        bsdf.location = (0, 0)
        bsdf.inputs['Base Color'].default_value = (0.6, 0.55, 0.5, 1.0)  # Beige/concrete
        bsdf.inputs['Roughness'].default_value = 0.8
        
        # Add noise texture for variation
        noise = nodes.new(type='ShaderNodeTexNoise')
        noise.location = (-400, 0)
        noise.inputs['Scale'].default_value = 5.0
        
        color_ramp = nodes.new(type='ShaderNodeValToRGB')
        color_ramp.location = (-200, 0)
        
        # Connect nodes
        links.new(noise.outputs['Fac'], color_ramp.inputs['Fac'])
        links.new(color_ramp.outputs['Color'], bsdf.inputs['Base Color'])
        links.new(bsdf.outputs['BSDF'], output_node.inputs['Surface'])
        
        building_obj.data.materials.append(material)
    
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
            
            # Left and right vertices
            vertices.append((x + px, y + py, 0.1))
            vertices.append((x - px, y - py, 0.1))
        
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
        
        # Add material with asphalt texture
        material = bpy.data.materials.new(name="StreetMaterial")
        material.use_nodes = True
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        
        # Clear default nodes
        nodes.clear()
        
        # Create nodes for asphalt texture
        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (400, 0)
        
        bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
        bsdf.location = (100, 0)
        bsdf.inputs['Roughness'].default_value = 0.7
        
        # Add noise for asphalt texture
        noise = nodes.new(type='ShaderNodeTexNoise')
        noise.location = (-400, 0)
        noise.inputs['Scale'].default_value = 50.0
        noise.inputs['Detail'].default_value = 15.0
        
        color_ramp = nodes.new(type='ShaderNodeValToRGB')
        color_ramp.location = (-200, 0)
        color_ramp.color_ramp.elements[0].color = (0.1, 0.1, 0.1, 1.0)  # Very dark gray
        color_ramp.color_ramp.elements[1].color = (0.25, 0.25, 0.25, 1.0)  # Dark gray
        
        # Connect nodes
        links.new(noise.outputs['Fac'], color_ramp.inputs['Fac'])
        links.new(color_ramp.outputs['Color'], bsdf.inputs['Base Color'])
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
                
                # Inner and outer vertices
                inner_x = x + offset_x - px * half_width * side
                inner_y = y + offset_y - py * half_width * side
                outer_x = x + offset_x + px * half_width * side
                outer_y = y + offset_y + py * half_width * side
                
                vertices.append((inner_x, inner_y, 0.2))
                vertices.append((outer_x, outer_y, 0.2))
            
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
            
            # Add material
            material = bpy.data.materials.new(name="SidewalkMaterial")
            material.use_nodes = True
            nodes = material.node_tree.nodes
            links = material.node_tree.links
            
            # Clear default nodes
            nodes.clear()
            
            # Create nodes for concrete sidewalk
            output_node = nodes.new(type='ShaderNodeOutputMaterial')
            output_node.location = (400, 0)
            
            bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
            bsdf.location = (100, 0)
            bsdf.inputs['Roughness'].default_value = 0.85
            
            # Add noise for concrete texture
            noise = nodes.new(type='ShaderNodeTexNoise')
            noise.location = (-400, 0)
            noise.inputs['Scale'].default_value = 30.0
            
            color_ramp = nodes.new(type='ShaderNodeValToRGB')
            color_ramp.location = (-200, 0)
            color_ramp.color_ramp.elements[0].color = (0.5, 0.5, 0.5, 1.0)  # Light gray
            color_ramp.color_ramp.elements[1].color = (0.65, 0.65, 0.65, 1.0)  # Lighter gray
            
            # Connect nodes
            links.new(noise.outputs['Fac'], color_ramp.inputs['Fac'])
            links.new(color_ramp.outputs['Color'], bsdf.inputs['Base Color'])
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
        
        # Add material
        material = bpy.data.materials.new(name="WaterMaterial")
        material.use_nodes = True
        bsdf = material.node_tree.nodes["Principled BSDF"]
        bsdf.inputs['Base Color'].default_value = (0.2, 0.4, 0.8, 1.0)  # Blue
        bsdf.inputs['Metallic'].default_value = 0.5
        bsdf.inputs['Roughness'].default_value = 0.1
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
        
        # Add trunk material
        trunk_material = bpy.data.materials.new(name="TrunkMaterial")
        trunk_material.use_nodes = True
        nodes = trunk_material.node_tree.nodes
        links = trunk_material.node_tree.links
        nodes.clear()
        
        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (300, 0)
        
        bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
        bsdf.location = (0, 0)
        bsdf.inputs['Base Color'].default_value = (0.3, 0.2, 0.1, 1.0)  # Brown
        bsdf.inputs['Roughness'].default_value = 0.9
        
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
        
        # Add canopy material
        canopy_material = bpy.data.materials.new(name="CanopyMaterial")
        canopy_material.use_nodes = True
        nodes = canopy_material.node_tree.nodes
        links = canopy_material.node_tree.links
        nodes.clear()
        
        output_node = nodes.new(type='ShaderNodeOutputMaterial')
        output_node.location = (400, 0)
        
        bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
        bsdf.location = (100, 0)
        bsdf.inputs['Roughness'].default_value = 0.8
        
        # Add noise for foliage variation
        noise = nodes.new(type='ShaderNodeTexNoise')
        noise.location = (-400, 0)
        noise.inputs['Scale'].default_value = 10.0
        
        color_ramp = nodes.new(type='ShaderNodeValToRGB')
        color_ramp.location = (-200, 0)
        color_ramp.color_ramp.elements[0].color = (0.1, 0.3, 0.05, 1.0)  # Dark green
        color_ramp.color_ramp.elements[1].color = (0.2, 0.5, 0.1, 1.0)  # Bright green
        
        links.new(noise.outputs['Fac'], color_ramp.inputs['Fac'])
        links.new(color_ramp.outputs['Color'], bsdf.inputs['Base Color'])
        links.new(bsdf.outputs['BSDF'], output_node.inputs['Surface'])
        
        canopy_obj.data.materials.append(canopy_material)
    
    def export_to_3ds(self, filename="city_model.3ds"):
        """Export the scene to supported formats (FBX, OBJ, or Blender)"""
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
        
        print("\n" + "="*50)
        print("3D City Generation Complete!")
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
