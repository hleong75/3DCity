# Testing Guide for 3D City Generator

This document provides instructions for testing the 3D City Generator after removing multithreading to avoid 429 rate limit errors.

## Changes Made

### Removed Multithreading
- Removed `ThreadPoolExecutor` and concurrent processing
- Removed thread-safe locks (`Lock`)
- Removed `max_workers` and `requests_per_second` configuration

### Implemented Sequential Processing
- Added `request_delay` configuration (default: 0.2 seconds = 5 req/s)
- Sequential loop processes elevation points one at a time
- Simple delay between requests to avoid rate limiting

### Preserved Features
- ✅ All texture materials (buildings, terrain, streets, water, trees)
- ✅ Export functionality (FBX, OBJ, Blender formats)
- ✅ Error handling and retry logic
- ✅ Progress reporting

## Testing Instructions

### Prerequisites
1. Install Blender 2.8 or higher (tested with 4.5.4 LTS)
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Manual Testing

Test with a single small location first:

```bash
blender --background --python generator.py -- \
  --min-lat 48.8566 --max-lat 48.8600 \
  --min-lon 2.2900 --max-lon 2.2950
```

Expected output:
- No 429 (rate limit) errors
- Sequential progress updates (10%, 20%, 30%, ...)
- Successful export to FBX/OBJ/blend format
- Output in `export/` directory

### Automated Testing (10 Locations)

Run the test suite to validate 10 different locations:

```bash
python3 test_locations.py
```

This will test:
1. Paris, France (Eiffel Tower)
2. New York, USA (Manhattan)
3. London, UK (Big Ben)
4. Tokyo, Japan (Shibuya)
5. Sydney, Australia (Opera House)
6. Dubai, UAE (Burj Khalifa)
7. Rome, Italy (Colosseum)
8. Singapore (Marina Bay)
9. San Francisco, USA (Golden Gate)
10. Barcelona, Spain (Sagrada Familia)

Expected results:
- All 10 tests should pass
- No 429 errors
- Each test takes ~5-10 minutes (depending on grid size)
- Total test time: ~1-2 hours

### What to Check

For each test, verify:

1. **No Rate Limiting Errors**
   - No "429" or "Too Many Requests" in output
   - No "rate limit" errors

2. **Textures Present**
   - Buildings have window patterns and brick facades
   - Terrain has grass texture with detail
   - Streets have asphalt texture
   - Water has wave patterns
   - Trees have bark and foliage textures

3. **Export Success**
   - File created in `export/` directory
   - Format is FBX (or OBJ/blend as fallback)
   - File size is reasonable (> 0 bytes)

4. **Geometry Generated**
   - Output shows "Created X buildings"
   - Output shows "Created X streets"
   - Output shows "Created X water bodies"
   - Output shows "Created X trees"

### Performance Expectations

With sequential processing:
- Grid size: 21×21 = 441 points → ~1.5 minutes
- Grid size: 51×51 = 2,601 points → ~9 minutes
- Grid size: 101×101 = 10,201 points → ~34 minutes

Trade-off: Slower but no 429 errors!

### Troubleshooting

If you encounter issues:

1. **Still getting 429 errors?**
   - Increase `request_delay` in generator.py:
     ```python
     self.request_delay = 0.5  # Slower (2 req/s)
     ```

2. **Too slow?**
   - Decrease `request_delay` (risk of 429 errors):
     ```python
     self.request_delay = 0.1  # Faster (10 req/s)
     ```

3. **Export fails?**
   - Check `export/` directory permissions
   - Verify Blender export addons are enabled
   - Check Blender console output for errors

## Test Results Template

When reporting test results, use this format:

```
Test Location: [Location Name]
Grid Size: [e.g., 21×21]
Duration: [e.g., 2.5 minutes]
Status: [PASS/FAIL]
429 Errors: [Yes/No]
Export Format: [FBX/OBJ/blend]
Buildings: [count]
Streets: [count]
Water: [count]
Trees: [count]
Notes: [any additional observations]
```

## Success Criteria

The changes are successful if:
- ✅ All 10 test locations complete without 429 errors
- ✅ Textures are visible in exported models
- ✅ Export to 3D format (FBX/OBJ/blend) succeeds
- ✅ No regression in functionality
- ✅ Reasonable performance (5-10 minutes for small areas)

## Code Validation

Before running tests with Blender, validate the code changes:

```bash
python3 validate_changes.py
```

This checks:
- Multithreading code is removed
- Sequential processing is implemented
- Textures are preserved
- Export functionality is preserved
- Documentation is updated
