# Getting Started with Splunk App Updater

This guide will help you set up and use the Splunk App Updater tool to automate app updates across your Splunk environments.

## Prerequisites

Before you begin, ensure you have:

1. **Python 3.7+** installed on your system
2. **Git** installed and accessible from command line
3. **GitLab repository access** - local clones of your Splunk repos
4. **Splunkbase account** with download permissions

## Initial Setup

### 1. Clone the Repository

```bash
git clone <your-gitlab-url>/splunk-app-updater.git
cd splunk-app-updater
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

The tool has minimal dependencies:
- `requests` - for Splunkbase API calls
- `PyYAML` - for configuration parsing

### 3. Configure Your Environment

Copy the example configuration:

```bash
cp config.yaml.example config.yaml
```

Edit `config.yaml` with your settings:

#### a. Update Repository Paths

Point to your local GitLab repository clones. **Important**: If your repos have `nonprod/` and `shared/` subdirectories, create separate entries for each:

```yaml
gitlab_repos:
  # Non-prod deployment server
  - path: "C:/repos/splunk-ds-config/nonprod"
    environment: "non-prod"
    component: "ds"
  
  # Shared/prod deployment server
  - path: "C:/repos/splunk-ds-config/shared"
    environment: "shared"
    component: "ds"
```

Component types:
- `ds` = Deployment Server (universal forwarders - no lookups/searches)
- `hf` = Heavy Forwarders (forwarders with search capability - includes lookups/searches)
- `shc` = Search Head Cluster
- `cm` = Cluster Manager (indexers)

#### b. Add Splunkbase Credentials

```yaml
splunkbase_credentials:
  username: "your_username"
  password: "your_password"
```

⚠️ **Security Note**: Never commit `config.yaml` to Git. It's already in `.gitignore`.

#### c. Map Apps to Splunkbase IDs (Optional)

Some apps don't include their Splunkbase ID in `app.conf`. Add them manually:

```yaml
splunkbase_id_mapping:
  Splunk_TA_windows: "742"
  Splunk_TA_nix: "833"
  Splunk_TA_aws: "1876"
```

To find an app's Splunkbase ID, visit its page on Splunkbase. The ID is in the URL:
`https://splunkbase.splunk.com/app/742/` → ID is `742`

## Basic Usage

### Check for Updates (Preview Only)

See which apps have updates without making changes:

```bash
python main.py --check-only
```

Output example:
```
Discovered 15 apps across 3 repositories

Updates Available:
1. Splunk_TA_windows: 9.1.1 -> 9.2.0 [shared/ds]
   ⚠️  WARNING: Matches non-prod version 9.2.0
2. Splunk_TA_aws: 7.3.0 -> 8.0.0 [nonprod/shc]
3. TA-user-agents: 1.7.8 -> 1.7.10 [nonprod/shc]

Total: 3 apps with updates available
```

### Interactive Update (Recommended)

Select which apps to update from a menu:

```bash
python main.py
```

You'll see:
```
Select apps to update:
1. [shared/ds] Splunk_TA_windows: 9.1.1 -> 9.2.0
2. [nonprod/shc] Splunk_TA_aws: 7.3.0 -> 8.0.0
3. [nonprod/shc] TA-user-agents: 1.7.8 -> 1.7.10

Enter selection (e.g., '1,3' or '1-3' or 'all'): 1,3
```

### Update All Apps Automatically

Skip the interactive menu:

```bash
python main.py --no-interactive
```

### Filter by Component

Update only specific component types:

```bash
# Update only deployment server apps
python main.py --component ds

# Update only search head apps
python main.py --component shc

# Update only cluster manager apps
python main.py --component cm
```

### Filter by Environment

```bash
# Update only non-prod apps
python main.py --environment non-prod

# Update only shared/prod apps
python main.py --environment shared
```

### Combine Filters

```bash
# Update non-prod search head apps only
python main.py --environment non-prod --component shc
```

## Understanding Version Matching

The tool implements a **promotion workflow**: non-prod versions automatically promote to shared/prod.

### How It Works

1. When updating a shared/prod app, the tool checks if the same app exists in non-prod
2. If found, it uses non-prod's **current version** (not the latest available)
3. This ensures you're promoting tested versions to production

Example:
```
Non-prod has: Splunk_TA_windows v9.2.0
Splunkbase has: v9.3.0 available
Shared will get: v9.2.0 (matching non-prod)
```

### Version Selection

If a non-prod version isn't available on Splunkbase, you'll be prompted:

```
Version 9.2.0 (from non-prod) not available on Splunkbase

Available versions:
1. 9.3.0 (latest)
2. 9.1.1
3. 9.1.0
...

Select version (1-10), enter version directly, or 's' to skip: 1
```

## Working with Branches

### Branch Naming

Each app update creates a Git branch:

**Format**: `YYYYMMDD-component-environment-app-vX_X_X`

Examples:
- `20260104-ds-shared-Splunk-TA-windows-v9_2_0`
- `20260104-shc-nonprod-Splunk-TA-aws-v8_0_0`

### Review Changes

View diffs for pending branches:

```bash
# Summary view
python main.py --show-diffs

# Full diffs
python main.py --show-diffs --full-diff
```

### Push to GitLab

Push all unpushed branches:

```bash
python main.py --push-branches
```

This will:
1. Show unpushed branches
2. Confirm before pushing
3. Display GitLab merge request URLs

