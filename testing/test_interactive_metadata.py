#!/usr/bin/env python3
"""
Test script to demonstrate the enhanced interactive menu with metadata display
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from splunk_app_updater import SplunkApp, select_apps_interactive


def test_interactive_with_metadata():
    """Test interactive selection with environment/region/component metadata"""
    
    # Create mock apps with metadata
    test_apps = [
        SplunkApp(
            name="Splunk_TA_windows",
            local_path=Path("C:/repos/shared/splunk-ds-config/apps/Splunk_TA_windows"),
            current_version="8.8.0",
            splunkbase_id="742",
            deployment_types=["forwarder"],
            latest_version="9.1.2",
            needs_update=True,
            environment="shared",
            region=None,
            component="ds"
        ),
        SplunkApp(
            name="Splunk_TA_nix",
            local_path=Path("C:/repos/nonprod/east/splunk-ds-config/apps/Splunk_TA_nix"),
            current_version="8.7.0",
            splunkbase_id="833",
            deployment_types=["forwarder"],
            latest_version="9.0.1",
            needs_update=True,
            environment="non-prod",
            region="east",
            component="ds"
        ),
        SplunkApp(
            name="Splunk_TA_aws",
            local_path=Path("C:/repos/prod/west/splunk-sh-config/apps/Splunk_TA_aws"),
            current_version="7.2.0",
            splunkbase_id="1876",
            deployment_types=["searchhead"],
            latest_version="7.3.0",
            needs_update=True,
            environment="prod",
            region="west",
            component="shc"
        ),
        SplunkApp(
            name="Splunk_SA_CIM",
            local_path=Path("C:/repos/nonprod/west/splunk-cm-config/apps/Splunk_SA_CIM"),
            current_version="5.0.0",
            splunkbase_id="1621",
            deployment_types=["indexer", "searchhead"],
            latest_version="5.1.0",
            needs_update=True,
            environment="non-prod",
            region="west",
            component="cm"
        ),
    ]
    
    print("\n" + "="*80)
    print("TEST 1: Interactive selection WITHOUT filters")
    print("="*80)
    print("\nThis shows the enhanced display with metadata for each app:")
    input("\nPress Enter to continue...")
    
    selected = select_apps_interactive(test_apps, active_filters=None)
    
    print("\n" + "="*80)
    print("RESULT:")
    if selected:
        print(f"You selected {len(selected)} apps:")
        for app in selected:
            print(f"  - {app.name} ({app.environment}/{app.region}/{app.component})")
    else:
        print("No apps selected")
    
    print("\n\n" + "="*80)
    print("TEST 2: Interactive selection WITH active filters")
    print("="*80)
    print("\nThis shows how filters are displayed at the top:")
    input("\nPress Enter to continue...")
    
    # Simulate filtering to non-prod east
    filtered_apps = [app for app in test_apps 
                     if app.environment == "non-prod" and app.region == "east"]
    
    active_filters = {
        'environment': 'non-prod',
        'region': 'east',
        'component': 'ds'
    }
    
    selected = select_apps_interactive(filtered_apps, active_filters=active_filters)
    
    print("\n" + "="*80)
    print("RESULT:")
    if selected:
        print(f"You selected {len(selected)} apps:")
        for app in selected:
            print(f"  - {app.name}")
    else:
        print("No apps selected")


def test_metadata_display_comparison():
    """Show before/after comparison of metadata display"""
    
    print("\n" + "="*80)
    print("METADATA DISPLAY COMPARISON")
    print("="*80)
    
    print("\n📋 OLD DISPLAY (without metadata):")
    print("-" * 80)
    print("""
  1. Splunk_TA_windows
     Current: v8.8.0 -> New: v9.1.2
     Path: C:/repos/shared/splunk-ds-config/apps/Splunk_TA_windows
""")
    
    print("\u2728 NEW DISPLAY (with metadata):")
    print("-" * 80)
    print("""
Active Filters: Environment: shared | Component: ds

  1. Splunk_TA_windows
     Current: v8.8.0 -> New: v9.1.2
     Env: shared | Component: ds
     Path: C:/repos/shared/splunk-ds-config/apps/Splunk_TA_windows
  
  2. Splunk_TA_nix
     Current: v8.7.0 -> New: v9.0.1
     Env: non-prod | Region: east | Component: ds
     Path: C:/repos/nonprod/east/splunk-ds-config/apps/Splunk_TA_nix
""")
    
    print("\n📊 BENEFITS:")
    print("-" * 80)
    print("✓ See which environment each app belongs to")
    print("✓ See which region (east/west) each app is in")
    print("✓ See which component (ds/shc/cm) each app is part of")
    print("✓ Active filters displayed at the top for context")
    print("✓ Make informed decisions when selecting apps")


def main():
    print("="*80)
    print("INTERACTIVE MENU METADATA DISPLAY TEST")
    print("="*80)
    
    print("\n1. Show metadata display comparison")
    print("2. Test interactive selection without filters")
    print("3. Test interactive selection with filters")
    print("4. Run all tests")
    
    choice = input("\nEnter choice (1-4): ").strip()
    
    if choice == '1':
        test_metadata_display_comparison()
    elif choice == '2':
        test_interactive_with_metadata()
    elif choice == '3':
        # Just the filtered test
        test_apps = [
            SplunkApp(
                name="Splunk_TA_nix",
                local_path=Path("C:/repos/nonprod/east/splunk-ds-config/apps/Splunk_TA_nix"),
                current_version="8.7.0",
                splunkbase_id="833",
                deployment_types=["forwarder"],
                latest_version="9.0.1",
                needs_update=True,
                environment="non-prod",
                region="east",
                component="ds"
            ),
        ]
        active_filters = {'environment': 'non-prod', 'region': 'east', 'component': 'ds'}
        select_apps_interactive(test_apps, active_filters=active_filters)
    elif choice == '4':
        test_metadata_display_comparison()
        input("\nPress Enter to continue to interactive tests...")
        test_interactive_with_metadata()
    else:
        print("Invalid choice")


if __name__ == '__main__':
    main()
