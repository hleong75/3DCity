#!/usr/bin/env python3
"""
Test script to run the 3D City generator on 10 different locations worldwide.
This validates that the changes work correctly without 429 errors.
"""

import subprocess
import sys
import time
from pathlib import Path

# 10 test locations from around the world
# Each location is a small area (~0.01 degree bounding box, roughly 1km x 1km)
TEST_LOCATIONS = [
    {
        "name": "Paris, France (Eiffel Tower)",
        "min_lat": 48.8566,
        "max_lat": 48.8600,
        "min_lon": 2.2900,
        "max_lon": 2.2950,
    },
    {
        "name": "New York, USA (Manhattan)",
        "min_lat": 40.7580,
        "max_lat": 40.7610,
        "min_lon": -73.9855,
        "max_lon": -73.9805,
    },
    {
        "name": "London, UK (Big Ben)",
        "min_lat": 51.4995,
        "max_lat": 51.5025,
        "min_lon": -0.1280,
        "max_lon": -0.1230,
    },
    {
        "name": "Tokyo, Japan (Shibuya)",
        "min_lat": 35.6580,
        "max_lat": 35.6610,
        "min_lon": 139.6965,
        "max_lon": 139.7015,
    },
    {
        "name": "Sydney, Australia (Opera House)",
        "min_lat": -33.8585,
        "max_lat": -33.8555,
        "min_lon": 151.2115,
        "max_lon": 151.2165,
    },
    {
        "name": "Dubai, UAE (Burj Khalifa)",
        "min_lat": 25.1950,
        "max_lat": 25.1980,
        "min_lon": 55.2700,
        "max_lon": 55.2750,
    },
    {
        "name": "Rome, Italy (Colosseum)",
        "min_lat": 41.8895,
        "max_lat": 41.8925,
        "min_lon": 12.4905,
        "max_lon": 12.4955,
    },
    {
        "name": "Singapore (Marina Bay)",
        "min_lat": 1.2795,
        "max_lat": 1.2825,
        "min_lon": 103.8510,
        "max_lon": 103.8560,
    },
    {
        "name": "San Francisco, USA (Golden Gate)",
        "min_lat": 37.8080,
        "max_lat": 37.8110,
        "min_lon": -122.4800,
        "max_lon": -122.4750,
    },
    {
        "name": "Barcelona, Spain (Sagrada Familia)",
        "min_lat": 41.4030,
        "max_lat": 41.4060,
        "min_lon": 2.1720,
        "max_lon": 2.1770,
    },
]


def find_blender():
    """Find blender executable in common locations"""
    common_paths = [
        "blender",  # In PATH
        "/usr/bin/blender",
        "/usr/local/bin/blender",
        "/snap/bin/blender",
        "C:\\Program Files\\Blender Foundation\\Blender\\blender.exe",
        "C:\\Program Files\\Blender Foundation\\Blender 4.2\\blender.exe",
        "C:\\Program Files\\Blender Foundation\\Blender 3.6\\blender.exe",
    ]
    
    for path in common_paths:
        try:
            result = subprocess.run(
                [path, "--version"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"Found Blender at: {path}")
                return path
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    
    return None


def run_test(location_num, location_data, blender_path):
    """Run a single test for a location"""
    print(f"\n{'='*80}")
    print(f"TEST {location_num}/10: {location_data['name']}")
    print(f"{'='*80}")
    print(f"Coordinates: ({location_data['min_lat']}, {location_data['min_lon']}) to "
          f"({location_data['max_lat']}, {location_data['max_lon']})")
    
    # Build command
    cmd = [
        blender_path,
        "--background",
        "--python", "generator.py",
        "--",
        "--min-lat", str(location_data['min_lat']),
        "--max-lat", str(location_data['max_lat']),
        "--min-lon", str(location_data['min_lon']),
        "--max-lon", str(location_data['max_lon']),
    ]
    
    print(f"\nRunning command: {' '.join(cmd)}")
    print(f"Start time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    start_time = time.time()
    
    try:
        # Run with timeout to avoid hanging
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout per location
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"\nEnd time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
        
        # Check for success indicators
        success_indicators = [
            "Successfully exported",
            "3D City Generation Complete",
            "Generation completed successfully"
        ]
        
        error_indicators = [
            "ERROR:",
            "rate limit",
            "429",
            "Too Many Requests",
            "All export formats failed"
        ]
        
        has_success = any(indicator in result.stdout for indicator in success_indicators)
        has_error = any(indicator in result.stdout or indicator in result.stderr 
                       for indicator in error_indicators)
        
        # Print relevant output
        if result.returncode != 0:
            print(f"\n❌ FAILED with exit code {result.returncode}")
            print("\nSTDERR:")
            print(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
            return False
        elif has_error:
            print(f"\n⚠️  COMPLETED WITH ERRORS")
            print("\nRelevant output:")
            for line in result.stdout.split('\n'):
                if any(indicator.lower() in line.lower() for indicator in error_indicators):
                    print(line)
            return False
        elif has_success:
            print(f"\n✅ SUCCESS")
            # Print summary lines
            for line in result.stdout.split('\n'):
                if 'Created' in line or 'exported' in line or 'Complete' in line:
                    print(line)
            return True
        else:
            print(f"\n⚠️  UNCERTAIN (no clear success/error indicators)")
            print("\nLast 1000 chars of output:")
            print(result.stdout[-1000:])
            return False
            
    except subprocess.TimeoutExpired:
        print(f"\n❌ TIMEOUT after 10 minutes")
        return False
    except Exception as e:
        print(f"\n❌ EXCEPTION: {str(e)}")
        return False


def main():
    """Main test runner"""
    print("="*80)
    print("3D City Generator - 10 Location Test Suite")
    print("="*80)
    print("\nThis will test the generator on 10 different locations worldwide")
    print("to verify that sequential processing avoids 429 rate limit errors.\n")
    
    # Find Blender
    blender_path = find_blender()
    if not blender_path:
        print("ERROR: Could not find Blender executable!")
        print("Please install Blender or add it to your PATH.")
        sys.exit(1)
    
    # Run tests
    results = []
    start_time = time.time()
    
    for i, location in enumerate(TEST_LOCATIONS, 1):
        success = run_test(i, location, blender_path)
        results.append({
            "location": location["name"],
            "success": success
        })
        
        # Wait between tests to avoid any rate limiting issues
        if i < len(TEST_LOCATIONS):
            print("\nWaiting 10 seconds before next test...")
            time.sleep(10)
    
    # Summary
    end_time = time.time()
    total_duration = end_time - start_time
    
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"\nTotal duration: {total_duration/60:.1f} minutes")
    print(f"\nResults:")
    
    passed = 0
    failed = 0
    
    for i, result in enumerate(results, 1):
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        print(f"  {i:2d}. {status} - {result['location']}")
        if result["success"]:
            passed += 1
        else:
            failed += 1
    
    print(f"\nTotal: {passed}/{len(results)} passed, {failed}/{len(results)} failed")
    
    if passed == len(results):
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    elif passed > 0:
        print(f"\n⚠️  PARTIAL SUCCESS: {passed}/{len(results)} tests passed")
        return 1
    else:
        print("\n❌ ALL TESTS FAILED")
        return 2


if __name__ == "__main__":
    sys.exit(main())
