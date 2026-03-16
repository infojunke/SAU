"""Track pending app updates to avoid duplicate updates"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

from .enums import UpdateStatus

logger = logging.getLogger(__name__)

# Platform-specific file locking
try:
    import msvcrt
    def _lock_file(f):
        """Lock file on Windows using msvcrt"""
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, max(os.fstat(f.fileno()).st_size, 1))
    def _unlock_file(f):
        """Unlock file on Windows using msvcrt"""
        try:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, max(os.fstat(f.fileno()).st_size, 1))
        except OSError:
            pass
except ImportError:
    try:
        import fcntl
        def _lock_file(f):
            """Lock file on Unix using fcntl"""
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        def _unlock_file(f):
            """Unlock file on Unix using fcntl"""
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except ImportError:
        def _lock_file(f):
            """No-op: file locking not available on this platform"""
            pass
        def _unlock_file(f):
            """No-op: file locking not available on this platform"""
            pass


class UpdateTracker:
    """Tracks pending app updates across multiple runs"""
    
    def __init__(self, tracking_file: Path = None):
        if tracking_file is None:
            tracking_file = Path("work/update_tracking.json")
        self.tracking_file = tracking_file
        self.tracking_file.parent.mkdir(parents=True, exist_ok=True)
        self.updates = self._load_tracking()
    
    def _load_tracking(self) -> Dict:
        """Load tracking data from file with file locking"""
        if not self.tracking_file.exists():
            return {"updates": []}
        
        try:
            with open(self.tracking_file, 'r') as f:
                try:
                    _lock_file(f)
                except OSError:
                    logger.debug("Could not acquire read lock on tracking file, proceeding without lock")
                try:
                    return json.load(f)
                finally:
                    _unlock_file(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Could not load tracking file: {e}. Starting fresh.")
            return {"updates": []}
    
    def _save_tracking(self):
        """Save tracking data to file with file locking"""
        try:
            with open(self.tracking_file, 'w') as f:
                try:
                    _lock_file(f)
                except OSError:
                    logger.debug("Could not acquire write lock on tracking file, proceeding without lock")
                try:
                    json.dump(self.updates, f, indent=2)
                finally:
                    _unlock_file(f)
        except IOError as e:
            logger.error(f"Could not save tracking file: {e}")
    
    def is_update_pending(self, app_name: str, repo_path: Union[str, Path], new_version: str, app_path: Union[str, Path] = None) -> bool:
        """Check if an update is already pending for this app
        
        Args:
            app_name: Name of the app
            repo_path: Root path of the repository
            new_version: Version to update to
            app_path: Specific path to the app installation (optional, for disambiguation)
        """
        for update in self.updates["updates"]:
            if (update["app_name"] == app_name and 
                update["repo_path"] == str(repo_path) and
                update["new_version"] == new_version and
                update["status"] == UpdateStatus.PENDING.value):
                # If app_path is provided, also check it for exact match
                if app_path:
                    if update.get("app_path") == str(app_path):
                        return True
                else:
                    # Backward compatibility: if no app_path specified, match on other fields
                    return True
        return False
    
    def get_pending_update(self, app_name: str, repo_path: Union[str, Path], app_path: Union[str, Path] = None) -> Optional[Dict]:
        """Get pending update details for an app
        
        Args:
            app_name: Name of the app
            repo_path: Root path of the repository
            app_path: Specific path to the app installation (optional, for disambiguation)
        """
        for update in self.updates["updates"]:
            if (update["app_name"] == app_name and 
                update["repo_path"] == str(repo_path) and
                update["status"] == UpdateStatus.PENDING.value):
                # If app_path is provided, also check it for exact match
                if app_path:
                    if update.get("app_path") == str(app_path):
                        return update
                else:
                    # Backward compatibility: if no app_path specified, return first match
                    return update
        return None
    
    def track_update(self, app_name: str, repo_path: Path, old_version: str, 
                    new_version: str, branch_name: str, app_path: Path = None,
                    environment: Optional[str] = None, region: Optional[str] = None,
                    is_test: bool = False):
        """Record a new update
        
        Args:
            app_name: Name of the app
            repo_path: Root path of the repository
            old_version: Current version
            new_version: Version to update to
            branch_name: Git branch name for the update
            app_path: Specific path to the app installation
            environment: Environment (prod, nonprod, shared, etc.)
            region: Region identifier
            is_test: Mark this as a test update (not for production)
        """
        from .git_manager import GitBranchManager
        
        # Get remote tracking info
        git_manager = GitBranchManager(repo_path)
        remote_info = git_manager.get_remote_info()
        remote_branch = git_manager.get_remote_branch_name(branch_name)
        is_pushed = git_manager.is_branch_on_remote(branch_name)
        
        update_record = {
            "app_name": app_name,
            "repo_path": str(repo_path),
            "app_path": str(app_path) if app_path else None,
            "old_version": old_version,
            "new_version": new_version,
            "branch_name": branch_name,
            "environment": environment,
            "region": region,
            "timestamp": datetime.now().isoformat(),
            "status": UpdateStatus.PENDING.value,
            "is_test": is_test,
            "remote_url": remote_info.get('url') if remote_info else None,
            "remote_branch": remote_branch if is_pushed else None,
            "is_pushed": is_pushed,
            "gitlab_mr_url": None,  # Will be set when MR is created
            "last_modified": datetime.now().isoformat()
        }
        
        self.updates["updates"].append(update_record)
        self._save_tracking()
        
        test_marker = " (TEST)" if is_test else ""
        logger.info(f"Tracked update for {app_name} in branch {branch_name}{test_marker}")
    
    def mark_merged(self, branch_name: str, merge_commit: str = None):
        """Mark an update as merged
        
        Args:
            branch_name: Branch that was merged
            merge_commit: Optional merge commit hash
        """
        for update in self.updates["updates"]:
            if update["branch_name"] == branch_name:
                update["status"] = UpdateStatus.MERGED.value
                update["merged_at"] = datetime.now().isoformat()
                update["last_modified"] = datetime.now().isoformat()
                if merge_commit:
                    update["merge_commit"] = merge_commit
                self._save_tracking()
                logger.info(f"Marked {update['app_name']} as merged")
                return True
        return False
    
    def mark_pushed(self, branch_name: str, remote_branch: str = None):
        """Mark a branch as pushed to remote
        
        Args:
            branch_name: Local branch name
            remote_branch: Remote branch name (e.g., 'origin/branch-name')
        """
        from .git_manager import mr_url_from_update
        
        for update in self.updates["updates"]:
            if update["branch_name"] == branch_name:
                update["is_pushed"] = True
                update["remote_branch"] = remote_branch or f"origin/{branch_name}"
                update["pushed_at"] = datetime.now().isoformat()
                update["last_modified"] = datetime.now().isoformat()
                
                # Try to generate GitLab MR URL with app details
                mr_url = mr_url_from_update(update)
                if mr_url:
                    update["gitlab_mr_url"] = mr_url
                
                self._save_tracking()
                logger.info(f"Marked {update['app_name']} branch as pushed to remote")
                return True
        return False
    
    def set_gitlab_mr_url(self, branch_name: str, mr_url: str):
        """Set GitLab MR URL for a tracked update
        
        Args:
            branch_name: Branch name
            mr_url: GitLab merge request URL
        """
        for update in self.updates["updates"]:
            if update["branch_name"] == branch_name:
                update["gitlab_mr_url"] = mr_url
                update["last_modified"] = datetime.now().isoformat()
                self._save_tracking()
                logger.info(f"Set GitLab MR URL for {update['app_name']}")
                return True
        return False
    
    def get_all_pending(self, include_test: bool = True) -> List[Dict]:
        """Get all pending updates
        
        Args:
            include_test: Include test updates (default: True)
        """
        pending = [u for u in self.updates["updates"] if u["status"] == UpdateStatus.PENDING.value]
        if not include_test:
            pending = [u for u in pending if not u.get("is_test", False)]
        return pending
    
    def get_pending_by_repo(self, repo_path: Path, include_test: bool = True) -> List[Dict]:
        """Get pending updates for a specific repository
        
        Args:
            repo_path: Repository path
            include_test: Include test updates (default: True)
        """
        pending = [u for u in self.updates["updates"] 
                   if u["repo_path"] == str(repo_path) and u["status"] == UpdateStatus.PENDING.value]
        if not include_test:
            pending = [u for u in pending if not u.get("is_test", False)]
        return pending
    
    def get_unpushed_updates(self) -> List[Dict]:
        """Get pending updates that haven't been pushed to remote"""
        return [u for u in self.updates["updates"] 
                if u["status"] == UpdateStatus.PENDING.value and not u.get("is_pushed", False)]
    
    def get_updates_without_mr(self) -> List[Dict]:
        """Get pending updates that don't have a GitLab MR URL yet"""
        return [u for u in self.updates["updates"] 
                if u["status"] == UpdateStatus.PENDING.value and not u.get("gitlab_mr_url")]
    
    def get_test_updates(self) -> List[Dict]:
        """Get all test updates"""
        return [u for u in self.updates["updates"] if u.get("is_test", False)]
    
    def clear_all(self):
        """Clear all tracking data"""
        self.updates = {"updates": []}
        self._save_tracking()
        logger.info("Cleared all tracking data")
    
    def clear_merged(self):
        """Remove merged updates from tracking"""
        before_count = len(self.updates["updates"])
        self.updates["updates"] = [u for u in self.updates["updates"] 
                                   if u["status"] == UpdateStatus.PENDING.value]
        after_count = len(self.updates["updates"])
        removed = before_count - after_count
        self._save_tracking()
        logger.info(f"Removed {removed} merged updates from tracking")
        return removed
    
    def remove_branch(self, branch_name: str) -> bool:
        """Remove a specific branch from tracking"""
        before_count = len(self.updates["updates"])
        self.updates["updates"] = [u for u in self.updates["updates"] 
                                   if u["branch_name"] != branch_name]
        after_count = len(self.updates["updates"])
        
        if before_count > after_count:
            self._save_tracking()
            logger.info(f"Removed tracking for branch {branch_name}")
            return True
        return False
    
    def get_stats(self) -> Dict:
        """Get statistics about tracked updates"""
        all_updates = self.updates["updates"]
        pending = [u for u in all_updates if u["status"] == UpdateStatus.PENDING.value]
        merged = [u for u in all_updates if u["status"] == UpdateStatus.MERGED.value]
        
        return {
            "total": len(all_updates),
            "pending": len(pending),
            "merged": len(merged)
        }
    
    def get_pending_branches_with_diffs(self, base_branch: str = 'main') -> Dict[str, Dict]:
        """Get pending updates organized by branch with their diffs
        
        Args:
            base_branch: The base branch to compare against (default: 'main')
        
        Returns:
            Dict mapping branch names to branch info including diff and updates
        """
        from .git_manager import GitBranchManager
        
        pending = self.get_all_pending()
        branches = {}
        
        for update in pending:
            branch_name = update['branch_name']
            repo_path = Path(update['repo_path'])
            
            if branch_name not in branches:
                # Get diff for this branch
                git_manager = GitBranchManager(repo_path)
                diff = git_manager.get_branch_diff(branch_name, base_branch)
                files_changed = git_manager.get_branch_file_changes(branch_name, base_branch)
                
                branches[branch_name] = {
                    'repo_path': str(repo_path),
                    'updates': [],
                    'diff': diff,
                    'files_changed': files_changed or []
                }
            
            branches[branch_name]['updates'].append(update)
        
        return branches
    
    def generate_diff_report(self, base_branch: str = 'main', include_full_diff: bool = True) -> str:
        """Generate a report showing diffs for all pending branches
        
        Args:
            base_branch: The base branch to compare against (default: 'main')
            include_full_diff: Whether to include full diff output (default: True)
        
        Returns:
            Formatted diff report as string
        """
        branches = self.get_pending_branches_with_diffs(base_branch)
        
        if not branches:
            return "No pending updates with diffs to display."
        
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("PENDING UPDATES - DIFF REPORT")
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"Base branch: {base_branch}")
        report_lines.append("=" * 80)
        report_lines.append("")
        
        for branch_name, branch_info in sorted(branches.items()):
            report_lines.append("#" * 80)
            report_lines.append(f"BRANCH: {branch_name}")
            report_lines.append("#" * 80)
            report_lines.append(f"Repository: {branch_info['repo_path']}")
            report_lines.append("")
            
            # List updates in this branch
            report_lines.append("Updates in this branch:")
            for update in branch_info['updates']:
                env_region = ""
                if update.get('environment'):
                    env_region += f" [{update['environment']}"
                    if update.get('region'):
                        env_region += f"/{update['region']}"
                    env_region += "]"
                
                report_lines.append(f"  • {update['app_name']}: v{update['old_version']} -> v{update['new_version']}{env_region}")
                if update.get('app_path'):
                    report_lines.append(f"    Path: {update['app_path']}")
            
            report_lines.append("")
            
            # List files changed
            if branch_info['files_changed']:
                report_lines.append(f"Files changed ({len(branch_info['files_changed'])}):")
                for file_path in sorted(branch_info['files_changed']):
                    report_lines.append(f"  {file_path}")
                report_lines.append("")
            
            # Show diff
            if include_full_diff:
                if branch_info['diff']:
                    report_lines.append("-" * 80)
                    report_lines.append("DIFF:")
                    report_lines.append("-" * 80)
                    report_lines.append(branch_info['diff'])
                    report_lines.append("")
                else:
                    report_lines.append("[WARN]  No diff available (branch may not exist or has no changes)")
                    report_lines.append("")
            else:
                report_lines.append("(Use --full-diff to see complete diff output)")
                report_lines.append("")
            
            report_lines.append("")
        
        report_lines.append("=" * 80)
        report_lines.append(f"Total branches: {len(branches)}")
        report_lines.append("=" * 80)
        
        return "\n".join(report_lines)
