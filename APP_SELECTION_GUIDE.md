# App Selection Guide

This guide shows all the ways you can select which apps to update with the Splunk App Updater.

## Selection Methods

### 1. Update All Apps (Default)

Updates all apps that have available updates:

```bash
python splunk_app_updater.py
```

### 2. Single App by Name

Update one specific app by its exact name:

```bash
python splunk_app_updater.py --app "Splunk_TA_windows"
```

### 3. Multiple Apps (Comma-Separated)

Update multiple specific apps by listing them:

```bash
python splunk_app_updater.py --app "Splunk_TA_windows,Splunk_TA_nix,Splunk_TA_aws"
```

### 4. Pattern Matching (Wildcards)

Update apps matching a pattern:

```bash
# All Technology Add-ons
python splunk_app_updater.py --app "Splunk_TA_*"

# All apps starting with "SA-"
python splunk_app_updater.py --app "SA-*"

# Apps with specific substring
python splunk_app_updater.py --app "*windows*"
```

### 5. Interactive Selection (NEW!)

Choose apps from an interactive menu:

```bash
python splunk_app_updater.py --interactive
```

**Example interactive session:**
```
================================================================================
SELECT APPS TO UPDATE
================================================================================

Found 22 apps with updates available:

  1. Splunk_TA_windows
     Current: v8.8.0 -> New: v9.1.2
     Path: C:/repos/splunk-ds-config/apps/Splunk_TA_windows

  2. Splunk_TA_nix
     Current: v8.7.0 -> New: v9.0.1
     Path: C:/repos/splunk-ds-config/apps/Splunk_TA_nix

  3. Splunk_TA_aws
     Current: v7.2.0 -> New: v7.3.0
     Path: C:/repos/splunk-sh-config/apps/Splunk_TA_aws

  ... (more apps)

================================================================================

Selection options:
  - Enter numbers separated by commas (e.g., 1,3,5)
  - Enter ranges with dash (e.g., 1-3)
  - Enter 'all' to select all apps
  - Enter 'none' or press Ctrl+C to cancel

Select apps to update: 1,3,5-7

Selected 5 app(s):
  - Splunk_TA_windows (v8.8.0 -> v9.1.2)
  - Splunk_TA_aws (v7.2.0 -> v7.3.0)
  - Splunk_SA_CIM (v5.0.0 -> v5.1.0)
  - SA-Utils (v2.3.0 -> v2.4.0)
  - TA-alert_manager (v3.0.0 -> v3.1.0)
```

## Combining with Other Filters

### Component Filter + Interactive

Filter to specific component, then interactively select:

```bash
# Show only search head apps, then let me choose
python splunk_app_updater.py --component shc --interactive

# Show only deployment server apps, then let me choose
python splunk_app_updater.py --component ds --interactive

# Show only cluster manager apps, then let me choose
python splunk_app_updater.py --component cm --interactive
```

### Component Filter + Pattern

Filter by component and app name pattern:

```bash
# Update all TA apps on deployment server
python splunk_app_updater.py --component ds --app "Splunk_TA_*"

# Update specific apps on search head cluster
python splunk_app_updater.py --component shc --app "Splunk_TA_aws,Splunk_TA_windows"
```

### Check-Only Mode

Preview updates before selecting:

```bash
# See what's available, then decide
python splunk_app_updater.py --check-only

# See what's available for specific component
python splunk_app_updater.py --component ds --check-only
```

## Interactive Selection Examples

### Select by Numbers
```
Select apps to update: 1,3,5
```
Updates apps 1, 3, and 5 from the list.

### Select by Range
```
Select apps to update: 1-5
```
Updates apps 1 through 5 (inclusive).

### Combine Numbers and Ranges
```
Select apps to update: 1,3-5,8,10-12
```
Updates apps 1, 3, 4, 5, 8, 10, 11, and 12.

### Select All
```
Select apps to update: all
```
Updates all apps shown in the list.

### Cancel Selection
```
Select apps to update: none
```
Or just press Ctrl+C to cancel.

## Workflow Examples

### Scenario 1: Careful Updates
1. Check what's available: `python splunk_app_updater.py --check-only`
2. Use interactive mode: `python splunk_app_updater.py --interactive`
3. Select only the apps you want to test first

### Scenario 2: Update All Splunk TAs
```bash
python splunk_app_updater.py --app "Splunk_TA_*"
```

### Scenario 3: Update Search Head Apps One at a Time
```bash
# First see what's available
python splunk_app_updater.py --component shc --check-only

# Then update interactively
python splunk_app_updater.py --component shc --interactive
```

### Scenario 4: Batch Update Specific Apps
```bash
# Update multiple known apps at once
python splunk_app_updater.py --app "Splunk_TA_windows,Splunk_TA_nix,Splunk_SA_CIM"
```

## Tips

1. **Start with check-only**: Always use `--check-only` first to see what updates are available
2. **Use interactive mode for safety**: Interactive selection lets you carefully choose which apps to update
3. **Test with one component**: Use `--component` to limit scope when testing
4. **Use patterns for bulk updates**: Once confident, use wildcards for efficiency
5. **Combine filters**: Use component + pattern + interactive for maximum control

## Command Reference

```bash
# Basic commands
python splunk_app_updater.py                    # Update all apps
python splunk_app_updater.py --check-only       # Check only, no updates
python splunk_app_updater.py --list-apps        # List all discovered apps

# Selection options
python splunk_app_updater.py --app "NAME"                    # Single app
python splunk_app_updater.py --app "NAME1,NAME2,NAME3"      # Multiple apps
python splunk_app_updater.py --app "PATTERN*"               # Pattern match
python splunk_app_updater.py --interactive                   # Interactive menu

# Component filtering
python splunk_app_updater.py --component ds         # Deployment Server only
python splunk_app_updater.py --component shc        # Search Head Cluster only
python splunk_app_updater.py --component cm         # Cluster Manager only

# Combining options
python splunk_app_updater.py --component shc --interactive
python splunk_app_updater.py --component ds --app "Splunk_TA_*"
python splunk_app_updater.py --component cm --check-only

# Other options
python splunk_app_updater.py --no-branch            # Don't create Git branches
python splunk_app_updater.py --config custom.yaml   # Use custom config file
```
