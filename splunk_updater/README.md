# Splunk App Updater - Modular Structure

## Overview

The Splunk App Updater has been refactored into a modular package structure for better maintainability, testability, and reusability.

## Package Structure

```
splunk_updater/
├── __init__.py          # Package initialization and exports
├── models.py            # Data models (SplunkApp, DeploymentConfig)
├── utils.py             # Utility functions (version comparison, logging setup)
├── config.py            # Configuration management
├── splunkbase.py        # Splunkbase API client
├── repo_analyzer.py     # GitLab repository analyzer
├── file_manager.py      # App file management and filtering
├── git_manager.py       # Git branch and commit management
├── updater.py           # Main update orchestrator
├── interactive.py       # Interactive app selection interface
└── cli.py               # Command-line interface
```

## Key Improvements

### DRY (Don't Repeat Yourself)
- Extracted common patterns into reusable methods
- Eliminated duplicate error handling code
- Consolidated file path checking logic
- Unified version comparison logic

### Separation of Concerns
- Each module has a single, well-defined responsibility
- Clean interfaces between modules
- Reduced coupling between components

### Better Testability
- Smaller, focused modules are easier to test
- Clear dependencies make mocking straightforward
- Each class can be tested in isolation

### Improved Readability
- Shorter files (150-300 lines vs 1500+ lines)
- Logical grouping of related functionality
- Clear naming conventions

## Usage

### As a Command-Line Tool
```bash
python main.py --help
python main.py --component shc --environment non-prod --interactive
```

### As a Python Package
```python
from splunk_updater import SplunkAppUpdater, ConfigManager

# Initialize updater
updater = SplunkAppUpdater('config.yaml')

# Discover apps
apps = updater.discover_apps(component_filter='shc')

# Check for updates
apps_with_updates = updater.check_for_updates(apps)

# Update apps
results = updater.update_all_apps(apps_with_updates)
```

## Module Descriptions

### models.py
Data classes representing Splunk apps and deployment configurations.

### config.py
Manages YAML configuration loading and provides typed access to settings.

### splunkbase.py
Handles all interactions with the Splunkbase API including authentication, version checking, and downloading.

### repo_analyzer.py
Scans GitLab repositories to find Splunk apps and extract metadata from app.conf files.

### file_manager.py
Manages file operations including extraction, copying with filtering, and local folder preservation.

### git_manager.py
Handles Git operations including branch creation, staging, committing, and verification.

### updater.py
Main orchestrator that coordinates all components to perform app updates.

### interactive.py
Provides the interactive CLI interface for selecting which apps to update.

### cli.py
Command-line interface with argument parsing and high-level workflow coordination.

### utils.py
Common utility functions used across multiple modules.

## Migration Notes

The original `splunk_app_updater.py` can be gradually phased out in favor of using `main.py` or importing from the `splunk_updater` package directly.

All functionality is preserved - this is purely a refactoring for code quality.
