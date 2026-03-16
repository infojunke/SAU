"""Git commit-based caching for repository scans

Caches scanned app data with Git commit hashes as cache keys,
allowing instant lookups when a repository hasn't changed.
Works offline once cached.
"""

import json
import logging
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import SplunkApp
from .utils import find_git_root, safe_cache_path

logger = logging.getLogger(__name__)


@dataclass
class RepoScanEntry:
    """A cached repository scan result"""
    repo_path: str
    remote_branch: Optional[str]
    commit_hash: str
    scanned_at: str  # ISO format timestamp
    app_count: int
    apps_data: List[Dict[str, Any]]  # Serialized SplunkApp objects
    
    def to_apps(self) -> List[SplunkApp]:
        """Convert cached data back to SplunkApp objects"""
        apps = []
        for app_data in self.apps_data:
            try:
                # Handle Path conversion
                local_path = app_data.get('local_path')
                if local_path:
                    app_data['local_path'] = Path(local_path)
                apps.append(SplunkApp(**app_data))
            except Exception as e:
                logger.warning(f"Failed to deserialize cached app: {e}")
        return apps
    
    @staticmethod
    def from_apps(
        repo_path: str,
        remote_branch: Optional[str],
        commit_hash: str,
        apps: List[SplunkApp]
    ) -> 'RepoScanEntry':
        """Create a cache entry from scanned apps"""
        apps_data = []
        for app in apps:
            app_dict = {
                'name': app.name,
                'local_path': str(app.local_path) if app.local_path else None,
                'current_version': app.current_version,
                'splunkbase_id': app.splunkbase_id,
                'deployment_types': app.deployment_types,
            }
            apps_data.append(app_dict)
        
        return RepoScanEntry(
            repo_path=repo_path,
            remote_branch=remote_branch,
            commit_hash=commit_hash,
            scanned_at=datetime.now().isoformat(),
            app_count=len(apps),
            apps_data=apps_data
        )


