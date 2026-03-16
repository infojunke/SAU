# Environment and Region Filtering

This guide explains how to use environment and region filtering to target specific deployments.

## Overview

The Splunk App Updater now supports filtering by:
- **Environment**: prod, non-prod, shared, dev, test, etc.
- **Region**: east, west, central, or any custom region names
- **Component**: ds (deployment server), shc (search head cluster), cm (cluster manager)

You can combine these filters to precisely target which apps to update.

## Configuration

### New Config Format (Recommended)

Update your `config.yaml` to include environment and region metadata for each repository:

```yaml
gitlab_repos:
  # Production environments
  - path: "C:/repos/prod-east-ds-config"
    environment: "prod"
    region: "east"
    component: "ds"
  
  - path: "C:/repos/prod-west-shc-config"
    environment: "prod"
    region: "west"
    component: "shc"
  
  # Non-production environments
  - path: "C:/repos/non-prod-east-ds-config"
    environment: "non-prod"
    region: "east"
    component: "ds"
  
  - path: "C:/repos/non-prod-west-shc-config"
    environment: "non-prod"
    region: "west"
    component: "shc"
  
  # Shared environments (no region)
  - path: "C:/repos/shared-ds-config"
    environment: "shared"
    component: "ds"
  
  - path: "C:/repos/shared-cm-config"
    environment: "shared"
    component: "cm"
```

### Backward Compatible Format

The old string format still works:

```yaml
gitlab_repos:
  - "C:/repos/splunk-ds-config"
  - "C:/repos/splunk-sh-config"
```

When using this format, the tool will attempt to detect environment/region from the path name.

## Command-Line Usage

### Filter by Environment

Update only apps in a specific environment:

```bash
# Shared environment only
python splunk_app_updater.py --environment shared

# Non-prod environment only
python splunk_app_updater.py --environment non-prod --check-only

# Prod environment only
python splunk_app_updater.py --environment prod --interactive
```

### Filter by Region

Update only apps in a specific region:

```bash
# East region only
python splunk_app_updater.py --region east

# West region only
python splunk_app_updater.py --region west --check-only
```

### Combine Multiple Filters

Combine environment, region, and component filters for precise targeting:

```bash
# Non-prod East deployment servers
python splunk_app_updater.py --environment non-prod --region east --component ds

# Prod West search heads
python splunk_app_updater.py --environment prod --region west --component shc

# Shared cluster managers (no region)
python splunk_app_updater.py --environment shared --component cm

# Non-prod East search heads, interactive selection
python splunk_app_updater.py --env non-prod --region east --component shc --interactive
```

### Heavy Forwarder Support

If your deployment server manages heavy forwarders (which perform searches), use the `hf` component:

```bash
# Update heavy forwarder deployment server
python splunk_app_updater.py --component hf

# Update non-prod heavy forwarders only
python splunk_app_updater.py --environment non-prod --component hf
```

**Why use `hf` instead of `ds`?**
- Heavy forwarders can execute searches and need lookups, saved searches, macros, and eventtypes
- The `ds` component (universal forwarders) excludes these files
- The `hf` component includes search capabilities while excluding UI elements

**Configuration example:**
```yaml
gitlab_repos:
  - path: "C:/repos/heavy-forwarder-config"
    environment: "prod"
    component: "hf"  # Use 'hf' for heavy forwarders
  
  - path: "C:/repos/universal-forwarder-config"
    environment: "prod"
    component: "ds"  # Use 'ds' for universal forwarders
```

## Real-World Scenarios

### Scenario 1: Update Shared Environment

Your shared environment hosts apps used across multiple prod/non-prod systems:

```bash
# Check what's available in shared
python splunk_app_updater.py --environment shared --check-only

# Update all shared apps
python splunk_app_updater.py --environment shared

# Update only shared deployment server apps
python splunk_app_updater.py --environment shared --component ds
```

### Scenario 2: Regional Rollout

Roll out updates region by region:

```bash
# Phase 1: Update East region first
python splunk_app_updater.py --region east --check-only
python splunk_app_updater.py --region east --interactive

# Phase 2: After testing, update West region
python splunk_app_updater.py --region west --interactive
```

### Scenario 3: Environment-Specific Updates

Update non-prod first for testing:

```bash
# Step 1: Update non-prod
python splunk_app_updater.py --environment non-prod --check-only
python splunk_app_updater.py --environment non-prod

# Step 2: After validation, update prod
python splunk_app_updater.py --environment prod --check-only
python splunk_app_updater.py --environment prod --interactive
```

### Scenario 4: Targeted Component Update

Update specific component in specific environment and region:

```bash
# Non-prod East search heads only
python splunk_app_updater.py --env non-prod --region east --component shc --app "Splunk_TA_*"

# Shared deployment servers only
python splunk_app_updater.py --env shared --component ds --interactive
```

