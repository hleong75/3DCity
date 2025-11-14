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
        
        print(f"Initialized CityGenerator for area:")
        print(f"  Latitude: {min_lat} to {max_lat}")
        print(f"  Longitude: {min_lon} to {max_lon}")
    
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
        """Download terrain elevation data"""
        print("Downloading terrain data...")
        
        # Use Open-Elevation API for terrain data
        # For a real implementation, you might want to use SRTM or other elevation services
        
        # Create a grid of points to sample elevation
        grid_size = 20
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
        
        # Add material
        material = bpy.data.materials.new(name="TerrainMaterial")
        material.use_nodes = True
        bsdf = material.node_tree.nodes["Principled BSDF"]
        bsdf.inputs['Base Color'].default_value = (0.3, 0.5, 0.2, 1.0)  # Green
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
        
        # Add material
        material = bpy.data.materials.new(name="BuildingMaterial")
        material.use_nodes = True
        bsdf = material.node_tree.nodes["Principled BSDF"]
        bsdf.inputs['Base Color'].default_value = (0.7, 0.7, 0.7, 1.0)  # Gray
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
                
                # Create street
                self.create_street_mesh(coords, width)
                street_count += 1
        
        print(f"Created {street_count} streets")
    
    def create_street_mesh(self, coords, width):
        """Create a single street mesh"""
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
        
        # Add material
        material = bpy.data.materials.new(name="StreetMaterial")
        material.use_nodes = True
        bsdf = material.node_tree.nodes["Principled BSDF"]
        bsdf.inputs['Base Color'].default_value = (0.2, 0.2, 0.2, 1.0)  # Dark gray
        street_obj.data.materials.append(material)
    
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
    
    def export_to_3ds(self, filename="city_model.3ds"):
        """Export the scene to .3ds format"""
        print("Exporting to .3ds format...")
        
        export_path = self.export_dir / filename
        
        # Select all objects
        bpy.ops.object.select_all(action='SELECT')
        
        # Export
        try:
            bpy.ops.export_scene.autodesk_3ds(
                filepath=str(export_path),
                use_selection=True
            )
            print(f"Successfully exported to {export_path}")
        except Exception as e:
            print(f"Error exporting to .3ds: {e}")
            print("Note: .3ds export may require additional Blender setup")
    
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
