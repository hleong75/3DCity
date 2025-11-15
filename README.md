# 3DCity

A Blender script for automatically generating 3D city models from OpenStreetMap data with real terrain elevation.

## Features

- 🗺️ Downloads OpenStreetMap data (buildings, streets, water bodies, trees)
- 🏔️ Downloads real terrain elevation data with 50cm resolution
- ⚡ **Fast multithreaded elevation data fetching** (20 concurrent threads)
- 🎨 **F4map-quality photorealistic textures** with advanced procedural materials
- 🏗️ Automatically generates:
  - Terrain mesh with elevation, detailed grass texture, and dirt patches
  - Buildings with realistic heights, **window patterns, brick facades, and tiled roofs**
  - Streets and roads with **asphalt texture, lane markings, and wear patterns**
  - Sidewalks on both sides of residential streets with **concrete tile texture**
  - Water bodies with **realistic wave patterns and transparency**
  - Trees from OSM data with **detailed bark and leaf textures**
- 🌟 **Professional-grade materials** including:
  - Building facades: Procedural windows, bricks, weathering, bump mapping
  - Separate roofs: Clay tile patterns with color variation
  - High-res terrain: Grass blades (150+ detail scale) and organic dirt patches
  - Road surfaces: Fine asphalt grain, cracks, and white lane markings
  - Concrete sidewalks: Tile patterns with weathering effects
  - Dynamic water: Wave patterns, transparency (IOR 1.333), depth variation
  - Natural tree bark: Vertical grain patterns with high detail
  - Detailed foliage: Subsurface scattering for light transmission through leaves
- 💾 Exports to multiple formats (.fbx, .obj, .blend)

See [TEXTURE_ENHANCEMENTS.md](TEXTURE_ENHANCEMENTS.md) for detailed documentation on all texture improvements.

## Requirements

- Blender 2.8 or higher (tested with Blender 4.5.4 LTS)
- Python 3.7+
- Python packages: `requests`, `numpy`
- Blender addons (automatically enabled by the script):
  - `io_scene_fbx` - For .fbx export (primary format)

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
1. `.fbx` format (Autodesk FBX) - Primary format, widely supported
2. `.obj` format (Wavefront OBJ) - Fallback format
3. `.blend` format (Native Blender) - Last resort

Note: The `.3ds` format has been deprecated and removed in Blender 4.0+. FBX is now the primary export format and is compatible with most 3D modeling applications.

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
- Rate limiting is applied to prevent API errors (configurable)
- Building heights are estimated if not specified in OSM data

## Configuration

You can customize download behavior by modifying the generator settings:

```python
generator = CityGenerator(min_lat, max_lat, min_lon, max_lon)

# Adjust rate limiting (default: 5 workers, 10 req/s)
generator.max_workers = 10  # More concurrent threads (may cause 429 errors)
generator.requests_per_second = 20  # Higher request rate (may cause 429 errors)

# Adjust retry behavior
generator.max_retries = 5  # More retry attempts
generator.initial_timeout = 60  # Longer timeout for slow connections

generator.generate()
```

**Note**: Increasing `max_workers` or `requests_per_second` may trigger rate limiting errors (429). The default settings are conservative to ensure reliability.

## Performance

The script uses **multithreading with rate limiting** to efficiently fetch elevation data:
- **5 concurrent worker threads** fetch elevation data in parallel
- **Rate limiting at 10 requests/second** to prevent API errors (429 rate limit)
- Thread-safe progress tracking with real-time updates
- Automatic retry with exponential backoff for failed requests

### Rate Limiting Protection
To avoid API rate limit errors (HTTP 429):
- Maximum 5 concurrent threads (down from 20) to reduce API load
- Built-in rate limiting ensures no more than 10 requests per second
- Special handling for 429 errors with progressive wait times (10s, 20s, 30s)
- Configurable parameters for different API limits

For example, on a standard grid:
- Grid size: 101×101 = 10,201 points
- With 5 threads and rate limiting: ~20-30 seconds
- Without rate limiting (old behavior): Risk of 429 errors
- **Trade-off: Slightly slower but more reliable**

## Troubleshooting

### "requests library not found"
Install the requests library in Blender's Python environment (see Installation section).

### "No buildings generated"
The selected area might not have building data in OpenStreetMap. Try a different, more urban area.

### Download errors or timeouts
The script includes robust error handling with automatic retries and server fallback:
- **Multiple API servers**: OSM data is requested from multiple Overpass API servers for redundancy
  - Primary: overpass-api.de
  - Fallback 1: overpass.kumi.systems
  - Fallback 2: overpass.openstreetmap.ru
- **Automatic retries**: Failed downloads are automatically retried up to 3 times per server with exponential backoff
- **Rate limiting protection**: Built-in throttling prevents 429 (Too Many Requests) errors
  - Maximum 5 concurrent threads
  - 10 requests per second limit
  - Special handling for 429 errors with progressive wait times
- **Smart retry logic**: 504 Gateway Timeout errors get extra wait time before retrying
- **Server rotation**: If one server fails, the script automatically tries the next server
- **Progress reporting**: Long-running downloads show progress updates every 10%
- **Graceful degradation**: If all servers fail after all retries, the script continues with empty/flat data
- **Error summary**: At the end of generation, all errors and warnings are displayed

If you experience persistent download issues:
- Check your internet connection
- The script automatically handles rate limits with built-in throttling
- For faster downloads, you can increase `max_workers` and `requests_per_second` (at risk of 429 errors)
- Check the error summary at the end for specific failure reasons
- Gateway timeouts (504) are common during peak hours - the script handles these automatically

### Export fails
The script automatically tries multiple export formats (.fbx, .obj, .blend). If all formats fail:
- Check that you have write permissions in the `export/` directory
- Ensure Blender is properly installed with the required export addons
- Try running Blender with administrator/sudo privileges

### "Blender 4.5+ Compatibility"
- The `.3ds` format has been deprecated and removed in Blender 4.0+
- The script now uses FBX as the primary export format
- OBJ export uses the new `wm.obj_export` operator (Blender 3.2+) with fallback to legacy API
- All export formats are tested and working with Blender 4.5.4 LTS

## Contributing

Contributions are welcome! Feel free to open issues or submit pull requests.

## License

This project is open source and available under the MIT License.