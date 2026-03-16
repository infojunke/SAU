"""Command-line interface for Splunk app updater"""

import argparse
import fnmatch
import logging
import sys
import time
from datetime import datetime
from typing import Optional, List

from .interactive import select_apps_interactive
from .version_selector import prompt_version_selection_for_apps
from .updater import SplunkAppUpdater
from .update_tracker import UpdateTracker
from .utils import setup_logging, find_git_root
from .enums import Component
from .csv_importer import CSVAppImporter

logger = logging.getLogger(__name__)


def main():
    """Main entry point"""
    args = _parse_arguments()
    setup_logging(debug=args.debug)
    
    # Handle tracking commands first
    if args.show_pending:
        _show_pending_updates()
        return
    
    if args.clear_tracking:
        _clear_tracking()
        return
    
    if args.clear_merged:
        _clear_merged_updates()
        return
    
    if args.cleanup_branches:
        _cleanup_pending_branches()
        return
    
    if args.show_diffs:
        _show_pending_diffs(args.base_branch, args.full_diff, args.output)
        return
    
    if args.push_branches:
        _push_pending_branches()
        return
    
    if args.clear_test_updates:
        _clear_test_updates()
        return
    
    if args.sync_tracking:
        _sync_tracking_with_gitlab()
        return
    
    if args.check_compatibility:
        # Override remote_branch to None if --local flag is set
        remote_branch = None if getattr(args, 'use_local', False) else args.remote_branch
        _check_app_compatibility(args.check_compatibility, args.app, remote_branch, config_path=args.config)
        return
    
    if args.update_incompatible:
        # Override remote_branch to None if --local flag is set
        remote_branch = None if getattr(args, 'use_local', False) else args.remote_branch
        _update_incompatible_apps(args)
        return
    
    # Handle CSV import
    csv_app_names = None
    if args.import_csv:
        csv_app_names = _import_from_csv(args.import_csv, args.export_csv_mapping)
        if not csv_app_names and not args.export_csv_mapping:
            return
    
    try:
        updater = SplunkAppUpdater(args.config, skip_tracking=args.force, is_test=args.test_mode)
        component_filter = _normalize_component_filter(args.component)
        
        # Pull repos if requested
        if args.pull:
            _pull_repos(updater)
        
        _log_filters(component_filter, args.environment, args.region)
        
        # Override remote_branch to None if --local flag is set
        remote_branch = None if getattr(args, 'use_local', False) else args.remote_branch
        apps = _discover_apps(updater, component_filter, args.environment, args.region, remote_branch)
        
        if args.list_apps:
            _list_apps_mode(apps)
            return
        
        apps_with_updates = _check_for_updates(updater, apps)
        
        if not apps_with_updates:
            logger.info("No updates available")
            return
        
        apps_with_updates = _filter_apps_by_name(apps_with_updates, args.app)
        
        # Filter by CSV import list if provided
        if csv_app_names:
            apps_with_updates = _filter_apps_by_csv(apps_with_updates, csv_app_names)
        
        if args.check_only:
            _check_only_mode(apps_with_updates)
            return
        
        # Interactive selection (including version selection) before dry-run
        apps_with_updates = _select_apps(args, apps_with_updates, component_filter)
        
        if not apps_with_updates:
            logger.info("No apps selected for update")
            return
        
        if args.dry_run:
            _dry_run_mode(apps_with_updates, args.no_branch)
            return
        
        _perform_updates(updater, apps, apps_with_updates, args.no_branch)
        
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


