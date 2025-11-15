# Blender 4.5.4 Compatibility Fix

## Issue Summary
The 3DCity generator script was failing when generating tree materials in Blender 4.5.4 LTS with the following error:

```
KeyError: 'bpy_prop_collection[key]: key "Subsurface Color" not found'
```

This error occurred in the `create_tree_mesh` function at line 1641 when trying to set the subsurface color for the tree canopy material.

## Root Cause
In Blender 4.x, the Principled BSDF shader was updated and simplified. The `Subsurface Color` input was removed from the shader. In the newer versions, the subsurface color is automatically derived from the `Base Color` input, making the separate `Subsurface Color` parameter redundant.

## Solution
**File Changed:** `generator.py` (line 1641)

**Before:**
```python
bsdf.inputs['Roughness'].default_value = 0.85
bsdf.inputs['Subsurface Weight'].default_value = 0.1  # Slight subsurface for leaves
bsdf.inputs['Subsurface Color'].default_value = (0.3, 0.6, 0.2, 1.0)
```

**After:**
```python
bsdf.inputs['Roughness'].default_value = 0.85
bsdf.inputs['Subsurface Weight'].default_value = 0.1  # Slight subsurface for leaves
# Note: In Blender 4.x+, subsurface color is derived from Base Color automatically
```

### Changes Made
1. Removed the line that sets `bsdf.inputs['Subsurface Color']` (incompatible with Blender 4.x)
2. Added an explanatory comment about the Blender 4.x behavior
3. Kept `Subsurface Weight` which is the correct Blender 4.x parameter for controlling subsurface scattering intensity

## Visual Impact
**None** - The visual result should be identical because:
- The `Subsurface Weight` parameter (0.1) still controls the amount of subsurface scattering
- The subsurface effect automatically uses the Base Color, which is already set to green tones (0.3, 0.6, 0.2, 1.0) on line 1713
- This is exactly the same color that was being explicitly set for subsurface in the old code

## Compatibility
- ✅ **Blender 4.5.4 LTS** - Fixed (primary target)
- ✅ **Blender 4.0+** - Compatible (uses the same API)
- ⚠️ **Blender 2.8-3.x** - This fix removes compatibility with older versions that required explicit Subsurface Color. However, the README states the script is "tested with Blender 4.5.4 LTS", so this is acceptable.

## Testing
A new test file `test_blender_compatibility.py` was added to verify:
1. No references to the incompatible `Subsurface Color` input remain
2. The valid `Subsurface Weight` input is present and used correctly
3. The `create_tree_mesh` function exists

All tests pass successfully.

## Security Analysis
CodeQL security scan completed with **0 alerts**.

## Additional Notes
- This is a minimal, surgical fix that changes only 1 line of code
- No other Blender 4.x incompatibilities were found in the codebase
- The script already uses `Specular IOR Level` (Blender 4.x API) instead of the old `Specular` parameter, indicating partial Blender 4.x compatibility was already in place
