"""GitLab API client for branch and MR status checking"""

import logging
import re
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import quote, urlparse

import requests

from .utils import parse_gitlab_remote_url

logger = logging.getLogger(__name__)


class GitLabClient:
    """Client for interacting with GitLab API"""
    
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.gitlab_base, self.project_path = self._get_gitlab_info()
        self.api_base = None
        if self.gitlab_base:
            # Convert web URL to API URL (e.g., https://gitlab.example.com -> https://gitlab.example.com/api/v4)
            self.api_base = f"{self.gitlab_base}/api/v4"
        self.token = self._get_gitlab_token()
    
    def _get_gitlab_info(self) -> Tuple[Optional[str], Optional[str]]:
        """Extract GitLab URL and project path from git remote"""
        try:
            result = subprocess.run(
                ['git', 'remote', 'get-url', 'origin'],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return parse_gitlab_remote_url(result.stdout.strip())
        except subprocess.CalledProcessError:
            logger.debug("Could not get git remote URL")
            return None, None
    
    def _get_gitlab_token(self) -> Optional[str]:
        """Get GitLab access token from git config"""
        try:
            # Check for token in git config (git config --global gitlab.token)
            result = subprocess.run(
                ['git', 'config', '--get', 'gitlab.token'],
                capture_output=True,
                text=True,
                check=True
            )
            token = result.stdout.strip()
            if token:
                logger.debug("Found GitLab token in git config")
                return token
        except subprocess.CalledProcessError:
            pass
        
        # Could also check environment variable
        import os
        token = os.environ.get('GITLAB_TOKEN')
        if token:
            logger.debug("Found GitLab token in environment")
            return token
        
        logger.debug("No GitLab token found")
        return None
    
    def is_configured(self) -> bool:
        """Check if GitLab API is properly configured"""
        return self.api_base is not None and self.project_path is not None
    
    def check_branch_status(self, branch_name: str) -> Dict:
        """Check if a branch exists and its merge status
        
        Returns:
            dict with keys:
                - exists: bool - whether branch exists on remote
                - merged: bool - whether branch has been merged
                - merge_commit: str - merge commit SHA if merged
                - error: str - error message if any
        """
        if not self.is_configured():
            return {"exists": False, "merged": False, "error": "GitLab not configured"}
        
        # Check if branch exists
        branch_exists = self._check_branch_exists(branch_name)
        if not branch_exists:
            # Branch doesn't exist - likely merged and deleted
            return {"exists": False, "merged": True, "merge_commit": None}
        
        # Branch exists - check if it's been merged via MR
        mr_status = self._check_merge_request_status(branch_name)
        
        return {
            "exists": True,
            "merged": mr_status.get("merged", False),
            "merge_commit": mr_status.get("merge_commit"),
            "error": mr_status.get("error")
        }
    
    def _check_branch_exists(self, branch_name: str) -> bool:
        """Check if branch exists on remote"""
        if not self.token:
            # Fallback to git command
            try:
                result = subprocess.run(
                    ['git', 'ls-remote', '--heads', 'origin', branch_name],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    check=True
                )
                return bool(result.stdout.strip())
            except subprocess.CalledProcessError:
                return False
        
        # Use GitLab API
        try:
            encoded_project = quote(self.project_path, safe='')
            encoded_branch = quote(branch_name, safe='')
            url = f"{self.api_base}/projects/{encoded_project}/repository/branches/{encoded_branch}"
            
            headers = {"PRIVATE-TOKEN": self.token}
            response = requests.get(url, headers=headers, timeout=10)
            
            return response.status_code == 200
            
        except requests.RequestException as e:
            logger.debug(f"Error checking branch existence: {e}")
            return False
    
    def _check_merge_request_status(self, branch_name: str) -> Dict:
        """Check merge request status for a branch"""
        if not self.token:
            return {"merged": False, "error": "No GitLab token configured"}
        
        try:
            encoded_project = quote(self.project_path, safe='')
            url = f"{self.api_base}/projects/{encoded_project}/merge_requests"
            
            headers = {"PRIVATE-TOKEN": self.token}
            params = {
                "source_branch": branch_name,
                "state": "all"  # Check all states (opened, closed, merged)
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            
            merge_requests = response.json()
            
            if not merge_requests:
                return {"merged": False}
            
            # Get the most recent MR for this branch
            mr = merge_requests[0]
            
            is_merged = mr.get("state") == "merged"
            merge_commit = mr.get("merge_commit_sha") if is_merged else None
            
            return {
                "merged": is_merged,
                "merge_commit": merge_commit,
                "mr_iid": mr.get("iid"),
                "mr_title": mr.get("title")
            }
            
        except requests.RequestException as e:
            logger.debug(f"Error checking MR status: {e}")
            return {"merged": False, "error": str(e)}
    
    def sync_tracking_status(self, tracker) -> Dict[str, int]:
        """Sync tracking file with GitLab status
        
        Args:
            tracker: UpdateTracker instance
        
        Returns:
            dict with counts of merged/deleted branches
        """
        if not self.is_configured():
            logger.warning("GitLab not configured - cannot sync tracking status")
            return {"merged": 0, "deleted": 0, "errors": 0}
        
        pending_updates = tracker.get_all_pending()
        merged_count = 0
        deleted_count = 0
        error_count = 0
        
        for update in pending_updates:
            branch_name = update["branch_name"]
            logger.info(f"Checking GitLab status for branch: {branch_name}")
            
            status = self.check_branch_status(branch_name)
            
            if status.get("error"):
                logger.warning(f"Error checking {branch_name}: {status['error']}")
                error_count += 1
                continue
            
            if status["merged"]:
                # Mark as merged
                tracker.mark_merged(branch_name, status.get("merge_commit"))
                logger.info(f"[MERGED] {update['app_name']} (branch: {branch_name})")
                merged_count += 1
            elif not status["exists"]:
                # Branch doesn't exist but no MR found - mark as merged anyway
                tracker.mark_merged(branch_name)
                logger.info(f"[MERGED] {update['app_name']} (branch deleted)")
                deleted_count += 1
        
        return {
            "merged": merged_count,
            "deleted": deleted_count,
            "errors": error_count
        }
