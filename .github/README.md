# Splunk App Updater for GitLab Repositories

A modular Python tool that automates the process of updating Splunk apps from Splunkbase across deployment servers (forwarders), search head clusters, and indexer clusters. The tool intelligently manages which files are deployed to each component type and creates isolated Git branches for each app update.

## Key Features

- **Interactive Selection**: Menu-based app selection with metadata display (default mode)
- **CSV Import**: Import app lists from CSV files (e.g., Splunk inventory reports)
- **Version Matching**: Automatic version promotion from non-prod to shared/prod environments
- **Smart Filtering**: Filter by component, environment, region, or app pattern
- **Modular Architecture**: Clean, maintainable codebase with 12 focused modules
- **Isolated Updates**: Each app gets its own Git branch with isolated commits
- **GitLab Integration**: Track remote branches, generate MR URLs, distinguish test vs production updates
- **Diff Reporting**: View changes for all pending branches organized by branch (no GitLab needed)
- **Component-Based Deployment**: Filters files appropriately for indexers, search heads, and forwarders
- **Download Caching**: Reuses previously downloaded files from work/downloads/
- **Automated Downloads**: Authenticated Splunkbase integration with manual fallback
- **Comprehensive Reporting**: Detailed update reports with statistics
- **Debug Mode**: Optional verbose logging with --debug flag

## Quick Start

```bash
# 1. Check what apps need updating (preview only)
python splunk_app_updater.py --check-only

# 2. Run with default interactive mode (select which apps to update)
python splunk_app_updater.py

# 3. Update all apps automatically (bypass interactive mode)
python splunk_app_updater.py --no-interactive

# 4. View diffs for pending updates (see actual code changes)
python splunk_app_updater.py --show-diffs
python splunk_app_updater.py --show-diffs --full-diff  # with complete diffs

# 5. Update specific component interactively
python splunk_app_updater.py --component shc

# 6. Update apps by pattern (bypasses interactive mode)
python splunk_app_updater.py --app "Splunk_TA_*"

# 7. Import app list from CSV and update only those apps
python splunk_app_updater.py --import-csv path/to/apps.csv
python splunk_app_updater.py --import-csv apps.csv --export-csv-mapping  # Extract IDs

# 8. Update specific environment
python splunk_app_updater.py --environment shared

# 8. Update specific region
python splunk_app_updater.py --region east

# 9. Combine filters for precise targeting
python splunk_app_updater.py --env non-prod --region east --component shc

# 10. Enable debug logging (shows all log messages)
python splunk_app_updater.py --debug

# 11. Dry-run mode (includes version selection without making changes)
python splunk_app_updater.py --dry-run

# 12. Check remote branch instead of local files (useful for CI/CD or checking main branch)
python splunk_app_updater.py --remote origin/main --check-only

# 13. GitLab Integration - Track and manage remote branches
python splunk_app_updater.py --show-pending  # Shows push status & MR URLs
python splunk_app_updater.py --push-branches  # Push all unpushed branches
python splunk_app_updater.py --sync-tracking  # Sync with GitLab to detect merged branches

# 14. Validate apps with AppInspect after updates
python splunk_app_updater.py --validate  # Run AppInspect on updated apps
python splunk_app_updater.py --validate --validate-mode precert  # Use precert mode

# 15. Validate existing apps without updating
python splunk_app_updater.py --validate-only  # Validate all apps
python splunk_app_updater.py --validate-only --component shc  # Validate SHC apps only
python splunk_app_updater.py --validate-only --app "Splunk_TA_*"  # Validate specific pattern

# 16. Test mode - Mark updates as test runs
python splunk_app_updater.py --test-mode  # Helps distinguish test from production
python splunk_app_updater.py --clear-test-updates  # Remove test updates
```

**Note:** Interactive mode is now the default! Use `--no-interactive` to update all apps automatically.

**Quick Links:**
- 🚀 **New User?** Start with [GETTING_STARTED.md](GETTING_STARTED.md) - Complete setup guide
- 📖 **Documentation:**
  - [APP_SELECTION_GUIDE.md](APP_SELECTION_GUIDE.md) - Complete app selection options
  - [CSV_IMPORT_GUIDE.md](CSV_IMPORT_GUIDE.md) - Import app lists from CSV files
  - [ENVIRONMENT_REGION_GUIDE.md](ENVIRONMENT_REGION_GUIDE.md) - Environment and region filtering
  - [splunk_updater/README.md](splunk_updater/README.md) - Module architecture and API reference
  - [CHANGELOG.md](CHANGELOG.md) - Version history and features

