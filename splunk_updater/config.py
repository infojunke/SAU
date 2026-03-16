"""Configuration management for Splunk app updater"""

import logging
import os
import tempfile
import yaml
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from .models import DeploymentConfig

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages configuration from YAML file"""
    
    def __init__(self, config_path: str = 'config.yaml'):
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        """Load configuration from YAML file"""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded configuration from {self.config_path}")
            return config
        except FileNotFoundError:
            logger.error(f"Configuration file {self.config_path} not found")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML config: {e}")
            raise
    
    def get_gitlab_repos(self) -> List[Dict]:
        """Get list of GitLab repository configurations
        
        Returns list of dicts with keys: path, environment, region, component
        Supports both old string format and new dict format for backward compatibility
        """
        repos = self.config.get('gitlab_repos', [])
        normalized_repos = []
        
        for repo in repos:
            if isinstance(repo, str):
                # Old format: simple string path
                normalized_repos.append({
                    'path': repo,
                    'environment': None,
                    'region': None,
                    'component': None
                })
            elif isinstance(repo, dict):
                # New format: dict with metadata
                normalized_repos.append({
                    'path': repo.get('path', repo.get('repo', '')),
                    'environment': repo.get('environment'),
                    'region': repo.get('region'),
                    'component': repo.get('component')
                })
        
        return normalized_repos
    
    def get_splunkbase_credentials(self) -> Tuple[str, str]:
        """Get Splunkbase username and password.
        
        Environment variables ``SPLUNKBASE_USERNAME`` and ``SPLUNKBASE_PASSWORD``
        take precedence over the config file values.
        """
        import os
        creds = self.config.get('splunkbase_credentials', {})
        username = os.environ.get('SPLUNKBASE_USERNAME') or creds.get('username', '')
        password = os.environ.get('SPLUNKBASE_PASSWORD') or creds.get('password', '')
        return username, password
    
    def get_deployment_config(self) -> DeploymentConfig:
        """Get deployment configuration"""
        deploy = self.config.get('deployment', {})
        return DeploymentConfig(
            indexer_dirs=deploy.get('indexer_dirs', ['bin', 'default', 'metadata']),
            searchhead_dirs=deploy.get('searchhead_dirs', ['bin', 'default', 'metadata', 'local']),
            forwarder_dirs=deploy.get('forwarder_dirs', ['bin', 'default']),
            indexer_excludes=deploy.get('indexer_excludes', []),
            searchhead_excludes=deploy.get('searchhead_excludes', []),
            forwarder_excludes=deploy.get('forwarder_excludes', []),
            heavy_forwarder_excludes=deploy.get('heavy_forwarder_excludes', []),
            global_excludes=deploy.get('global_excludes', [])
        )
    
    def get_work_directory(self) -> Path:
        """Get working directory for downloads and extraction"""
        work_dir = Path(self.config.get('work_directory', './work'))
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir
    
    def get_manual_download_directory(self) -> Optional[Path]:
        """Get manual download directory if configured"""
        manual_dir = self.config.get('manual_download_directory')
        if manual_dir:
            path = Path(manual_dir)
            path.mkdir(parents=True, exist_ok=True)
            return path
        return None
    
    def get_splunkbase_id_mapping(self) -> Dict[str, str]:
        """Get mapping of app names to Splunkbase IDs"""
        return self.config.get('splunkbase_id_mapping', {})
    
    def get_sha256_checksums(self) -> Dict[str, str]:
        """Get SHA256 checksums for specific app versions
        
        Returns dict mapping "app_id:version" to sha256 hash
        Example: {"742:9.1.2": "abc123...", "833:10.2.0": "def456..."}
        """
        return self.config.get('sha256_checksums', {})
    
    def get_splunk_version(self) -> Optional[str]:
        """Get target Splunk Enterprise version for compatibility checking
        
        Returns version string like "9.0.0" or None if not configured
        """
        return self.config.get('splunk_version')
    
    def should_check_compatibility(self) -> bool:
        """Check if compatibility checking is enabled"""
        return self.config.get('check_splunk_compatibility', False)
    
    def save_splunkbase_id(self, app_name: str, app_id: str) -> bool:
        """Save a discovered Splunkbase ID to the config file
        
        Uses YAML round-trip (load → modify → atomic write) to avoid
        brittle line-by-line text manipulation.
        
        Args:
            app_name: Name of the app
            app_id: Splunkbase ID (must be numeric)
        
        Returns:
            True if saved successfully
        """
        # Validate that the ID is numeric
        if not app_id or not str(app_id).isdigit():
            logger.warning(f"Invalid Splunkbase ID '{app_id}' for {app_name} - must be numeric, not saving")
            return False
        
        try:
            # Re-read the config file to avoid overwriting concurrent changes
            with open(self.config_path, 'r') as f:
                file_config = yaml.safe_load(f) or {}
            
            # Update the mapping
            if 'splunkbase_id_mapping' not in file_config:
                file_config['splunkbase_id_mapping'] = {}
            
            file_config['splunkbase_id_mapping'][app_name] = app_id
            
            # Atomic write: write to temp file in same directory, then rename
            config_dir = os.path.dirname(os.path.abspath(self.config_path))
            fd, tmp_path = tempfile.mkstemp(dir=config_dir, suffix='.yaml.tmp')
            try:
                with os.fdopen(fd, 'w') as f:
                    yaml.dump(file_config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
                os.replace(tmp_path, self.config_path)
            except Exception:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            
            # Update in-memory config to match
            self.config = file_config
            
            logger.info(f"Saved Splunkbase ID for {app_name} to config: {app_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save Splunkbase ID for {app_name}: {e}")
            return False
    
    def get_preserve_paths(self, app_name: str) -> List[str]:
        """Get list of file/folder paths to preserve during updates for a specific app
        
        These are paths relative to the app root (e.g., 'bin/custom_script.sh').
        The local/ folder is always preserved automatically and doesn't need to be listed.
        
        Args:
            app_name: Name of the app (e.g., 'SA-ldapsearch')
        
        Returns:
            List of relative paths to preserve, or empty list
        """
        preserve_config = self.config.get('preserve_paths', {})
        return preserve_config.get(app_name, [])
    
    def get_git_settings(self) -> Dict:
        """Get git settings including auto_push configuration"""
        return self.config.get('git_settings', {})
    
    def should_auto_push(self) -> bool:
        """Check if branches should be automatically pushed"""
        git_settings = self.get_git_settings()
        return git_settings.get('auto_push', False)