## Filter Combinations

| Environment | Region | Component | Example Use Case |
|------------|--------|-----------|------------------|
| prod | east | shc | Production East search heads |
| prod | west | ds | Production West deployment servers |
| non-prod | east | cm | Non-prod East cluster managers |
| non-prod | west | shc | Non-prod West search heads |
| shared | - | ds | Shared deployment servers |
| shared | - | cm | Shared cluster managers |

## Path-Based Fallback

If you don't specify environment/region in config, the tool tries to detect from path:

```yaml
gitlab_repos:
  - "C:/repos/prod-east-ds-config"    # Detects: prod, east, ds
  - "C:/repos/nonprod-west-shc"       # Detects: nonprod, west, shc
  - "C:/repos/shared-cm-config"       # Detects: shared, cm
```

The tool looks for these keywords in paths:
- **Environment**: prod, non-prod, nonprod, shared, dev, test
- **Region**: east, west, central, north, south
- **Component**: ds, shc, cm, deployment, search, cluster

## Migration Guide

### From Old Config to New Config

**Old format:**
```yaml
gitlab_repos:
  - "C:/repos/prod-east-ds-config"
  - "C:/repos/nonprod-west-shc-config"
```

**New format:**
```yaml
gitlab_repos:
  - path: "C:/repos/prod-east-ds-config"
    environment: "prod"
    region: "east"
    component: "ds"
  
  - path: "C:/repos/nonprod-west-shc-config"
    environment: "non-prod"
    region: "west"
    component: "shc"
```

**Benefits of new format:**
- Explicit configuration (no guessing from path)
- More reliable filtering
- Better logging and debugging
- Supports any custom names

## Complete Examples

### Example 1: Careful Production Rollout

```bash
# 1. Check shared environment
python splunk_app_updater.py --env shared --check-only

# 2. Update shared environment
python splunk_app_updater.py --env shared --interactive

# 3. Test in non-prod East
python splunk_app_updater.py --env non-prod --region east --check-only
python splunk_app_updater.py --env non-prod --region east --interactive

# 4. Roll to non-prod West
python splunk_app_updater.py --env non-prod --region west --interactive

# 5. Finally, prod rollout (East then West)
python splunk_app_updater.py --env prod --region east --interactive
python splunk_app_updater.py --env prod --region west --interactive
```

### Example 2: Emergency Hotfix

Update specific app across all environments in one region:

```bash
# Update Splunk_TA_windows in East region across all environments
python splunk_app_updater.py --region east --app "Splunk_TA_windows"
```

### Example 3: Component-Specific Maintenance

Update all deployment servers in non-prod:

```bash
# All non-prod deployment servers
python splunk_app_updater.py --env non-prod --component ds --check-only
python splunk_app_updater.py --env non-prod --component ds --interactive
```

## Tips

1. **Always use --check-only first** to preview what will be updated
2. **Use --interactive with filters** for maximum control
3. **Update shared environment first** if apps are used across environments
4. **Test in non-prod** before updating prod
5. **Roll out by region** for safer deployments
6. **Combine with --app patterns** for targeted updates

## Command Reference

```bash
# Environment filtering
--environment <env>    # or --env <env>
--region <region>

# Combinations
--env shared                              # All shared repos
--env prod --region east                  # Prod East only
--env non-prod --region west --component shc  # Non-prod West search heads
--env shared --component ds --interactive # Shared DS with selection

# With app selection
--env prod --app "Splunk_TA_*"           # Prod TAs only
--env non-prod --region east --app "SA-*" --interactive  # Non-prod East SAs

# Check before updating
--env prod --check-only                   # See what's available in prod
--region west --check-only                # See what's available in west
```

## Troubleshooting

### No apps found
- Check `config.yaml` has correct paths
- Verify environment/region names match exactly (case-insensitive)
- Try without filters to see all repos: `--list-apps`

### Wrong repos being scanned
- Add explicit environment/region to `config.yaml`
- Check for typos in filter values
- Use `--check-only` to preview before updating

### Need to see which repos are being scanned
- Enable debug logging: Check `splunk_app_updater.log`
- Look for "Skipping" messages to see why repos were filtered out
- Use `--list-apps` to see discovered apps

## Logging

The tool logs filtering decisions:

```
INFO - Filtering to environment: non-prod
INFO - Filtering to region: east
INFO - Filtering to component: shc
DEBUG - Skipping C:/repos/prod-west-ds-config (environment 'prod' != 'non-prod')
DEBUG - Skipping C:/repos/non-prod-west-shc (region 'west' != 'east')
INFO - Scanning repository: C:/repos/non-prod-east-shc-config
```

Check `splunk_app_updater.log` for detailed filtering information.
