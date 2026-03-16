#!/usr/bin/env python3
"""
Test script to demonstrate branch name sanitization with environment/region
"""

import re
from datetime import datetime
from typing import Optional


def sanitize_branch_name_old(app_name: str, new_version: str) -> str:
    """Old method - update/ prefix"""
    safe_version = new_version.replace('.', '_').replace('/', '-').replace(':', '-')
    safe_app_name = app_name.replace(' ', '-').replace('_', '-')
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    return f"update/{safe_app_name}-v{safe_version}-{timestamp}"


def sanitize_branch_name_new(app_name: str, new_version: str, environment: Optional[str] = None, region: Optional[str] = None) -> str:
    """New method - environment-region prefix"""
    # Sanitize version string for branch name
    safe_version = new_version.replace('.', '_').replace('/', '-').replace(':', '-')
    safe_app_name = app_name.replace(' ', '-').replace('_', '-')
    
    # Build branch prefix from environment and region
    prefix_parts = []
    if environment:
        prefix_parts.append(environment.lower())
    if region:
        prefix_parts.append(region.lower())
    
    # If no environment/region, fall back to 'update'
    prefix = '-'.join(prefix_parts) if prefix_parts else 'update'
    
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    return f"{prefix}-{safe_app_name}-v{safe_version}-{timestamp}"


print("=" * 80)
print("BRANCH NAME WITH ENVIRONMENT/REGION")
print("=" * 80)

test_cases = [
    ("Splunk_TA_windows", "9.1.2", "shared", None),
    ("Splunk_TA_nix", "10.2.0", "non-prod", "east"),
    ("Splunk_TA_aws", "7.3.0", "prod", "west"),
    ("Splunk SA CIM", "5.0.1", "non-prod", "west"),
    ("Splunk_TA_oracle", "3.0.0", None, None),  # No env/region
]

print("\n📋 Old Format (update/ prefix):")
print("-" * 80)
for app_name, version, env, region in test_cases:
    old_branch = sanitize_branch_name_old(app_name, version)
    print(f"  {old_branch}")

print("\n✨ New Format (environment-region/ prefix):")
print("-" * 80)
for app_name, version, env, region in test_cases:
    new_branch = sanitize_branch_name_new(app_name, version, env, region)
    metadata = []
    if env:
        metadata.append(f"Env: {env}")
    if region:
        metadata.append(f"Region: {region}")
    metadata_str = f"  ({', '.join(metadata)})" if metadata else "  (no metadata)"
    print(f"  {new_branch}{metadata_str}")

print("\n" + "=" * 80)
print("EXAMPLES:")
print("=" * 80)
print("✓ Shared environment (no region):")
print("    shared/Splunk-TA-windows-v9_1_2-20251222-094719")
print()
print("✓ Non-prod East:")
print("    non-prod-east/Splunk-TA-nix-v10_2_0-20251222-094719")
print()
print("✓ Prod West:")
print("    prod-west/Splunk-TA-aws-v7_3_0-20251222-094719")
print()
print("✓ No environment/region (fallback):")
print("    update/Splunk-TA-oracle-v3_0_0-20251222-094719")
print("\n✅ Branch names now include deployment context!")
