# Changelog

All notable changes to the Splunk App Updater project.

## [2.1.0] - 2026-01-04

### New Features

- **CSV Import** - Import app lists from CSV files
  - Import apps from Splunk inventory reports or custom CSV files
  - Automatic Splunkbase ID extraction from URLs
  - Export config.yaml mapping from CSV
  - Flexible name matching (display names to folder names)
  - See [CSV_IMPORT_GUIDE.md](CSV_IMPORT_GUIDE.md)
  
- **Version Matching Workflow** - Automatic version promotion from non-prod to shared/prod
  - Shared/prod apps automatically match non-prod's current version
  - Interactive version selection when non-prod version not available
  - Ensures tested versions promote to production
  
- **Date-First Branch Naming** - Improved branch organization
  - Format: `YYYYMMDD-component-env-region-app-vX_X_X`
  - Example: `20260104-shc-nonprod-Splunk-TA-aws-v8_0_0`
  - Chronological sorting for better branch management
  
- **Download Caching** - Reuse previously downloaded files
  - Checks `work/downloads/` before re-downloading
  - Reduces Splunkbase API calls
  - Faster updates for apps already downloaded
  
- **Debug Mode** - Control log verbosity
  - `--debug` flag shows all INFO-level logs
  - Default mode shows only WARNING and above
  - Cleaner console output by default
  
- **Enhanced Interactive Menu** - Better visibility
  - Warnings for apps with unavailable versions
  - Clear indicators when current version not on Splunkbase
  - Version matching status displayed

## [2.0.0] - 2025-12-22

### Initial Modular Release

- **Modular Architecture** - Refactored into organized package structure
  - 11 focused modules for better maintainability
  - Clean separation of concerns
  - Improved testability and reusability
  
- **Interactive Selection** - Menu-based app selection (default mode)
  - Choose specific apps to update from numbered list
  - View app metadata (environment, region, component)
  - See active filters at menu top
  - Select ranges, individual apps, or all
  
- **Flexible Filtering**
  - Component filtering: `--component ds|shc|cm`
  - Environment filtering: `--environment prod|non-prod|shared`
  - Region filtering: `--region east|west|central`
  - Pattern matching: `--app "Splunk_TA_*"`
  - Combine filters for precise targeting

- **Smart Deployment** - Component-based file filtering
  - Forwarders: inputs, basic configs only
  - Indexers: index-time processing, no UI
  - Search Heads: full app with UI, knowledge objects
  
- **Git Integration**
  - Automatic branch creation per app update
  - Isolated commits (one app per branch)
  - Descriptive branch names with timestamps
  - Returns to original branch after each update

- **Splunkbase Integration**
  - Automated downloads with session authentication
  - Version comparison and update detection
  - Manual download fallback support
  - Splunkbase ID mapping in configuration

- **Additional Features**
  - Detailed update reports with statistics
  - Automatic backup management
  - Check-only mode for previewing updates
  - List all discovered apps
  - Custom configuration file support
  - Comprehensive logging

## Usage Examples

```bash
# Interactive selection (default)
python splunk_app_updater.py

# Update all apps automatically
python splunk_app_updater.py --no-interactive

# Check for updates without making changes
python splunk_app_updater.py --check-only

# Filter by component
python splunk_app_updater.py --component shc

# Filter by environment and region
python splunk_app_updater.py --environment non-prod --region east

# Update specific apps with pattern
python splunk_app_updater.py --app "Splunk_TA_*"

# Combine filters for precision
python splunk_app_updater.py --env prod --region west --component shc --interactive
```

## See Also

- [README.md](README.md) - Complete documentation and setup guide
- [APP_SELECTION_GUIDE.md](APP_SELECTION_GUIDE.md) - App selection options
- [ENVIRONMENT_REGION_GUIDE.md](ENVIRONMENT_REGION_GUIDE.md) - Environment and region filtering
- [splunk_updater/README.md](splunk_updater/README.md) - Module architecture and API
- [examples.py](examples.py) - Programmatic usage examples
- Rollback functionality for failed updates

## Support

For issues, questions, or contributions:
1. Check [README.md](README.md) for documentation
2. Review [APP_SELECTION_GUIDE.md](APP_SELECTION_GUIDE.md) for examples
3. Run test script: `python testing/test_selection.py`
4. Check logs in `splunk_app_updater.log`

## Credits

Built for automating Splunk app management across complex deployments.
