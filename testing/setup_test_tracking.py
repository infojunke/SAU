"""Setup test tracking with real branches"""

from pathlib import Path
from splunk_updater.update_tracker import UpdateTracker

def setup_test_tracking():
    """Create test tracking with real branches that exist"""
    tracker = UpdateTracker()
    tracker.clear_all()
    
    # Track the actual branches that exist in the repo
    tracker.track_update(
        "Splunk_TA_aws",
        Path("C:/repos/splunk-sh-config"),
        "8.0.0",
        "8.1.0",
        "non-prod-Splunk-TA-aws-v8_1_0-20251222-131122",
        environment="non-prod",
        region=None
    )
    
    tracker.track_update(
        "Splunk_TA_nix",
        Path("C:/repos/splunk-sh-config"),
        "9.0.0",
        "10.2.0",
        "non-prod-Splunk-TA-nix-v10_2_0-20251222-131114",
        environment="non-prod",
        region=None
    )
    
    tracker.track_update(
        "Splunk_TA_windows",
        Path("C:/repos/splunk-sh-config"),
        "9.0.0",
        "9.1.2",
        "non-prod-east-Splunk-TA-windows-v9_1_2-20251222-103636",
        environment="non-prod",
        region="east"
    )
    
    print("✓ Tracking setup complete!")
    print("\nTracked branches:")
    for update in tracker.get_all_pending():
        print(f"  - {update['branch_name']}")
    
    print(f"\nRun: python main.py --show-pending")
    print(f"Then: python main.py --cleanup-branches")

if __name__ == '__main__':
    setup_test_tracking()
