"""Splunk App Updater - Modular package for managing Splunk app updates"""

from .models import SplunkApp, DeploymentConfig
from .config import ConfigManager
from .splunkbase import SplunkbaseClient
from .repo_analyzer import GitLabRepoAnalyzer
from .file_manager import AppFileManager
from .git_manager import GitBranchManager
from .updater import SplunkAppUpdater
from .update_tracker import UpdateTracker
from .interactive import select_apps_interactive
from .version_selector import select_version_interactive, prompt_version_selection_for_apps

# New modules for enhanced functionality
from .enums import UpdateStatus, Environment, Component, DeploymentType, ArchiveType
from .cache import PersistentCache, CacheTTL, create_splunkbase_cache
from .repo_cache import RepoScanCache  # Distinct from cache.PersistentCache (TTL-based API cache)
from .retry import retry_with_backoff, RetryError, RetryContext
from .parallel import ParallelExecutor, BatchVersionChecker, TaskResult, parallel_map

__all__ = [
    # Core models
    'SplunkApp',
    'DeploymentConfig',
    # Configuration
    'ConfigManager',
    # Clients
    'SplunkbaseClient',
    # Repository operations
    'GitLabRepoAnalyzer',
    'AppFileManager',
    'GitBranchManager',
    # Main orchestrator
    'SplunkAppUpdater',
    'UpdateTracker',
    # Interactive features
    'select_apps_interactive',
    'select_version_interactive',
    'prompt_version_selection_for_apps',
    # Enums
    'UpdateStatus',
    'Environment',
    'Component',
    'DeploymentType',
    'ValidationMode',
    'ArchiveType',
    # Caching
    'PersistentCache',
    'CacheTTL',
    'create_splunkbase_cache',
    'RepoScanCache',
    # Retry Logic
    'retry_with_backoff',
    'RetryError',
    'RetryContext',
    # Parallel Execution
    'ParallelExecutor',
    'BatchVersionChecker',
    'TaskResult',
    'parallel_map',
]
