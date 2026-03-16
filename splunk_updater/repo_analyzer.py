"""GitLab repository analyzer for finding Splunk apps"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

from .models import SplunkApp
from .utils import find_git_root, detect_default_branch

if TYPE_CHECKING:
    from .repo_cache import RepoScanCache

logger = logging.getLogger(__name__)


class GitLabRepoAnalyzer:
    """Analyzes GitLab repositories to find Splunk apps
    
    Supports optional caching based on Git commit hashes.
    When cache is enabled, unchanged repositories return cached results instantly.
    """
    
    def __init__(
        self, 
        id_mapping: Optional[Dict[str, str]] = None,
        repo_cache: Optional['RepoScanCache'] = None
    ):
        self.id_mapping = id_mapping or {}
        self.repo_cache = repo_cache
    
    def find_splunk_apps(
        self, 
        repo_path: Path, 
        remote_branch: Optional[str] = None,
        use_cache: bool = True
    ) -> List[SplunkApp]:
        """Find all Splunk apps in a GitLab repository
        
        Args:
            repo_path: Path to the repository
            remote_branch: Read from remote branch instead of local files (e.g., 'origin/main')
            use_cache: Whether to use cached results if available (default: True)
            
        Returns:
            List of SplunkApp objects found in the repository
        """
        # Resolve 'auto' to actual branch name for caching
        resolved_branch = remote_branch
        if remote_branch and remote_branch.lower() == 'auto':
            git_root = find_git_root(repo_path)
            if git_root:
                resolved_branch = self._detect_default_remote_branch(git_root)
                logger.debug(f"Resolved 'auto' to branch: {resolved_branch}")
        
        # Check cache if enabled
        current_commit = None
        if use_cache and self.repo_cache:
            current_commit = self.repo_cache.get_commit_hash(repo_path, resolved_branch)
            cached_apps = self.repo_cache.get(repo_path, resolved_branch, current_commit)
            
            if cached_apps is not None:
                logger.debug(f"Using cached scan for {repo_path} ({len(cached_apps)} apps)")
                return cached_apps
        
        # Perform actual scan (use original remote_branch to maintain existing logic)
        if remote_branch:
            apps = self._find_apps_from_remote(repo_path, remote_branch)
        else:
            apps = self._find_apps_from_local(repo_path)
        
        # Cache results using resolved branch name
        if use_cache and self.repo_cache and current_commit:
            self.repo_cache.set(repo_path, resolved_branch, current_commit, apps)
        
        return apps
    
    def _find_apps_from_local(self, repo_path: Path) -> List[SplunkApp]:
        """Find Splunk apps from local filesystem"""
        apps = []
        
        # Look for app.conf files which indicate Splunk apps
        for app_conf in repo_path.rglob('app.conf'):
            app_dir = app_conf.parent.parent  # Go up from default/ or local/ to app root
            
            # Parse app.conf to get app info
            app_info = self._parse_app_conf(app_conf)
            if app_info:
                app_name = app_info.get('name', app_dir.name)
                
                # Try to get Splunkbase ID from multiple sources (in priority order)
                splunkbase_id = (
                    app_info.get('id') or  # From app.conf [package] or [install] section
                    self._get_id_from_splunkbase_manifest(app_dir) or  # From splunkbase.manifest
                    self._get_id_from_app_manifest(app_dir) or  # From app.manifest 
                    self.id_mapping.get(app_name) or  # From config mapping by app name
                    self.id_mapping.get(app_dir.name)  # From config mapping by directory name
                )
                
                app = SplunkApp(
                    name=app_name,
                    local_path=app_dir,
                    current_version=app_info.get('version', 'unknown'),
                    splunkbase_id=splunkbase_id,
                    deployment_types=self._detect_deployment_types(app_dir)
                )
                apps.append(app)
                
                id_info = f"(ID: {splunkbase_id})" if splunkbase_id else "(No Splunkbase ID)"
                logger.debug(f"Found app: {app.name} v{app.current_version} {id_info} at {app_dir}")
        
        return apps
    
    def _detect_default_remote_branch(self, git_root: Path) -> Optional[str]:
        """Detect the default remote branch (main or master)"""
        return detect_default_branch(git_root, include_remote_prefix=True)
    
    def _find_apps_from_remote(self, repo_path: Path, remote_branch: str) -> List[SplunkApp]:
        """Find Splunk apps from a remote git branch"""
        apps = []
        
        # Find the actual git root (might be a parent directory)
        git_root = find_git_root(repo_path)
        if not git_root:
            logger.error(f"Could not find git repository root for {repo_path}")
            return apps
        
        # Auto-detect branch if needed
        if remote_branch.lower() == 'auto':
            detected_branch = self._detect_default_remote_branch(git_root)
            if detected_branch:
                logger.info(f"Auto-detected remote branch: {detected_branch} for {git_root}")
                remote_branch = detected_branch
            else:
                logger.error(f"Could not auto-detect default remote branch for {git_root}")
                return apps
        
        # Get the relative path from git root to repo_path
        try:
            rel_path = repo_path.relative_to(git_root)
            path_prefix = str(rel_path).replace('\\', '/') + '/' if rel_path != Path('.') else ''
        except ValueError:
            # repo_path is not relative to git_root
            path_prefix = ''
        
        try:
            # First, try to fetch the remote to ensure we have the latest refs
            logger.debug(f"Fetching remote for {git_root}")
            fetch_result = subprocess.run(
                ['git', 'fetch', '--quiet'],
                cwd=git_root,
                capture_output=True,
                text=True,
                timeout=30
            )
            if fetch_result.returncode != 0:
                logger.warning(f"Could not fetch remote for {git_root}: {fetch_result.stderr.strip()}")
            
            # List all files in the remote branch
            result = subprocess.run(
                ['git', 'ls-tree', '-r', '--name-only', remote_branch],
                cwd=git_root,
                capture_output=True,
                text=True,
                check=True
            )
            
            all_files = result.stdout.strip().split('\n')
            
            # Filter to files within our path prefix and find app.conf files
            if path_prefix:
                all_files = [f for f in all_files if f.startswith(path_prefix)]
            
            app_conf_files = [f for f in all_files if f.endswith('/default/app.conf') or f.endswith('/local/app.conf')]
            
            for app_conf_path in app_conf_files:
                # Get app directory (remove /default/app.conf or /local/app.conf)
                app_dir_path = app_conf_path.rsplit('/default/', 1)[0] if '/default/' in app_conf_path else app_conf_path.rsplit('/local/', 1)[0]
                
                # Read app.conf content from remote
                app_info = self._parse_app_conf_from_remote(git_root, remote_branch, app_conf_path)
                if not app_info:
                    continue
                
                app_name = app_info.get('name', Path(app_dir_path).name)
                
                # Try to get Splunkbase ID
                splunkbase_id = (
                    app_info.get('id') or
                    self._get_id_from_remote_manifest(git_root, remote_branch, app_dir_path, 'splunkbase.manifest') or
                    self._get_id_from_remote_manifest(git_root, remote_branch, app_dir_path, 'app.manifest') or
                    self.id_mapping.get(app_name) or
                    self.id_mapping.get(Path(app_dir_path).name)
                )
                
                # Convert git path to local path (remove path_prefix if present)
                if path_prefix and app_dir_path.startswith(path_prefix):
                    relative_app_path = app_dir_path[len(path_prefix):]
                else:
                    relative_app_path = app_dir_path
                
                # Create app object with local path
                app = SplunkApp(
                    name=app_name,
                    local_path=repo_path / relative_app_path,
                    current_version=app_info.get('version', 'unknown'),
                    splunkbase_id=splunkbase_id,
                    deployment_types=[]  # Can't detect from remote easily
                )
                apps.append(app)
                
                id_info = f"(ID: {splunkbase_id})" if splunkbase_id else "(No Splunkbase ID)"
                logger.debug(f"Found app from {remote_branch}: {app.name} v{app.current_version} {id_info} at {app_dir_path}")
        
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            
            # Provide helpful error messages
            if "Not a valid object name" in error_msg or "unknown revision" in error_msg:
                logger.error(f"Remote branch '{remote_branch}' not found in {git_root}")
                logger.error(f"Tip: Run 'git fetch' first, or check available branches with 'git branch -r'")
            else:
                logger.error(f"Error reading from remote branch {remote_branch}: {error_msg}")
        
        return apps
    
    def _parse_app_conf_from_remote(self, repo_path: Path, remote_branch: str, file_path: str) -> Optional[Dict]:
        """Parse app.conf from remote branch"""
        try:
            result = subprocess.run(
                ['git', 'show', f'{remote_branch}:{file_path}'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return self._parse_app_conf_lines(result.stdout.splitlines())
        except subprocess.CalledProcessError:
            return None
    
    def _get_id_from_remote_manifest(self, repo_path: Path, remote_branch: str, app_dir: str, manifest_file: str) -> Optional[str]:
        """Get Splunkbase ID from manifest file in remote branch"""
        try:
            manifest_path = f"{app_dir}/{manifest_file}"
            result = subprocess.run(
                ['git', 'show', f'{remote_branch}:{manifest_path}'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            manifest = json.loads(result.stdout)
            return self._extract_id_from_manifest(manifest, manifest_file)
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
            return None
    
    def _parse_app_conf(self, app_conf_path: Path) -> Optional[Dict]:
        """Parse app.conf file to extract app metadata"""
        try:
            with open(app_conf_path, 'r', encoding='utf-8') as f:
                return self._parse_app_conf_lines(f)
        except Exception as e:
            logger.error(f"Error parsing app.conf at {app_conf_path}: {e}")
            return None
    
    def _parse_app_conf_lines(self, lines) -> Optional[Dict]:
        """Parse app.conf key-value pairs from an iterable of lines.
        
        Shared by both local file and remote (git show) parsing paths.
        """
        app_info = {}
        current_section = None
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('[') and line.endswith(']'):
                current_section = line[1:-1]
                continue
            if '=' in line and current_section:
                key, value = line.split('=', 1)
                self._extract_field(app_info, current_section, key.strip(), value.strip())
        
        return app_info if app_info else None
    
    @staticmethod
    def _extract_field(app_info: Dict, section: str, key: str, value: str):
        """Extract field from app.conf section"""
        if section == 'launcher':
            if key in ['version', 'description']:
                app_info[key] = value
        elif section == 'id':
            if key in ['name', 'version']:
                app_info[key] = value
        elif section == 'ui':
            if key == 'label':
                app_info['label'] = value
        elif section == 'package':
            if key == 'id' and value.isdigit():
                app_info['id'] = value
        elif section == 'install':
            if key in ['splunkbase_id', 'id']:
                app_info['id'] = value
    
    @staticmethod
    def _extract_id_from_manifest(manifest: dict, manifest_type: str) -> Optional[str]:
        """Extract Splunkbase ID from a parsed manifest dict.
        
        Shared by both local file and remote (git show) manifest parsing.
        """
        if manifest_type == 'splunkbase.manifest':
            app_id = manifest.get('app', {}).get('id')
        else:  # app.manifest
            app_id = (
                manifest.get('splunkbase_id') or
                manifest.get('info', {}).get('splunkbase_id') or
                manifest.get('info', {}).get('id', {}).get('splunkbase_id')
            )
        return str(app_id) if app_id else None

    @staticmethod
    def _get_id_from_splunkbase_manifest(app_dir: Path) -> Optional[str]:
        """Extract Splunkbase ID from splunkbase.manifest file"""
        manifest_path = app_dir / 'splunkbase.manifest'
        if not manifest_path.exists():
            return None
        
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
                return GitLabRepoAnalyzer._extract_id_from_manifest(manifest, 'splunkbase.manifest')
        except Exception as e:
            logger.debug(f"Error parsing splunkbase.manifest at {manifest_path}: {e}")
        
        return None
    
    @staticmethod
    def _get_id_from_app_manifest(app_dir: Path) -> Optional[str]:
        """Extract Splunkbase ID from app.manifest file
        
        Note: app.manifest typically doesn't contain the Splunkbase ID directly,
        but we check it for completeness in case it's added in future formats.
        """
        manifest_path = app_dir / 'app.manifest'
        if not manifest_path.exists():
            return None
        
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
                return GitLabRepoAnalyzer._extract_id_from_manifest(manifest, 'app.manifest')
        except Exception as e:
            logger.debug(f"Error parsing app.manifest at {manifest_path}: {e}")
        
        return None
    
    @staticmethod
    def _detect_deployment_types(app_dir: Path) -> List[str]:
        """Detect which deployment types an app is configured for (informational only)"""
        deployment_types = []
        
        # Check for specific indicators
        has_inputs = (app_dir / 'default' / 'inputs.conf').exists() or \
                     (app_dir / 'local' / 'inputs.conf').exists()
        has_views = (app_dir / 'default' / 'data' / 'ui' / 'views').exists()
        has_indexes = (app_dir / 'default' / 'indexes.conf').exists() or \
                      (app_dir / 'local' / 'indexes.conf').exists()
        
        # Heuristics for deployment type
        if has_inputs:
            deployment_types.append('forwarder')
        if has_views:
            deployment_types.append('searchhead')
        if has_indexes:
            deployment_types.append('indexer')
        
        # If no specific indicators, assume it could be deployed anywhere
        if not deployment_types:
            deployment_types = ['indexer', 'searchhead', 'forwarder']
        
        return deployment_types
