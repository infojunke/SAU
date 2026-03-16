#!/usr/bin/env python3
"""
Test version matching and selection workflow
"""

from pathlib import Path
from splunk_updater.models import SplunkApp
from splunk_updater.version_selector import select_version_interactive

def test_version_selection():
    """Test interactive version selection"""
    print("Testing Version Selection Workflow")
    print("=" * 80)
    
    # Create test app
    test_app = SplunkApp(
        name="Splunk_TA_aws",
        local_path=Path("C:/test/apps/Splunk_TA_aws"),
        current_version="7.3.0",
        splunkbase_id="1876",
        deployment_types=["searchhead"],
        environment="shared",
        component="shc"
    )
    
    # Simulate available versions
    available_versions = [
        "8.0.0",
        "7.4.0",
        "7.3.1",
        "7.3.0",
        "7.2.0",
        "7.1.0",
        "7.0.0",
        "6.5.0",
        "6.4.0",
        "6.3.0"
    ]
    
    # Test case 1: Non-prod version not found
    print("\nTest Case 1: Non-prod version (7.3.5) not found on Splunkbase")
    print("-" * 80)
    nonprod_version = "7.3.5"
    
    selected = select_version_interactive(test_app, available_versions, nonprod_version)
    
    if selected:
        print(f"\n✓ User selected version: {selected}")
        test_app.latest_version = selected
    else:
        print("\n✗ User skipped the app")
    
    print("\n" + "=" * 80)
    print("Test completed!")

if __name__ == '__main__':
    test_version_selection()