def _parse_arguments():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Splunk App Updater for GitLab Repositories'
    )
    parser.add_argument(
        '--config',
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )
    parser.add_argument(
        '--check-only',
        action='store_true',
        help='Only check for updates, do not download or update'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simulate updates without making any changes (shows what would be updated)'
    )
    parser.add_argument(
        '--no-branch',
        action='store_true',
        help='Do not create Git branches for updates'
    )
    parser.add_argument(
        '--app',
        help='Update only specified app (by name)'
    )
    parser.add_argument(
        '--list-apps',
        action='store_true',
        help='List all discovered apps with their Splunkbase IDs'
    )
    parser.add_argument(
        '--component',
        choices=['ds', 'shc', 'cm', 'deployment-server', 'search-head', 'cluster-manager'],
        help='Update only apps in specific component (ds/deployment-server, shc/search-head, cm/cluster-manager)'
    )
    parser.add_argument(
        '--environment',
        '--env',
        dest='environment',
        help='Filter by environment (e.g., nonprod, shared, nonprod,shared, or prod). Use comma-separated values for multiple environments.'
    )
    parser.add_argument(
        '--region',
        help='Filter by region (e.g., east, west)'
    )
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='Force interactive selection mode (default unless --app or --no-interactive used)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging (shows all log messages)'
    )
    parser.add_argument(
        '--remote',
        '--remote-branch',
        dest='remote_branch',
        nargs='?',
        const='auto',
        default='auto',
        metavar='BRANCH',
        help='Read from remote branch (default: auto-detect main/master). Use --remote-branch origin/main to specify, or --local to use working directory instead'
    )
    parser.add_argument(
        '--local',
        dest='use_local',
        action='store_true',
        help='Read from local working directory instead of remote branch (ignores pending MRs)'
    )
    parser.add_argument(
        '--pull',
        action='store_true',
        help='Pull latest changes from remote before discovering apps (runs git pull on each repo)'
    )
    parser.add_argument(
        '--no-interactive',
        action='store_true',
        help='Disable interactive mode and update all matching apps automatically'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force update even if already tracked as pending'
    )
    parser.add_argument(
        '--show-pending',
        action='store_true',
        help='Show all pending updates and exit'
    )
    parser.add_argument(
        '--clear-tracking',
        action='store_true',
        help='Clear all update tracking data and exit'
    )
    parser.add_argument(
        '--clear-merged',
        action='store_true',
        help='Remove merged updates from tracking and exit'
    )
    parser.add_argument(
        '--cleanup-branches',
        action='store_true',
        help='Delete local pending branches and remove from tracking'
    )
    parser.add_argument(
        '--show-diffs',
        action='store_true',
        help='Show diffs for all pending update branches organized by branch'
    )
    parser.add_argument(
        '--base-branch',
        default='main',
        help='Base branch to compare against for diffs (default: main)'
    )
    parser.add_argument(
        '--full-diff',
        action='store_true',
        help='Include full diff output in the report (default: summary only)'
    )
    parser.add_argument(
        '--output',
        '-o',
        help='Save diff report to specified file'
    )
    parser.add_argument(
        '--push-branches',
        action='store_true',
        help='Push all unpushed pending branches to remote'
    )
    parser.add_argument(        '--import-csv',
        help='Import app list from CSV file and update only those apps'
    )
    parser.add_argument(
        '--export-csv-mapping',
        action='store_true',
        help='Export Splunkbase ID mapping from imported CSV (use with --import-csv)'
    )
    parser.add_argument(        '--test-mode',
        action='store_true',
        help='Mark updates as test (helps distinguish from production updates)'
    )
    parser.add_argument(
        '--clear-test-updates',
        action='store_true',
        help='Remove all test updates from tracking'
    )
    parser.add_argument(
        '--sync-tracking',
        action='store_true',
        help='Sync tracking file with GitLab to detect merged branches'
    )
    parser.add_argument(
        '--check-compatibility',
        metavar='SPLUNK_VERSION',
        help='Check app compatibility with specified Splunk version (e.g., 9.0.0) and show compatible versions'
    )
    parser.add_argument(
        '--update-incompatible',
        metavar='SPLUNK_VERSION',
        help='Update only apps incompatible with specified Splunk version (e.g., 9.4.7). Checks current version compatibility and updates to compatible version if available.'
    )
    return parser.parse_args()


def _normalize_component_filter(component: str) -> str:
    """Normalize component filter using the Component enum"""
    if not component:
        return None
    try:
        return str(Component.from_string(component))
    except ValueError:
        logger.warning(f"Unknown component type '{component}' — component filter ignored")
        return None


