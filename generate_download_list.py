#!/usr/bin/env python3
"""
Generate a list of apps to download manually from Splunkbase
"""

import sys
from splunk_app_updater import SplunkAppUpdater
import argparse

def main():
    parser = argparse.ArgumentParser(
        description='Generate download list for manual Splunkbase downloads'
    )
    parser.add_argument(
        '--config',
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )
    parser.add_argument(
        '--component',
        choices=['ds', 'shc', 'cm', 'deployment-server', 'search-head', 'cluster-manager'],
        help='Filter to specific component'
    )
    parser.add_argument(
        '--format',
        choices=['text', 'csv', 'powershell', 'bash'],
        default='text',
        help='Output format (default: text)'
    )
    
    args = parser.parse_args()
    
    # Initialize updater
    updater = SplunkAppUpdater(args.config)
    
    # Normalize component filter
    component_filter = None
    if args.component:
        component_map = {
            'ds': 'ds',
            'deployment-server': 'ds',
            'shc': 'shc',
            'search-head': 'shc',
            'cm': 'cm',
            'cluster-manager': 'cm'
        }
        component_filter = component_map.get(args.component.lower())
    
    # Discover apps
    apps = updater.discover_apps(component_filter=component_filter)
    
    # Check for updates
    apps_with_updates = updater.check_for_updates(apps)
    
    if not apps_with_updates:
        print("No updates available")
        return
    
    # Generate output based on format
    if args.format == 'text':
        print("\n" + "=" * 80)
        print("SPLUNKBASE MANUAL DOWNLOAD LIST")
        print("=" * 80)
        print(f"\nTotal apps needing updates: {len(apps_with_updates)}\n")
        print("Instructions:")
        print("1. Log in to Splunkbase: https://splunkbase.splunk.com/")
        print("2. Download each app using the URLs below")
        print("3. Place downloaded files in: manual_downloads/")
        print("4. Run the updater again\n")
        print("-" * 80)
        
        for app in apps_with_updates:
            print(f"\nApp: {app.name}")
            print(f"  Current Version: {app.current_version}")
            print(f"  New Version: {app.latest_version}")
            print(f"  Splunkbase ID: {app.splunkbase_id}")
            print(f"  Download URL: https://splunkbase.splunk.com/app/{app.splunkbase_id}/")
            print(f"  Direct Link: https://splunkbase.splunk.com/app/{app.splunkbase_id}/#/details")
    
    elif args.format == 'csv':
        print("app_name,current_version,new_version,splunkbase_id,download_url")
        for app in apps_with_updates:
            print(f"{app.name},{app.current_version},{app.latest_version},{app.splunkbase_id},"
                  f"https://splunkbase.splunk.com/app/{app.splunkbase_id}/")
    
    elif args.format == 'powershell':
        print("# PowerShell script to open download pages in browser")
        print("# Run this to open all download pages\n")
        for app in apps_with_updates:
            print(f"Start-Process 'https://splunkbase.splunk.com/app/{app.splunkbase_id}/'  "
                  f"# {app.name} v{app.latest_version}")
    
    elif args.format == 'bash':
        print("#!/bin/bash")
        print("# Bash script to open download pages in browser\n")
        for app in apps_with_updates:
            print(f"xdg-open 'https://splunkbase.splunk.com/app/{app.splunkbase_id}/'  "
                  f"# {app.name} v{app.latest_version}")
    
    print("\n" + "=" * 80)
    print(f"\nTotal: {len(apps_with_updates)} apps")

if __name__ == '__main__':
    main()
