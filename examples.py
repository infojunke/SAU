#!/usr/bin/env python3
"""
Example usage script for Splunk App Updater
Demonstrates various ways to use the updater programmatically
"""

from splunk_app_updater import (
    SplunkAppUpdater,
    ConfigManager,
    SplunkbaseClient,
    GitLabRepoAnalyzer
)
from pathlib import Path
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def example_basic_usage():
    """Basic example: Check and update all apps"""
    logger.info("=== Basic Usage Example ===")
    
    # Initialize updater with config file
    updater = SplunkAppUpdater('config.yaml')
    
    # Discover all apps in GitLab repos
    apps = updater.discover_apps()
    logger.info(f"Discovered {len(apps)} apps")
    
    # Check for updates
    apps_with_updates = updater.check_for_updates(apps)
    logger.info(f"Found {len(apps_with_updates)} apps with updates")
    
    # Update all apps
    if apps_with_updates:
        results = updater.update_all_apps(apps_with_updates)
        logger.info(f"Update results: {results}")
        
        # Generate report
        report = updater.generate_report(apps, results)
        print(report)


def example_check_only():
    """Example: Only check for updates without downloading"""
    logger.info("=== Check Only Example ===")
    
    updater = SplunkAppUpdater('config.yaml')
    apps = updater.discover_apps()
    apps_with_updates = updater.check_for_updates(apps)
    
    if apps_with_updates:
        print("\nApps with updates available:")
        for app in apps_with_updates:
            print(f"  - {app.name}: {app.current_version} -> {app.latest_version}")
            print(f"    Deployment types: {', '.join(app.deployment_types)}")
    else:
        print("\nAll apps are up to date!")


def example_single_app_update():
    """Example: Update a single specific app"""
    logger.info("=== Single App Update Example ===")
    
    app_name_to_update = "Splunk_TA_windows"
    
    updater = SplunkAppUpdater('config.yaml')
    apps = updater.discover_apps()
    apps_with_updates = updater.check_for_updates(apps)
    
    # Find the specific app
    target_app = None
    for app in apps_with_updates:
        if app.name == app_name_to_update:
            target_app = app
            break
    
    if target_app:
        logger.info(f"Updating {target_app.name}...")
        success = updater.update_app(target_app, create_branch=True)
        if success:
            logger.info(f"Successfully updated {target_app.name}")
        else:
            logger.error(f"Failed to update {target_app.name}")
    else:
        logger.info(f"App '{app_name_to_update}' not found or doesn't need update")


def example_custom_config():
    """Example: Using custom configuration programmatically"""
    logger.info("=== Custom Configuration Example ===")
    
    # Load config
    config = ConfigManager('config.yaml')
    
    # Get Splunkbase credentials
    username, password = config.get_splunkbase_credentials()
    
    # Create Splunkbase client
    client = SplunkbaseClient(username, password)
    
    # Check specific app on Splunkbase
    app_id = "1274"  # Example: Splunk App for AWS
    latest_version = client.get_latest_version(app_id)
    logger.info(f"Latest version of app {app_id}: {latest_version}")
    
    # Get app info
    app_info = client.get_app_info(app_id)
    if app_info:
        logger.info(f"App info: {app_info.get('title', 'Unknown')}")


def example_repo_analysis():
    """Example: Analyze a repository without updating"""
    logger.info("=== Repository Analysis Example ===")
    
    analyzer = GitLabRepoAnalyzer()
    
    # Analyze a specific repo
    repo_path = Path("/path/to/your/repo")
    
    if repo_path.exists():
        apps = analyzer.find_splunk_apps(repo_path)
        
        print(f"\nFound {len(apps)} apps in {repo_path}:")
        for app in apps:
            print(f"\n  App: {app.name}")
            print(f"    Version: {app.current_version}")
            print(f"    Path: {app.local_path}")
            print(f"    Splunkbase ID: {app.splunkbase_id or 'Not found'}")
            print(f"    Deployment types: {', '.join(app.deployment_types)}")
    else:
        logger.warning(f"Repository path does not exist: {repo_path}")


def example_with_filters():
    """Example: Update only specific types of apps"""
    logger.info("=== Filtered Update Example ===")
    
    updater = SplunkAppUpdater('config.yaml')
    apps = updater.discover_apps()
    apps_with_updates = updater.check_for_updates(apps)
    
    # Filter: only update apps that deploy to search heads
    searchhead_apps = [
        app for app in apps_with_updates 
        if 'searchhead' in app.deployment_types
    ]
    
    logger.info(f"Found {len(searchhead_apps)} search head apps to update")
    
    if searchhead_apps:
        results = updater.update_all_apps(searchhead_apps)
        logger.info(f"Updated {sum(results.values())} search head apps")


