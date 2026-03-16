"""Test AppInspect validation functionality"""

from pathlib import Path
from splunk_updater.app_validator import AppValidator


def test_validator_availability():
    """Test if AppInspect is available"""
    validator = AppValidator()
    
    print("=" * 80)
    print("APPINSPECT AVAILABILITY TEST")
    print("=" * 80)
    
    if validator.is_available():
        print("✓ AppInspect is installed and available")
    else:
        print("⊘ AppInspect is not installed")
        print("\nTo install AppInspect:")
        print("  pip install splunk-appinspect")
    
    print("=" * 80 + "\n")


def test_validation_output():
    """Test validation output format"""
    print("=" * 80)
    print("APPINSPECT VALIDATION OUTPUT TEST")
    print("=" * 80)
    
    validator = AppValidator(mode='test')
    
    # Example apps (paths won't exist, just for testing output format)
    test_apps = [
        ('Splunk_TA_windows', Path('C:/test/Splunk_TA_windows')),
        ('Splunk_TA_aws', Path('C:/test/Splunk_TA_aws')),
        ('custom_app', Path('C:/test/custom_app'))
    ]
    
    # This will show the structure even if apps don't exist
    results = validator.validate_apps(test_apps)
    validator.print_summary(results)


if __name__ == '__main__':
    test_validator_availability()
    # Uncomment to test output format:
    # test_validation_output()
