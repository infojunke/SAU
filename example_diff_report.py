#!/usr/bin/env python3
"""
Example: Generate diff reports for pending updates

This demonstrates how to use the UpdateTracker to generate diff reports
showing all changes in pending update branches.
"""

from pathlib import Path
from splunk_updater.update_tracker import UpdateTracker


def main():
    """Generate and display diff reports for pending updates"""
    
    # Initialize tracker
    tracker = UpdateTracker()
    
    print("=" * 80)
    print("DIFF REPORT EXAMPLE")
    print("=" * 80)
    print()
    
    # Check if there are pending updates
    pending = tracker.get_all_pending()
    
    if not pending:
        print("No pending updates found.")
        print("\nTo create some test updates, run:")
        print("  python splunk_app_updater.py --check-only")
        print("  python splunk_app_updater.py  # and select some apps")
        return
    
    print(f"Found {len(pending)} pending update(s)")
    print()
    
    # Example 1: Generate summary report (files changed only, no full diff)
    print("EXAMPLE 1: Summary Report (files changed)")
    print("-" * 80)
    summary_report = tracker.generate_diff_report(base_branch='main', include_full_diff=False)
    print(summary_report)
    print()
    
    # Example 2: Generate full diff report
    print("\nEXAMPLE 2: Full Diff Report")
    print("-" * 80)
    full_report = tracker.generate_diff_report(base_branch='main', include_full_diff=True)
    
    # Save to file
    output_file = Path("work/example_diff_report.txt")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(full_report)
    
    print(f"Full diff report saved to: {output_file}")
    print()
    
    # Example 3: Get branch details programmatically
    print("\nEXAMPLE 3: Access Branch Data Programmatically")
    print("-" * 80)
    branches = tracker.get_pending_branches_with_diffs()
    
    for branch_name, branch_info in branches.items():
        print(f"\nBranch: {branch_name}")
        print(f"  Repository: {branch_info['repo_path']}")
        print(f"  Files changed: {len(branch_info['files_changed'])}")
        print(f"  Updates: {len(branch_info['updates'])}")
        
        for update in branch_info['updates']:
            print(f"    - {update['app_name']}: {update['old_version']} -> {update['new_version']}")
        
        if branch_info['files_changed']:
            print(f"  Changed files:")
            for file_path in branch_info['files_changed'][:5]:  # Show first 5
                print(f"    - {file_path}")
            if len(branch_info['files_changed']) > 5:
                print(f"    ... and {len(branch_info['files_changed']) - 5} more")
    
    print()
    print("=" * 80)
    print("Examples complete!")
    print()
    print("To use from command line:")
    print("  python splunk_app_updater.py --show-diffs")
    print("  python splunk_app_updater.py --show-diffs --full-diff")
    print("  python splunk_app_updater.py --show-diffs --full-diff -o my_report.txt")


if __name__ == '__main__':
    main()