### View Pending Updates

```bash
python main.py --show-pending
```

Shows:
- ✅ Pushed branches (with MR URLs)
- ⏳ Local-only branches
- Version information
- Test vs production markers

### Merge Workflow

1. **Review locally**: `--show-diffs --full-diff`
2. **Push branches**: `--push-branches`
3. **Create MR**: Click the displayed GitLab URL
4. **After merging**: `--cleanup-branches`

## Advanced Features

### Test Mode

Mark updates as test runs (doesn't affect production tracking):

```bash
python main.py --test-mode
```

Test updates are marked with 🧪 in `--show-pending`. Clean them up:

```bash
python main.py --clear-test-updates
```

### Dry Run

See what would happen without making changes (includes version selection):

```bash
python main.py --dry-run
```

### Debug Mode

Show detailed logs (normally hidden):

```bash
python main.py --debug
```

### Manual Downloads

If Splunkbase downloads fail:

1. Download the `.tgz` or `.spl` file from Splunkbase manually
2. Place it in the `manual_downloads/` folder
3. Run the updater - it will find and use the local file

Generate a download list:

```bash
python generate_download_list.py --component shc --format text
```

## Troubleshooting

### "No Splunkbase ID found"

Run with `--list-apps` to see which apps are missing IDs:

```bash
python main.py --list-apps
```

Add missing IDs to `config.yaml`:

```yaml
splunkbase_id_mapping:
  your_app_name: "1234"
```

### "Authentication failed"

- Verify Splunkbase username/password in `config.yaml`
- Ensure your account has download permissions
- Try logging into Splunkbase.com manually to verify credentials

### Git Errors

Check:
- Git is installed: `git --version`
- No uncommitted changes in repos
- Not in detached HEAD state

### Version Matching Issues

If shared apps aren't finding non-prod versions:
- Ensure `config.yaml` has separate entries for nonprod/ and shared/ subdirectories
- Verify environment labels match: "non-prod" and "shared"
- Check that app names are identical in both environments

### Download Caching

Previously downloaded files are cached in `work/downloads/`. The tool checks there first before downloading from Splunkbase. To force re-download, delete the cached file.

## Daily Workflow Examples

### Scenario 1: Update Non-Prod Apps

```bash
# Check what needs updating
python main.py --environment non-prod --check-only

# Update interactively
python main.py --environment non-prod

# Review and push
python main.py --show-diffs --full-diff
python main.py --push-branches
```

### Scenario 2: Promote to Shared/Prod

```bash
# Update shared apps (will match non-prod versions)
python main.py --environment shared

# The tool automatically uses non-prod's versions
# Review what was selected
python main.py --show-diffs --full-diff

# Push and create MRs
python main.py --push-branches
```

### Scenario 3: Update Specific App Pattern

```bash
# Update all Splunk TA apps
python main.py --app "Splunk_TA_*"

# Update specific app
python main.py --app "Splunk_TA_windows"
```

## Files and Directories

### Configuration
- `config.yaml` - Your configuration (not in Git)
- `config.yaml.example` - Template for new users
- `config.yaml.example-environments` - Advanced examples

### Runtime
- `work/` - Working directory (downloads, tracking, reports)
  - `downloads/` - Cached downloads from Splunkbase
  - `extracted/` - Temporary extraction location
  - `backups/` - Automatic backups of replaced apps
  - `update_tracking.json` - Tracks pending/pushed/merged updates
  - `*_report_*.txt` - Detailed update reports
- `manual_downloads/` - Place manual downloads here
- `splunk_app_updater.log` - Detailed logs

### Documentation
- `README.md` - Main documentation
- `GETTING_STARTED.md` - This file
- `APP_SELECTION_GUIDE.md` - App selection patterns
- `ENVIRONMENT_REGION_GUIDE.md` - Environment filtering
- `CHANGELOG.md` - Version history

## Getting Help

1. **Check documentation**: Start with `README.md`
2. **Review logs**: Check `splunk_app_updater.log` with `--debug` flag
3. **Test mode**: Use `--test-mode` to experiment safely
4. **Dry run**: Use `--dry-run` to preview changes

## Best Practices

1. **Always test in non-prod first**: Update non-prod, test, then promote to shared
2. **Review changes**: Use `--show-diffs --full-diff` before pushing
3. **One environment at a time**: Update non-prod, then shared separately
4. **Check tracking**: Use `--show-pending` to see what's in flight
5. **Keep credentials secure**: Never commit `config.yaml`
6. **Use test mode**: Test new workflows with `--test-mode` first

## Common Commands Reference

```bash
# Preview updates
python main.py --check-only

# Update interactively (default)
python main.py

# Update all automatically
python main.py --no-interactive

# Filter by component
python main.py --component shc

# Filter by environment
python main.py --environment non-prod

# Combine filters
python main.py --env non-prod --component shc

# View diffs
python main.py --show-diffs --full-diff

# Push branches
python main.py --push-branches

# View pending
python main.py --show-pending

# Debug mode
python main.py --debug

# Dry run
python main.py --dry-run

# Test mode
python main.py --test-mode
python main.py --clear-test-updates

# List all apps
python main.py --list-apps
```

---

**Questions?** Check the [README.md](README.md) for detailed documentation or review the [CHANGELOG.md](CHANGELOG.md) for recent features.
