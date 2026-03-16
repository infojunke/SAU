"""Git branch management for app updates"""

import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .utils import find_git_root, detect_default_branch, parse_gitlab_remote_url

logger = logging.getLogger(__name__)


class GitBranchManager:
    """Manages Git branches for app updates"""
    
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.git_root = find_git_root(repo_path) or repo_path  # Actual Git repository root
        self.expected_paths = []  # Track expected file paths for verification
        self.expected_environment = None
        self.expected_region = None
    
    def create_update_branch(self, app_name: str, new_version: str, environment: Optional[str] = None, region: Optional[str] = None, component: Optional[str] = None) -> Optional[str]:
        """Create a new branch for app update"""
        try:
            branch_name = self._build_branch_name(app_name, new_version, environment, region, component)
            
            # If branch already exists locally, delete it first (stale from a previous run)
            if self._branch_exists(branch_name):
                logger.warning(f"Branch {branch_name} already exists locally - deleting stale branch")
                self._delete_local_branch(branch_name)
            
            self._create_branch(branch_name)
            return branch_name
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Error with branch operation: {e.stderr}")
            return None
    
    def _build_branch_name(self, app_name: str, new_version: str, environment: Optional[str] = None, region: Optional[str] = None, component: Optional[str] = None) -> str:
        """Build branch name for app update
        
        Args:
            app_name: Name of the app
            new_version: Version to update to
            environment: Environment (prod, non-prod, shared)
            region: Region identifier
            component: Component type (ds, shc, cm)
        
        Returns:
            Branch name string (format: YYYYMMDD-component-env-region-app-vX_X_X)
        """
        safe_version = self._sanitize_version(new_version)
        safe_app_name = app_name.replace(' ', '-').replace('_', '-')
        prefix = self._build_branch_prefix(environment, region, component)
        date_prefix = datetime.now().strftime('%Y%m%d')
        return f"{date_prefix}-{prefix}-{safe_app_name}-v{safe_version}"
    
    @staticmethod
    def _sanitize_version(version: str) -> str:
        """Sanitize version string for branch name"""
        return version.replace('.', '_').replace('/', '-').replace(':', '-')
    
    @staticmethod
    def _build_branch_prefix(environment: Optional[str], region: Optional[str], component: Optional[str] = None) -> str:
        """Build branch prefix from component, environment and region"""
        prefix_parts = []
        if component:
            prefix_parts.append(component.lower())
        if environment:
            prefix_parts.append(environment.lower())
        if region:
            prefix_parts.append(region.lower())
        return '-'.join(prefix_parts) if prefix_parts else 'update'
    
    def _branch_exists(self, branch_name: str) -> bool:
        """Check if branch exists"""
        result = subprocess.run(
            ['git', 'rev-parse', '--verify', branch_name],
            cwd=self.git_root,
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    
    def _delete_local_branch(self, branch_name: str):
        """Delete a local branch (force delete)
        
        Used to clean up stale branches from previous runs before recreating.
        """
        # Make sure we're not on the branch we're trying to delete
        current = self.get_current_branch()
        if current == branch_name:
            # Switch to default branch first
            base_branch = self._detect_default_branch() or 'main'
            subprocess.run(
                ['git', 'checkout', base_branch],
                cwd=self.git_root,
                capture_output=True,
                text=True
            )
        
        result = subprocess.run(
            ['git', 'branch', '-D', branch_name],
            cwd=self.git_root,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            logger.info(f"Deleted stale local branch: {branch_name}")
        else:
            logger.warning(f"Could not delete branch {branch_name}: {result.stderr.strip()}")
    
    def _checkout_branch(self, branch_name: str):
        """Checkout existing branch"""
        logger.info(f"Branch {branch_name} already exists, checking out...")
        subprocess.run(
            ['git', 'checkout', branch_name],
            cwd=self.git_root,
            capture_output=True,
            text=True,
            check=True
        )
    
    def _create_branch(self, branch_name: str):
        """Create and checkout new branch from the default branch (main/master)
        
        Always creates from the default branch to ensure branch isolation.
        Each app update branch only contains commits for that specific app.
        """
        # Determine the base branch to create from
        base_branch = self._detect_default_branch() or 'main'
        
        # First checkout the base branch to ensure clean starting point
        try:
            subprocess.run(
                ['git', 'checkout', base_branch],
                cwd=self.git_root,
                capture_output=True,
                text=True,
                check=True
            )
            logger.debug(f"Checked out base branch '{base_branch}' before creating new branch")
        except subprocess.CalledProcessError as e:
            logger.warning(f"Could not checkout base branch '{base_branch}': {e.stderr}")
            # Try 'master' as fallback if 'main' failed
            if base_branch == 'main':
                try:
                    subprocess.run(
                        ['git', 'checkout', 'master'],
                        cwd=self.git_root,
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    base_branch = 'master'
                    logger.debug(f"Fell back to 'master' branch")
                except subprocess.CalledProcessError:
                    logger.warning("Could not checkout 'main' or 'master', creating branch from current HEAD")
        
        # Create the new branch from current position (which is now the base branch)
        subprocess.run(
            ['git', 'checkout', '-b', branch_name],
            cwd=self.git_root,
            capture_output=True,
            text=True,
            check=True
        )
        logger.info(f"Created branch: {branch_name} (from {base_branch})")
    
    def ensure_gitattributes(self) -> bool:
        """Ensure .gitattributes exists in the repo to prevent line ending issues.
        
        On Windows, core.autocrlf=true can convert line endings in binary files
        like .rtf, causing Git to think they are modified. A .gitattributes file
        marks these file types as binary to prevent conversion.
        
        Returns:
            True if .gitattributes was created or updated, False if already correct
        """
        gitattributes_path = self.git_root / '.gitattributes'
        
        # Binary extensions commonly found in Splunk apps
        required_entries = [
            '# Splunk app binary files - prevent line ending conversion',
            '*.rtf binary',
            '*.pdf binary',
            '*.png binary',
            '*.jpg binary',
            '*.jpeg binary',
            '*.gif binary',
            '*.ico binary',
            '*.bmp binary',
            '*.tgz binary',
            '*.gz binary',
            '*.tar binary',
            '*.zip binary',
            '*.spl binary',
            '*.pyc binary',
            '*.pyo binary',
            '*.so binary',
            '*.dll binary',
            '*.exe binary',
        ]
        
        existing_content = ''
        if gitattributes_path.exists():
            existing_content = gitattributes_path.read_text(encoding='utf-8', errors='replace')
            # Check if binary entries already present
            if '*.rtf binary' in existing_content:
                logger.debug(".gitattributes already has binary file entries")
                return False
        
        # Append our entries
        with open(gitattributes_path, 'a', encoding='utf-8') as f:
            if existing_content and not existing_content.endswith('\n'):
                f.write('\n')
            if existing_content:
                f.write('\n')  # Blank line separator
            f.write('\n'.join(required_entries))
            f.write('\n')
        
        logger.info("Added binary file entries to .gitattributes to prevent line ending issues")
        return True
    
    def set_expected_paths(self, app_path: Path, environment: Optional[str] = None, region: Optional[str] = None):
        """Set expected file paths that should be changed"""
        try:
            rel_path = app_path.relative_to(self.git_root)
            self.expected_paths = [str(rel_path)]
            self.expected_environment = environment.lower() if environment else None
            self.expected_region = region.lower() if region else None
            
            logger.debug(f"Expected paths set: {self.expected_paths}")
            logger.debug(f"Expected environment: {self.expected_environment}, region: {self.expected_region}")
        except ValueError:
            logger.warning(f"Could not compute relative path for {app_path} from {self.repo_path}")
            self.expected_paths = []
    
    def verify_staged_changes(self) -> Tuple[bool, List[str]]:
        """Verify that staged changes match expected paths and environment/region"""
        try:
            staged_files = self._get_staged_files()
            
            if not staged_files:
                logger.info("No staged files to verify")
                return True, []
            
            unexpected_files = self._check_unexpected_files(staged_files)
            
            if unexpected_files:
                self._log_verification_failure(unexpected_files)
                return False, unexpected_files
            
            logger.info(f"Verified {len(staged_files)} staged files - all match expected scope")
            return True, []
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Error verifying staged changes: {e.stderr}")
            return False, []
    
    def _get_staged_files(self) -> List[str]:
        """Get list of staged files"""
        result = subprocess.run(
            ['git', 'diff', '--cached', '--name-only'],
            cwd=self.git_root,
            capture_output=True,
            text=True,
            check=True
        )
        return [f.strip() for f in result.stdout.strip().split('\n') if f.strip()]
    
    def _check_unexpected_files(self, staged_files: List[str]) -> List[str]:
        """Check for unexpected files in staged changes"""
        unexpected_files = []
        
        for staged_file in staged_files:
            if not self._is_expected_file(staged_file):
                unexpected_files.append(staged_file)
        
        return unexpected_files
    
    def _is_expected_file(self, staged_file: str) -> bool:
        """Check if a staged file is expected"""
        file_lower = staged_file.lower().replace('\\', '/')
        
        # Allow .gitattributes changes (managed by ensure_gitattributes)
        if file_lower == '.gitattributes':
            return True
        
        # Check if file is within expected app path - must match one of the expected paths
        for expected_path in self.expected_paths:
            expected_lower = expected_path.lower().replace('\\', '/')
            if file_lower.startswith(expected_lower):
                return True
        
        # File is not in any expected path
        return False
    
    def _log_verification_failure(self, unexpected_files: List[str]):
        """Log verification failure details"""
        logger.error("Staged changes contain unexpected files:")
        for f in unexpected_files:
            logger.error(f"  - {f}")
        logger.error(f"Expected paths: {self.expected_paths}")
        logger.error(f"Expected environment: {self.expected_environment}")
    
    def stage_and_commit(self, app_path: Path, message: str, environment: Optional[str] = None, region: Optional[str] = None) -> bool:
        """Stage and commit changes for an app with verification"""
        try:
            # Ensure .gitattributes exists to prevent line ending issues (e.g., .rtf files)
            if self.ensure_gitattributes():
                self._stage_gitattributes()
            
            self.set_expected_paths(app_path, environment, region)
            self._stage_app_changes(app_path)
            
            # Verify staged changes
            is_valid, unexpected_files = self.verify_staged_changes()
            if not is_valid:
                logger.error("VERIFICATION FAILED: Staged changes include unexpected files")
                logger.error("Unstaging all changes to prevent accidental commits")
                self._unstage_all()
                return False
            
            # Commit if there are changes
            return self._commit_changes(message)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Error committing changes: {e.stderr}")
            return False
    
    def stage_and_commit_multiple(self, app_paths: List[Path], message: str, environment: Optional[str] = None) -> bool:
        """Stage and commit changes for multiple app paths with verification
        
        Used when updating the same app in multiple locations (e.g., east and west regions).
        """
        try:
            # Set expected paths for all apps
            self.expected_paths = []
            for app_path in app_paths:
                try:
                    rel_path = app_path.relative_to(self.git_root)
                    self.expected_paths.append(str(rel_path))
                except ValueError:
                    logger.warning(f"Could not compute relative path for {app_path} from {self.git_root}")
            
            self.expected_environment = environment.lower() if environment else None
            self.expected_region = None  # Don't constrain by region when updating multiple locations
            
            # Ensure .gitattributes exists to prevent line ending issues (e.g., .rtf files)
            if self.ensure_gitattributes():
                self._stage_gitattributes()
            
            # Stage all app changes
            for app_path in app_paths:
                self._stage_app_changes(app_path)
            
            # Verify staged changes
            is_valid, unexpected_files = self.verify_staged_changes()
            if not is_valid:
                logger.error("VERIFICATION FAILED: Staged changes include unexpected files")
                logger.error("Unstaging all changes to prevent accidental commits")
                self._unstage_all()
                return False
            
            # Commit if there are changes
            return self._commit_changes(message)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Error committing changes: {e.stderr}")
            return False
    
    def _stage_app_changes(self, app_path: Path):
        """Stage changes for the app"""
        try:
            rel_path = app_path.relative_to(self.git_root)
            subprocess.run(
                ['git', 'add', str(rel_path)],
                cwd=self.git_root,
                capture_output=True,
                text=True,
                check=True
            )
            logger.info(f"Staged changes for: {rel_path}")
        except ValueError:
            subprocess.run(
                ['git', 'add', str(app_path)],
                cwd=self.git_root,
                capture_output=True,
                text=True,
                check=True
            )
            logger.info(f"Staged changes for: {app_path}")
    
    def _stage_gitattributes(self):
        """Stage the .gitattributes file"""
        subprocess.run(
            ['git', 'add', '.gitattributes'],
            cwd=self.git_root,
            capture_output=True,
            text=True,
            check=True
        )
        logger.info("Staged .gitattributes")
    
    def _unstage_all(self):
        """Unstage all changes"""
        subprocess.run(
            ['git', 'reset', 'HEAD'],
            cwd=self.git_root,
            capture_output=True,
            text=True
        )
    
    def _commit_changes(self, message: str) -> bool:
        """Commit staged changes if any exist"""
        status_result = subprocess.run(
            ['git', 'diff', '--cached', '--quiet'],
            cwd=self.git_root,
            capture_output=True,
            text=True
        )
        
        if status_result.returncode != 0:  # There are changes
            subprocess.run(
                ['git', 'commit', '-m', message],
                cwd=self.git_root,
                capture_output=True,
                text=True,
                check=True
            )
            logger.info(f"Committed changes: {message}")
        else:
            logger.warning(f"No changes to commit for: {message}")
        
        return True
    
    def checkout_branch(self, branch_name: str) -> bool:
        """Checkout a specific branch"""
        try:
            subprocess.run(
                ['git', 'checkout', branch_name],
                cwd=self.git_root,
                capture_output=True,
                text=True,
                check=True
            )
            logger.info(f"Checked out branch: {branch_name}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Error checking out branch {branch_name}: {e.stderr}")
            return False
    
    def get_current_branch(self) -> Optional[str]:
        """Get current branch name"""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                cwd=self.git_root,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None
    
    def get_branch_diff(self, branch_name: str, base_branch: str = 'main') -> Optional[str]:
        """Get diff for a specific branch compared to base branch
        
        Args:
            branch_name: The branch to get diff for
            base_branch: The base branch to compare against (default: 'main')
        
        Returns:
            Diff output as string, or None if error
        """
        try:
            # Check if branch exists
            result = subprocess.run(
                ['git', 'rev-parse', '--verify', branch_name],
                cwd=self.git_root,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                logger.warning(f"Branch {branch_name} does not exist")
                return None
            
            # Get the diff - use binary mode and decode with error handling
            result = subprocess.run(
                ['git', 'diff', f'{base_branch}...{branch_name}'],
                cwd=self.git_root,
                capture_output=True
            )
            
            # If base_branch doesn't exist, try 'master' as fallback
            if result.returncode != 0 and base_branch == 'main':
                logger.debug(f"Trying 'master' as fallback base branch")
                result = subprocess.run(
                    ['git', 'diff', f'master...{branch_name}'],
                    cwd=self.git_root,
                    capture_output=True
                )
            
            if result.returncode != 0:
                stderr_msg = result.stderr.decode('utf-8', errors='replace') if result.stderr else ''
                logger.error(f"Error getting diff for branch {branch_name}: {stderr_msg}")
                return None
            
            # Decode with error handling for non-UTF-8 characters
            try:
                diff_output = result.stdout.decode('utf-8', errors='replace')
            except Exception:
                diff_output = result.stdout.decode('latin-1', errors='replace')
            
            return diff_output.strip()
            
        except subprocess.CalledProcessError as e:
            stderr_msg = e.stderr.decode('utf-8', errors='replace') if isinstance(e.stderr, bytes) else str(e.stderr)
            logger.error(f"Error getting diff for branch {branch_name}: {stderr_msg}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting diff for branch {branch_name}: {e}")
            return None
    
    def get_branch_file_changes(self, branch_name: str, base_branch: str = 'main') -> Optional[List[str]]:
        """Get list of files changed in a branch
        
        Args:
            branch_name: The branch to check
            base_branch: The base branch to compare against (default: 'main')
        
        Returns:
            List of changed file paths, or None if error
        """
        try:
            result = subprocess.run(
                ['git', 'diff', '--name-only', f'{base_branch}...{branch_name}'],
                cwd=self.git_root,
                capture_output=True
            )
            
            # If base_branch doesn't exist, try 'master' as fallback
            if result.returncode != 0 and base_branch == 'main':
                logger.debug(f"Trying 'master' as fallback base branch for file changes")
                result = subprocess.run(
                    ['git', 'diff', '--name-only', f'master...{branch_name}'],
                    cwd=self.git_root,
                    capture_output=True
                )
            
            if result.returncode != 0:
                stderr_msg = result.stderr.decode('utf-8', errors='replace') if result.stderr else ''
                logger.error(f"Error getting file changes for branch {branch_name}: {stderr_msg}")
                return None
            
            # Decode with error handling
            try:
                output = result.stdout.decode('utf-8', errors='replace')
            except Exception:
                output = result.stdout.decode('latin-1', errors='replace')
            
            files = [f.strip() for f in output.strip().split('\n') if f.strip()]
            return files
            
        except subprocess.CalledProcessError as e:
            stderr_msg = e.stderr.decode('utf-8', errors='replace') if isinstance(e.stderr, bytes) else str(e.stderr)
            logger.error(f"Error getting file changes for branch {branch_name}: {stderr_msg}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting file changes for branch {branch_name}: {e}")
            return None
    
    def get_remote_info(self) -> Optional[dict]:
        """Get information about the remote repository
        
        Returns:
            Dict with 'name' and 'url' keys, or None if no remote
        """
        try:
            # Get remote name (usually 'origin')
            result = subprocess.run(
                ['git', 'remote'],
                cwd=self.git_root,
                capture_output=True,
                text=True,
                check=True
            )
            
            remotes = [r.strip() for r in result.stdout.strip().split('\n') if r.strip()]
            if not remotes:
                return None
            
            remote_name = remotes[0]  # Use first remote (usually 'origin')
            
            # Get remote URL
            result = subprocess.run(
                ['git', 'remote', 'get-url', remote_name],
                cwd=self.git_root,
                capture_output=True,
                text=True,
                check=True
            )
            
            remote_url = result.stdout.strip()
            
            return {
                'name': remote_name,
                'url': remote_url
            }
            
        except subprocess.CalledProcessError:
            logger.debug("No remote repository configured")
            return None
    
    def is_branch_on_remote(self, branch_name: str, remote: str = 'origin') -> bool:
        """Check if a branch exists on the remote
        
        Args:
            branch_name: Local branch name
            remote: Remote name (default: 'origin')
        
        Returns:
            True if branch exists on remote
        """
        try:
            result = subprocess.run(
                ['git', 'ls-remote', '--heads', remote, branch_name],
                cwd=self.git_root,
                capture_output=True,
                text=True
            )
            
            return result.returncode == 0 and result.stdout.strip() != ''
            
        except subprocess.CalledProcessError:
            return False
    
    def get_remote_branch_name(self, local_branch: str, remote: str = 'origin') -> Optional[str]:
        """Get the remote branch name for a local branch
        
        Args:
            local_branch: Local branch name
            remote: Remote name (default: 'origin')
        
        Returns:
            Remote branch name (e.g., 'origin/branch-name') or None
        """
        if self.is_branch_on_remote(local_branch, remote):
            return f"{remote}/{local_branch}"
        return None
    
    def _detect_default_branch(self) -> Optional[str]:
        """Detect the default branch name (main or master)"""
        return detect_default_branch(self.git_root, include_remote_prefix=False)
    
    def push_branch(self, branch_name: str, remote: str = 'origin', set_upstream: bool = True) -> bool:
        """Push a branch to remote
        
        Args:
            branch_name: Branch to push
            remote: Remote name (default: 'origin')
            set_upstream: Set upstream tracking (default: True)
        
        Returns:
            True if push succeeded
        """
        try:
            cmd = ['git', 'push']
            if set_upstream:
                cmd.extend(['-u', remote, branch_name])
            else:
                cmd.extend([remote, branch_name])
            
            result = subprocess.run(
                cmd,
                cwd=self.git_root,
                capture_output=True,
                text=True,
                check=True
            )
            
            logger.info(f"Pushed branch {branch_name} to {remote}")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Error pushing branch {branch_name}: {e.stderr}")
            return False
    
    def generate_gitlab_mr_url(self, branch_name: str, target_branch: str = None,
                              app_name: str = None, old_version: str = None, 
                              new_version: str = None, environment: str = None) -> Optional[str]:
        """Generate GitLab merge request URL for a branch
        
        Args:
            branch_name: Source branch for MR
            target_branch: Target branch (default: auto-detect main/master)
            app_name: Application name for MR title
            old_version: Current version
            new_version: New version
            environment: Environment (for title)
        
        Returns:
            GitLab MR creation URL with title and description or None
        """
        # Auto-detect target branch if not specified
        if not target_branch:
            target_branch = self._detect_default_branch() or 'main'
        
        remote_info = self.get_remote_info()
        if not remote_info:
            return None
        
        remote_url = remote_info['url']
        gitlab_base, project_path = parse_gitlab_remote_url(remote_url)
        
        if not gitlab_base or not project_path:
            logger.debug(f"Could not parse GitLab URL from: {remote_url}")
            return None
        
        # Build MR title
        if app_name and new_version:
            env_prefix = f"[{environment.upper()}] " if environment else ""
            if old_version:
                title = f"{env_prefix}Update {app_name} from v{old_version} to v{new_version}"
            else:
                title = f"{env_prefix}Update {app_name} to v{new_version}"
        else:
            title = f"Update from {branch_name}"
        
        # Build MR description
        description_parts = []
        description_parts.append("## Splunk App Update")
        description_parts.append("")
        
        if app_name:
            description_parts.append(f"**App:** {app_name}")
        if old_version and new_version:
            description_parts.append(f"**Version Change:** {old_version} → {new_version}")
        elif new_version:
            description_parts.append(f"**New Version:** {new_version}")
        if environment:
            description_parts.append(f"**Environment:** {environment}")
        
        description_parts.append(f"**Branch:** `{branch_name}`")
        description_parts.append("")
        description_parts.append("### Changes")
        description_parts.append("This MR updates the Splunk app to the latest version from Splunkbase.")
        description_parts.append("")
        description_parts.append("---")
        description_parts.append("*Auto-generated by Splunk App Updater*")
        
        description = "\n".join(description_parts)
        
        # URL encode parameters
        from urllib.parse import quote
        
        # Generate MR URL with title and description
        # GitLab MR creation URL format supports:
        # - merge_request[source_branch]
        # - merge_request[target_branch]
        # - merge_request[title]
        # - merge_request[description]
        mr_url = (
            f"{gitlab_base}/{project_path}/-/merge_requests/new"
            f"?merge_request[source_branch]={quote(branch_name)}"
            f"&merge_request[target_branch]={quote(target_branch)}"
            f"&merge_request[title]={quote(title)}"
            f"&merge_request[description]={quote(description)}"
        )
        
        return mr_url
    
    def get_commit_hash(self, ref: str = 'HEAD') -> Optional[str]:
        """Get commit hash for a reference
        
        Args:
            ref: Git reference (default: 'HEAD')
        
        Returns:
            Commit hash or None
        """
        try:
            result = subprocess.run(
                ['git', 'rev-parse', ref],
                cwd=self.git_root,
                capture_output=True,
                text=True,
                check=True
            )
            
            return result.stdout.strip()
            
        except subprocess.CalledProcessError:
            return None


def mr_url_from_update(update: dict) -> Optional[str]:
    """Generate a GitLab MR URL from an update-tracking dict.

    This is a convenience wrapper around
    ``GitBranchManager.generate_gitlab_mr_url`` that avoids repeating the
    same field-extraction pattern in every caller.

    Args:
        update: A dict as stored in ``update_tracking.json`` with at least
            ``repo_path`` and ``branch_name`` keys.

    Returns:
        MR creation URL string, or ``None``.
    """
    repo_path = Path(update.get('repo_path', ''))
    branch_name = update.get('branch_name')
    if not repo_path.exists() or not branch_name:
        return None

    git_manager = GitBranchManager(repo_path)
    return git_manager.generate_gitlab_mr_url(
        branch_name,
        app_name=update.get('app_name'),
        old_version=update.get('old_version'),
        new_version=update.get('new_version'),
        environment=update.get('environment'),
    )
