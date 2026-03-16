"""Interactive version selection for apps"""

import logging
from typing import List, Optional

from .models import SplunkApp

logger = logging.getLogger(__name__)


def select_version_interactive(app: SplunkApp, available_versions: List[str], nonprod_version: Optional[str] = None) -> Optional[str]:
    """Interactively select version to install for an app
    
    Args:
        app: App to select version for
        available_versions: List of available versions from Splunkbase
        nonprod_version: Version from non-prod environment (if found)
    
    Returns:
        Selected version string, or None if user cancels
    """
    print(f"\n{'=' * 80}")
    print(f"SELECT VERSION FOR: {app.name}")
    print(f"{'=' * 80}")
    print(f"Current version: {app.current_version}")
    print(f"Environment: {app.environment or 'unknown'}")
    if app.component:
        print(f"Component: {app.component}")
    
    # Debug: Show what nonprod search found
    if app.nonprod_version_requested:
        logger.debug(f"Non-prod version requested: {app.nonprod_version_requested}")
    
    if nonprod_version:
        print(f"\n[WARN]  Non-prod version {nonprod_version} not found on Splunkbase")
        print(f"   The non-prod environment has this app at v{nonprod_version}, but it's not available for download.")
        print(f"   Available versions on Splunkbase:")
    else:
        print(f"\nℹ️  No matching app found in non-prod environment")
        print(f"   (Searched for: {app.name} with component: {app.component})")
        print(f"   Available versions:")
    
    # Show top 10 versions
    display_versions = available_versions[:10]
    for idx, version in enumerate(display_versions, 1):
        marker = " (latest)" if idx == 1 else ""
        print(f"  {idx}. {version}{marker}")
    
    if len(available_versions) > 10:
        print(f"  ... and {len(available_versions) - 10} more versions")
    
    print(f"\nOptions:")
    print(f"  - Enter number (1-{len(display_versions)}) to select that version")
    print(f"  - Enter 'latest' or '1' for the latest version")
    print(f"  - Enter version number directly (e.g., '8.0.0')")
    print(f"  - Enter 'skip' to skip this app")
    
    try:
        while True:
            selection = input(f"\nSelect version for {app.name}: ").strip()
            
            if not selection or selection.lower() == 'skip':
                print(f"Skipping {app.name}")
                return None
            
            # Check if it's a number selection
            if selection.isdigit():
                idx = int(selection)
                if 1 <= idx <= len(display_versions):
                    selected_version = display_versions[idx - 1]
                    print(f"Selected version {selected_version}")
                    return selected_version
                else:
                    print(f"Invalid selection. Please enter a number between 1 and {len(display_versions)}")
                    continue
            
            # Check if it's 'latest'
            if selection.lower() == 'latest':
                selected_version = available_versions[0]
                print(f"Selected latest version {selected_version}")
                return selected_version
            
            # Check if it's a direct version string
            if selection in available_versions:
                print(f"Selected version {selection}")
                return selection
            else:
                print(f"Version '{selection}' not found on Splunkbase")
                print(f"Please select from available versions")
                continue
    
    except KeyboardInterrupt:
        print(f"\n\nSkipping {app.name}")
        return None
    except Exception as e:
        logger.error(f"Error during version selection: {e}")
        return None


def prompt_version_selection_for_apps(apps: List[SplunkApp]) -> List[SplunkApp]:
    """Prompt for version selection for apps that need it
    
    Args:
        apps: List of apps to check
    
    Returns:
        List of apps with selected versions (excluding skipped apps)
    """
    apps_with_selection = []
    
    for app in apps:
        # Check if app has available versions stored and needs selection
        available_versions = app.available_versions or None
        nonprod_version = app.nonprod_version_requested
        needs_selection = app.needs_version_selection
        
        if needs_selection and available_versions:
            selected_version = select_version_interactive(app, available_versions, nonprod_version)
            
            if selected_version:
                app.latest_version = selected_version
                apps_with_selection.append(app)
            else:
                logger.info(f"User skipped {app.name}")
        else:
            # App doesn't need selection, include as-is
            apps_with_selection.append(app)
    
    return apps_with_selection
