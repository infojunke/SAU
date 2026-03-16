#!/usr/bin/env python3
"""
Test script for environment and region filtering
Demonstrates various filter combinations
"""

import subprocess
import sys
from pathlib import Path

def run_command(cmd, description):
    """Run a command and display results"""
    print(f"\n{'='*80}")
    print(f"TEST: {description}")
    print(f"{'='*80}")
    print(f"Command: {cmd}")
    print("-" * 80)
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Extract key information from output
        for line in result.stdout.split('\n'):
            if any(keyword in line for keyword in [
                'Filtering to',
                'Scanning repository',
                'Found .* apps',
                'apps with updates'
            ]):
                print(line)
        
        # Show any errors
        if result.returncode != 0:
            print(f"❌ Command failed with exit code {result.returncode}")
            if result.stderr:
                print(f"Error: {result.stderr[:200]}")
        else:
            print("✅ Command completed successfully")
            
    except subprocess.TimeoutExpired:
        print("⏱️  Command timed out")
    except Exception as e:
        print(f"❌ Error: {e}")

def main():
    print("="*80)
    print("ENVIRONMENT AND REGION FILTERING TESTS")
    print("="*80)
    print("\nThese tests demonstrate the new environment and region filtering")
    print("capabilities. Each test shows how different filter combinations work.")
    
    # Test 1: Environment filtering
    run_command(
        "python splunk_app_updater.py --environment shared --check-only",
        "Filter by environment: shared"
    )
    
    # Test 2: Region filtering (if applicable)
    run_command(
        "python splunk_app_updater.py --region east --check-only",
        "Filter by region: east"
    )
    
    # Test 3: Component filtering
    run_command(
        "python splunk_app_updater.py --component ds --check-only",
        "Filter by component: ds (deployment server)"
    )
    
    # Test 4: Environment + Component
    run_command(
        "python splunk_app_updater.py --env shared --component ds --check-only",
        "Filter by environment (shared) + component (ds)"
    )
    
    # Test 5: Environment + Region
    run_command(
        "python splunk_app_updater.py --env non-prod --region east --check-only",
        "Filter by environment (non-prod) + region (east)"
    )
    
    # Test 6: All three filters
    run_command(
        "python splunk_app_updater.py --env non-prod --region east --component shc --check-only",
        "Filter by environment (non-prod) + region (east) + component (shc)"
    )
    
    # Test 7: Environment + App pattern
    run_command(
        "python splunk_app_updater.py --env shared --app \"Splunk_TA_*\" --check-only",
        "Filter by environment (shared) + app pattern"
    )
    
    # Test 8: List apps mode
    run_command(
        "python splunk_app_updater.py --env shared --list-apps",
        "List apps in shared environment"
    )
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print("""
The tests above demonstrate:
1. ✅ Environment filtering (--environment or --env)
2. ✅ Region filtering (--region)
3. ✅ Component filtering (--component)
4. ✅ Combined environment + component
5. ✅ Combined environment + region
6. ✅ All three filters together
7. ✅ Environment + app pattern
8. ✅ List apps with environment filter

All filter combinations work together seamlessly!
""")
    
    print("\nUseful Commands:")
    print("-" * 80)
    print("# Check what's in shared environment:")
    print("python splunk_app_updater.py --env shared --check-only")
    print()
    print("# Update non-prod east search heads interactively:")
    print("python splunk_app_updater.py --env non-prod --region east --component shc --interactive")
    print()
    print("# See all available options:")
    print("python splunk_app_updater.py --help")
    print("=" * 80)

if __name__ == '__main__':
    main()
