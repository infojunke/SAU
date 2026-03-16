"""Splunkbase API client"""

import hashlib
import logging
import re
import shutil
import sys
import time
import requests
from pathlib import Path
from typing import Dict, List, Optional

from .retry import retry_with_backoff, RetryError
from .cache import PersistentCache, CacheTTL

logger = logging.getLogger(__name__)


class SplunkbaseClient:
    """Client for interacting with Splunkbase API"""
    
    BASE_URL = "https://splunkbase.splunk.com/api/v1"
    
    def __init__(
        self, 
        username: str = '', 
        password: str = '', 
        sha256_checksums: Dict[str, str] = None,
        cache: Optional[PersistentCache] = None
    ):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.logged_in = False
        self.sha256_checksums = sha256_checksums or {}
        self._search_cache = {}  # Cache app name searches to avoid duplicate API calls
        self._verified_hashes = {}  # Cache of verified hashes during this session: {checksum_key: hash}
        self._releases_cache = {}  # Cache raw release lists by app_id to avoid duplicate API calls
        self.cache = cache  # Optional persistent cache for API responses
        self.no_interactive = False  # Set to True to skip interactive prompts
        
        # Login if credentials provided
        if username and password:
            self._login()
    
    def close(self):
        """Close the underlying requests session"""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _login(self) -> bool:
        """Login to Splunkbase to get session cookies"""
        
        @retry_with_backoff(
            max_retries=2,
            base_delay=2.0,
            max_delay=15.0,
            exceptions=(requests.RequestException, requests.Timeout)
        )
        def _do_login():
            login_url = "https://splunkbase.splunk.com/api/account:login/"
            response = self.session.post(
                login_url,
                data={'username': self.username, 'password': self.password},
                timeout=30
            )
            if response.status_code != 200:
                raise requests.HTTPError(f"Login failed with status {response.status_code}")
            return response
        
        try:
            _do_login()
            self.logged_in = True
            logger.debug("Successfully logged in to Splunkbase")
            return True
        except RetryError as e:
            logger.error(f"Splunkbase login failed after {e.attempts} attempts: {e.last_exception}")
            return False
        except Exception as e:
            logger.error(f"Error logging in to Splunkbase: {e}")
            return False
    
    def get_app_info(self, app_id: str) -> Optional[Dict]:
        """Get app information from Splunkbase"""
        
        @retry_with_backoff(
            max_retries=3,
            base_delay=1.0,
            max_delay=30.0,
            exceptions=(requests.RequestException, requests.Timeout)
        )
        def _fetch_app_info():
            url = f"{self.BASE_URL}/app/{app_id}"
            logger.debug(f"Fetching app info from: {url}")
            response = self.session.get(url, timeout=30)
            logger.debug(f"Response status: {response.status_code}")
            response.raise_for_status()
            return response.json()
        
        try:
            data = _fetch_app_info()
            logger.debug(f"Received app info for {app_id}")
            return data
        except RetryError as e:
            logger.error(f"Error fetching app info for ID {app_id} after {e.attempts} attempts: {e.last_exception}")
            return None
        except Exception as e:
            logger.error(f"Error fetching app info for ID {app_id}: {e}")
            return None
    
    def search_app_by_name(self, app_name: str) -> Optional[str]:
        """Search for an app by name and return its Splunkbase ID
        
        Note: Splunkbase API does not support search by app name.
        This function is maintained for compatibility but will not find IDs.
        Use the config.yaml splunkbase_id_mapping instead.
        
        Args:
            app_name: App name to search for (e.g., "Splunk_TA_windows")
        
        Returns:
            Splunkbase app ID as string, or None if not found
        """
        # Check cache first
        if app_name in self._search_cache:
            cached_result = self._search_cache[app_name]
            if cached_result:
                logger.debug(f"Using cached Splunkbase ID for {app_name}: {cached_result}")
            else:
                logger.debug(f"Using cached negative result for {app_name} (not found)")
            return cached_result
        
        # Splunkbase API does not support searching by app name via query parameters.
        # The API only supports:
        # - Getting app by ID: /api/v1/app/{id}
        # - Listing all apps: /api/v2/apps (paginated, no search)
        # 
        # To avoid wasting time with failing API calls, we immediately return None.
        # Users should add missing IDs to config.yaml's splunkbase_id_mapping section.
        
        logger.debug(f"Splunkbase API does not support name search. Add '{app_name}' to config.yaml splunkbase_id_mapping")
        self._search_cache[app_name] = None
        return None
    
    def get_latest_version(self, app_id: str) -> Optional[str]:
        """Get latest version of an app from Splunkbase"""
        versions = self.get_available_versions(app_id)
        return versions[0] if versions else None
    
    def get_available_versions(self, app_id: str) -> List[str]:
        """Get all available versions of an app from Splunkbase"""
        cache_key = f"versions_{app_id}"
        
        # Check persistent cache first
        if self.cache:
            cached_versions = self.cache.get(cache_key)
            if cached_versions is not None:
                logger.debug(f"Using cached versions for app ID {app_id}")
                return cached_versions
        
        logger.debug(f"Checking Splunkbase for app ID {app_id}")
        
        @retry_with_backoff(
            max_retries=3,
            base_delay=1.0,
            max_delay=30.0,
            exceptions=(requests.RequestException, requests.Timeout)
        )
        def _fetch_versions():
            url = f"{self.BASE_URL}/app/{app_id}/release"
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        
        try:
            releases = _fetch_versions()
            
            if releases and isinstance(releases, list):
                versions = []
                for release in releases:
                    version = release.get('name')
                    if version:
                        versions.append(version)
                
                if versions:
                    logger.debug(f"Found {len(versions)} versions for app ID {app_id}: {', '.join(versions[:5])}")
                    
                    # Store in persistent cache
                    if self.cache:
                        self.cache.set(cache_key, versions, CacheTTL.SPLUNKBASE_VERSIONS)
                    
                    # Cache full release objects for reuse by compatibility checks
                    self._releases_cache[app_id] = releases
                    
                    return versions
                else:
                    logger.warning(f"No version names found in releases for app ID {app_id}")
            else:
                logger.warning(f"No releases found for app ID {app_id}")
        except RetryError as e:
            logger.error(f"Error fetching release info for app ID {app_id} after {e.attempts} attempts: {e.last_exception}")
        except Exception as e:
            logger.error(f"Error fetching release info for app ID {app_id}: {e}")
        
        return []
    
    def download_app(self, app_id: str, download_path: Path, manual_download_dir: Optional[Path] = None, version: Optional[str] = None) -> Optional[Path]:
        """Download app from Splunkbase or use cached/manually downloaded file
        
        Args:
            app_id: Splunkbase app ID
            download_path: Directory to save downloaded file
            manual_download_dir: Directory to check for manually downloaded files
            version: Specific version to download (optional, defaults to latest)
        
        Returns:
            Path to downloaded file or None if failed
        """
        # Check for previously downloaded file in cache (work/downloads/)
        cached_file = self._find_cached_download(app_id, download_path, version)
        if cached_file:
            logger.info(f"Using previously downloaded file: {cached_file.name}")
            return cached_file
        
        # Check for manually downloaded file
        manual_file = self._find_manual_download(app_id, manual_download_dir)
        if manual_file:
            dest = download_path / manual_file.name
            shutil.copy2(manual_file, dest)
            logger.info(f"Using manually downloaded file: {manual_file.name}")
            return dest
        
        # Download from Splunkbase
        return self._download_from_splunkbase(app_id, download_path, manual_download_dir, version)
    
    def _find_cached_download(self, app_id: str, download_path: Path, version: Optional[str] = None) -> Optional[Path]:
        """Find previously downloaded file in cache directory
        
        Args:
            app_id: Splunkbase app ID
            download_path: Directory where downloads are cached
            version: Specific version to look for (optional)
        
        Returns:
            Path to cached file if found and valid, None otherwise
        """
        if not download_path.exists():
            return None
        
        # Look for files matching this app ID
        for file in download_path.glob('*'):
            if not file.is_file():
                continue
            
            # Check if filename contains app ID
            if str(app_id) not in file.name.lower():
                continue
            
            # If version specified, check if it matches with boundary-aware check
            if version:
                # Normalize version for comparison
                version_patterns = [
                    version.replace('.', '_'),
                    version.replace('.', ''),
                    version.replace('.', '-'),
                    version
                ]
                # Require version to appear as a delimited token, not a substring
                import re
                found = False
                for v in version_patterns:
                    # Match version bounded by non-alphanumeric chars or string edges
                    if re.search(r'(?<![\w.])' + re.escape(v) + r'(?![\w.])', file.name.lower()):
                        found = True
                        break
                if not found:
                    continue
            
            # File exists and matches - check if it's a valid archive with non-zero size
            valid_extensions = file.name.lower().endswith(('.tgz', '.tar.gz', '.spl', '.gz'))
            if valid_extensions and file.stat().st_size > 0:
                logger.debug(f"Found cached download: {file.name}")
                return file
        
        return None
    
    def _find_manual_download(self, app_id: str, manual_download_dir: Optional[Path]) -> Optional[Path]:
        """Find manually downloaded file for the app.
        
        Only matches files whose name contains the app ID to prevent
        returning the wrong file when multiple archives exist.
        """
        if not manual_download_dir or not manual_download_dir.exists():
            return None
        
        for file in manual_download_dir.glob('*'):
            if file.is_file() and str(app_id) in file.name and file.name.lower().endswith(('.tgz', '.tar.gz', '.spl', '.gz', '.zip')):
                logger.info(f"Found manually downloaded file: {file.name}")
                return file
        return None
    
    def _download_from_splunkbase(self, app_id: str, download_path: Path, manual_download_dir: Optional[Path], version: Optional[str] = None) -> Optional[Path]:
        """Download app from Splunkbase API
        
        Args:
            app_id: Splunkbase app ID
            download_path: Directory to save file
            manual_download_dir: Directory for manual downloads
            version: Specific version to download (optional, defaults to latest)
        
        Returns:
            Path to downloaded file or None if failed
        """
        try:
            # Get release information
            releases_url = f"{self.BASE_URL}/app/{app_id}/release"
            releases_response = self.session.get(releases_url, timeout=30)
            releases_response.raise_for_status()
            releases = releases_response.json()
            
            if not releases or not isinstance(releases, list) or len(releases) == 0:
                logger.error(f"No releases found for app {app_id}")
                return None
            
            # Find the requested version or use latest
            if version:
                target_release = None
                for release in releases:
                    if release.get('name') == version:
                        target_release = release
                        break
                if not target_release:
                    logger.error(f"Version {version} not found for app {app_id} on Splunkbase")
                    logger.error(f"Available versions: {[r.get('name') for r in releases[:10]]}")
                    if manual_download_dir:
                        logger.info(f"Please download v{version} manually and place in: {manual_download_dir}")
                    return None
            else:
                target_release = releases[0]
            
            # Debug: Log all available fields in release data
            logger.debug(f"Release data fields for app {app_id}: {list(target_release.keys())}")
            logger.debug(f"Full release data: {target_release}")
            
            release_version = target_release.get('name')
            
            if not release_version:
                logger.error(f"No version found for app {app_id}")
                return None
            
            if not self.logged_in:
                logger.error("Not logged in to Splunkbase. Check credentials in config.yaml")
                if manual_download_dir:
                    logger.info(f"Please download manually and place in: {manual_download_dir}")
                return None
            
            # Initialize checksum variable
            expected_sha256 = None
            user_entered_checksum = False
            
            # Check for config-provided checksum first
            checksum_key = f"{app_id}:{release_version}"
            if checksum_key in self.sha256_checksums:
                expected_sha256 = self.sha256_checksums[checksum_key]
                logger.info(f"Using SHA256 checksum from config for {app_id} v{release_version}")
                logger.debug(f"Config checksum: {expected_sha256[:16]}...")
            # Check if we've already verified this hash in this session
            elif checksum_key in self._verified_hashes:
                expected_sha256 = self._verified_hashes[checksum_key]
                logger.info(f"Reusing previously verified SHA256 checksum for {app_id} v{release_version}")
            
            # Download using v2 API
            download_url = f"https://api.splunkbase.splunk.com/api/v2/apps/{app_id}/releases/{release_version}/download/?origin=sb"
            
            logger.info(f"Downloading app {app_id} v{release_version} from Splunkbase...")
            response = self.session.get(download_url, stream=True, timeout=300, allow_redirects=True)
            response.raise_for_status()
            
            # Log all response headers to check for integrity hashes
            logger.debug(f"Download response headers: {dict(response.headers)}")
            
            # Check for ETag or Content-MD5 headers
            etag = response.headers.get('ETag', '').strip('"')
            content_md5 = response.headers.get('Content-MD5')
            if etag:
                logger.debug(f"ETag from CDN: {etag}")
            if content_md5:
                logger.debug(f"Content-MD5 from CDN: {content_md5}")
            
            # If no checksum in config, prompt user for it (skip in non-interactive mode)
            if not expected_sha256 and not self.no_interactive and sys.stdin.isatty():
                print(f"\n{'='*80}")
                print(f"SHA256 CHECKSUM VERIFICATION")
                print(f"{'='*80}")
                print(f"App: {app_id} v{release_version}")
                print(f"\nTo verify download integrity, please visit:")
                print(f"  https://splunkbase.splunk.com/app/{app_id}/")
                print(f"\nDownload the app manually to see the SHA256 hash in the popup,")
                print(f"then paste it here.\n")
                
                while True:
                    user_input = input("SHA256 hash (or 'cancel' to abort download): ").strip()
                    
                    if not user_input or user_input.lower() == 'cancel':
                        print("Download cancelled by user.")
                        print(f"{'='*80}\n")
                        return None
                    
                    # Parse Splunkbase format: sha256 -c <hash> 'filename'
                    # Also support plain hash input
                    if user_input.startswith('sha256 -c '):
                        parts = user_input.split()
                        parsed_hash = parts[2].lower() if len(parts) >= 3 else None
                    else:
                        parsed_hash = user_input.replace(" ", "").replace("-", "").lower()
                    
                    # Validate it's a proper SHA256 hash
                    if parsed_hash and len(parsed_hash) == 64 and all(c in '0123456789abcdef' for c in parsed_hash):
                        expected_sha256 = parsed_hash
                        user_entered_checksum = True
                        logger.info(f"Using user-provided SHA256 checksum for verification")
                        break
                    else:
                        print(f"⚠ Invalid SHA256 format. Expected 64 hex characters, got: {parsed_hash if parsed_hash else 'empty'}")
                        print(f"  Please try again.\n")
                
                print(f"{'='*80}\n")
            elif not expected_sha256:
                logger.info(f"No SHA256 checksum for {app_id} v{release_version} (non-interactive — skipping prompt)")
            
            # Determine filename from headers or use default
            filename = self._extract_filename(response.headers, app_id)
            file_path = download_path / filename
            
            # Write file
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Downloaded app to {file_path}")
            
            # Verify SHA256 checksum if available
            if expected_sha256:
                if self._verify_checksum(file_path, expected_sha256):
                    print(f"✓ SHA256 checksum verified for {file_path.name}")
                    logger.info(f"[OK] SHA256 checksum verified for {file_path.name}")
                    
                    # Cache the verified hash for reuse in this session
                    self._verified_hashes[checksum_key] = expected_sha256
                    
                    # Offer to save user-entered checksum to config
                    if user_entered_checksum:
                        print(f"\nWould you like to save this checksum to config.yaml for future use?")
                        save_choice = input("Save to config? (y/N): ").strip().lower()
                        if save_choice in ['y', 'yes']:
                            print(f"Add this to your config.yaml under 'sha256_checksums':")
                            print(f'  "{checksum_key}": "{expected_sha256}"')
                            print()
                else:
                    actual = self._calculate_sha256(file_path)
                    # Allow retry if interactive
                    verified = False
                    if not self.no_interactive and sys.stdin.isatty():
                        while True:
                            print(f"\n{'='*80}")
                            print(f"✗ SHA256 CHECKSUM MISMATCH")
                            print(f"{'='*80}")
                            print(f"Expected: {expected_sha256}")
                            print(f"Actual:   {actual}")
                            print(f"\n⚠ Please verify that the version you see here (v{release_version})")
                            print(f"  is matching the version you see on Splunkbase.")
                            print(f"\nOptions:")
                            print(f"  - Paste a corrected SHA256 hash to try again")
                            print(f"  - Press Enter to abort this download")
                            retry_input = input(f"\nSHA256 hash (or Enter to abort): ").strip()
                            
                            if not retry_input:
                                # User chose to abort
                                break
                            
                            # Parse the new hash
                            if retry_input.startswith('sha256 -c '):
                                parts = retry_input.split()
                                new_hash = parts[2].lower() if len(parts) >= 3 else None
                            else:
                                new_hash = retry_input.replace(" ", "").replace("-", "").lower()
                            
                            if not new_hash or len(new_hash) != 64 or not all(c in '0123456789abcdef' for c in new_hash):
                                print(f"⚠ Invalid SHA256 format. Expected 64 hex characters.")
                                continue
                            
                            expected_sha256 = new_hash
                            if self._verify_checksum(file_path, expected_sha256):
                                print(f"✓ SHA256 checksum verified for {file_path.name}")
                                logger.info(f"[OK] SHA256 checksum verified on retry for {file_path.name}")
                                self._verified_hashes[checksum_key] = expected_sha256
                                print(f"\nWould you like to save this checksum to config.yaml for future use?")
                                save_choice = input("Save to config? (y/N): ").strip().lower()
                                if save_choice in ['y', 'yes']:
                                    print(f"Add this to your config.yaml under 'sha256_checksums':")
                                    print(f'  "{checksum_key}": "{expected_sha256}"')
                                    print()
                                verified = True
                                break
                            else:
                                # Still doesn't match — loop again
                                actual = self._calculate_sha256(file_path)
                                continue
                    
                    if not verified:
                        print(f"\n{'='*80}")
                        print(f"✗ SHA256 CHECKSUM VERIFICATION FAILED")
                        print(f"{'='*80}")
                        print(f"Expected: {expected_sha256}")
                        print(f"Actual:   {actual}")
                        print(f"\nFile may be corrupted or tampered with. Deleting download.")
                        print(f"{'='*80}\n")
                        logger.error(f"[FAILED] SHA256 checksum verification FAILED for {file_path.name}")
                        logger.error(f"Expected: {expected_sha256}")
                        logger.error(f"Actual: {actual}")
                        logger.error(f"File may be corrupted or tampered with. Deleting.")
                        file_path.unlink()
                        return None
            else:
                logger.warning(f"No SHA256 checksum available for {app_id} v{release_version}")
                logger.info(f"Consider adding checksums to config.yaml or entering them when prompted")
            
            return file_path
            
        except requests.RequestException as e:
            logger.error(f"Error downloading app {app_id}: {e}")
            return None
    
    @staticmethod
    def _calculate_sha256(file_path: Path) -> str:
        """Calculate SHA256 hash of a file
        
        Args:
            file_path: Path to file
        
        Returns:
            SHA256 hash as hex string
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, 'rb') as f:
            # Read file in chunks to handle large files efficiently
            for byte_block in iter(lambda: f.read(8192), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    @staticmethod
    def _verify_checksum(file_path: Path, expected_sha256: str) -> bool:
        """Verify SHA256 checksum of downloaded file
        
        Args:
            file_path: Path to file to verify
            expected_sha256: Expected SHA256 hash (hex string)
        
        Returns:
            True if checksum matches, False otherwise
        """
        try:
            actual_sha256 = SplunkbaseClient._calculate_sha256(file_path)
            logger.debug(f"SHA256 comparison:")
            logger.debug(f"  Expected: {expected_sha256}")
            logger.debug(f"  Actual:   {actual_sha256}")
            
            return actual_sha256.lower() == expected_sha256.lower()
        except Exception as e:
            logger.error(f"Error calculating SHA256: {e}")
            return False
    
    @staticmethod
    def _extract_filename(headers: Dict, app_id: str) -> str:
        """Extract filename from response headers"""
        filename = f"{app_id}_latest.tgz"
        if 'content-disposition' in headers:
            cd = headers['content-disposition']
            filename_match = re.search(r'filename="?([^"]+)"?', cd)
            if filename_match:
                filename = filename_match.group(1)
        return filename
    
    def get_release_details(self, app_id: str, version: Optional[str] = None) -> Optional[Dict]:
        """Get detailed release information including compatibility
        
        Args:
            app_id: Splunkbase app ID
            version: Specific version to get details for (defaults to latest)
        
        Returns:
            Release details dict including splunk_compatibility or None
        """
        try:
            url = f"{self.BASE_URL}/app/{app_id}/release"
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            releases = response.json()
            
            if not releases or not isinstance(releases, list):
                return None
            
            # Find requested version or use latest
            if version:
                for release in releases:
                    if release.get('name') == version:
                        return release
            
            # Return latest if no version specified or version not found
            return releases[0] if releases else None
            
        except requests.RequestException as e:
            logger.error(f"Error fetching release details for app {app_id}: {e}")
            return None
    
    def check_splunk_compatibility(self, app_id: str, splunk_version: str, app_version: Optional[str] = None) -> bool:
        """Check if an app version is compatible with a Splunk version
        
        Args:
            app_id: Splunkbase app ID
            splunk_version: Splunk Enterprise version (e.g., "9.0.0")
            app_version: Specific app version to check (defaults to latest)
        
        Returns:
            True if compatible, False otherwise
        """
        release_details = self.get_release_details(app_id, app_version)
        if not release_details:
            logger.warning(f"Could not retrieve release details for app {app_id}")
            return False
        
        compat_info = self.get_compatibility_info(release_details)
        if not compat_info:
            logger.warning(f"No compatibility information available for app {app_id}")
            return False
        
        return self._is_version_compatible(splunk_version, compat_info)
    
    def get_compatibility_info(self, release_details: Dict) -> Optional[Dict]:
        """Extract compatibility information from release details
        
        Args:
            release_details: Release data from Splunkbase API
        
        Returns:
            Dict with min_version, max_version, compatible_versions list, or None
        """
        # Debug: Log all available fields to understand the structure
        logger.debug(f"Release details keys: {list(release_details.keys())}")
        
        # Check for product_versions field (the actual field Splunkbase uses)
        product_versions = release_details.get('product_versions', [])
        if product_versions:
            logger.debug(f"Found product_versions: {product_versions}")
            # product_versions is a list like ['10.1', '10.0', '9.4', '9.3', '9.2']
            # Extract min and max from the list
            if product_versions:
                # Convert to floats for comparison, filter out non-numeric
                numeric_versions = []
                for v in product_versions:
                    try:
                        numeric_versions.append(float(v))
                    except ValueError:
                        logger.debug(f"Skipping non-numeric version: {v}")
                
                if numeric_versions:
                    min_ver = str(min(numeric_versions))
                    max_ver = str(max(numeric_versions))
                    return {
                        'min_version': min_ver,
                        'max_version': max_ver,
                        'compatible_versions': product_versions
                    }
        
        # Try legacy field names for compatibility info
        compat = (
            release_details.get('splunk_compatibility') or
            release_details.get('compatibility') or
            release_details.get('product_compatibility') or
            {}
        )
        
        if not compat:
            # Try to find it in nested structures
            if 'product' in release_details:
                compat = release_details['product'].get('compatibility', {})
        
        if not compat:
            logger.debug(f"No compatibility info found. Available fields: {release_details.keys()}")
            return None
        
        logger.debug(f"Compatibility data: {compat}")
        
        # Extract min and max versions - try various field name variations
        min_version = (
            compat.get('min_version') or 
            compat.get('min') or
            compat.get('minimum_version') or
            compat.get('minimum')
        )
        max_version = (
            compat.get('max_version') or 
            compat.get('max') or
            compat.get('maximum_version') or
            compat.get('maximum')
        )
        
        # Some APIs return it as a string range like "8.0 - 9.2"
        if isinstance(compat, str) and '-' in compat:
            parts = compat.split('-')
            if len(parts) == 2:
                min_version = parts[0].strip()
                max_version = parts[1].strip()
        
        return {
            'min_version': min_version,
            'max_version': max_version
        }
    
    def _is_version_compatible(self, splunk_version: str, compat_info: Dict) -> bool:
        """Check if Splunk version falls within compatibility range
        
        Args:
            splunk_version: Splunk version to check (e.g., "9.4.7")
            compat_info: Dict with min_version, max_version, and optionally compatible_versions list
        
        Returns:
            True if compatible
        """
        from .utils import version_compare
        
        # Check if there's a list of specific compatible versions (like product_versions)
        compatible_versions = compat_info.get('compatible_versions', [])
        if compatible_versions:
            # Extract major.minor from the provided Splunk version (e.g., "9.4.7" -> "9.4")
            splunk_major_minor = '.'.join(splunk_version.split('.')[:2])
            
            # Check if the major.minor version is in the compatible list
            if splunk_major_minor in compatible_versions:
                logger.debug(f"Splunk {splunk_version} (major.minor: {splunk_major_minor}) is in compatible versions: {compatible_versions}")
                return True
            else:
                logger.debug(f"Splunk {splunk_version} (major.minor: {splunk_major_minor}) NOT in compatible versions: {compatible_versions}")
                return False
        
        # Fall back to min/max range checking
        min_version = compat_info.get('min_version')
        max_version = compat_info.get('max_version')
        
        # If no constraints, assume compatible
        if not min_version and not max_version:
            return True
        
        # Check minimum version
        if min_version:
            if version_compare(splunk_version, min_version) < 0:
                logger.debug(f"Splunk {splunk_version} < minimum {min_version}")
                return False
        
        # Check maximum version
        if max_version:
            if version_compare(splunk_version, max_version) > 0:
                logger.debug(f"Splunk {splunk_version} > maximum {max_version}")
                return False
        
        return True
    
    def get_compatible_versions_for_splunk(self, app_id: str, splunk_version: str, max_versions: int = 10) -> List[str]:
        """Get all app versions compatible with a Splunk version
        
        Args:
            app_id: Splunkbase app ID
            splunk_version: Splunk Enterprise version
            max_versions: Maximum number of versions to return
        
        Returns:
            List of compatible app version strings
        """
        try:
            # Reuse cached releases from get_available_versions() if present
            releases = self._releases_cache.get(app_id)
            if not releases:
                url = f"{self.BASE_URL}/app/{app_id}/release"
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                releases = response.json()
                if releases and isinstance(releases, list):
                    self._releases_cache[app_id] = releases
            
            if not releases or not isinstance(releases, list):
                return []
            
            compatible_versions = []
            for release in releases:
                version = release.get('name')
                if not version:
                    continue
                
                compat_info = self.get_compatibility_info(release)
                if compat_info and self._is_version_compatible(splunk_version, compat_info):
                    compatible_versions.append(version)
                
                if len(compatible_versions) >= max_versions:
                    break
            
            return compatible_versions
            
        except requests.RequestException as e:
            logger.error(f"Error fetching compatible versions for app {app_id}: {e}")
            return []
