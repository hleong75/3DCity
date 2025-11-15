# Changes - Enhanced 3D City Details

## Summary
This update addresses the requirements for improved output detail, textures, sidewalks, and trees with enhanced resolution.

## Changes Made

### 1. Improved Resolution (50cm target)
- Updated terrain grid calculation to support 50cm (0.5m) resolution
- Grid size is now calculated dynamically based on area dimensions
- Formula: `grid_size = min(area_meters / 0.5, 100)` (capped at 100 for API limits)
- Minimum grid size of 20 maintained for quality

### 2. Enhanced Textures
All materials now use procedural node-based textures instead of flat colors:

#### Buildings
- Procedural brick/concrete texture with noise variation
- Beige/concrete color (0.6, 0.55, 0.5)
- Roughness: 0.8
- Noise texture at scale 5.0 with color ramp

#### Terrain
- Grass texture with noise variation
- Two-tone green color (dark green to light green)
- Roughness: 0.9
- High-detail noise (scale 15.0, detail 10.0)

#### Streets (Asphalt)
- Dark asphalt texture with fine grain
- Color range: very dark gray (0.1, 0.1, 0.1) to dark gray (0.25, 0.25, 0.25)
- Roughness: 0.7
- Fine noise (scale 50.0, detail 15.0)

#### Sidewalks (Concrete)
- Light concrete texture
- Color range: light gray (0.5, 0.5, 0.5) to lighter gray (0.65, 0.65, 0.65)
- Roughness: 0.85
- Medium noise (scale 30.0)
- Height: 0.2m above street level

### 3. Sidewalk Generation
- Sidewalks are automatically created on both sides of streets
- Width: 1.5 meters
- Only created for non-motorway roads (residential, tertiary, primary, secondary)
- Motorways and trunk roads do not get sidewalks
- Positioned at appropriate offset from street edge

### 4. Tree Generation
- Trees are now extracted from OpenStreetMap data
- Supports two types:
  - Individual trees: `natural=tree` (node)
  - Tree rows: `natural=tree_row` (way)
- Each tree consists of:
  - Trunk: 0.6m diameter, 2m height, brown textured
  - Canopy: 4m diameter spheroid, 3m height, green with variation
- Trees placed every other node in tree rows for spacing

### 5. OSM Data Query Enhancement
- Added queries for:
  - `node["natural"="tree"]` - Individual trees
  - `way["natural"="tree_row"]` - Tree-lined streets/paths

## Technical Details

### Material Node Setup
All materials now use a standard node setup:
1. Noise Texture Node
2. Color Ramp Node (for color variation)
3. Principled BSDF Node
4. Material Output Node

### Resolution Calculation
```python
lat_meters = (max_lat - min_lat) * 111320
lon_meters = (max_lon - min_lon) * 111320 * cos(center_lat)
grid_size = min(int(area_meters / 0.5), 100)
```

### Tree Geometry
- Trunk: 6-segment cylinder
- Canopy: 8x6 spheroid mesh
- Both use procedural materials with noise variation

## Testing
To test these changes:
```bash
blender --background --python generator.py -- \
  --min-lat 48.8566 --max-lat 48.8600 \
  --min-lon 2.2900 --max-lon 2.2950
```

Expected improvements in output:
- More detailed terrain with visible elevation changes
- Textured buildings with realistic concrete/brick appearance
- Streets with asphalt texture
- Sidewalks on both sides of residential streets
- Trees at documented locations from OSM
- Overall improved visual quality at 50cm resolution

## Files Modified
- `generator.py`: Main implementation file with all enhancements
