#!/usr/bin/env python3
"""
Example: GitLab Integration Features

This demonstrates the new GitLab tracking capabilities including:
- Remote branch tracking
- GitLab MR URL generation
- Test vs production update distinction
- Push status tracking
"""

from pathlib import Path
from splunk_updater.update_tracker import UpdateTracker
from splunk_updater.git_manager import GitBranchManager


def main():
    """Demonstrate GitLab integration features"""
    
    tracker = UpdateTracker()
    
    print("=" * 80)
    print("GITLAB INTEGRATION EXAMPLES")
    print("=" * 80)
    print()
    
    # Example 1: Check remote status
    print("EXAMPLE 1: Check Remote Status")
    print("-" * 80)
    
    pending = tracker.get_all_pending()
    if pending:
        for update in pending[:2]:  # Show first 2
            repo_path = Path(update['repo_path'])
            branch_name = update['branch_name']
            
            print(f"\nBranch: {branch_name}")
            print(f"  Repository: {repo_path}")
            
            git_manager = GitBranchManager(repo_path)
            
            # Check if pushed
            is_pushed = update.get('is_pushed', False)
            print(f"  Pushed to remote: {'✅ Yes' if is_pushed else '⏳ No'}")
            
            # Get remote info
            remote_info = git_manager.get_remote_info()
            if remote_info:
                print(f"  Remote: {remote_info['name']} ({remote_info['url']})")
            
            # Generate MR URL
            mr_url = git_manager.generate_gitlab_mr_url(
                branch_name,
                app_name=update.get('app_name'),
                old_version=update.get('old_version'),
                new_version=update.get('new_version'),
                environment=update.get('environment')
            )
            if mr_url:
                print(f"  GitLab MR URL: {mr_url}")
    else:
        print("No pending updates found.")
    
    print()
    
    # Example 2: Filter by test/production
    print("\nEXAMPLE 2: Filter Test vs Production Updates")
    print("-" * 80)
    
    all_updates = tracker.get_all_pending(include_test=True)
    prod_updates = tracker.get_all_pending(include_test=False)
    test_updates = tracker.get_test_updates()
    
    print(f"Total pending: {len(all_updates)}")
    print(f"  Production: {len(prod_updates)}")
    print(f"  Test: {len(test_updates)}")
    
    if test_updates:
        print("\nTest updates:")
        for update in test_updates:
            print(f"  🧪 {update['app_name']} - {update['branch_name']}")
    
    print()
    
    # Example 3: Find updates needing attention
    print("\nEXAMPLE 3: Updates Needing Attention")
    print("-" * 80)
    
    unpushed = tracker.get_unpushed_updates()
    no_mr = tracker.get_updates_without_mr()
    
    print(f"Unpushed branches: {len(unpushed)}")
    if unpushed:
        for update in unpushed[:3]:  # Show first 3
            print(f"  📤 {update['app_name']} - {update['branch_name']}")
    
    print(f"\nWithout MR URL: {len(no_mr)}")
    if no_mr:
        for update in no_mr[:3]:  # Show first 3
            print(f"  📝 {update['app_name']} - {update['branch_name']}")
    
    print()
    
    # Example 4: Programmatic MR URL generation
    print("\nEXAMPLE 4: Generate GitLab MR URLs")
    print("-" * 80)
    
    if pending:
        for update in pending[:2]:  # Show first 2
            repo_path = Path(update['repo_path'])
            branch_name = update['branch_name']
            
            git_manager = GitBranchManager(repo_path)
            mr_url = git_manager.generate_gitlab_mr_url(
                branch_name,
                target_branch='main',
                app_name=update.get('app_name'),
                old_version=update.get('old_version'),
                new_version=update.get('new_version'),
                environment=update.get('environment')
            )
            
            if mr_url:
                print(f"\n{update['app_name']}:")
                print(f"  Branch: {branch_name}")
                print(f"  Create MR: {mr_url}")
                
                # You could set this in tracking
                # tracker.set_gitlab_mr_url(branch_name, mr_url)
    
    print()
    
    # Example 5: Workflow demonstration
    print("\nEXAMPLE 5: Complete Workflow")
    print("-" * 80)
    print("""
Typical workflow with GitLab integration:

1. Run updates (optionally mark as test):
   python splunk_app_updater.py --test-mode

2. Review pending updates with remote status:
   python splunk_app_updater.py --show-pending

3. View diffs locally:
   python splunk_app_updater.py --show-diffs --full-diff

4. Push branches to remote:
   python splunk_app_updater.py --push-branches

5. After pushing, use the displayed MR URLs to create merge requests

6. After merging, clean up:
   python splunk_app_updater.py --cleanup-branches

7. Remove test updates when done testing:
   python splunk_app_updater.py --clear-test-updates
""")
    
    print("=" * 80)
    print("Examples complete!")
    print()


if __name__ == '__main__':
    main()
