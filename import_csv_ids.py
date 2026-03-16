"""Import Splunkbase IDs from CSV into config.yaml"""

import csv
import yaml
from pathlib import Path

def normalize_name(name: str) -> str:
    """Normalize app name for comparison"""
    return name.lower().replace('-', '_').replace(' ', '_')

def import_ids_from_csv(csv_path: str, config_path: str = 'config.yaml'):
    """Import IDs from CSV and merge with existing config without duplicates"""
    
    # Read existing config
    config_file = Path(config_path)
    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    existing_mapping = config.get('splunkbase_id_mapping', {})
    
    # Create normalized lookup for existing entries
    normalized_existing = {normalize_name(k): k for k in existing_mapping.keys()}
    
    # Read CSV
    new_entries = {}
    skipped_duplicates = []
    skipped_no_id = []
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            app_name = row['App Name'].strip()
            app_id = row['App ID'].strip()
            
            # Skip if no ID
            if not app_id:
                skipped_no_id.append(app_name)
                continue
            
            # Check if already exists (normalized comparison)
            norm_name = normalize_name(app_name)
            if norm_name in normalized_existing:
                existing_name = normalized_existing[norm_name]
                existing_id = existing_mapping[existing_name]
                if existing_id == app_id:
                    skipped_duplicates.append(f"{app_name} (already exists as {existing_name})")
                else:
                    print(f"⚠️  Conflict: {app_name} in CSV has ID {app_id}, but exists as {existing_name} with ID {existing_id}")
                continue
            
            # Add new entry
            new_entries[app_name] = app_id
    
    # Print summary
    print(f"\n{'=' * 80}")
    print(f"CSV IMPORT SUMMARY")
    print(f"{'=' * 80}")
    print(f"New entries to add: {len(new_entries)}")
    print(f"Skipped (already in config): {len(skipped_duplicates)}")
    print(f"Skipped (no ID in CSV): {len(skipped_no_id)}")
    print(f"{'=' * 80}\n")
    
    if skipped_duplicates:
        print(f"Already in config ({len(skipped_duplicates)} apps):")
        for app in sorted(skipped_duplicates)[:10]:
            print(f"  - {app}")
        if len(skipped_duplicates) > 10:
            print(f"  ... and {len(skipped_duplicates) - 10} more")
        print()
    
    if new_entries:
        print(f"\nNew entries to add to config.yaml ({len(new_entries)} apps):\n")
        print("# New entries from CSV import")
        for app_name, app_id in sorted(new_entries.items()):
            print(f'  {app_name}: "{app_id}"')
        print()
        
        # Ask for confirmation
        response = input("\nAdd these entries to config.yaml? (yes/no): ").strip().lower()
        if response in ('yes', 'y'):
            # Merge new entries into existing mapping
            existing_mapping.update(new_entries)
            config['splunkbase_id_mapping'] = existing_mapping
            
            # Write back to config
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            
            print(f"\n✅ Successfully added {len(new_entries)} new entries to {config_path}")
        else:
            print("\n❌ Import cancelled")
    else:
        print("No new entries to add. All apps with IDs are already in config.yaml!")

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    else:
        csv_file = 'splunk_apps_full_with_ids.csv'
    import_ids_from_csv(csv_file)
