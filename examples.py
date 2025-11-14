#!/usr/bin/env python3
"""
Example usage script for 3DCity generator
This demonstrates how to use the generator with different city coordinates.
"""

# Example coordinates for various cities
EXAMPLES = {
    "Paris - Eiffel Tower": {
        "min_lat": 48.8566,
        "max_lat": 48.8600,
        "min_lon": 2.2900,
        "max_lon": 2.2950
    },
    "New York - Times Square": {
        "min_lat": 40.7580,
        "max_lat": 40.7600,
        "min_lon": -73.9870,
        "max_lon": -73.9850
    },
    "London - Big Ben": {
        "min_lat": 51.4995,
        "max_lat": 51.5015,
        "min_lon": -0.1280,
        "max_lon": -0.1250
    },
    "Tokyo - Shibuya": {
        "min_lat": 35.6580,
        "max_lat": 35.6620,
        "min_lon": 139.6960,
        "max_lon": 139.7010
    }
}

def print_blender_command(name, coords):
    """Print the Blender command to generate a city"""
    print(f"\n{name}:")
    print("-" * 60)
    cmd = (f"blender --background --python generator.py -- "
           f"--min-lat {coords['min_lat']} "
           f"--max-lat {coords['max_lat']} "
           f"--min-lon {coords['min_lon']} "
           f"--max-lon {coords['max_lon']}")
    print(cmd)

if __name__ == "__main__":
    print("=" * 60)
    print("3DCity Generator - Example Commands")
    print("=" * 60)
    
    for name, coords in EXAMPLES.items():
        print_blender_command(name, coords)
    
    print("\n" + "=" * 60)
    print("Custom Coordinates:")
    print("=" * 60)
    print("Find coordinates at: https://www.openstreetmap.org/")
    print("Right-click on the map and select 'Show address'")
    print("\nThen use:")
    print("blender --background --python generator.py -- \\")
    print("  --min-lat YOUR_MIN_LAT --max-lat YOUR_MAX_LAT \\")
    print("  --min-lon YOUR_MIN_LON --max-lon YOUR_MAX_LON")
    print("=" * 60)
