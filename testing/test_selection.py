#!/usr/bin/env python3
"""
Quick test script to verify the new app selection features
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from splunk_app_updater import SplunkApp, select_apps_interactive

def test_interactive_selection():
    """Test the interactive selection function"""
    
    # Create some mock apps for testing
    test_apps = [
        SplunkApp(
            name="Splunk_TA_windows",
            local_path=Path("C:/repos/splunk-ds-config/apps/Splunk_TA_windows"),
            current_version="8.8.0",
            splunkbase_id="742",
            deployment_types=["forwarder"],
            latest_version="9.1.2",
            needs_update=True
        ),
        SplunkApp(
            name="Splunk_TA_nix",
            local_path=Path("C:/repos/splunk-ds-config/apps/Splunk_TA_nix"),
            current_version="8.7.0",
            splunkbase_id="833",
            deployment_types=["forwarder"],
            latest_version="9.0.1",
            needs_update=True
        ),
        SplunkApp(
            name="Splunk_TA_aws",
            local_path=Path("C:/repos/splunk-sh-config/apps/Splunk_TA_aws"),
            current_version="7.2.0",
            splunkbase_id="1876",
            deployment_types=["searchhead"],
            latest_version="7.3.0",
            needs_update=True
        ),
        SplunkApp(
            name="Splunk_SA_CIM",
            local_path=Path("C:/repos/splunk-sh-config/apps/Splunk_SA_CIM"),
            current_version="5.0.0",
            splunkbase_id="1621",
            deployment_types=["searchhead"],
            latest_version="5.1.0",
            needs_update=True
        ),
        SplunkApp(
            name="SA-Utils",
            local_path=Path("C:/repos/splunk-sh-config/apps/SA-Utils"),
            current_version="2.3.0",
            splunkbase_id="1796",
            deployment_types=["searchhead"],
            latest_version="2.4.0",
            needs_update=True
        )
    ]
    
    print("Testing interactive selection feature...")
    print("Try different inputs:")
    print("  - Single: 1")
    print("  - Multiple: 1,3,5")
    print("  - Range: 1-3")
    print("  - Combined: 1,3-5")
    print("  - All: all")
    print("  - Cancel: none or Ctrl+C")
    print("\n")
    
    selected = select_apps_interactive(test_apps)
    
    print("\n" + "="*80)
    print("RESULT:")
    if selected:
        print(f"You selected {len(selected)} apps:")
        for app in selected:
            print(f"  - {app.name}")
    else:
        print("No apps selected")


def test_pattern_matching():
    """Test wildcard pattern matching"""
    import fnmatch
    
    test_apps = [
        "Splunk_TA_windows",
        "Splunk_TA_nix",
        "Splunk_TA_aws",
        "Splunk_SA_CIM",
        "SA-Utils",
        "TA-alert_manager"
    ]
    
    patterns = [
        "Splunk_TA_*",
        "SA-*",
        "*_TA_*",
        "Splunk_*"
    ]
    
    print("\n" + "="*80)
    print("PATTERN MATCHING TEST")
    print("="*80)
    
    for pattern in patterns:
        matches = [app for app in test_apps if fnmatch.fnmatch(app, pattern)]
        print(f"\nPattern: {pattern}")
        print(f"Matches: {matches}")


def test_comma_separated():
    """Test comma-separated parsing"""
    
    test_input = "Splunk_TA_windows,Splunk_TA_nix,SA-Utils"
    
    print("\n" + "="*80)
    print("COMMA-SEPARATED TEST")
    print("="*80)
    
    app_names = [name.strip() for name in test_input.split(',')]
    print(f"\nInput: {test_input}")
    print(f"Parsed: {app_names}")


if __name__ == '__main__':
    print("="*80)
    print("SPLUNK APP UPDATER - SELECTION FEATURE TESTS")
    print("="*80)
    
    # Run tests
    test_pattern_matching()
    test_comma_separated()
    
    print("\n" + "="*80)
    print("INTERACTIVE SELECTION TEST")
    print("="*80)
    print("\nThis test requires user input...")
    
    response = input("Run interactive test? (y/n): ").strip().lower()
    if response == 'y':
        test_interactive_selection()
    else:
        print("Skipped interactive test")
    
    print("\n" + "="*80)
    print("All tests completed!")
    print("="*80)
