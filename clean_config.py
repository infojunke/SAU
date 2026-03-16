"""Clean up config.yaml - move misplaced IDs and remove duplicates"""

import yaml
from pathlib import Path
from collections import OrderedDict

def normalize_name(name: str) -> str:
    """Normalize app name for comparison"""
    return name.lower().replace('-', '_').replace(' ', '_')

def clean_config(config_path: str = 'config.yaml'):
    """Clean up config.yaml"""
    
    # Read config
    config_file = Path(config_path)
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # Get sections
    id_mapping = config.get('splunkbase_id_mapping', {})
    checksums = config.get('sha256_checksums', {})
    
    # Find misplaced IDs in checksums (should be in id_mapping)
    misplaced_ids = {}
    valid_checksums = {}
    
    for key, value in checksums.items():
        # Valid checksum keys are in format "app_id:version" or have long hash values
        if ':' in str(key) and str(value).isdigit():
            # This is likely a misplaced ID (e.g., "app_id:version": "id")
            continue
        elif isinstance(value, str) and len(value) == 64:
            # Valid SHA256 hash
            valid_checksums[key] = value
        elif str(value).isdigit() and len(str(value)) < 10:
            # This is an ID, not a checksum - move to id_mapping
            misplaced_ids[key] = str(value)
        else:
            # Keep it in checksums
            valid_checksums[key] = value
    
    # Merge misplaced IDs into id_mapping (avoiding duplicates)
    normalized_existing = {normalize_name(k): k for k in id_mapping.keys()}
    
    moved_count = 0
    duplicate_count = 0
    
    for app_name, app_id in misplaced_ids.items():
        norm_name = normalize_name(app_name)
        if norm_name in normalized_existing:
            existing_name = normalized_existing[norm_name]
            existing_id = id_mapping[existing_name]
            if existing_id != app_id:
                print(f"⚠️  Conflict: {app_name} (ID {app_id}) vs {existing_name} (ID {existing_id})")
            duplicate_count += 1
        else:
            id_mapping[app_name] = app_id
            moved_count += 1
    
    # Remove duplicates from id_mapping itself
    seen_normalized = {}
    cleaned_id_mapping = {}
    removed_duplicates = []
    
    for app_name, app_id in id_mapping.items():
        norm_name = normalize_name(app_name)
        if norm_name in seen_normalized:
            # Duplicate found
            existing_name = seen_normalized[norm_name]
            existing_id = cleaned_id_mapping[existing_name]
            if existing_id == app_id:
                removed_duplicates.append(f"{app_name} (same as {existing_name})")
            else:
                print(f"⚠️  ID Conflict: keeping {existing_name}={existing_id}, removing {app_name}={app_id}")
                removed_duplicates.append(f"{app_name} (conflict with {existing_name})")
        else:
            cleaned_id_mapping[app_name] = app_id
            seen_normalized[norm_name] = app_name
    
    # Update config
    config['splunkbase_id_mapping'] = cleaned_id_mapping
    config['sha256_checksums'] = valid_checksums
    
    print(f"\n{'=' * 80}")
    print(f"CONFIG CLEANUP SUMMARY")
    print(f"{'=' * 80}")
    print(f"Moved from checksums to ID mapping: {moved_count}")
    print(f"Skipped (already in ID mapping): {duplicate_count}")
    print(f"Removed duplicate IDs: {len(removed_duplicates)}")
    print(f"Final ID mapping entries: {len(cleaned_id_mapping)}")
    print(f"Final checksum entries: {len(valid_checksums)}")
    print(f"{'=' * 80}\n")
    
    if removed_duplicates:
        print(f"Removed duplicates:")
        for item in removed_duplicates:
            print(f"  - {item}")
        print()
    
    # Write back
    with open(config_file, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    
    print(f"✅ Config cleaned and saved to {config_path}")
    print(f"\nRecommendation: Review {config_path} to ensure ID mapping looks correct.")

if __name__ == '__main__':
    clean_config()