def _pull_repos(updater):
    """Pull latest changes from remote for all configured repos"""
    import subprocess
    from pathlib import Path
    
    logger.info("Pulling latest changes from remote repositories...")
    
    for repo_config in updater.config_manager.get_gitlab_repos():
        repo_path = Path(repo_config['path'])
        
        # Find git root
        git_root = find_git_root(repo_path)
        if not git_root:
            logger.warning(f"Skipping {repo_path} - not a git repository")
            continue
        
        try:
            logger.info(f"Pulling {git_root}...")
            result = subprocess.run(
                ['git', 'pull'],
                cwd=git_root,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                output = result.stdout.strip()
                if "Already up to date" in output or "Already up-to-date" in output:
                    logger.info(f"  [OK] Already up to date")
                else:
                    logger.info(f"  [OK] Updated: {output.split(chr(10))[0]}")
            else:
                logger.error(f"  [FAILED] {result.stderr.strip()}")
                
        except subprocess.TimeoutExpired:
            logger.error(f"  [FAILED] Timeout pulling {git_root}")
        except Exception as e:
            logger.error(f"  [FAILED] Error pulling {git_root}: {e}")
    
    logger.info("")


def _log_filters(component_filter, environment_filter, region_filter):
    """Log active filters"""
    if component_filter:
        logger.info(f"Filtering to component: {component_filter}")
    if environment_filter:
        envs = environment_filter.split(',') if ',' in environment_filter else [environment_filter]
        logger.info(f"Filtering to environment(s): {', '.join(envs)}")
    if region_filter:
        logger.info(f"Filtering to region: {region_filter}")


def _discover_apps(updater, component_filter, environment_filter, region_filter, remote_branch=None):
    """Discover apps"""
    if remote_branch:
        print(f"\n🔍 Discovering Splunk apps from remote branch: {remote_branch}")
        logger.info(f"Discovering Splunk apps from remote branch: {remote_branch}")
    else:
        print("\n🔍 Scanning repositories for Splunk apps...")
        logger.info("Discovering Splunk apps in GitLab repositories...")
    
    import time
    start_time = time.time()
    
    apps = updater.discover_apps(
        component_filter=component_filter,
        environment_filter=environment_filter,
        region_filter=region_filter,
        remote_branch=remote_branch
    )
    
    total_time = time.time() - start_time
    print(f"\n✓ Found {len(apps)} apps in {total_time:.1f}s\n")
    logger.info(f"Found {len(apps)} apps")
    return apps


def _list_apps_mode(apps):
    """List apps mode"""
    print("\n" + "=" * 80)
    print("DISCOVERED SPLUNK APPS")
    print("=" * 80)
    print(f"\nTotal apps found: {len(apps)}\n")
    
    apps_with_id = [app for app in apps if app.splunkbase_id]
    apps_without_id = [app for app in apps if not app.splunkbase_id]
    
    if apps_with_id:
        _print_apps_with_id(apps_with_id)
    
    if apps_without_id:
        _print_apps_without_id(apps_without_id)
    
    _print_apps_summary(apps_with_id, apps_without_id)


def _print_apps_with_id(apps):
    """Print apps with Splunkbase ID"""
    print("Apps WITH Splunkbase ID:")
    print("-" * 80)
    for app in sorted(apps, key=lambda x: x.name):
        print(f"  {app.name}:")
        print(f"    Version: {app.current_version}")
        print(f"    Splunkbase ID: {app.splunkbase_id}")
        print(f"    Path: {app.local_path}")
        print()


def _print_apps_without_id(apps):
    """Print apps without Splunkbase ID"""
    print("\nApps WITHOUT Splunkbase ID (add to config.yaml):")
    print("-" * 80)
    for app in sorted(apps, key=lambda x: x.name):
        print(f"  {app.name}:")
        print(f"    Version: {app.current_version}")
        print(f"    Path: {app.local_path}")
        print(f"    Add to config.yaml:")
        print(f"      {app.name}: \"YOUR_SPLUNKBASE_ID\"")
        print()


def _print_apps_summary(apps_with_id, apps_without_id):
    """Print apps summary"""
    print("=" * 80)
    print(f"\nApps with ID: {len(apps_with_id)}")
    print(f"Apps without ID: {len(apps_without_id)}")
    print("\nTo find Splunkbase IDs, visit: https://splunkbase.splunk.com/")


def _check_for_updates(updater, apps):
    """Check for updates"""
    logger.info("Checking for updates on Splunkbase...")
    return updater.check_for_updates(apps)


def _filter_apps_by_name(apps, app_filter):
    """Filter apps by name"""
    if not app_filter:
        return apps
    
    if ',' in app_filter:
        app_names = [name.strip() for name in app_filter.split(',')]
        apps = [app for app in apps if app.name in app_names]
    elif '*' in app_filter or '?' in app_filter:
        apps = [app for app in apps if fnmatch.fnmatch(app.name, app_filter)]
    else:
        apps = [app for app in apps if app.name == app_filter]
    
    if not apps:
        logger.error(f"No apps matching '{app_filter}' found or need update")
    
    return apps


def _check_only_mode(apps):
    """Check-only mode"""
    logger.info("Check-only mode: Not performing updates")
    for app in apps:
        # Build context info: component/environment/region
        context_parts = app.metadata_parts(labeled=False)
        context = f" [{'/'.join(context_parts)}]" if context_parts else ""
        logger.info(f"  {app.name}: {app.current_version} -> {app.latest_version}{context}")


def _dry_run_mode(apps, no_branch):
    """Dry-run mode - show what would be updated without making changes"""
    print("\n" + "=" * 80)
    print("DRY RUN MODE - No changes will be made")
    print("=" * 80)
    print(f"\nWould update {len(apps)} app(s):\n")
    
    for app in apps:
        print(f"  • {app.instance_id}")
        print(f"    Version: {app.current_version} -> {app.latest_version}")
        
        if app.environment:
            print(f"    Environment: {app.environment}")
        if app.region:
            print(f"    Region: {app.region}")
        if app.component:
            print(f"    Component: {app.component}")
        
        print(f"    Path: {app.local_path}")
        
        if not no_branch:
            # Generate what the branch name would be
            from .git_manager import GitBranchManager
            repo_path = app.repo_root if app.repo_root else app.local_path.parent
            git_manager = GitBranchManager(repo_path)
            branch_name = git_manager._build_branch_name(app.name, app.latest_version, app.environment, app.region, app.component)
            print(f"    Would create branch: {branch_name}")
        
        print()
    
    print("=" * 80)
    print("DRY RUN COMPLETE - No actual changes were made")
    print("To perform these updates, run without --dry-run")
    print("=" * 80)



def _open_mr_urls_in_browser(apps, updater):
    """Open GitLab MR URLs in default browser for successfully updated apps"""
    import webbrowser
    from pathlib import Path
    from .git_manager import GitBranchManager
    
    tracker = updater.tracker
    opened_urls = set()
    
    print("\n" + "=" * 80)
    print("OPENING MERGE REQUESTS IN BROWSER")
    print("=" * 80)
    
    for app in apps:
        # Get the pending update from tracker
        repo_path = Path(app.repo_root if app.repo_root else app.local_path.parent)
        pending = tracker.get_pending_update(app.name, repo_path, app.local_path)
        
        if not pending:
            continue
        
        branch_name = pending.get('branch_name')
        if not branch_name:
            continue
        
        # Generate MR URL
        git_manager = GitBranchManager(repo_path)
        mr_url = git_manager.generate_gitlab_mr_url(
            branch_name,
            app_name=app.name,
            old_version=app.current_version,
            new_version=app.latest_version,
            environment=app.environment
        )
        
        if mr_url and mr_url not in opened_urls:
            print(f"Opening MR for {app.name}...")
            print(f"  {mr_url}")
            try:
                webbrowser.open_new_tab(mr_url)
                opened_urls.add(mr_url)
            except Exception as e:
                logger.warning(f"Could not open browser for {app.name}: {e}")
    
    if opened_urls:
        print(f"\n[OK] Opened {len(opened_urls)} merge request(s) in browser")
    else:
        print("\nNo merge requests to open")


def _select_apps(args, apps_with_updates, component_filter):
    """Select apps to update"""
    use_interactive = args.interactive or (not args.app and not args.no_interactive)
    
    if use_interactive:
        logger.info("Starting interactive selection mode...")
        active_filters = {}
        if component_filter:
            active_filters['component'] = component_filter
        if args.environment:
            active_filters['environment'] = args.environment
        if args.region:
            active_filters['region'] = args.region
        
        apps_with_updates = select_apps_interactive(apps_with_updates, active_filters)
        
        # Check if any apps need version selection (shared/prod without matching non-prod version)
        if apps_with_updates:
            apps_needing_version = [app for app in apps_with_updates if getattr(app, '_needs_version_selection', False)]
            if apps_needing_version:
                logger.info(f"\n{len(apps_needing_version)} app(s) need version selection...")
                apps_with_updates = prompt_version_selection_for_apps(apps_with_updates)
    
    return apps_with_updates


def _perform_updates(updater, apps, apps_with_updates, no_branch):
    """Perform app updates"""
    import webbrowser
    
    logger.info("Starting app updates...")
    results = updater.update_all_apps(apps_with_updates, create_branches=not no_branch)
    
    # Generate and display report
    report = updater.generate_report(apps, results)
    print("\n" + report)
    
    # Write report to file
    report_file = updater.work_dir / f"update_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, 'w') as f:
        f.write(report)
    logger.info(f"Report saved to {report_file}")
    
    # Generate and display diff summary for branches created
    if not no_branch:
        successful_updates = [app for app in apps_with_updates if results.get(app.name, False)]
        if successful_updates:
            print("\n" + "=" * 80)
            print("DIFF SUMMARY (Changes by Branch)")
            print("=" * 80)
            print("\nTo view full diffs for all pending branches, run:")
            print("  python -m splunk_updater.cli --show-diffs")
            print("  python -m splunk_updater.cli --show-diffs --full-diff  # for complete diffs")
            print("  python -m splunk_updater.cli --show-diffs --full-diff -o my_diff.txt  # save to file")
            
            # Open MR URLs in browser
            _open_mr_urls_in_browser(successful_updates, updater)


def _show_pending_updates():
    """Show all pending updates"""
    tracker = UpdateTracker()
    pending = tracker.get_all_pending()
    
    if not pending:
        print("\nNo pending updates tracked.")
        return
    
    # Separate test and production updates
    prod_updates = [u for u in pending if not u.get('is_test', False)]
    test_updates = [u for u in pending if u.get('is_test', False)]
    
    if prod_updates:
        print(f"\n{len(prod_updates)} Production Update(s):")
        print("=" * 80)
        _print_update_list(prod_updates)
    
    if test_updates:
        print(f"\n{len(test_updates)} Test Update(s):")
        print("=" * 80)
        _print_update_list(test_updates)
    
    stats = tracker.get_stats()
    print(f"\nTotal tracked: {stats['total']} (Pending: {stats['pending']}, Merged: {stats['merged']})")
    
    # Show unpushed and MR status
    unpushed = tracker.get_unpushed_updates()
    no_mr = tracker.get_updates_without_mr()
    
    if unpushed:
        print(f"\n{len(unpushed)} update(s) not yet pushed to remote")
    if no_mr:
        print(f"{len(no_mr)} update(s) without GitLab MR URL")


def _print_update_list(updates):
    """Print a formatted list of updates"""
    for update in updates:
        env_region = ""
        if update.get('environment'):
            env_region += f" [{update['environment']}"
            if update.get('region'):
                env_region += f"/{update['region']}"
            env_region += "]"
        
        test_marker = " [TEST]" if update.get('is_test') else ""
        push_marker = " [Pushed]" if update.get('is_pushed') else " [Local only]"
        
        print(f"\nApp: {update['app_name']}{env_region}{test_marker}")
        print(f"  Version: {update['old_version']} -> {update['new_version']}")
        print(f"  Branch: {update['branch_name']} {push_marker}")
        
        if update.get('remote_branch'):
            print(f"  Remote: {update['remote_branch']}")
        
        if update.get('gitlab_mr_url'):
            print(f"  MR: {update['gitlab_mr_url']}")
        elif update.get('is_pushed'):
            # Generate MR URL if pushed but not set
            from .git_manager import mr_url_from_update
            mr_url = mr_url_from_update(update)
            if mr_url:
                print(f"  Create MR: {mr_url}")
        
        print(f"  Repo: {update['repo_path']}")
        print(f"  Date: {update['timestamp']}")


def _clear_tracking():
    """Clear all tracking data"""
    tracker = UpdateTracker()
    tracker.clear_all()
    print("\nAll tracking data cleared.")


def _clear_merged_updates():
    """Remove merged updates from tracking"""
    tracker = UpdateTracker()
    removed = tracker.clear_merged()
    print(f"\nRemoved {removed} merged update(s) from tracking.")


def _clear_test_updates():
    """Remove all test updates from tracking"""
    tracker = UpdateTracker()
    test_updates = tracker.get_test_updates()
    
    if not test_updates:
        print("\nNo test updates found.")
        return
    
    print(f"\n🧪 Found {len(test_updates)} test update(s):")
    for update in test_updates:
        print(f"  - {update['app_name']} ({update['branch_name']})")
    
    confirm = input("\nRemove all test updates? (yes/no): ").strip().lower()
    if confirm in ['yes', 'y']:
        for update in test_updates:
            tracker.remove_branch(update['branch_name'])
        print(f"\n✅ Removed {len(test_updates)} test update(s).")
    else:
        print("\nCancelled.")


def _push_pending_branches():
    """Push all unpushed pending branches to remote"""
    from pathlib import Path
    from .git_manager import GitBranchManager
    
    tracker = UpdateTracker()
    unpushed = tracker.get_unpushed_updates()
    
    if not unpushed:
        print("\n✅ All pending branches are already pushed to remote.")
        return
    
    print(f"\n📤 Found {len(unpushed)} unpushed branch(es):")
    print("=" * 80)
    
    for update in unpushed:
        print(f"\nApp: {update['app_name']}")
        print(f"  Branch: {update['branch_name']}")
        print(f"  Repo: {update['repo_path']}")
    
    print("\n" + "=" * 80)
    confirm = input("\nPush all branches to remote? (yes/no): ").strip().lower()
    
    if confirm not in ['yes', 'y']:
        print("\nCancelled.")
        return
    
    pushed_count = 0
    failed_count = 0
    
    for update in unpushed:
        branch_name = update['branch_name']
        repo_path = Path(update['repo_path'])
        
        print(f"\n📤 Pushing {branch_name}...")
        
        if not repo_path.exists():
            print(f"  ❌ Repository not found: {repo_path}")
            failed_count += 1
            continue
        
        git_manager = GitBranchManager(repo_path)
        
        # Push the branch
        if git_manager.push_branch(branch_name):
            # Update tracking
            remote_branch = git_manager.get_remote_branch_name(branch_name)
            tracker.mark_pushed(branch_name, remote_branch)
            
            # Show GitLab MR URL
            mr_url = git_manager.generate_gitlab_mr_url(
                branch_name,
                app_name=update.get('app_name'),
                old_version=update.get('old_version'),
                new_version=update.get('new_version'),
                environment=update.get('environment')
            )
            if mr_url:
                print(f"  ✅ Pushed! Create MR: {mr_url}")
            else:
                print(f"  ✅ Pushed to remote")
            
            pushed_count += 1
        else:
            print(f"  ❌ Failed to push")
            failed_count += 1
    
    print("\n" + "=" * 80)
    print(f"✅ Pushed: {pushed_count}")
    if failed_count > 0:
        print(f"❌ Failed: {failed_count}")


def _show_pending_diffs(base_branch: str = 'main', full_diff: bool = False, output_file: str = None):
    """Show diffs for all pending update branches organized by branch"""
    from pathlib import Path
    
    tracker = UpdateTracker()
    
    # Generate the diff report
    report = tracker.generate_diff_report(base_branch=base_branch, include_full_diff=full_diff)
    
    # Display to console
    print("\n" + report)
    
    # Save to file if requested
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n✅ Diff report saved to: {output_path}")
    else:
        # Auto-save to work directory with timestamp
        work_dir = Path("work")
        work_dir.mkdir(parents=True, exist_ok=True)
        auto_file = work_dir / f"diff_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(auto_file, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n📄 Diff report auto-saved to: {auto_file}")


