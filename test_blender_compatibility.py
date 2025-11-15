#!/usr/bin/env python3
"""
Test script to verify Blender 4.5.4 compatibility for tree material generation.
This test checks that the tree material setup doesn't reference incompatible shader inputs.
"""

import sys
import re


def test_no_subsurface_color_reference():
    """Test that generator.py doesn't reference the incompatible 'Subsurface Color' input"""
    with open('generator.py', 'r') as f:
        content = f.read()
    
    # Search for any reference to 'Subsurface Color' in the BSDF input context
    # This should not appear after our fix
    pattern = r"\.inputs\[['\"]Subsurface Color['\"]\]"
    matches = re.findall(pattern, content)
    
    if matches:
        print(f"FAIL: Found {len(matches)} reference(s) to 'Subsurface Color' input")
        print("This input is not available in Blender 4.x and will cause a KeyError")
        return False
    
    print("PASS: No references to incompatible 'Subsurface Color' input found")
    return True


def test_subsurface_weight_present():
    """Test that the valid 'Subsurface Weight' input is still being used"""
    with open('generator.py', 'r') as f:
        content = f.read()
    
    # Search for the proper Blender 4.x subsurface parameter
    pattern = r"\.inputs\[['\"]Subsurface Weight['\"]\]"
    matches = re.findall(pattern, content)
    
    if not matches:
        print("FAIL: 'Subsurface Weight' input not found")
        print("This is the correct Blender 4.x parameter for subsurface scattering")
        return False
    
    print(f"PASS: Found {len(matches)} reference(s) to 'Subsurface Weight' input (Blender 4.x compatible)")
    return True


def test_create_tree_mesh_function_exists():
    """Test that the create_tree_mesh function exists"""
    with open('generator.py', 'r') as f:
        content = f.read()
    
    if 'def create_tree_mesh(' not in content:
        print("FAIL: create_tree_mesh function not found")
        return False
    
    print("PASS: create_tree_mesh function exists")
    return True


def main():
    """Run all compatibility tests"""
    print("=" * 60)
    print("Blender 4.5.4 Compatibility Test Suite")
    print("=" * 60)
    print()
    
    tests = [
        test_no_subsurface_color_reference,
        test_subsurface_weight_present,
        test_create_tree_mesh_function_exists,
    ]
    
    results = []
    for test in tests:
        print(f"Running: {test.__name__}")
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"ERROR: Test {test.__name__} failed with exception: {e}")
            results.append(False)
        print()
    
    print("=" * 60)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)
    
    if all(results):
        print("\n✓ All compatibility tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
