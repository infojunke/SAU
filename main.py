#!/usr/bin/env python3
"""
Splunk App Updater - Main entry point

This is a backwards-compatible wrapper that imports from the new modular structure.
For development, you can also import directly from the splunk_updater package.
"""

from splunk_updater.cli import main

if __name__ == '__main__':
    main()