def _sync_tracking_with_gitlab():
    """Sync tracking file with GitLab to detect merged branches"""
    from .gitlab_client import GitLabClient
    from pathlib import Path
    
    tracker = UpdateTracker()
    pending = tracker.get_all_pending()
    
    if not pending:
        print("\nNo pending updates to sync.")
        return
    
    # Group by repo
    repos = {}
    for update in pending:
        repo_path = update['repo_path']
        if repo_path not in repos:
            repos[repo_path] = []
        repos[repo_path].append(update)
    
    print(f"\n🔄 Syncing {len(pending)} pending update(s) across {len(repos)} repository(ies) with GitLab...")
    print("=" * 80)
    
    total_merged = 0
    total_deleted = 0
    total_errors = 0
    
    for repo_path, updates in repos.items():
        repo = Path(repo_path)
        
        if not repo.exists():
            print(f"\n⚠️  Repository not found: {repo_path}")
            print(f"   Skipping {len(updates)} update(s)")
            continue
        
        print(f"\n📁 Repository: {repo_path}")
        print(f"   Checking {len(updates)} pending branch(es)...")
        
        gitlab_client = GitLabClient(repo)
        
        if not gitlab_client.is_configured():
            print(f"   ⚠️  GitLab not configured for this repository")
            print(f"      Set GitLab token: git config --global gitlab.token <your-token>")
            print(f"      Or set environment variable: GITLAB_TOKEN=<your-token>")
            continue
        
        # Sync this repo's tracking
        results = gitlab_client.sync_tracking_status(tracker)
        
        merged = results["merged"]
        deleted = results["deleted"]
        errors = results["errors"]
        
        total_merged += merged
        total_deleted += deleted
        total_errors += errors
        
        if merged > 0:
            print(f"   ✓ Marked {merged} branch(es) as merged")
        if deleted > 0:
            print(f"   ✓ Marked {deleted} deleted branch(es) as merged")
        if errors > 0:
            print(f"   ⚠️  {errors} error(s) encountered")
    
    print(f"\n{'=' * 80}")
    print("Sync Summary:")
    print(f"  ✓ Merged: {total_merged}")
    print(f"  ✓ Deleted (assumed merged): {total_deleted}")
    print(f"  ⚠️  Errors: {total_errors}")
    print(f"  Total processed: {total_merged + total_deleted + total_errors}")
    
    # Show remaining pending
    remaining = tracker.get_all_pending()
    if remaining:
        print(f"\n📋 {len(remaining)} update(s) still pending")
    else:
        print(f"\n✓ All updates have been merged!")


