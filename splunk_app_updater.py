#!/usr/bin/env python3
"""
Splunk App Updater for GitLab Repositories

NOTE: This file has been refactored into a modular package structure.
Please use main.py or import from splunk_updater package instead.

This file is kept for backwards compatibility but imports from the new modules.

ARCHITECTURE:
- Apps are filtered based on the repo's component type (ds/shc/cm)
- DS repos: forwarder-relevant files only
- SHC repos: searchhead-relevant files only
- CM repos: indexer-relevant files only
- Apps maintain standard Splunk structure (no component subfolders)
- Example: nonprod/shcluster/apps/Splunk_TA_aws/default/... (searchhead files only)

For the new modular structure, see: splunk_updater/README.md
"""

# Import from new modular structure
from splunk_updater import (
    SplunkApp,
    DeploymentConfig,
    ConfigManager,
    SplunkbaseClient,
    GitLabRepoAnalyzer,
    AppFileManager,
    GitBranchManager,
    SplunkAppUpdater,
    select_apps_interactive
)
from splunk_updater.cli import main

# Re-export for backwards compatibility
__all__ = [
    'SplunkApp',
    'DeploymentConfig',
    'ConfigManager',
    'SplunkbaseClient',
    'GitLabRepoAnalyzer',
    'AppFileManager',
    'GitBranchManager',
    'SplunkAppUpdater',
    'select_apps_interactive',
    'main'
]


if __name__ == '__main__':
    main()
