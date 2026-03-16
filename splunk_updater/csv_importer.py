"""CSV import functionality for app lists"""

import csv
import logging
import re
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class CSVAppImporter:
    """Import app lists from CSV files"""
    
    @staticmethod
    def import_from_csv(csv_path: Path) -> List[Dict[str, str]]:
        """
        Import app list from CSV file.
        
        Expected CSV format:
        - App: App name
        - splunkbase_url: URL with app ID (e.g., https://splunkbase.splunk.com/app/1467/)
        - version: Current version (optional)
        - Available Version: Target version (optional)
        
        Args:
            csv_path: Path to CSV file
            
        Returns:
            List of dicts with keys: name, splunkbase_id, current_version, target_version
        """
        if not csv_path.exists():
            logger.error(f"CSV file not found: {csv_path}")
            return []
        
        apps = []
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    app_info = CSVAppImporter._parse_row(row)
                    if app_info:
                        apps.append(app_info)
                        logger.debug(f"Imported: {app_info['name']} (ID: {app_info.get('splunkbase_id', 'N/A')})")
            
            logger.info(f"Imported {len(apps)} apps from {csv_path}")
            return apps
            
        except Exception as e:
            logger.error(f"Error reading CSV file {csv_path}: {e}")
            return []
    
    @staticmethod
    def _parse_row(row: Dict[str, str]) -> Optional[Dict[str, str]]:
        """Parse a CSV row into app info"""
        try:
            # Extract app name
            app_name = row.get('App', '').strip()
            if not app_name:
                return None
            
            # Extract Splunkbase ID from URL
            splunkbase_id = None
            url = row.get('splunkbase_url', '')
            if url:
                match = re.search(r'/app/(\d+)/', url)
                if match:
                    splunkbase_id = match.group(1)
            
            # Extract versions
            current_version = row.get('version', '').strip()
            target_version = row.get('Available Version', '').strip()
            
            # Clean up app name (remove extra quotes)
            app_name = app_name.strip('"')
            
            # Convert app name to likely folder name
            # "Splunk Add-on for Microsoft Windows" -> "Splunk_TA_windows"
            # This is approximate - user may need to adjust
            folder_name = CSVAppImporter._guess_folder_name(app_name)
            
            app_info = {
                'name': folder_name,
                'display_name': app_name,
            }
            
            if splunkbase_id:
                app_info['splunkbase_id'] = splunkbase_id
            
            if current_version:
                app_info['current_version'] = current_version
            
            if target_version:
                app_info['target_version'] = target_version
            
            return app_info
            
        except Exception as e:
            logger.debug(f"Error parsing row: {e}")
            return None
    
    @staticmethod
    def _guess_folder_name(display_name: str) -> str:
        """
        Attempt to convert display name to folder name.
        This is approximate and may need manual adjustment.
        """
        # Common patterns
        if display_name.startswith("Splunk Add-on for "):
            app_part = display_name.replace("Splunk Add-on for ", "")
            # Simple conversion - real apps may vary
            return f"Splunk_TA_{app_part.replace(' ', '_').lower()}"
        
        if display_name.startswith("Splunk App for "):
            app_part = display_name.replace("Splunk App for ", "")
            return f"splunk_app_{app_part.replace(' ', '_').lower()}"
        
        # Default: replace spaces with underscores
        return display_name.replace(' ', '_').replace('-', '_')
    
    @staticmethod
    def export_id_mapping(apps: List[Dict[str, str]], output_path: Optional[Path] = None) -> str:
        """
        Export app ID mapping in config.yaml format.
        
        Args:
            apps: List of app info dicts
            output_path: Optional path to save output
            
        Returns:
            YAML formatted string
        """
        lines = ["# Splunkbase ID mapping from CSV import"]
        lines.append("splunkbase_id_mapping:")
        
        for app in apps:
            if 'splunkbase_id' in app:
                name = app['name']
                app_id = app['splunkbase_id']
                display = app.get('display_name', name)
                lines.append(f'  {name}: "{app_id}"  # {display}')
        
        output = '\n'.join(lines)
        
        if output_path:
            output_path.write_text(output)
            logger.info(f"Exported ID mapping to {output_path}")
        
        return output