## Architecture

The tool is organized into a modular package structure for better maintainability:

```
splunk_updater/
├── models.py           # Data models (SplunkApp, DeploymentConfig)
├── utils.py            # Utilities (version comparison, logging)
├── config.py           # Configuration management
├── splunkbase.py       # Splunkbase API client
├── repo_analyzer.py    # Repository discovery and analysis
├── file_manager.py     # File operations and filtering
├── git_manager.py      # Git branch and commit operations
├── gitlab_client.py    # GitLab API integration
├── updater.py          # Main update orchestrator
├── interactive.py      # Interactive menu interface
├── version_selector.py # Interactive version selection
├── update_tracker.py   # Update tracking and duplicate prevention
└── cli.py              # Command-line argument parsing
```

**Entry Points:**
- `main.py` - Primary entry point (recommended)
- `splunk_app_updater.py` - Backwards-compatible wrapper

**See [splunk_updater/README.md](splunk_updater/README.md) for detailed architecture documentation.**

## Installation

### Prerequisites

- Python 3.7 or higher
- Git installed and accessible from command line
- Access to GitLab repositories (local clones)
- Splunkbase account (for downloading apps)

### Setup

1. Clone or download this tool:
```bash
git clone <your-repo-url>
cd splunk_app_updater
```

2. Install required Python packages:
```bash
pip install -r requirements.txt
```

3. Configure the tool by editing `config.yaml`:
```bash
cp config.yaml.example config.yaml
# Edit config.yaml with your settings
```

## Configuration

### Basic Configuration

Edit `config.yaml` to set up your environment:

```yaml
gitlab_repos:
  - "/path/to/deployment-server-repo"
  - "/path/to/searchhead-cluster-repo"
  - "/path/to/indexer-cluster-repo"

splunkbase_credentials:
  username: "your_username"
  password: "your_password"
```

### Deployment Type Configuration

The tool uses component-based file filtering based on Splunk best practices. Files are filtered according to the repository's component type to ensure only appropriate files are deployed:

**Universal Forwarders (DS with component: ds):**
- Include: `inputs.conf`, `bin/`, `metadata/`
- Exclude: UI components, lookups, knowledge objects

**Heavy Forwarders (DS with component: hf):**
- Include: `inputs.conf`, `bin/`, `metadata/`, **lookups**, **savedsearches**, **macros**, **eventtypes**
- Exclude: UI components (views, dashboards, navigation)
- **Use this when your deployment server manages heavy forwarders that perform searches**

**Indexers (CM):**
- Include: `indexes.conf`, `props.conf` (index-time), `transforms.conf` (index-time)
- Exclude: `inputs.conf`, UI components, search-time knowledge objects

**Search Heads (SHC):**
- Include: All UI, dashboards, saved searches, lookups, knowledge objects
- Exclude: `inputs.conf`, `indexes.conf`

Configure filtering in `config.yaml`:

```yaml
deployment:
  # Universal forwarders
  forwarder_excludes:
    - "local"
    - "lookups"
    - "default/savedsearches.conf"
  
  # Heavy forwarders (includes search capability)
  heavy_forwarder_excludes:
    - "local"
    - "samples"
    - "static"
    - "appserver"
    - "default/views"
  
  # Indexers
  indexer_excludes:
    - "local"
    - "appserver"
    - "default/data/ui"
  
  # Search heads
  searchhead_excludes:
    - "samples"
```

## Usage

### Check for Updates Only

To see which apps have updates available without making changes:

```bash
python splunk_app_updater.py --check-only
```

### Update by Component

Update apps in only one component at a time:

```bash
# Update only deployment server apps
python splunk_app_updater.py --component ds

# Update only search head cluster apps
python splunk_app_updater.py --component shc

# Update only cluster manager/indexer apps
python splunk_app_updater.py --component cm
```

You can also use longer aliases:
```bash
python splunk_app_updater.py --component deployment-server
python splunk_app_updater.py --component search-head
python splunk_app_updater.py --component cluster-manager
```