def _cleanup_pending_branches():
    """Delete local pending branches and remove from tracking"""
    import subprocess
    from pathlib import Path
    
    tracker = UpdateTracker()
    pending = tracker.get_all_pending()
    
    if not pending:
        print("\nNo pending updates to clean up.")
        return
    
    # Group by repo
    repos = {}
    for update in pending:
        repo_path = update['repo_path']
        if repo_path not in repos:
            repos[repo_path] = []
        repos[repo_path].append(update)
    
    print(f"\nFound {len(pending)} pending update(s) across {len(repos)} repository(ies)")
    print("=" * 80)
    
    deleted_count = 0
    not_found_count = 0
    error_count = 0
    
    for repo_path, updates in repos.items():
        repo = Path(repo_path)
        
        if not repo.exists():
            print(f"\n⚠️  Repository not found: {repo_path}")
            print(f"   Skipping {len(updates)} branch(es)")
            not_found_count += len(updates)
            continue
        
        print(f"\n📁 Repository: {repo_path}")
        
        for update in updates:
            branch_name = update['branch_name']
            
            # Check if branch exists locally
            result = subprocess.run(
                ['git', 'rev-parse', '--verify', branch_name],
                cwd=repo,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print(f"   ⚠️  Branch not found: {branch_name}")
                not_found_count += 1
                # Remove from tracking even if branch doesn't exist
                tracker.remove_branch(branch_name)
                continue
            
            # Delete the local branch
            result = subprocess.run(
                ['git', 'branch', '-D', branch_name],
                cwd=repo,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print(f"   ✓ Deleted: {branch_name}")
                tracker.remove_branch(branch_name)
                deleted_count += 1
            else:
                print(f"   ✗ Failed to delete: {branch_name}")
                print(f"     Error: {result.stderr.strip()}")
                error_count += 1
    
    print(f"\n{'=' * 80}")
    print(f"Summary:")
    print(f"  ✓ Deleted: {deleted_count}")
    print(f"  ⚠️  Not found: {not_found_count}")
    print(f"  ✗ Errors: {error_count}")
    print(f"  Total processed: {deleted_count + not_found_count + error_count}")


def _import_from_csv(csv_path: str, export_mapping: bool = False) -> Optional[List[str]]:
    """Import app list from CSV file"""
    from pathlib import Path
    
    csv_file = Path(csv_path)
    importer = CSVAppImporter()
    
    apps = importer.import_from_csv(csv_file)
    
    if not apps:
        logger.error(f"No apps imported from {csv_path}")
        return None
    
    print(f"\nImported {len(apps)} apps from CSV:")
    for app in apps[:10]:  # Show first 10
        print(f"  - {app['display_name']}")
        if 'splunkbase_id' in app:
            print(f"    ID: {app['splunkbase_id']}, Folder: {app['name']}")
    
    if len(apps) > 10:
        print(f"  ... and {len(apps) - 10} more")
    
    # Export mapping if requested
    if export_mapping:
        output_file = Path('work') / 'csv_id_mapping.yaml'
        output_file.parent.mkdir(exist_ok=True)
        mapping = importer.export_id_mapping(apps, output_file)
        print(f"\nExported Splunkbase ID mapping to: {output_file}")
        print("\nYou can copy this to your config.yaml:")
        print("=" * 80)
        print(mapping)
        print("=" * 80)
    
    # Return list of app names for filtering
    return [app['name'] for app in apps]


def _filter_apps_by_csv(apps: list, csv_app_names: List[str]) -> list:
    """Filter apps to only those in CSV import list"""
    if not csv_app_names:
        return apps
    
    # Match by app name (case-insensitive, flexible matching)
    filtered = []
    for app in apps:
        app_name_lower = app.name.lower()
        for csv_name in csv_app_names:
            csv_name_lower = csv_name.lower()
            # Exact match or contains match
            if app_name_lower == csv_name_lower or csv_name_lower in app_name_lower or app_name_lower in csv_name_lower:
                filtered.append(app)
                break
    
    if filtered:
        logger.info(f"Filtered to {len(filtered)} apps from CSV import list")
    else:
        logger.warning("No apps matched CSV import list - app names may not match folder names")
        print("\nWARNING: No apps matched the CSV import list.")
        print("   This may be because CSV display names don't match folder names.")
        print("   Example: 'Splunk Add-on for Microsoft Windows' -> 'Splunk_TA_windows'")
        print("\n   Try using --export-csv-mapping to see suggested mappings.")
    
    return filtered


def _check_app_compatibility(splunk_version: str, app_filter: Optional[str] = None, remote_branch: Optional[str] = None, config_path: str = 'config.yaml'):
    """Check app compatibility with specified Splunk version"""
    from .config import ConfigManager
    from .splunkbase import SplunkbaseClient
    from .updater import SplunkAppUpdater
    
    print(f"\n{'=' * 80}")
    print(f"SPLUNK APP COMPATIBILITY CHECK")
    print(f"Target Splunk Version: {splunk_version}")
    if remote_branch:
        source = f"remote branch ({remote_branch})" if remote_branch != 'auto' else "remote branch (auto-detect)"
    else:
        source = "local working directory"
    print(f"Source: {source}")
    print(f"{'=' * 80}\n")
    
    config_manager = ConfigManager(config_path)
    creds = config_manager.get_splunkbase_credentials()
    splunkbase = SplunkbaseClient(creds[0], creds[1])
    
    # Get existing ID mappings from config
    existing_mappings = config_manager.get_splunkbase_id_mapping()
    
    # Create normalized lookup (handle hyphens vs underscores, case variations)
    def normalize_name(name: str) -> str:
        """Normalize app name for comparison"""
        return name.lower().replace('-', '_').replace(' ', '_')
    
    normalized_mappings = {normalize_name(k): k for k in existing_mappings.keys()}
    
    print("Discovering Splunk apps...")
    if remote_branch:
        print("(This may take a moment when reading from remote branches)")
    
    updater = SplunkAppUpdater(config_path)
    apps = updater.discover_apps(remote_branch=remote_branch)
    
    print(f"Found {len(apps)} apps total")
    
    # Filter by app name if specified
    if app_filter:
        apps = [app for app in apps if app_filter.lower() in app.name.lower()]
        if not apps:
            print(f"No apps found matching '{app_filter}'")
            return
        print(f"Filtered to {len(apps)} apps matching '{app_filter}'")
    
    # Count apps with Splunkbase IDs
    apps_with_ids = [app for app in apps if app.splunkbase_id]
    apps_without_ids = [app for app in apps if not app.splunkbase_id]
    
    # Filter out apps that already have IDs in config but aren't showing up in app instances
    # (This happens when the ID is in config.yaml but not in the app's app.conf)
    # Use normalized lookup to handle name variations (hyphens vs underscores)
    def has_mapping(app_name: str) -> bool:
        """Check if app has ID in config (normalized comparison)"""
        return normalize_name(app_name) in normalized_mappings
    
    truly_missing = [app for app in apps_without_ids if not has_mapping(app.name)]
    already_in_config = [app for app in apps_without_ids if has_mapping(app.name)]
    
    print(f"Apps with Splunkbase IDs: {len(apps_with_ids)}")
    if already_in_config:
        unique_already_mapped = sorted(set(app.name for app in already_in_config))
        print(f"Apps with IDs in config.yaml: {len(already_in_config)} instances ({len(unique_already_mapped)} unique apps)")
    if truly_missing:
        # Get unique app names
        unique_missing = sorted(set(app.name for app in truly_missing))
        print(f"Apps without Splunkbase IDs: {len(truly_missing)} instances ({len(unique_missing)} unique apps)")
        print(f"\nWARNING: Splunkbase API does not support searching by app name.")
        print(f"   Add the following to your config.yaml under 'splunkbase_id_mapping':\n")
        
        for app_name in unique_missing:
            # Count how many instances of this app
            instance_count = len([a for a in truly_missing if a.name == app_name])
            print(f"  {app_name}: \"\"  # {instance_count} instance(s) - search: https://splunkbase.splunk.com/apps/?keyword={app_name}")
        
        print(f"\n   Find app IDs by searching Splunkbase. The ID is in the URL:")
        print(f"   Example: https://splunkbase.splunk.com/app/742/ → ID is \"742\"")
        print()
    
    print(f"\nChecking compatibility for {len(apps_with_ids)} app instances...\n")
    
    # Check compatibility for each app
    results = []
    checked_count = 0
    for app in apps:
        if not app.splunkbase_id:
            continue
        
        checked_count += 1
        
        # Build location string (component/environment/region)
        location_parts = app.metadata_parts(labeled=False)
        location = '/'.join(location_parts) if location_parts else 'unknown'
        
        print(f"[{checked_count}/{len(apps_with_ids)}] Checking {app.name} [{location}] (ID: {app.splunkbase_id})...")
        
        # Get release details
        release = splunkbase.get_release_details(app.splunkbase_id)
        if not release:
            print(f"  ❌ Could not retrieve release information")
            continue
        
        # Debug: Show what fields are available
        logger.debug(f"Release fields for {app.name}: {list(release.keys())}")
        logger.debug(f"Full release data: {release}")
        
        compat_info = splunkbase.get_compatibility_info(release)
        if not compat_info or (not compat_info.get('min_version') and not compat_info.get('max_version')):
            print(f"  ⚠️  No compatibility information available")
            print(f"  Available release fields: {', '.join(list(release.keys())[:10])}")
            continue
        
        is_compatible = splunkbase._is_version_compatible(splunk_version, compat_info)
        
        min_ver = compat_info.get('min_version', 'N/A')
        max_ver = compat_info.get('max_version', 'N/A')
        
        status = "✅ Compatible" if is_compatible else "❌ Incompatible"
        print(f"  {status}")
        print(f"  Current version: {app.current_version}")
        print(f"  Supported Splunk range: {min_ver} - {max_ver}")
        
        # Get compatible versions
        if not is_compatible:
            compatible_versions = splunkbase.get_compatible_versions_for_splunk(
                app.splunkbase_id, splunk_version, max_versions=5
            )
            if compatible_versions:
                print(f"  Compatible versions available: {', '.join(compatible_versions[:5])}")
        
        print()
        
        results.append({
            'name': app.name,
            'compatible': is_compatible,
            'min_version': min_ver,
            'max_version': max_ver
        })
    
    # Summary
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    compatible_count = sum(1 for r in results if r['compatible'])
    print(f"Total apps checked: {len(results)}")
    print(f"Compatible: {compatible_count}")
    print(f"Incompatible: {len(results) - compatible_count}")
    print(f"{'=' * 80}\n")


def _update_incompatible_apps(args):
    """Update only apps that are incompatible with specified Splunk version"""
    from .updater import SplunkAppUpdater
    
    splunk_version = args.update_incompatible
    
    print(f"\n{'=' * 80}")
    print(f"UPDATE INCOMPATIBLE APPS")
    print(f"Target Splunk Version: {splunk_version}")
    print(f"{'=' * 80}\n")
    
    # Initialize updater
    updater = SplunkAppUpdater(args.config, skip_tracking=args.force, is_test=args.test_mode)
    component_filter = _normalize_component_filter(args.component)
    
    # Override remote_branch to None if --local flag is set
    remote_branch = None if getattr(args, 'use_local', False) else args.remote_branch
    
    # Pull repos if requested
    if args.pull:
        _pull_repos(updater)
    
    _log_filters(component_filter, args.environment, args.region)
    
    # Discover apps
    print("Discovering Splunk apps...")
    apps = _discover_apps(updater, component_filter, args.environment, args.region, remote_branch)
    
    # Filter to only apps with Splunkbase IDs
    apps_with_ids = [app for app in apps if app.splunkbase_id]
    print(f"Found {len(apps)} apps total, {len(apps_with_ids)} with Splunkbase IDs")
    
    if not apps_with_ids:
        print("No apps with Splunkbase IDs found.")
        return
    
    # Check compatibility for each app — reuse updater's splunkbase client
    splunkbase = updater.splunkbase_client
    
    incompatible_apps = []
    print(f"\nChecking compatibility for {len(apps_with_ids)} apps...\n")
    
    for idx, app in enumerate(apps_with_ids, 1):
        # Build location string
        location_parts = app.metadata_parts(labeled=False)
        location = '/'.join(location_parts) if location_parts else 'unknown'
        
        print(f"[{idx}/{len(apps_with_ids)}] {app.name} [{location}] v{app.current_version}...", end=' ')
        
        # Get release details
        release = splunkbase.get_release_details(app.splunkbase_id)
        if not release:
            print("❌ No release info")
            continue
        
        compat_info = splunkbase.get_compatibility_info(release)
        if not compat_info or (not compat_info.get('min_version') and not compat_info.get('max_version')):
            print("⚠️  No compatibility info")
            continue
        
        is_compatible = splunkbase._is_version_compatible(splunk_version, compat_info)
        
        if is_compatible:
            print("✅ Compatible")
        else:
            print("❌ INCOMPATIBLE - will update")
            incompatible_apps.append(app)
    
    # Summary
    print(f"\n{'=' * 80}")
    print(f"Found {len(incompatible_apps)} incompatible apps to update")
    print(f"{'=' * 80}\n")
    
    if not incompatible_apps:
        print("All apps are compatible! No updates needed.")
        return
    
    # Check for updates for incompatible apps only
    print("Checking for updates to compatible versions...\n")
    apps_with_updates = updater.check_for_updates(incompatible_apps)
    
    if not apps_with_updates:
        print("No compatible updates available for incompatible apps.")
        return
    
    print(f"Found {len(apps_with_updates)} apps with compatible updates available\n")
    
    # Interactive selection or auto-select all
    if not args.no_interactive:
        apps_with_updates = _select_apps(args, apps_with_updates, component_filter)
    
    if not apps_with_updates:
        logger.info("No apps selected for update")
        return
    
    if args.dry_run:
        _dry_run_mode(apps_with_updates, args.no_branch)
        return
    
    # Perform updates
    _perform_updates(updater, apps, apps_with_updates, args.no_branch)


if __name__ == '__main__':
    main()
