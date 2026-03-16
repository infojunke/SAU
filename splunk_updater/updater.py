"""Main Splunk app updater orchestrator"""

import logging
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .config import ConfigManager
from .file_manager import AppFileManager
from .git_manager import GitBranchManager
from .models import SplunkApp
from .repo_analyzer import GitLabRepoAnalyzer
from . import repo_cache as repo_cache_mod
from .splunkbase import SplunkbaseClient
from .update_tracker import UpdateTracker
from .utils import version_compare

logger = logging.getLogger(__name__)


class SplunkAppUpdater:
    """Main orchestrator for Splunk app updates"""
    
    def __init__(self, config_path: str = 'config.yaml', skip_tracking: bool = False, is_test: bool = False):
        self.config_manager = ConfigManager(config_path)
        
        username, password = self.config_manager.get_splunkbase_credentials()
        sha256_checksums = self.config_manager.get_sha256_checksums()
        self.splunkbase_client = SplunkbaseClient(username, password, sha256_checksums)
        
        id_mapping = self.config_manager.get_splunkbase_id_mapping()
        
        self.deployment_config = self.config_manager.get_deployment_config()
        self.file_manager = AppFileManager(self.deployment_config)
        self.work_dir = self.config_manager.get_work_directory()
        
        scan_cache = repo_cache_mod.RepoScanCache(self.work_dir / "cache")
        self.repo_analyzer = GitLabRepoAnalyzer(id_mapping, repo_cache=scan_cache)
        
        # Initialize update tracker
        self.skip_tracking = skip_tracking
        self.is_test = is_test
        self.tracker = UpdateTracker()
        
        # Cache for non-prod app lookups (populated lazily by find_nonprod_version)
        self._nonprod_apps_cache: Optional[List[SplunkApp]] = None
    
    def find_nonprod_version(self, app_name: str, component: Optional[str] = None) -> Optional[str]:
        """Find the version of an app in non-prod environment
        
        Args:
            app_name: Name of the app to find
            component: Component type (ds, shc, cm) to match (not used for discovery, only for matching)
        
        Returns:
            Version string if found in non-prod, None otherwise
        """
        # Discover non-prod apps once and cache for subsequent lookups
        if self._nonprod_apps_cache is None:
            logger.info(f"Discovering non-prod apps for version matching...")
            self._nonprod_apps_cache = self.discover_apps(environment_filter='non-prod', quiet=True)
            logger.info(f"Cached {len(self._nonprod_apps_cache)} non-prod apps for version matching")
        
        nonprod_apps = self._nonprod_apps_cache
        logger.debug(f"Looking up {app_name} (component: {component}) in {len(nonprod_apps)} cached non-prod apps")
        
        # Find matching app by name and component
        matches_by_name = []
        for app in nonprod_apps:
            if app.name == app_name:
                matches_by_name.append(f"{app.name} (component: {app.component})")
                if app.component == component:
                    logger.debug(f"MATCH! Found {app.name} with component {component} at version {app.current_version}")
                    logger.info(f"Found {app_name} in non-prod with version {app.current_version} (component: {app.component})")
                    return app.current_version
        
        if matches_by_name:
            logger.debug(f"Found {len(matches_by_name)} apps named '{app_name}' but wrong component: {matches_by_name}")
        else:
            logger.debug(f"No apps found with name '{app_name}' in any non-prod repo")
        
        logger.info(f"No non-prod version found for {app_name} (component: {component})")
        return None
    
    def discover_apps(self, component_filter: Optional[str] = None, 
                     environment_filter: Optional[str] = None,
                     region_filter: Optional[str] = None,
                     remote_branch: Optional[str] = None,
                     quiet: bool = False) -> List[SplunkApp]:
        """Discover all Splunk apps in configured GitLab repos
        
        Args:
            component_filter: Filter by component type
            environment_filter: Filter by environment
            region_filter: Filter by region
            remote_branch: Read from remote branch instead of local files (e.g., 'origin/main')
            quiet: Suppress per-repo progress output (used for internal lookups)
        """
        import time
        
        all_apps = []
        repos = self.config_manager.get_gitlab_repos()
        
        # Filter repos first to get accurate count
        repos_to_scan = [
            repo_config for repo_config in repos
            if not self._should_skip_repo(repo_config, component_filter, environment_filter, region_filter)
            and Path(repo_config['path']).exists()
        ]
        
        total_repos = len(repos_to_scan)
        start_time = time.time()
        
        for idx, repo_config in enumerate(repos_to_scan, 1):
            repo = Path(repo_config['path'])
            repo_start = time.time()
            
            # Show progress with metadata
            repo_name = repo.name
            env = repo_config.get('environment', '')
            component = repo_config.get('component', '')
            metadata = f"({component}/{env})" if component and env else f"({component or env})" if (component or env) else ""
            
            if not quiet:
                if remote_branch:
                    print(f"  [{idx}/{total_repos}] {repo_name} {metadata} [remote: {remote_branch}]", end='', flush=True)
                else:
                    print(f"  [{idx}/{total_repos}] {repo_name} {metadata}", end='', flush=True)
            
            logger.debug(f"Scanning repository: {repo_config['path']}{f' ({remote_branch})' if remote_branch else ''}")
            
            apps = self.repo_analyzer.find_splunk_apps(repo, remote_branch=remote_branch)
            
            # Add metadata to apps
            self._enhance_app_metadata(apps, repo_config, repo)
            all_apps.extend(apps)
            
            # Show results for this repo
            repo_time = time.time() - repo_start
            if not quiet:
                print(f" → {len(apps)} apps ({repo_time:.1f}s)")
            else:
                logger.debug(f"  {repo_name} {metadata} → {len(apps)} apps ({repo_time:.1f}s)")
        
        return all_apps
    
    def _should_skip_repo(self, repo_config: Dict, component_filter: Optional[str], 
                          environment_filter: Optional[str], region_filter: Optional[str]) -> bool:
        """Check if repo should be skipped based on filters"""
        if not self._matches_environment_filter(repo_config, environment_filter):
            return True
        if not self._matches_region_filter(repo_config, region_filter):
            return True
        if not self._matches_component_filter(repo_config, component_filter):
            return True
        return False
    
    @staticmethod
    def _matches_environment_filter(repo_config: Dict, environment_filter: Optional[str]) -> bool:
        """Check if repo matches environment filter
        
        Supports comma-separated environment filters (e.g., 'nonprod,shared')
        """
        if not environment_filter:
            return True
        
        # Split comma-separated environments and normalize (prod = shared)
        allowed_envs = []
        for env in environment_filter.split(','):
            env_normalized = env.strip().lower()
            allowed_envs.append(env_normalized)
            # If 'shared' or 'prod' specified, allow both
            if env_normalized == 'shared':
                allowed_envs.append('prod')
            elif env_normalized == 'prod':
                allowed_envs.append('shared')
        
        repo_env = repo_config.get('environment')
        if repo_env:
            # Check if repo environment matches any of the allowed environments
            if repo_env.lower() in allowed_envs:
                return True
            logger.debug(f"Skipping {repo_config['path']} (environment '{repo_env}' not in {allowed_envs})")
            return False
        
        # If no explicit environment set, try to detect from path
        repo_lower = str(repo_config['path']).lower()
        for env in allowed_envs:
            if env in repo_lower:
                return True
        
        logger.debug(f"Skipping {repo_config['path']} (no matching environment in {allowed_envs})")
        return False
    
    @staticmethod
    def _matches_region_filter(repo_config: Dict, region_filter: Optional[str]) -> bool:
        """Check if repo matches region filter"""
        if not region_filter:
            return True
        
        repo_region = repo_config.get('region')
        if repo_region and repo_region.lower() != region_filter.lower():
            logger.debug(f"Skipping {repo_config['path']} (region '{repo_region}' != '{region_filter}')")
            return False
        
        if not repo_region:
            repo_lower = str(repo_config['path']).lower()
            if region_filter.lower() not in repo_lower:
                logger.debug(f"Skipping {repo_config['path']} (no matching region)")
                return False
        
        return True
    
    @staticmethod
    def _matches_component_filter(repo_config: Dict, component_filter: Optional[str]) -> bool:
        """Check if repo matches component filter"""
        if not component_filter:
            return True
        
        repo_component = repo_config.get('component')
        if repo_component and repo_component.lower() != component_filter.lower():
            logger.debug(f"Skipping {repo_config['path']} (component '{repo_component}' != '{component_filter}')")
            return False
        
        if not repo_component:
            # Fallback to path-based detection
            repo_lower = str(repo_config['path']).lower()
            if not SplunkAppUpdater._component_in_path(component_filter, repo_lower):
                return False
        
        return True
    
    @staticmethod
    def _component_in_path(component_filter: str, repo_lower: str) -> bool:
        """Check if component is in repo path"""
        if component_filter == 'ds' and 'ds-config' not in repo_lower and 'deployment' not in repo_lower:
            logger.debug(f"Skipping (not deployment-server component)")
            return False
        elif component_filter == 'shc' and 'sh-config' not in repo_lower and 'search' not in repo_lower and 'shcluster' not in repo_lower:
            logger.debug(f"Skipping (not search-head component)")
            return False
        elif component_filter == 'cm' and 'cm-config' not in repo_lower and 'cluster' not in repo_lower and 'manager' not in repo_lower:
            logger.debug(f"Skipping (not cluster-manager component)")
            return False
        return True
    
    @staticmethod
    def _enhance_app_metadata(apps: List[SplunkApp], repo_config: Dict, repo: Path):
        """Add environment, region, component metadata to apps"""
        for app in apps:
            app_path_lower = str(app.local_path).lower()
            detected_env = SplunkAppUpdater._detect_environment(app_path_lower)
            
            app.environment = detected_env if detected_env else repo_config.get('environment')
            app.region = repo_config.get('region')
            app.component = repo_config.get('component')
            app.repo_root = repo
    
    @staticmethod
    def _detect_environment(app_path_lower: str) -> Optional[str]:
        """Detect environment from app path"""
        if '\\shared\\' in app_path_lower or '/shared/' in app_path_lower:
            return 'shared'
        elif '\\nonprod\\' in app_path_lower or '/nonprod/' in app_path_lower or '\\non-prod\\' in app_path_lower or '/non-prod/' in app_path_lower:
            return 'non-prod'
        elif '\\prod\\' in app_path_lower or '/prod/' in app_path_lower:
            if 'nonprod' not in app_path_lower and 'non-prod' not in app_path_lower:
                return 'prod'
        return None
    
    def check_for_updates(self, apps: List[SplunkApp]) -> List[SplunkApp]:
        """Check which apps have updates available on Splunkbase"""
        apps_with_updates = []
        
        # Log apps without IDs so the user knows to add them
        apps_without_ids = [app for app in apps if not app.splunkbase_id]
        if apps_without_ids:
            unique_missing = sorted(set(app.name for app in apps_without_ids))
            logger.info(f"{len(unique_missing)} app(s) have no Splunkbase ID and will be skipped: {', '.join(unique_missing[:10])}")
            logger.info("Add missing IDs to config.yaml under 'splunkbase_id_mapping'")
        
        for app in apps:
            if not self._can_check_update(app):
                continue
            
            # Check if update is already pending (unless skipping tracking)
            repo_path = app.repo_root if app.repo_root else app.local_path.parent
            if not self.skip_tracking and self.tracker.is_update_pending(app.name, repo_path, app.latest_version or "", app.local_path):
                pending = self.tracker.get_pending_update(app.name, repo_path, app.local_path)
                if pending:
                    logger.info(f"Skipping {app.name}: Update already pending in branch '{pending['branch_name']}'")
                    continue
            
            # Get available versions from Splunkbase
            available_versions = self.splunkbase_client.get_available_versions(app.splunkbase_id)
            if not available_versions:
                logger.warning(f"No versions available for {app.name} on Splunkbase")
                continue
            
            # Filter by Splunk compatibility if configured
            splunk_version = self.config_manager.get_splunk_version()
            if splunk_version and self.config_manager.should_check_compatibility():
                logger.debug(f"Checking compatibility with Splunk {splunk_version} for {app.name}")
                compatible_versions = self.splunkbase_client.get_compatible_versions_for_splunk(
                    app.splunkbase_id, splunk_version, max_versions=len(available_versions)
                )
                if compatible_versions:
                    logger.info(f"{app.name}: {len(compatible_versions)}/{len(available_versions)} versions compatible with Splunk {splunk_version}")
                    available_versions = compatible_versions
                else:
                    logger.warning(f"{app.name}: No versions compatible with Splunk {splunk_version}")
                    continue
            
            latest_version = available_versions[0]
            target_version = latest_version
            
            # Check if current version is still available on Splunkbase
            if app.current_version not in available_versions:
                app.current_version_unavailable = True
                logger.debug(f"{app.name}: Current version {app.current_version} not available on Splunkbase")
            
            # For shared/prod environments, try to match non-prod version
            needs_version_selection = False
            if app.environment and app.environment.lower() in ['shared', 'prod']:
                nonprod_version = self.find_nonprod_version(app.name, app.component)
                
                if nonprod_version:
                    logger.debug(f"VERSION CHECK - {app.name}: Looking for non-prod version '{nonprod_version}' in available versions: {available_versions[:5]}")
                    # Check if non-prod version is available on Splunkbase
                    if nonprod_version in available_versions:
                        target_version = nonprod_version
                        logger.debug(f"VERSION MATCH - {app.name} [{app.environment}/{app.component}]: Using non-prod version {nonprod_version} (latest on Splunkbase: {latest_version})")
                        logger.info(f"Using non-prod version {nonprod_version} for {app.name} (environment: {app.environment})")
                    else:
                        logger.debug(f"VERSION MISMATCH - '{nonprod_version}' not in {available_versions[:10]}")
                        app.nonprod_version_unavailable = True
                        app.nonprod_version_requested = nonprod_version
                        logger.debug(f"Non-prod version {nonprod_version} not found on Splunkbase for {app.name}")
                        # Use non-prod version anyway - it exists in non-prod so it's the correct version
                        target_version = nonprod_version
                        logger.debug(f"VERSION OVERRIDE - Using non-prod version {nonprod_version} anyway (exists in non-prod)")
                        logger.info(f"Using non-prod version {nonprod_version} for {app.name} even though not found on Splunkbase (exists in non-prod)")
                else:
                    logger.info(f"No non-prod version found for {app.name}, will prompt user to select version")
                    needs_version_selection = True
            
            app.latest_version = target_version
            logger.debug(f"VERSION SET - {app.name}: app.latest_version = {app.latest_version}, target_version = {target_version}")
            app.available_versions = available_versions  # Store for potential user selection
            app.needs_version_selection = needs_version_selection
            
            # Check again with the target version
            if not self.skip_tracking and self.tracker.is_update_pending(app.name, repo_path, target_version, app.local_path):
                pending = self.tracker.get_pending_update(app.name, repo_path, app.local_path)
                if pending:
                    logger.info(f"Skipping {app.name}: Update to v{target_version} already pending in branch '{pending['branch_name']}'")
                    continue
            
            if version_compare(target_version, app.current_version) > 0:
                app.needs_update = True
                apps_with_updates.append(app)
                logger.info(f"Update available for {app.name}: {app.current_version} -> {target_version}")
            else:
                logger.info(f"{app.name} is up to date (v{app.current_version})")
        
        return apps_with_updates
    
    @staticmethod
    def _can_check_update(app: SplunkApp) -> bool:
        """Check if app can be checked for updates"""
        if not app.splunkbase_id:
            logger.debug(f"Skipping {app.name}: No Splunkbase ID found (likely a custom app)")
            return False
        
        if not str(app.splunkbase_id).isdigit():
            logger.warning(f"Skipping {app.name}: Invalid Splunkbase ID '{app.splunkbase_id}' (must be numeric)")
            return False
        
        return True
    
    def update_app(self, app: SplunkApp, create_branch: bool = True) -> bool:
        """Download and update a single app"""
        logger.info(f"Updating {app.instance_id} from v{app.current_version} to v{app.latest_version}")
        logger.info(f"  Target path: {app.local_path}")
        
        repo_path = app.repo_root if app.repo_root else app.local_path.parent
        branch_manager = GitBranchManager(repo_path)
        original_branch = branch_manager.get_current_branch()
        
        try:
            if create_branch:
                if not self._create_and_checkout_branch(branch_manager, app):
                    return False
            
            if not self._download_and_extract_app(app):
                return False
            
            self._backup_current_app(app)
            
            if not self._copy_app_files(app):
                return False
            
            if create_branch:
                if not self._commit_changes(branch_manager, app, repo_path, original_branch):
                    return False
                
                # Track the update
                if not self.skip_tracking and app.branch_name:
                    self.tracker.track_update(
                        app.name,
                        repo_path,
                        app.current_version,
                        app.latest_version,
                        app.branch_name,
                        app.local_path,
                        app.environment,
                        app.region,
                        self.is_test
                    )
                
                self._return_to_original_branch(branch_manager, original_branch, repo_path)
            
            logger.info(f"Successfully updated {app.name}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating {app.name}: {e}")
            if create_branch and original_branch:
                self._return_to_original_branch(branch_manager, original_branch, repo_path)
            return False
    
    def _create_and_checkout_branch(self, branch_manager: GitBranchManager, app: SplunkApp) -> bool:
        """Create and checkout branch for app update"""
        branch_name = branch_manager.create_update_branch(
            app.name, 
            app.latest_version,
            environment=app.environment,
            region=app.region,
            component=app.component
        )
        if not branch_name:
            logger.error(f"Failed to create branch for {app.name}")
            return False
        
        # Store branch name for tracking
        app.branch_name = branch_name
        return True
    
    def _create_and_checkout_group_branch(self, branch_manager: GitBranchManager, 
                                          app: SplunkApp, regions: List[str] = None) -> Optional[str]:
        """Create and checkout branch for grouped app update
        
        When updating multiple regions, don't include region in branch name.
        """
        # Use None for region when updating multiple locations
        region = None if regions else app.region
        
        branch_name = branch_manager.create_update_branch(
            app.name, 
            app.latest_version,
            environment=app.environment,
            region=region,
            component=app.component
        )
        if not branch_name:
            logger.error(f"Failed to create branch for {app.name}")
            return None
        
        return branch_name
    
    def _download_and_extract_app(self, app: SplunkApp) -> bool:
        """Download and extract app from Splunkbase"""
        download_dir = self.work_dir / 'downloads'
        download_dir.mkdir(parents=True, exist_ok=True)
        
        manual_dir = self.config_manager.get_manual_download_directory()
        
        # Pass the target version to enable caching
        archive_path = self.splunkbase_client.download_app(
            app.splunkbase_id, 
            download_dir, 
            manual_dir,
            version=app.latest_version
        )
        if not archive_path:
            logger.error(f"Failed to download {app.name}")
            if manual_dir:
                logger.info(f"TIP: Place the downloaded file in: {manual_dir}")
            return False
        
        # Use a unique extraction directory per app+version to avoid collisions
        safe_name = f"{app.splunkbase_id}_{app.latest_version}".replace('.', '_')
        extract_dir = self.work_dir / 'extracted' / safe_name
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extracted_app_dir = self.file_manager.extract_archive(archive_path, extract_dir)
        if not extracted_app_dir:
            logger.error(f"Failed to extract {app.name}")
            return False
        
        app.extracted_dir = extracted_app_dir  # Store for later use
        return True
    
    def _backup_current_app(self, app: SplunkApp):
        """Backup current version of app"""
        backup_dir = self.work_dir / 'backups' / f"{app.name}_{app.current_version}"
        if app.local_path.exists():
            shutil.copytree(app.local_path, backup_dir, dirs_exist_ok=True)
            logger.info(f"Backed up current version to {backup_dir}")
    
    def _copy_app_files(self, app: SplunkApp) -> bool:
        """Copy app files with component filtering"""
        preserve_paths = self.config_manager.get_preserve_paths(app.name)
        if preserve_paths:
            logger.info(f"Will preserve custom paths for {app.name}: {preserve_paths}")
        if not self.file_manager.copy_app(app.extracted_dir, app.local_path, app.component, preserve_paths):
            logger.error(f"Failed to copy {app.name}")
            return False
        return True
    
    def _copy_app_files_for_instance(self, source_app: SplunkApp, target_app: SplunkApp) -> bool:
        """Copy app files for a specific instance with component filtering"""
        preserve_paths = self.config_manager.get_preserve_paths(target_app.name)
        if preserve_paths:
            logger.info(f"Will preserve custom paths for {target_app.name}: {preserve_paths}")
        if not self.file_manager.copy_app(source_app.extracted_dir, target_app.local_path, target_app.component, preserve_paths):
            logger.error(f"Failed to copy {target_app.name}")
            return False
        return True
    
    def _commit_changes(self, branch_manager: GitBranchManager, app: SplunkApp, 
                       repo_path: Path, original_branch: Optional[str]) -> bool:
        """Commit app changes"""
        commit_message = f"Update {app.name} from v{app.current_version} to v{app.latest_version}"
        success = branch_manager.stage_and_commit(
            app.local_path, 
            commit_message,
            environment=app.environment,
            region=app.region
        )
        if not success:
            logger.error(f"Failed to commit changes for {app.name} - verification failed")
            if original_branch:
                branch_manager.checkout_branch(original_branch)
            return False
        return True
    
    def _commit_group_changes(self, branch_manager: GitBranchManager, app: SplunkApp,
                             all_paths: List[Path], repo_path: Path, 
                             original_branch: Optional[str]) -> bool:
        """Commit changes for grouped app updates"""
        commit_message = f"Update {app.name} from v{app.current_version} to v{app.latest_version} in {len(all_paths)} location(s)"
        
        # Stage and commit all paths
        success = branch_manager.stage_and_commit_multiple(
            all_paths,
            commit_message,
            environment=app.environment
        )
        if not success:
            logger.error(f"Failed to commit changes for {app.name} - verification failed")
            if original_branch:
                branch_manager.checkout_branch(original_branch)
            return False
        return True
    
    def _track_group_update(self, primary_app: SplunkApp, app_instances: List[SplunkApp],
                           repo_path: Path, branch_name: str):
        """Track update for a group of app instances"""
        # Track each instance separately but in same branch
        for app_instance in app_instances:
            self.tracker.track_update(
                app_instance.name,
                repo_path,
                app_instance.current_version,
                app_instance.latest_version,
                branch_name,
                app_instance.local_path,
                app_instance.environment,
                app_instance.region,
                self.is_test
            )
    
    @staticmethod
    def _return_to_original_branch(branch_manager: GitBranchManager, original_branch: Optional[str], repo_path: Path):
        """Return to original branch after update"""
        if original_branch:
            if branch_manager.checkout_branch(original_branch):
                logger.info(f"Returned to branch: {original_branch}")
            else:
                logger.warning(f"Could not return to original branch {original_branch}")
    
    def update_all_apps(self, apps: List[SplunkApp], create_branches: bool = True) -> Dict[str, bool]:
        """Update all apps that need updates
        
        Groups apps by name/version/repo so multiple instances (e.g., east/west)
        are updated in a single branch.
        """
        results = {}
        
        # Group apps by (name, latest_version, repo_root)
        app_groups = self._group_apps_for_update(apps)
        
        for group_key, app_instances in app_groups.items():
            app_name, version, repo = group_key
            if len(app_instances) > 1:
                logger.info(f"Updating {len(app_instances)} instances of {app_name} v{version} in {repo}")
            
            success = self._update_app_group(app_instances, create_branches)
            results[app_name] = success
        
        return results
    
    def _group_apps_for_update(self, apps: List[SplunkApp]) -> Dict[tuple, List[SplunkApp]]:
        """Group apps by name, version, and repository"""
        groups = {}
        
        for app in apps:
            if not app.needs_update:
                continue
            
            repo_path = app.repo_root if app.repo_root else app.local_path.parent
            key = (app.name, app.latest_version, str(repo_path))
            
            if key not in groups:
                groups[key] = []
            groups[key].append(app)
        
        return groups
    
    def _update_app_group(self, app_instances: List[SplunkApp], create_branch: bool) -> bool:
        """Update a group of app instances (same app in multiple locations) together"""
        if not app_instances:
            return False
        
        # Use first app for metadata (they should all be the same app)
        primary_app = app_instances[0]
        repo_path = primary_app.repo_root if primary_app.repo_root else primary_app.local_path.parent
        branch_manager = GitBranchManager(repo_path)
        original_branch = branch_manager.get_current_branch()
        
        # Collect all regions for logging
        regions = list(set(app.region for app in app_instances if app.region))
        region_str = f" across {len(app_instances)} location(s)" if len(app_instances) > 1 else ""
        logger.info(f"Updating {primary_app.name} from v{primary_app.current_version} to v{primary_app.latest_version}{region_str}")
        
        try:
            branch_name = None
            if create_branch:
                # Create branch without region-specific info when updating multiple locations
                branch_name = self._create_and_checkout_group_branch(
                    branch_manager, primary_app, regions if len(regions) > 1 else None
                )
                if not branch_name:
                    return False
            
            # Download once, use for all instances
            if not self._download_and_extract_app(primary_app):
                return False
            
            # Update each instance
            all_paths = []
            for app_instance in app_instances:
                logger.info(f"  Updating instance at: {app_instance.local_path}")
                self._backup_current_app(app_instance)
                
                if not self._copy_app_files_for_instance(primary_app, app_instance):
                    logger.error(f"Failed to copy files for {app_instance.local_path}")
                    if create_branch and original_branch:
                        self._return_to_original_branch(branch_manager, original_branch, repo_path)
                    return False
                
                all_paths.append(app_instance.local_path)
            
            if create_branch:
                if not self._commit_group_changes(branch_manager, primary_app, all_paths, repo_path, original_branch):
                    return False
                
                # Track the update with all app paths
                if not self.skip_tracking and branch_name:
                    self._track_group_update(primary_app, app_instances, repo_path, branch_name)
                
                # Push branch if auto_push is enabled
                if self.config_manager.should_auto_push() and branch_name:
                    logger.info(f"Auto-pushing branch {branch_name} to remote...")
                    if branch_manager.push_branch(branch_name):
                        logger.info(f"Successfully pushed {branch_name} to remote")
                        # Mark as pushed in tracker
                        if not self.skip_tracking:
                            self.tracker.mark_pushed(branch_name, f"origin/{branch_name}")
                    else:
                        logger.warning(f"Failed to push {branch_name} to remote")
                
                self._return_to_original_branch(branch_manager, original_branch, repo_path)
            
            logger.info(f"Successfully updated {primary_app.name} in {len(app_instances)} location(s)")
            return True
            
        except Exception as e:
            logger.error(f"Error updating {primary_app.name}: {e}", exc_info=True)
            if create_branch and original_branch:
                self._return_to_original_branch(branch_manager, original_branch, repo_path)
            return False
    
    def generate_report(self, apps: List[SplunkApp], results: Dict[str, bool]) -> str:
        """Generate a summary report of updates"""
        report_lines = []
        report_lines.extend(self._report_header())
        report_lines.extend(self._report_summary(apps))
        report_lines.extend(self._report_update_results(apps, results))
        report_lines.extend(self._report_up_to_date(apps))
        report_lines.append("")
        report_lines.append("=" * 80)
        
        return "\n".join(report_lines)
    
    @staticmethod
    def _report_header() -> List[str]:
        """Generate report header"""
        return [
            "=" * 80,
            "SPLUNK APP UPDATE REPORT",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 80,
            ""
        ]
    
    @staticmethod
    def _report_summary(apps: List[SplunkApp]) -> List[str]:
        """Generate report summary section"""
        apps_needing_update = [app for app in apps if app.needs_update]
        return [
            f"Total apps checked: {len(apps)}",
            f"Apps needing updates: {len(apps_needing_update)}",
            ""
        ]
    
    @staticmethod
    def _report_update_results(apps: List[SplunkApp], results: Dict[str, bool]) -> List[str]:
        """Generate report update results section"""
        apps_needing_update = [app for app in apps if app.needs_update]
        if not apps_needing_update:
            return []
        
        lines = ["UPDATE RESULTS:", "-" * 80]
        for app in apps_needing_update:
            status = "SUCCESS" if results.get(app.name, False) else "FAILED"
            lines.append(f"  [{status}] {app.name}: v{app.current_version} -> v{app.latest_version}")
            
            metadata = app.metadata_parts()
            if metadata:
                lines.append(f"    {' | '.join(metadata)}")
            
            lines.append(f"    Path: {app.local_path}")
            lines.append("")
        
        return lines
    
    @staticmethod
    def _report_up_to_date(apps: List[SplunkApp]) -> List[str]:
        """Generate report up-to-date apps section"""
        up_to_date_apps = [app for app in apps if not app.needs_update and app.splunkbase_id]
        if not up_to_date_apps:
            return []
        
        lines = ["APPS UP TO DATE:", "-" * 80]
        for app in up_to_date_apps:
            lines.append(f"  {app.name}: v{app.current_version}")
        lines.append("")
        
        return lines
    
    def cleanup_work_dir(self, max_backups: int = 10):
        """Remove old backups and extracted directories to reclaim disk space.
        
        Keeps the *max_backups* most-recent backup directories.  Extracted
        directories are always removed since they are recreated on each run.
        
        Args:
            max_backups: Number of most-recent backups to keep (default 10).
        """
        # Clean extracted directories
        extracted_dir = self.work_dir / 'extracted'
        if extracted_dir.exists():
            shutil.rmtree(extracted_dir, ignore_errors=True)
            logger.debug("Cleaned up extracted directory")
        
        # Prune old backups
        backup_dir = self.work_dir / 'backups'
        if backup_dir.exists():
            backups = sorted(backup_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            for old_backup in backups[max_backups:]:
                shutil.rmtree(old_backup, ignore_errors=True)
                logger.debug(f"Removed old backup: {old_backup.name}")
            pruned = max(0, len(backups) - max_backups)
            if pruned:
                logger.info(f"Cleaned up {pruned} old backup(s)")
