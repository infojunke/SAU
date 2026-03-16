"""Utility functions for Splunk app updater"""

import hashlib
import logging
import re
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def find_git_root(path: Path) -> Optional[Path]:
    """Find the git root directory by walking up from *path* looking for .git/

    Args:
        path: Any path inside (or at the root of) a Git repository.

    Returns:
        The repository root ``Path``, or ``None`` if no ``.git`` directory is
        found in any ancestor.
    """
    current = path.resolve()
    while current != current.parent:
        if (current / '.git').exists():
            return current
        current = current.parent
    return None


def detect_default_branch(git_root: Path, *, include_remote_prefix: bool = False) -> Optional[str]:
    """Detect the default remote branch (main or master).

    Args:
        git_root: Root of the git repository.
        include_remote_prefix: If ``True`` return e.g. ``'origin/main'``;
            otherwise return just ``'main'``.

    Returns:
        Branch name string, or ``None`` if detection fails.
    """
    try:
        result = subprocess.run(
            ['git', 'symbolic-ref', 'refs/remotes/origin/HEAD'],
            cwd=git_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            ref = result.stdout.strip()  # e.g. "refs/remotes/origin/main"
            prefix = 'refs/remotes/'
            if ref.startswith(prefix):
                remote_branch = ref[len(prefix):]  # "origin/main"
                if include_remote_prefix:
                    return remote_branch
                # Strip "origin/" (or any remote name)
                parts = remote_branch.split('/', 1)
                return parts[1] if len(parts) == 2 else remote_branch

        # Fallback: inspect remote branch list
        result = subprocess.run(
            ['git', 'branch', '-r'],
            cwd=git_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            branches = [b.strip() for b in result.stdout.strip().split('\n')]
            for candidate in ('origin/main', 'origin/master'):
                if candidate in branches:
                    return candidate if include_remote_prefix else candidate.split('/', 1)[1]

        return None
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return None


def parse_gitlab_remote_url(remote_url: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse a GitLab remote URL into (base_url, project_path).

    Handles both SSH and HTTPS formats:
    - ``git@gitlab.example.com:group/project.git`` -> ``("https://gitlab.example.com", "group/project")``
    - ``https://gitlab.example.com/group/project.git`` -> same

    Returns:
        ``(gitlab_base, project_path)`` or ``(None, None)`` on failure.
    """
    if remote_url.startswith('http'):
        parsed = urlparse(remote_url)
        gitlab_base = f"{parsed.scheme}://{parsed.netloc}"
        project_path = parsed.path.lstrip('/').removesuffix('.git')
        if project_path:
            return gitlab_base, project_path
    elif remote_url.startswith('git@'):
        match = re.match(r'git@([^:]+):(.+?)(?:\.git)?$', remote_url)
        if match:
            host, path = match.groups()
            return f"https://{host}", path
    return None, None


def safe_cache_path(cache_dir: Path, key: str) -> Path:
    """Derive a filesystem-safe cache file path from an arbitrary key.

    Args:
        cache_dir: Directory where cache files are stored.
        key: Arbitrary string used as cache key.

    Returns:
        ``cache_dir / "<md5hex>.json"``
    """
    safe_key = hashlib.md5(key.encode()).hexdigest()
    return cache_dir / f"{safe_key}.json"


def version_compare(version1: str, version2: str) -> int:
    """Compare two version strings. 
    
    Returns: 
        1 if v1 > v2
        -1 if v1 < v2
        0 if equal
    """
    try:
        # Clean versions (remove 'v' prefix, etc.)
        v1_parts = [int(x) for x in version1.lstrip('v').split('.')]
        v2_parts = [int(x) for x in version2.lstrip('v').split('.')]
        
        # Pad with zeros to make them equal length
        max_len = max(len(v1_parts), len(v2_parts))
        v1_parts.extend([0] * (max_len - len(v1_parts)))
        v2_parts.extend([0] * (max_len - len(v2_parts)))
        
        for v1, v2 in zip(v1_parts, v2_parts):
            if v1 > v2:
                return 1
            elif v1 < v2:
                return -1
        
        return 0
    except (ValueError, AttributeError):
        # If parsing fails, fall back to per-component comparison.
        # Pure lexicographic comparison is wrong for versions like
        # "9.0" vs "10.0", so we split, compare ints where possible,
        # and only compare strings for non-numeric segments.
        try:
            parts1 = version1.lstrip('v').split('.')
            parts2 = version2.lstrip('v').split('.')
            max_len = max(len(parts1), len(parts2))
            parts1.extend(['0'] * (max_len - len(parts1)))
            parts2.extend(['0'] * (max_len - len(parts2)))
            for p1, p2 in zip(parts1, parts2):
                # Try integer comparison first
                try:
                    i1, i2 = int(p1), int(p2)
                    if i1 != i2:
                        return 1 if i1 > i2 else -1
                except ValueError:
                    if p1 != p2:
                        return 1 if p1 > p2 else -1
            return 0
        except Exception:
            logger.warning(f"Could not reliably compare versions '{version1}' and '{version2}', using string fallback")
            if version1 > version2:
                return 1
            elif version1 < version2:
                return -1
            return 0


def setup_logging(log_file: str = 'splunk_app_updater.log', debug: bool = False):
    """Setup logging configuration
    
    Args:
        log_file: Path to log file
        debug: Enable debug mode (shows all log levels)
    """
    import sys
    
    # Set base logging level
    log_level = logging.DEBUG if debug else logging.INFO
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Suppress INFO messages from updater module unless in debug mode
    if not debug:
        updater_logger = logging.getLogger('splunk_updater.updater')
        updater_logger.setLevel(logging.WARNING)
        
        # Also suppress INFO from repo_analyzer
        analyzer_logger = logging.getLogger('splunk_updater.repo_analyzer')
        analyzer_logger.setLevel(logging.WARNING)
