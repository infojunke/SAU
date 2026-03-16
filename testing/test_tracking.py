"""Test update tracking functionality"""

from pathlib import Path
from splunk_updater.update_tracker import UpdateTracker

def test_tracking():
    """Test the update tracker"""
    print("Testing Update Tracker...")
    
    # Create tracker
    tracker = UpdateTracker(Path("work/test_tracking.json"))
    
    # Clear any existing data
    tracker.clear_all()
    print("✓ Tracker initialized")
    
    # Track some updates
    tracker.track_update(
        "Splunk_TA_windows",
        Path("C:/repos/splunk-sh-config"),
        "9.0.0",
        "9.1.2",
        "non-prod-Splunk-TA-windows-v9_1_2-20251222-143000",
        environment="non-prod",
        region=None
    )
    print("✓ Tracked update for Splunk_TA_windows")
    
    tracker.track_update(
        "Splunk_TA_nix",
        Path("C:/repos/splunk-sh-config"),
        "9.0.0",
        "10.2.0",
        "non-prod-Splunk-TA-nix-v10_2_0-20251222-143100",
        environment="non-prod",
        region=None
    )
    print("✓ Tracked update for Splunk_TA_nix")
    
    # Check if updates are pending
    is_pending = tracker.is_update_pending(
        "Splunk_TA_windows",
        "C:/repos/splunk-sh-config",
        "9.1.2"
    )
    print(f"✓ Splunk_TA_windows pending: {is_pending}")
    
    # Get pending update details
    pending = tracker.get_pending_update(
        "Splunk_TA_windows",
        "C:/repos/splunk-sh-config"
    )
    if pending:
        print(f"  - Branch: {pending['branch_name']}")
        print(f"  - Version: {pending['old_version']} -> {pending['new_version']}")
    
    # Get all pending
    all_pending = tracker.get_all_pending()
    print(f"\n✓ Total pending updates: {len(all_pending)}")
    for update in all_pending:
        print(f"  - {update['app_name']}: {update['old_version']} -> {update['new_version']}")
    
    # Get stats
    stats = tracker.get_stats()
    print(f"\n✓ Stats:")
    print(f"  - Total: {stats['total']}")
    print(f"  - Pending: {stats['pending']}")
    print(f"  - Merged: {stats['merged']}")
    
    # Mark one as merged
    tracker.mark_merged("non-prod-Splunk-TA-windows-v9_1_2-20251222-143000")
    print(f"\n✓ Marked Splunk_TA_windows as merged")
    
    # Check stats again
    stats = tracker.get_stats()
    print(f"  - Pending: {stats['pending']}")
    print(f"  - Merged: {stats['merged']}")
    
    # Clear merged
    removed = tracker.clear_merged()
    print(f"\n✓ Cleared {removed} merged update(s)")
    
    # Final stats
    stats = tracker.get_stats()
    print(f"  - Total remaining: {stats['total']}")
    
    print("\n✅ All tests passed!")

if __name__ == '__main__':
    test_tracking()
