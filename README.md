# 3DCity

A Blender script for automatically generating 3D city models from OpenStreetMap data with real terrain elevation.

## Features

- 🗺️ Downloads OpenStreetMap data (buildings, streets, water bodies)
- 🏔️ Downloads real terrain elevation data
- 🏗️ Automatically generates:
  - Terrain mesh with elevation
  - Buildings with realistic heights
  - Streets and roads
  - Water bodies (rivers, lakes)
- 🎨 Applies simple textures to all objects
- 💾 Exports to .3ds format

## Requirements

- Blender 2.8 or higher
- Python 3.7+
- Python packages: `requests`, `numpy`

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

The generated model will be exported to the `export/` directory as `city_model.3ds`.

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
Make sure you have write permissions in the `export/` directory.

## Contributing

Contributions are welcome! Feel free to open issues or submit pull requests.

## License

This project is open source and available under the MIT License.