# CSV Import Guide

This guide explains how to import app lists from CSV files to update specific apps.

## Overview

The CSV import feature allows you to:
1. Import a list of apps from a CSV file (e.g., from Splunk's app inventory report)
2. Update only the apps in that list
3. Extract Splunkbase IDs for easy configuration

## CSV Format

The tool expects a CSV with the following columns:

| Column | Required | Description |
|--------|----------|-------------|
| `App` | Yes | Display name of the app |
| `splunkbase_url` | Recommended | URL containing Splunkbase ID (e.g., `https://splunkbase.splunk.com/app/742/`) |
| `version` | Optional | Current version |
| `Available Version` | Optional | Target version |

**Example CSV:**
```csv
App,author,splunkbase_url,version,Available Version
"Splunk Add-on for Microsoft Windows",Splunkbase,"https://splunkbase.splunk.com/app/742/","8.8.0","9.0.1"
"Splunk Add-on for AWS",Splunkbase,"https://splunkbase.splunk.com/app/1876/","7.3.0","8.0.0"
"TA-user-agents",Splunkbase,"https://splunkbase.splunk.com/app/1843/","1.7.8","1.7.10"
```

## Usage

### Basic Import

Import apps from CSV and update them interactively:

```bash
python main.py --import-csv path/to/apps.csv
```

This will:
1. Parse the CSV file
2. Extract app names and Splunkbase IDs
3. Filter discovered apps to only those in the CSV
4. Show interactive selection menu
5. Update selected apps

### Check What Would Be Updated

Preview which apps match:

```bash
python main.py --import-csv path/to/apps.csv --check-only
```

### Export Splunkbase ID Mapping

Generate config.yaml mapping from CSV:

```bash
python main.py --import-csv path/to/apps.csv --export-csv-mapping
```

This creates `work/csv_id_mapping.yaml` with:

```yaml
# Splunkbase ID mapping from CSV import
splunkbase_id_mapping:
  Splunk_TA_windows: "742"  # Splunk Add-on for Microsoft Windows
  Splunk_TA_aws: "1876"  # Splunk Add-on for AWS
  TA-user-agents: "1843"  # PAVO TA User Agents
```

Copy this into your `config.yaml`.

### Update All CSV Apps Automatically

Skip interactive selection:

```bash
python main.py --import-csv path/to/apps.csv --no-interactive
```

### Combine with Filters

Filter by component and CSV list:

```bash
# Update only search head apps from CSV
python main.py --import-csv apps.csv --component shc

# Update only non-prod apps from CSV
python main.py --import-csv apps.csv --environment non-prod
```

## Name Matching

The tool attempts to match CSV display names to folder names:

| CSV Display Name | Guessed Folder Name |
|-----------------|---------------------|
| "Splunk Add-on for Microsoft Windows" | `Splunk_TA_windows` |
| "Splunk Add-on for AWS" | `Splunk_TA_aws` |
| "Splunk App for Infrastructure" | `splunk_app_infrastructure` |
| "TA-user-agents" | `TA_user_agents` |

**Note:** Name matching is approximate. If apps don't match:

1. Use `--export-csv-mapping` to see what was imported
2. Check folder names in your repos
3. Manually adjust the CSV or use `--app` pattern matching instead

### Flexible Matching

The tool uses flexible matching (case-insensitive, partial matches):
- "Splunk_TA_windows" matches "Splunk Add-on for Microsoft Windows"
- "TA-user-agents" matches "TA_user_agents"
- Both forward slashes and underscores work

## Common Workflows

### Workflow 1: Update Apps from Splunk Inventory Report

1. **Export from Splunk:**
   - Run app inventory query in Splunk
   - Export results as CSV
   - Save to local file

2. **Preview what will be updated:**
   ```bash
   python main.py --import-csv inventory.csv --check-only
   ```

3. **Export ID mapping (first time):**
   ```bash
   python main.py --import-csv inventory.csv --export-csv-mapping
   ```
   - Copy output to `config.yaml`

4. **Update apps:**
   ```bash
   python main.py --import-csv inventory.csv
   ```

### Workflow 2: Update Specific Subset

You have a list of apps that need urgent updates:

1. **Create CSV:**
   ```csv
   App,splunkbase_url
   "Splunk Add-on for Microsoft Windows","https://splunkbase.splunk.com/app/742/"
   "Splunk Add-on for AWS","https://splunkbase.splunk.com/app/1876/"
   ```

2. **Update only non-prod:**
   ```bash
   python main.py --import-csv urgent_updates.csv --environment non-prod
   ```

3. **Review and push:**
   ```bash
   python main.py --show-diffs --full-diff
   python main.py --push-branches
   ```

4. **After testing, update shared:**
   ```bash
   python main.py --import-csv urgent_updates.csv --environment shared
   ```

### Workflow 3: Batch Update by Component

Update all search head apps from CSV:

```bash
# Check first
python main.py --import-csv apps.csv --component shc --check-only

# Update
python main.py --import-csv apps.csv --component shc --no-interactive
```

## Troubleshooting

### "No apps matched CSV import list"

**Problem:** CSV display names don't match folder names.

**Solutions:**

1. **Export mapping to see what was imported:**
   ```bash
   python main.py --import-csv apps.csv --export-csv-mapping
   ```
   Check `work/csv_id_mapping.yaml` for guessed folder names.

2. **Check actual folder names:**
   ```bash
   python main.py --list-apps
   ```
   Compare with CSV names.

3. **Use pattern matching instead:**
   ```bash
   python main.py --app "Splunk_TA_*"
   ```

### "No Splunkbase ID found"

**Problem:** CSV doesn't have `splunkbase_url` column or URLs are malformed.

**Solutions:**

1. **Add `splunkbase_url` column** with format: `https://splunkbase.splunk.com/app/123/`

2. **Manually configure IDs** in `config.yaml`:
   ```yaml
   splunkbase_id_mapping:
     your_app: "1234"
   ```

### CSV Apps Not Discovered

**Problem:** Apps in CSV aren't found in your repos.

**Possible causes:**
- Apps are in different repos than configured
- App folder names differ from CSV names
- Apps aren't deployed in filtered environment/component

**Solutions:**

1. **Check all repos:**
   ```bash
   python main.py --list-apps
   ```

2. **Remove filters:**
   ```bash
   python main.py --import-csv apps.csv --check-only
   # (no --component or --environment filters)
   ```

3. **Verify repo configuration** in `config.yaml`

## Example CSV Templates

### Minimal CSV

```csv
App,splunkbase_url
"Splunk Add-on for Microsoft Windows","https://splunkbase.splunk.com/app/742/"
"Splunk Add-on for AWS","https://splunkbase.splunk.com/app/1876/"
```

### From Splunk Query

Run this SPL to generate CSV:

```spl
| rest /services/apps/local
| where disabled=0 AND visible=1
| eval splunkbase_url="https://splunkbase.splunk.com/app/" + 
    if(isnull(splunkbase_id), "", splunkbase_id + "/")
| table label author version splunkbase_url
| rename label AS App
| outputcsv apps_inventory.csv
```

### Full Format

```csv
App,author,count,host,version,Available Version,Cloud Compatible,splunkbase_url
"Splunk Add-on for Microsoft Windows",Splunkbase,31,"indexer infosec searchcluster","8.7.0 8.8.0","9.0.1",True,"https://splunkbase.splunk.com/app/742/"
```

## Tips

1. **Always use `--check-only` first** to preview what will be updated

2. **Export mapping on first use** to verify name matching:
   ```bash
   python main.py --import-csv apps.csv --export-csv-mapping
   ```

3. **Combine with test mode** for safe experimentation:
   ```bash
   python main.py --import-csv apps.csv --test-mode
   ```

4. **Use with dry-run** to see full workflow without changes:
   ```bash
   python main.py --import-csv apps.csv --dry-run
   ```

5. **Filter by environment** to follow promotion workflow:
   ```bash
   # Update non-prod first
   python main.py --import-csv apps.csv --env non-prod
   
   # Then promote to shared
   python main.py --import-csv apps.csv --env shared
   ```

## See Also

- [APP_SELECTION_GUIDE.md](APP_SELECTION_GUIDE.md) - Other app selection methods
- [ENVIRONMENT_REGION_GUIDE.md](ENVIRONMENT_REGION_GUIDE.md) - Environment filtering
- [GETTING_STARTED.md](GETTING_STARTED.md) - Basic usage guide
