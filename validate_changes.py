#!/usr/bin/env python3
"""
Validation script to check that the code changes are correct.
This validates the generator.py without requiring Blender.
"""

import sys
import ast
import re
from pathlib import Path


def check_imports():
    """Check that multithreading imports are removed"""
    print("Checking imports...")
    
    with open('generator.py', 'r') as f:
        content = f.read()
    
    issues = []
    
    # Check that multithreading imports are gone
    if 'ThreadPoolExecutor' in content:
        issues.append("❌ ThreadPoolExecutor still imported")
    else:
        print("  ✅ ThreadPoolExecutor not imported")
    
    if 'as_completed' in content:
        issues.append("❌ as_completed still imported")
    else:
        print("  ✅ as_completed not imported")
    
    if 'from threading import Lock' in content:
        issues.append("❌ threading.Lock still imported")
    else:
        print("  ✅ threading.Lock not imported")
    
    return issues


def check_configuration():
    """Check that configuration is changed to sequential"""
    print("\nChecking configuration...")
    
    with open('generator.py', 'r') as f:
        content = f.read()
    
    issues = []
    
    # Check for removal of multithreading config
    if 'self.max_workers' in content:
        issues.append("❌ max_workers still present in code")
    else:
        print("  ✅ max_workers removed")
    
    if 'self.requests_per_second' in content:
        issues.append("❌ requests_per_second still present in code")
    else:
        print("  ✅ requests_per_second removed")
    
    if 'self._progress_lock' in content:
        issues.append("❌ _progress_lock still present in code")
    else:
        print("  ✅ _progress_lock removed")
    
    if 'self._rate_limit_lock' in content:
        issues.append("❌ _rate_limit_lock still present in code")
    else:
        print("  ✅ _rate_limit_lock removed")
    
    # Check for new sequential config
    if 'self.request_delay' in content:
        print("  ✅ request_delay added")
    else:
        issues.append("❌ request_delay not found")
    
    return issues


def check_download_terrain():
    """Check that download_terrain_data uses sequential processing"""
    print("\nChecking download_terrain_data()...")
    
    with open('generator.py', 'r') as f:
        content = f.read()
    
    issues = []
    
    # Check that ThreadPoolExecutor is not used
    if 'ThreadPoolExecutor' in content:
        issues.append("❌ ThreadPoolExecutor still used in code")
    else:
        print("  ✅ ThreadPoolExecutor not used")
    
    if 'as_completed' in content:
        issues.append("❌ as_completed still used in code")
    else:
        print("  ✅ as_completed not used")
    
    # Check for sequential processing
    terrain_func = re.search(
        r'def download_terrain_data\(self\):.*?(?=\n    def |\Z)',
        content,
        re.DOTALL
    )
    
    if terrain_func:
        func_content = terrain_func.group(0)
        
        # Check for sequential loop
        if 'for i in range(grid_size + 1):' in func_content:
            print("  ✅ Sequential loop found")
        else:
            issues.append("❌ Sequential loop not found")
        
        if 'for j in range(grid_size + 1):' in func_content:
            print("  ✅ Nested loop for grid traversal found")
        else:
            issues.append("❌ Nested loop not found")
        
        # Check that it's not using futures
        if 'future' in func_content.lower():
            issues.append("❌ Still using futures/concurrent processing")
        else:
            print("  ✅ No concurrent futures used")
    else:
        issues.append("❌ Could not find download_terrain_data function")
    
    return issues


def check_textures():
    """Check that texture code is still present"""
    print("\nChecking textures...")
    
    with open('generator.py', 'r') as f:
        content = f.read()
    
    issues = []
    
    # Check for material creation functions
    materials = [
        '_create_detailed_facade_material',
        '_create_roof_material',
    ]
    
    for material in materials:
        if f'def {material}' in content:
            print(f"  ✅ {material}() present")
        else:
            issues.append(f"❌ {material}() not found")
    
    # Check for texture nodes
    texture_nodes = [
        'ShaderNodeTexNoise',
        'ShaderNodeTexBrick',
        'ShaderNodeTexWave',
        'ShaderNodeBsdfPrincipled',
    ]
    
    for node in texture_nodes:
        if node in content:
            print(f"  ✅ {node} used")
        else:
            issues.append(f"❌ {node} not found")
    
    return issues


def check_export():
    """Check that export functions are still present"""
    print("\nChecking export functionality...")
    
    with open('generator.py', 'r') as f:
        content = f.read()
    
    issues = []
    
    # Check export function
    if 'def export_to_3ds' in content:
        print("  ✅ export_to_3ds() present")
    else:
        issues.append("❌ export_to_3ds() not found")
    
    # Check for FBX export (primary format)
    if 'export_scene.fbx' in content:
        print("  ✅ FBX export code present")
    else:
        issues.append("❌ FBX export code not found")
    
    # Check for OBJ export (fallback)
    if 'wm.obj_export' in content or 'export_scene.obj' in content:
        print("  ✅ OBJ export code present")
    else:
        issues.append("❌ OBJ export code not found")
    
    return issues


def check_readme():
    """Check that README is updated"""
    print("\nChecking README.md...")
    
    with open('README.md', 'r') as f:
        content = f.read()
    
    issues = []
    
    # Check that multithreading references are removed
    if 'multithreaded' in content.lower() or '20 concurrent threads' in content:
        issues.append("❌ README still mentions multithreading")
    else:
        print("  ✅ Multithreading references removed")
    
    # Check for sequential processing mention
    if 'sequential' in content.lower():
        print("  ✅ Sequential processing mentioned")
    else:
        issues.append("❌ Sequential processing not mentioned in README")
    
    return issues


def main():
    """Run all validations"""
    print("="*80)
    print("3D City Generator - Code Validation")
    print("="*80)
    print("\nValidating changes to remove multithreading...\n")
    
    all_issues = []
    
    # Run all checks
    all_issues.extend(check_imports())
    all_issues.extend(check_configuration())
    all_issues.extend(check_download_terrain())
    all_issues.extend(check_textures())
    all_issues.extend(check_export())
    all_issues.extend(check_readme())
    
    # Summary
    print("\n" + "="*80)
    print("VALIDATION SUMMARY")
    print("="*80)
    
    if not all_issues:
        print("\n✅ ALL VALIDATIONS PASSED!")
        print("\nChanges summary:")
        print("  • Multithreading removed")
        print("  • Sequential processing implemented")
        print("  • Textures preserved")
        print("  • Export functionality preserved")
        print("  • Documentation updated")
        return 0
    else:
        print(f"\n❌ {len(all_issues)} ISSUE(S) FOUND:\n")
        for issue in all_issues:
            print(f"  {issue}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