def example_with_error_handling():
    """Example: Proper error handling"""
    logger.info("=== Error Handling Example ===")
    
    try:
        updater = SplunkAppUpdater('config.yaml')
        apps = updater.discover_apps()
        
        if not apps:
            logger.warning("No apps found in configured repositories")
            return
        
        apps_with_updates = updater.check_for_updates(apps)
        
        if not apps_with_updates:
            logger.info("All apps are up to date")
            return
        
        # Update with error handling for each app
        for app in apps_with_updates:
            try:
                logger.info(f"Attempting to update {app.name}...")
                success = updater.update_app(app)
                
                if success:
                    logger.info(f"✓ Successfully updated {app.name}")
                else:
                    logger.error(f"✗ Failed to update {app.name}")
                    
            except Exception as e:
                logger.error(f"✗ Error updating {app.name}: {e}", exc_info=True)
                # Continue with next app
                continue
                
    except FileNotFoundError:
        logger.error("Configuration file not found")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)


def example_dry_run():
    """Example: Simulate updates without making changes"""
    logger.info("=== Dry Run Example ===")
    
    updater = SplunkAppUpdater('config.yaml')
    apps = updater.discover_apps()
    apps_with_updates = updater.check_for_updates(apps)
    
    if apps_with_updates:
        print("\nWould perform the following updates:\n")
        for app in apps_with_updates:
            print(f"  {app.name}:")
            print(f"    Current: v{app.current_version}")
            print(f"    Latest:  v{app.latest_version}")
            print(f"    Path:    {app.local_path}")
            print(f"    Branch:  update/{app.name}-{app.latest_version}")
            print()
        
        print(f"Total updates: {len(apps_with_updates)}")
    else:
        print("\nNo updates needed - all apps are current")


def main():
    """Run examples"""
    print("Splunk App Updater - Usage Examples\n")
    print("Choose an example to run:")
    print("1. Basic usage (discover, check, update)")
    print("2. Check only (no updates)")
    print("3. Update single app")
    print("4. Custom configuration")
    print("5. Repository analysis")
    print("6. Filtered updates (search heads only)")
    print("7. Error handling example")
    print("8. Dry run (simulate)")
    print("9. Interactive selection")
    print("10. Multiple apps by pattern")
    
    choice = input("\nEnter choice (1-10): ").strip()
    
    examples = {
        '1': example_basic_usage,
        '2': example_check_only,
        '3': example_single_app_update,
        '4': example_custom_config,
        '5': example_repo_analysis,
        '6': example_with_filters,
        '7': example_with_error_handling,
        '8': example_dry_run,
        '9': example_interactive_selection,
        '10': example_multiple_apps
    }
    
    example_func = examples.get(choice)
    if example_func:
        print(f"\nRunning example...\n")
        example_func()
    else:
        print("Invalid choice")


def example_interactive_selection():
    """Example: Interactive app selection"""
    logger.info("=== Interactive Selection Example ===")
    
    from splunk_app_updater import select_apps_interactive
    
    updater = SplunkAppUpdater('config.yaml')
    apps = updater.discover_apps()
    apps_with_updates = updater.check_for_updates(apps)
    
    if not apps_with_updates:
        logger.info("No updates available")
        return
    
    # Let user select apps interactively (no filters in this example)
    selected_apps = select_apps_interactive(apps_with_updates, active_filters=None)
    
    if selected_apps:
        logger.info(f"Updating {len(selected_apps)} selected apps...")
        results = updater.update_all_apps(selected_apps)
        
        # Show results
        for app_name, success in results.items():
            status = "✓ Success" if success else "✗ Failed"
            logger.info(f"  {status}: {app_name}")


def example_multiple_apps():
    """Example: Update multiple specific apps by pattern"""
    logger.info("=== Multiple Apps Update Example ===")
    
    import fnmatch
    
    updater = SplunkAppUpdater('config.yaml')
    apps = updater.discover_apps()
    apps_with_updates = updater.check_for_updates(apps)
    
    # Update all Splunk TA apps (Technology Add-ons)
    pattern = "Splunk_TA_*"
    matching_apps = [app for app in apps_with_updates if fnmatch.fnmatch(app.name, pattern)]
    
    if matching_apps:
        logger.info(f"Found {len(matching_apps)} apps matching pattern '{pattern}':")
        for app in matching_apps:
            logger.info(f"  - {app.name}")
        
        results = updater.update_all_apps(matching_apps)
        logger.info(f"Updated {sum(results.values())} apps successfully")
    else:
        logger.info(f"No apps matching pattern '{pattern}' need updates")


if __name__ == '__main__':
    main()