class RepoScanCache:
    """Git commit-based cache for repository scans
    
    Instead of using time-based expiration, this cache validates entries
    by comparing Git commit hashes. If the repository hasn't changed
    (same commit hash), the cached scan results are returned immediately.
    
    Features:
    - Commit hash validation (not time-based TTL)
    - Offline support (uses cache even if Git commands fail)
    - Fallback to cached data when network is unavailable
    
    Example:
        cache = RepoScanCache(Path("./work/cache"))
        
        # Check cache before scanning
        commit_hash = cache.get_commit_hash(repo_path, remote_branch)
        cached_apps = cache.get(repo_path, remote_branch, commit_hash)
        
        if cached_apps is not None:
            return cached_apps  # Cache hit!
        
        # Scan and cache
        apps = scan_repository(repo_path)
        cache.set(repo_path, remote_branch, commit_hash, apps)
    """
    
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir / "repo_scans"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: Dict[str, RepoScanEntry] = {}
    
    def _get_cache_key(self, repo_path: Path, remote_branch: Optional[str]) -> str:
        """Generate a cache key from repo path and branch"""
        key = str(repo_path.resolve())
        if remote_branch:
            key += f"::{remote_branch}"
        return key
    
    def _get_cache_path(self, cache_key: str) -> Path:
        """Get the file path for a cache key"""
        return safe_cache_path(self.cache_dir, cache_key)
    
    def get_commit_hash(self, repo_path: Path, remote_branch: Optional[str] = None) -> Optional[str]:
        """Get the current commit hash for a repository
        
        Args:
            repo_path: Path to the repository
            remote_branch: Remote branch to check (e.g., 'origin/main')
            
        Returns:
            Commit hash string, or None if unable to determine
        """
        git_root = find_git_root(repo_path)
        if not git_root:
            return None
        
        try:
            if remote_branch:
                # Get commit hash of remote branch
                result = subprocess.run(
                    ['git', 'rev-parse', remote_branch],
                    cwd=git_root,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
            else:
                # Get current HEAD commit hash
                result = subprocess.run(
                    ['git', 'rev-parse', 'HEAD'],
                    cwd=git_root,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
            
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                logger.debug(f"Failed to get commit hash: {result.stderr.strip()}")
                return None
                
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.debug(f"Error getting commit hash for {repo_path}: {e}")
            return None
    
    def get(
        self, 
        repo_path: Path, 
        remote_branch: Optional[str],
        current_commit: Optional[str]
    ) -> Optional[List[SplunkApp]]:
        """Get cached scan results if commit hash matches
        
        Args:
            repo_path: Path to the repository
            remote_branch: Remote branch name (or None for local)
            current_commit: Current commit hash to validate against
            
        Returns:
            List of cached SplunkApp objects if valid cache exists,
            None if cache miss or commit changed
        """
        cache_key = self._get_cache_key(repo_path, remote_branch)
        
        # Try memory cache first
        if cache_key in self._memory_cache:
            entry = self._memory_cache[cache_key]
            if current_commit is None or entry.commit_hash == current_commit:
                logger.debug(f"Memory cache hit for {repo_path}")
                return entry.to_apps()
            else:
                logger.debug(f"Memory cache invalidated (commit changed) for {repo_path}")
                del self._memory_cache[cache_key]
        
        # Try disk cache
        cache_path = self._get_cache_path(cache_key)
        if not cache_path.exists():
            logger.debug(f"No disk cache for {repo_path}")
            return None
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            entry = RepoScanEntry(**data)
            
            # Validate commit hash
            if current_commit is not None and entry.commit_hash != current_commit:
                logger.debug(f"Disk cache invalidated (commit changed) for {repo_path}")
                logger.debug(f"  Cached: {entry.commit_hash[:8]}, Current: {current_commit[:8]}")
                return None
            
            # If we couldn't get current commit (offline), use cached data anyway
            if current_commit is None:
                logger.info(f"Using offline cache for {repo_path} (scanned: {entry.scanned_at})")
            else:
                logger.debug(f"Disk cache hit for {repo_path}")
            
            # Store in memory cache
            self._memory_cache[cache_key] = entry
            return entry.to_apps()
            
        except (json.JSONDecodeError, OSError, TypeError, KeyError) as e:
            logger.warning(f"Failed to load repo cache for {repo_path}: {e}")
            return None
    
    def set(
        self,
        repo_path: Path,
        remote_branch: Optional[str],
        commit_hash: str,
        apps: List[SplunkApp]
    ):
        """Cache repository scan results
        
        Args:
            repo_path: Path to the repository
            remote_branch: Remote branch name (or None for local)
            commit_hash: Current commit hash
            apps: List of discovered SplunkApp objects
        """
        cache_key = self._get_cache_key(repo_path, remote_branch)
        entry = RepoScanEntry.from_apps(
            str(repo_path.resolve()),
            remote_branch,
            commit_hash,
            apps
        )
        
        # Save to disk
        cache_path = self._get_cache_path(cache_key)
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(asdict(entry), f, indent=2)
            # Update memory cache
            self._memory_cache[cache_key] = entry
            logger.debug(f"Cached scan for {repo_path}: {len(apps)} apps at commit {commit_hash[:8]}")
        except OSError as e:
            logger.error(f"Failed to cache repo scan for {repo_path}: {e}")
    
    def invalidate(self, repo_path: Path, remote_branch: Optional[str] = None):
        """Invalidate cache for a repository
        
        Args:
            repo_path: Path to the repository
            remote_branch: Remote branch name (or None for local)
        """
        cache_key = self._get_cache_key(repo_path, remote_branch)
        
        # Remove from memory cache
        self._memory_cache.pop(cache_key, None)
        
        # Remove from disk cache
        cache_path = self._get_cache_path(cache_key)
        cache_path.unlink(missing_ok=True)
        logger.debug(f"Invalidated cache for {repo_path}")
    
    def clear_all(self):
        """Clear all cached scan data"""
        self._memory_cache.clear()
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink(missing_ok=True)
        logger.info("Cleared all repo scan cache")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_files = list(self.cache_dir.glob("*.json"))
        total_apps = 0
        oldest_scan = None
        newest_scan = None
        
        for cache_file in total_files:
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                total_apps += data.get('app_count', 0)
                scanned_at = data.get('scanned_at')
                if scanned_at:
                    if oldest_scan is None or scanned_at < oldest_scan:
                        oldest_scan = scanned_at
                    if newest_scan is None or scanned_at > newest_scan:
                        newest_scan = scanned_at
            except (json.JSONDecodeError, OSError):
                pass
        
        return {
            'cached_repos': len(total_files),
            'cached_apps': total_apps,
            'oldest_scan': oldest_scan,
            'newest_scan': newest_scan,
            'memory_entries': len(self._memory_cache)
        }
