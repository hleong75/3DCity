# 3DCity

A Blender script for automatically generating 3D city models from OpenStreetMap data with real terrain elevation.

## Features

- 🗺️ Downloads OpenStreetMap data (buildings, streets, water bodies, trees)
- 🏔️ Downloads real terrain elevation data with 50cm resolution
- 🏗️ Automatically generates:
  - Terrain mesh with elevation and grass texture
  - Buildings with realistic heights and procedural textures
  - Streets and roads with asphalt texture
  - Sidewalks on both sides of residential streets
  - Trees from OSM data (individual trees and tree rows)
  - Water bodies (rivers, lakes)
- 🎨 Applies procedural node-based textures to all objects
- 💾 Exports to multiple formats (.3ds, .obj, .fbx, .blend)

## Requirements

- Blender 2.8 or higher
- Python 3.7+
- Python packages: `requests`, `numpy`
- Blender addons (automatically enabled by the script):
  - `io_scene_3ds` - For .3ds export
  - `io_scene_obj` - For .obj export (fallback)
  - `io_scene_fbx` - For .fbx export (fallback)

## Installation

1. Clone this repository:
```bash
git clone https://github.com/hleong75/3DCity.git
cd 3DCity
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

Note: If you're using Blender's bundled Python, you may need to install packages in Blender's Python environment:
```bash
# On Linux/Mac:
/path/to/blender/python/bin/python -m pip install -r requirements.txt

# On Windows:
C:\Program Files\Blender Foundation\Blender\python\bin\python.exe -m pip install -r requirements.txt
```

## Usage

### Command-Line Mode (Automated)

Generate a city model from the command line by providing coordinates:

```bash
blender --background --python generator.py -- --min-lat 48.8566 --max-lat 48.8666 --min-lon 2.3522 --max-lon 2.3622
```

Parameters:
- `--min-lat`: Minimum latitude (south boundary)
- `--max-lat`: Maximum latitude (north boundary)
- `--min-lon`: Minimum longitude (west boundary)
- `--max-lon`: Maximum longitude (east boundary)

Example (Paris city center):
```bash
blender --background --python generator.py -- --min-lat 48.8566 --max-lat 48.8666 --min-lon 2.3522 --max-lon 2.3622
```

### UI Mode (Interactive)

1. Open Blender
2. Go to `Scripting` workspace
3. Open `generator.py` and click `Run Script`
4. Press `N` to open the sidebar in the 3D View
5. Find the "3D City" tab
6. Enter your coordinates
7. Click "Generate City"

## Output

The generated model will be exported to the `export/` directory. The script will try to export in the following order:
1. `.3ds` format (Autodesk 3D Studio) - Primary format
2. `.obj` format (Wavefront OBJ) - Fallback if .3ds is not available
3. `.fbx` format (Autodesk FBX) - Second fallback
4. `.blend` format (Native Blender) - Last resort

The export addons are automatically enabled by the script.

## Examples

### Small Area (Paris - Eiffel Tower area)
```bash
blender --background --python generator.py -- --min-lat 48.8566 --max-lat 48.8600 --min-lon 2.2900 --max-lon 2.2950
```

### Medium Area (Manhattan downtown)
```bash
blender --background --python generator.py -- --min-lat 40.7080 --max-lat 40.7150 --min-lon -74.0150 --max-lon -74.0050
```

## Finding Coordinates

You can find coordinates for any area using:
- [OpenStreetMap](https://www.openstreetmap.org/) - Right-click and select "Show address"
- [LatLong.net](https://www.latlong.net/)
- [Google Maps](https://maps.google.com/) - Right-click and select coordinates

## Limitations

- Works best with small to medium areas (< 1km²)
- Large areas may take significant time to download and process
- Terrain elevation API may have rate limits
- Building heights are estimated if not specified in OSM data

## Troubleshooting

### "requests library not found"
Install the requests library in Blender's Python environment (see Installation section).

### "No buildings generated"
The selected area might not have building data in OpenStreetMap. Try a different, more urban area.

### Export fails
The script automatically tries multiple export formats (.3ds, .obj, .fbx, .blend). If all formats fail:
- Check that you have write permissions in the `export/` directory
- Ensure Blender is properly installed with the required export addons
- Try running Blender with administrator/sudo privileges

### ".3ds export operator not available"
The script will automatically attempt to enable the 3DS export addon. If this fails, it will fallback to OBJ or FBX formats which are more widely supported.

## Contributing

Contributions are welcome! Feel free to open issues or submit pull requests.

## License

This project is open source and available under the MIT License.