Combine with `--check-only` to preview:
```bash
python splunk_app_updater.py --component ds --check-only
```

### Update All Apps

To update all apps that have available updates:

```bash
python splunk_app_updater.py
```

This will:
1. Scan all configured GitLab repos
2. Check Splunkbase for updates
3. Download updated apps
4. Create a Git branch for each update
5. Extract and deploy files appropriately
6. Commit changes with descriptive messages

### Update Specific App

To update only a specific app:

```bash
python splunk_app_updater.py --app "Splunk_TA_windows"
```

### Update Multiple Apps

Update multiple specific apps using comma-separated list:

```bash
python splunk_app_updater.py --app "Splunk_TA_windows,Splunk_TA_nix,Splunk_TA_aws"
```

Or use wildcards:

```bash
python splunk_app_updater.py --app "Splunk_TA_*"
```

### Import Apps from CSV

Import a list of apps from a CSV file (e.g., from Splunk's app inventory):

```bash
# Import and update apps from CSV
python splunk_app_updater.py --import-csv path/to/apps.csv

# Export Splunkbase ID mapping from CSV
python splunk_app_updater.py --import-csv apps.csv --export-csv-mapping

# Combine with filters
python splunk_app_updater.py --import-csv apps.csv --component shc --environment non-prod
```

**CSV Format:**
```csv
App,splunkbase_url,version,Available Version
"Splunk Add-on for Microsoft Windows","https://splunkbase.splunk.com/app/742/","8.8.0","9.0.1"
"Splunk Add-on for AWS","https://splunkbase.splunk.com/app/1876/","7.3.0","8.0.0"
```

See [CSV_IMPORT_GUIDE.md](CSV_IMPORT_GUIDE.md) for complete documentation.

### Interactive App Selection

Use interactive mode to choose which apps to update from a menu:

```bash
python splunk_app_updater.py --interactive
```

You can also combine with component filtering:

```bash
python splunk_app_updater.py --component shc --interactive
```

The interactive mode allows you to:
- View all apps with available updates
- Select specific apps by number (e.g., `1,3,5`)
- Select ranges (e.g., `1-3`)
- Select all apps with `all`
- Cancel with `none` or Ctrl+C

### Update Without Creating Branches

If you want to update apps directly without creating branches:

```bash
python splunk_app_updater.py --no-branch
```

### Custom Configuration File

Use a different configuration file:

```bash
python splunk_app_updater.py --config /path/to/custom-config.yaml
```

## How It Works

### 1. App Discovery

The tool scans your GitLab repositories looking for Splunk apps by finding `app.conf` files. It extracts:
- App name and version
- Splunkbase ID (from app.conf or configuration mapping)
- Component type (from repository configuration)
- Environment and region metadata

### 2. Version Checking

For each app with a Splunkbase ID:
- Queries Splunkbase API for the latest version
- Compares with local version using semantic versioning
- Flags apps that need updates
- Displays update information in interactive menu

### 3. File Management

When updating, files are filtered based on component type:

**For Forwarders:**
- Keeps only inputs, outputs, and basic configurations
- Removes UI components, lookups, knowledge objects

**For Indexers:**
- Keeps index-time processing configurations
- Removes UI components and search-time knowledge objects

**For Search Heads:**
- Keeps all UI components, dashboards, and saved searches
- Keeps lookups and all knowledge objects

### 4. Git Branch Management

For each app update:
1. Saves current branch to return to later
2. Creates new branch: `{env}-{app}-v{version}-{timestamp}`
3. Stages the updated files
4. Commits with message: `Update {app} from v{old} to v{new}`
5. Returns to original branch
6. Each app gets an isolated branch with only its changes

## Repository Structure

Your GitLab repositories should follow Splunk's standard structure:

```
deployment-server-repo/
├── apps/
│   ├── Splunk_TA_windows/
│   │   ├── bin/
│   │   ├── default/
│   │   │   └── inputs.conf
│   │   └── metadata/
│   └── ...

searchhead-cluster-repo/
├── apps/
│   ├── Splunk_App_Infrastructure/
│   │   ├── bin/
│   │   ├── default/
│   │   ├── static/
│   │   └── appserver/
│   └── ...

indexer-cluster-repo/
├── apps/
│   ├── Splunk_TA_nix/
│   │   ├── bin/
│   │   ├── default/
│   │   │   ├── indexes.conf
│   │   │   └── props.conf
│   │   └── metadata/
│   └── ...
```

## App Metadata

The tool reads `app.conf` files to identify apps. Ensure proper metadata:

```conf
[launcher]
version = 8.0.0
description = My Splunk App

[id]
name = my_splunk_app
```

### Splunkbase ID Configuration

The tool needs Splunkbase IDs to check for updates. Configure them in `config.yaml`:

```yaml
splunkbase_id_mapping:
  Splunk_TA_windows: "742"
  Splunk_TA_nix: "833"
  Splunk_TA_aws: "1274"
  # Add your apps here
```

Or include in `app.conf`:

```conf
[install]
splunkbase_id = 1234
```

## Workflow Example

1. **Check for updates:**
   ```bash
   python splunk_app_updater.py --check-only
   ```
   Output:
   ```
   Discovered 15 apps across 3 repositories
   
   Updates Available:
   1. Splunk_TA_windows: 8.0.0 -> 8.1.0 [non-prod/east/ds]
   2. Splunk_App_Infrastructure: 2.0.1 -> 2.1.0 [prod/west/shc]
   ```

2. **Interactive selection:**
   ```bash
   python splunk_app_updater.py
   ```
   ```
   Select apps to update (e.g., 1,2 or 1-3 or 'all'):
   > 1
   
   Updating: Splunk_TA_windows
   Downloading from Splunkbase...
   Created branch: 20260104-ds-non-prod-Splunk_TA_windows-v8_1_0
   Extracting and filtering files for deployment server...
   Committed changes
   Returned to original branch
   ```

3. **Review and merge:**
   ```bash
   cd /path/to/repo
   git log --oneline 20260104-ds-non-prod-Splunk_TA_windows-v8_1_0
   git checkout main
   git merge 20260104-ds-non-prod-Splunk_TA_windows-v8_1_0
   git push
   ```

## Reports

After each run, the tool generates a detailed report saved to:
```
work/update_report_YYYYMMDD_HHMMSS.txt
```

The report includes:
- Total apps checked
- Apps needing updates
- Update results (success/failure)
- Apps already up to date

### Viewing Diffs for Pending Updates

To see the actual code changes in pending update branches without going to GitLab:

```bash
# Show summary of pending branches with file changes
python splunk_app_updater.py --show-diffs

# Show complete diffs for all pending branches
python splunk_app_updater.py --show-diffs --full-diff

# Save diff report to a specific file
python splunk_app_updater.py --show-diffs --full-diff -o my_diffs.txt

# Compare against a different base branch
python splunk_app_updater.py --show-diffs --base-branch develop
```

The diff report includes:
- All pending branches organized by branch name
- List of apps/versions in each branch
- Files changed in each branch
- Full git diff output (with `--full-diff`)
- Environment and region metadata

**Example output structure:**
```
################################################################################
BRANCH: 20260104-shc-non-prod-TA-user-agents-v1_7_10
################################################################################
Repository: C:\repos\splunk-sh-config

Updates in this branch:
  • TA-user-agents: v1.7.8 -> v1.7.10 [non-prod]
    Path: C:\repos\splunk-sh-config\nonprod\shcluster\apps\TA-user-agents

Files changed (3):
  nonprod/shcluster/apps/TA-user-agents/default/app.conf
  nonprod/shcluster/apps/TA-user-agents/README.md
  nonprod/shcluster/apps/TA-user-agents/bin/parser.py

--------------------------------------------------------------------------------
DIFF:
--------------------------------------------------------------------------------
[Complete git diff output here...]
```

Reports are auto-saved to `work/diff_report_YYYYMMDD_HHMMSS.txt` for later reference.

### GitLab Integration & Branch Management

The tool now tracks remote branch status and can generate GitLab MR URLs automatically:

```bash
# View pending updates with remote status and MR URLs
python splunk_app_updater.py --show-pending
```

**Output includes:**
- ✅ **Pushed** or ⏳ **Local only** status for each branch
- 🔗 **GitLab MR URLs** for creating merge requests
- 🧪 **Test marker** to distinguish test updates from production
- Remote branch tracking information

**Push branches to GitLab:**
```bash
# Push all unpushed branches to remote
python splunk_app_updater.py --push-branches
```

This will:
1. Show all unpushed branches
2. Confirm before pushing
3. Push each branch to the remote
4. Display GitLab MR creation URLs
5. Update tracking with remote status

**Test mode** - Distinguish test runs from production:
```bash
# Run in test mode (marks updates with 🧪)
python splunk_app_updater.py --test-mode

# View only production updates (exclude test)
# Shows test updates separately in --show-pending

# Clean up test updates when done
python splunk_app_updater.py --clear-test-updates
```

**GitLab MR URL Format:**
The tool automatically generates URLs like:
```
https://gitlab.your-domain.com/group/project/-/merge_requests/new
  ?merge_request[source_branch]=branch-name
  &merge_request[target_branch]=main
```

Simply click the URL to create a merge request in GitLab!

**Complete workflow:**
1. Run updates (optionally with `--test-mode`)
2. Review locally: `--show-diffs --full-diff`
3. Push to remote: `--push-branches`
4. Click the MR URL to create merge request in GitLab
5. Sync tracking with GitLab: `--sync-tracking` (detects merged branches)
6. After merging: `--cleanup-branches`
7. Clean up tests: `--clear-test-updates`

### GitLab API Integration

The tool can automatically detect when branches have been merged in GitLab:

**Configure GitLab access** (one-time setup):
```bash
# Option 1: Store token in git config (recommended)
git config --global gitlab.token <your-personal-access-token>

# Option 2: Set environment variable
export GITLAB_TOKEN=<your-personal-access-token>  # Linux/Mac
$env:GITLAB_TOKEN="<your-personal-access-token>"  # PowerShell
```

**Get a GitLab personal access token:**
1. In GitLab, go to Settings → Access Tokens
2. Create a token with `api` scope
3. Copy the token and configure as shown above

**Sync tracking with GitLab:**
```bash
# Check GitLab for merged branches and update tracking
python splunk_app_updater.py --sync-tracking
```

This will:
- Check each pending branch in GitLab
- Detect merged or deleted branches
- Update `work/update_tracking.json` status
- Show summary of merged branches

**Without GitLab token**: Uses git commands to check branch existence (limited functionality)
**With GitLab token**: Uses GitLab API to check merge request status (full functionality)

## Troubleshooting

### "No Splunkbase ID found"

Add the Splunkbase ID to `config.yaml`:
```yaml
splunkbase_id_mapping:
  YourAppName: "1234"
```

### "Authentication failed"

Check your Splunkbase credentials in `config.yaml`:
1. Verify username/password
2. Ensure account has download permissions

### Git errors

Ensure:
- Git is installed and in PATH
- Repository has no uncommitted changes
- Not in detached HEAD state

## Advanced Usage

### Environment and Region Configuration

Define metadata in `config.yaml`:

```yaml
gitlab_repos:
  - path: "C:/repos/prod-east-ds-config"
    environment: "prod"
    region: "east"
    component: "ds"
  
  - path: "C:/repos/non-prod-west-shc-config"
    environment: "non-prod"
    region: "west"
    component: "shc"
```

See [ENVIRONMENT_REGION_GUIDE.md](ENVIRONMENT_REGION_GUIDE.md) for complete examples.

### Version Matching and Promotion

The tool implements automatic version promotion from non-prod to shared/prod environments:

**How it works:**
1. When updating a shared/prod app, the tool looks for the same app in non-prod
2. If found, it uses non-prod's **current version** (not the latest available on Splunkbase)
3. This ensures you're promoting tested versions to production

**Example:**
```
Non-prod environment: Splunk_TA_windows v9.2.0
Splunkbase latest: v9.3.0
Shared environment gets: v9.2.0 (matching non-prod)
```

**Version Availability Warnings:**

The tool automatically detects when an app's current version is no longer available on Splunkbase (e.g., old versions that have been deprecated or removed). These apps are flagged in the interactive menu:

```
Select apps to update:
1. [shared/ds] Splunk_TA_windows: 9.1.1 -> 9.2.0
   ⚠️  WARNING: Current version 9.1.1 not available on Splunkbase
2. [nonprod/shc] Splunk_TA_aws: 7.3.0 -> 8.0.0
```

This helps identify apps that may have been manually modified or are running versions that are no longer supported. If the current version is unavailable, the update will install the latest available version.

**Interactive version selection:**
If the non-prod version isn't available on Splunkbase, you'll be prompted to select from available versions:

```
Version 9.2.0 (from non-prod) not available on Splunkbase

Available versions:
1. 9.3.0 (latest)
2. 9.1.1
3. 9.1.0

Select version (1-10), enter version directly, or 's' to skip:
```

This workflow ensures consistency across environments and reduces the risk of untested versions reaching production.

### Programmatic Usage

Use as a Python package:

```python
from splunk_updater import SplunkAppUpdater, ConfigManager

# Initialize
updater = SplunkAppUpdater('config.yaml')

# Discover and check for updates
apps = updater.discover_apps(component_filter='shc')
apps_to_update = updater.check_for_updates(apps)

# Update specific apps
results = updater.update_all_apps(apps_to_update)
```

See [examples.py](examples.py) and [splunk_updater/README.md](splunk_updater/README.md) for more details.

## AppInspect Validation

The updater can optionally validate apps after updating using Splunk's official AppInspect tool.

### Installation

```bash
# Install AppInspect (optional)
pip install splunk-appinspect
```

### Usage

```bash
# Validate apps after updating (test mode)
python splunk_app_updater.py --validate

# Use pre-certification mode (more strict)
python splunk_app_updater.py --validate --validate-mode precert

# Validate existing apps WITHOUT updating them
python splunk_app_updater.py --validate-only

# Validate only specific apps
python splunk_app_updater.py --validate-only --app "Splunk_TA_*"
python splunk_app_updater.py --validate-only --component shc
python splunk_app_updater.py --validate-only --environment prod

# Combine with other options
python splunk_app_updater.py --component shc --validate
```

### What Gets Validated

After apps are successfully updated, AppInspect runs checks for:
- ✓ Configuration file syntax
- ✓ Required files and structure
- ✓ Python code compatibility
- ✓ Security best practices
- ✓ Cloud compatibility (in precert mode)
- ✓ Splunk version compatibility

### Validation Output

```
================================================================================
APPINSPECT VALIDATION
================================================================================
Mode: test

  [1/3] Validating Splunk_TA_windows... ✓ Passed
  [2/3] Validating Splunk_TA_aws... ⚠️  2 warning(s)
  [3/3] Validating custom_app... ❌ 3 error(s)

================================================================================
APPINSPECT VALIDATION SUMMARY
================================================================================
Total apps validated: 3
✓ Passed: 1
⚠️  Warnings: 1
❌ Failed: 1

Failed apps:
  - custom_app: 3 issue(s)
================================================================================
```

**Note:** Validation is informational only and doesn't prevent updates. Review the output and fix issues as needed.

## Security Considerations

1. **Credentials**: Store Splunkbase credentials securely
   - Avoid committing credentials to Git
   - Use environment variables or secrets manager

2. **Review Changes**: Always review updates before merging
   - Check the created branch
   - Review file changes
   - Test in non-production first

3. **Backups**: Automatic backups are created in `work/backups/`
   - Keep these until updates are verified
   - Clean up old backups periodically

## Project Files

**Main Files:**
- `main.py` - Primary entry point
- `splunk_app_updater.py` - Backwards-compatible entry point
- `config.yaml` - Main configuration file
- `requirements.txt` - Python dependencies

**Utilities:**
- `examples.py` - Programmatic usage examples
- `generate_download_list.py` - Generate manual download lists

**Documentation:**
- `README.md` - This file (main documentation)
- `APP_SELECTION_GUIDE.md` - App selection options
- `ENVIRONMENT_REGION_GUIDE.md` - Environment/region filtering
- `CHANGELOG.md` - Version history
- `splunk_updater/README.md` - Module architecture

**Tests** (`testing/`):
- `test_branch_names.py` - Branch naming tests
- `test_environments.py` - Environment filtering tests
- `test_interactive_metadata.py` - Interactive UI tests
- `test_selection.py` - App selection tests

## Known Limitations

- Requires local GitLab repository clones
- Splunkbase account required for automated downloads
- Git must be installed and accessible

## Support

For issues:
- Review documentation in README.md and guide files
- Check [CHANGELOG.md](CHANGELOG.md) for recent changes
- Review logs in `splunk_app_updater.log`
