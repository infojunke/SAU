"""Interactive app selection interface"""

import logging
from typing import Dict, List, Optional

from .models import SplunkApp

logger = logging.getLogger(__name__)


def select_apps_interactive(apps: List[SplunkApp], active_filters: Optional[Dict[str, str]] = None) -> List[SplunkApp]:
    """Interactively select apps to update
    
    Args:
        apps: List of apps with updates available
        active_filters: Dict of active filters (environment, region, component)
    """
    if not apps:
        return []
    
    _print_header(active_filters)
    _print_app_list(apps)
    _print_instructions()
    
    try:
        selection = input("Select apps to update: ").strip().lower()
        
        if not selection or selection == 'none':
            print("\nNo apps selected.")
            return []
        
        if selection == 'all':
            print(f"\nSelected all {len(apps)} apps.")
            return apps
        
        # Check for environment-based selections
        if selection in ['non-prod', 'nonprod', 'shared', 'prod']:
            selected_apps = _filter_by_environment(selection, apps)
            if selected_apps:
                _print_selected_apps(selected_apps)
                return selected_apps
            else:
                print(f"\nNo apps found with environment '{selection}'.")
                return []
        
        selected_apps = _parse_selection(selection, apps)
        _print_selected_apps(selected_apps)
        
        return selected_apps
        
    except KeyboardInterrupt:
        print("\n\nCancelled by user.")
        return []
    except Exception as e:
        logger.error(f"Error during selection: {e}")
        return []


def _print_header(active_filters: Optional[Dict[str, str]]):
    """Print selection header"""
    print("\n" + "=" * 80)
    print("SELECT APPS TO UPDATE")
    print("=" * 80)
    
    if active_filters:
        filter_parts = []
        if active_filters.get('environment'):
            filter_parts.append(f"Environment: {active_filters['environment']}")
        if active_filters.get('region'):
            filter_parts.append(f"Region: {active_filters['region']}")
        if active_filters.get('component'):
            filter_parts.append(f"Component: {active_filters['component']}")
        if filter_parts:
            print(f"\nActive Filters: {' | '.join(filter_parts)}")


def _print_app_list(apps: List[SplunkApp]):
    """Print numbered list of apps"""
    print(f"\nFound {len(apps)} apps with updates available:\n")
    
    for idx, app in enumerate(apps, 1):
        print(f"  {idx}. {app.instance_id}")
        print(f"     Current: v{app.current_version} -> New: v{app.latest_version}")
        
        # Show warning if current version not available on Splunkbase
        if app.current_version_unavailable:
            print(f"     [WARN]  WARNING: Current version {app.current_version} not available on Splunkbase")
        
        # Show warning if non-prod version not available on Splunkbase
        if app.nonprod_version_unavailable:
            print(f"     [WARN]  WARNING: Non-prod version {app.nonprod_version_requested or 'unknown'} not available on Splunkbase")
        
        metadata = app.metadata_parts()
        if metadata:
            print(f"     {' | '.join(metadata)}")
        
        print(f"     Path: {app.local_path}")
        print()



def _print_instructions():
    """Print selection instructions"""
    print("=" * 80)
    print("\nSelection options:")
    print("  - Enter numbers separated by commas (e.g., 1,3,5)")
    print("  - Enter ranges with dash (e.g., 1-3)")
    print("  - Enter 'all' to select all apps")
    print("  - Enter 'non-prod' to select all non-prod apps")
    print("  - Enter 'shared' to select all shared apps")
    print("  - Enter 'prod' to select all prod apps")
    print("  - Enter 'none' or press Ctrl+C to cancel")
    print()


def _parse_selection(selection: str, apps: List[SplunkApp]) -> List[SplunkApp]:
    """Parse user selection string"""
    selected_indices = set()
    parts = selection.split(',')
    
    for part in parts:
        part = part.strip()
        if '-' in part:
            _parse_range(part, selected_indices)
        else:
            _parse_single(part, selected_indices)
    
    return _filter_apps_by_indices(selected_indices, apps)


def _parse_range(part: str, selected_indices: set):
    """Parse a range selection (e.g., '1-3')"""
    try:
        start, end = part.split('-')
        start, end = int(start.strip()), int(end.strip())
        selected_indices.update(range(start, end + 1))
    except ValueError:
        print(f"Invalid range: {part}")


def _parse_single(part: str, selected_indices: set):
    """Parse a single number selection"""
    try:
        selected_indices.add(int(part))
    except ValueError:
        print(f"Invalid number: {part}")


def _filter_apps_by_indices(selected_indices: set, apps: List[SplunkApp]) -> List[SplunkApp]:
    """Filter apps by selected indices"""
    selected_apps = []
    for idx in sorted(selected_indices):
        if 1 <= idx <= len(apps):
            selected_apps.append(apps[idx - 1])
        else:
            print(f"Warning: Invalid selection {idx} (valid range: 1-{len(apps)})")
    return selected_apps


def _filter_by_environment(env_selection: str, apps: List[SplunkApp]) -> List[SplunkApp]:
    """Filter apps by environment
    
    Args:
        env_selection: Environment selection ('non-prod', 'nonprod', 'shared', 'prod')
        apps: List of apps to filter
    
    Returns:
        List of apps matching the environment
    """
    # Normalize environment selection (prod = shared)
    env_map = {
        'non-prod': 'non-prod',
        'nonprod': 'non-prod',
        'shared': 'shared',
        'prod': 'shared'  # prod is treated as shared
    }
    target_env = env_map.get(env_selection.lower())
    
    if not target_env:
        return []
    
    # For shared/prod, match both 'shared' and 'prod'
    if target_env == 'shared':
        filtered_apps = [
            app for app in apps 
            if app.environment and app.environment.lower() in ['shared', 'prod']
        ]
    else:
        filtered_apps = [
            app for app in apps 
            if app.environment and app.environment.lower() == target_env
        ]
    
    print(f"\nFound {len(filtered_apps)} app(s) in '{target_env}' environment.")
    return filtered_apps


def _print_selected_apps(selected_apps: List[SplunkApp]):
    """Print the selected apps"""
    if selected_apps:
        print(f"\nSelected {len(selected_apps)} app(s):")
        for app in selected_apps:
            print(f"  - {app.instance_id} (v{app.current_version} -> v{app.latest_version})")
            print(f"    Path: {app.local_path}")
    else:
        print("\nNo valid apps selected.")
