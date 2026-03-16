"""Persistent caching with TTL for API responses and expensive operations"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Generic, Optional, TypeVar, Callable

from .utils import safe_cache_path

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class CacheEntry:
    """A single cache entry with metadata"""
    key: str
    value: Any
    created_at: str  # ISO format timestamp
    expires_at: str  # ISO format timestamp
    hit_count: int = 0
    
    def is_expired(self) -> bool:
        """Check if this entry has expired"""
        return datetime.fromisoformat(self.expires_at) < datetime.now()
    
    def time_until_expiry(self) -> timedelta:
        """Get time remaining until expiry"""
        return datetime.fromisoformat(self.expires_at) - datetime.now()


class PersistentCache:
    """A persistent file-based cache with TTL support
    
    Features:
    - Stores cache entries as JSON files
    - Configurable TTL (time-to-live)
    - Automatic expiration checking
    - Hit count tracking for analytics
    - Namespace support for organizing cache entries
    
    Example:
        cache = PersistentCache(Path("./work/cache"), default_ttl_seconds=3600)
        
        # Store a value
        cache.set("app_versions_742", ["9.1.2", "9.1.1", "9.1.0"])
        
        # Retrieve a value
        versions = cache.get("app_versions_742")
        
        # Use get_or_fetch for automatic caching
        versions = cache.get_or_fetch(
            "app_versions_742",
            lambda: splunkbase_client.get_available_versions("742"),
            ttl_seconds=3600
        )
    """
    
    def __init__(
        self, 
        cache_dir: Path, 
        default_ttl_seconds: int = 3600,
        namespace: str = "default"
    ):
        self.cache_dir = cache_dir / namespace
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.default_ttl_seconds = default_ttl_seconds
        self.namespace = namespace
        self._memory_cache: Dict[str, CacheEntry] = {}  # In-memory cache for performance
    
    def _get_cache_path(self, key: str) -> Path:
        """Get the file path for a cache key"""
        return safe_cache_path(self.cache_dir, key)
    
    def _load_entry(self, key: str) -> Optional[CacheEntry]:
        """Load a cache entry from disk"""
        # Check memory cache first
        if key in self._memory_cache:
            entry = self._memory_cache[key]
            if not entry.is_expired():
                entry.hit_count += 1
                return entry
            else:
                del self._memory_cache[key]
        
        # Try to load from disk
        cache_path = self._get_cache_path(key)
        if not cache_path.exists():
            return None
        
        try:
            with open(cache_path, 'r') as f:
                data = json.load(f)
            entry = CacheEntry(**data)
            
            if entry.is_expired():
                # Clean up expired entry
                cache_path.unlink(missing_ok=True)
                return None
            
            # Store in memory cache
            entry.hit_count += 1
            self._memory_cache[key] = entry
            return entry
            
        except (json.JSONDecodeError, OSError, TypeError) as e:
            logger.warning(f"Failed to load cache entry for {key}: {e}")
            return None
    
    def _save_entry(self, entry: CacheEntry):
        """Save a cache entry to disk"""
        cache_path = self._get_cache_path(entry.key)
        try:
            with open(cache_path, 'w') as f:
                json.dump(asdict(entry), f, indent=2, default=str)
            # Update memory cache
            self._memory_cache[entry.key] = entry
        except OSError as e:
            logger.error(f"Failed to save cache entry for {entry.key}: {e}")
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache
        
        Args:
            key: Cache key
            
        Returns:
            Cached value if found and not expired, None otherwise
        """
        entry = self._load_entry(key)
        if entry:
            logger.debug(f"Cache hit for {key} (hits: {entry.hit_count}, expires in: {entry.time_until_expiry()})")
            return entry.value
        logger.debug(f"Cache miss for {key}")
        return None
    
    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None):
        """Store a value in the cache
        
        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable)
            ttl_seconds: Time-to-live in seconds (uses default if not specified)
        """
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        now = datetime.now()
        expires_at = now + timedelta(seconds=ttl)
        
        entry = CacheEntry(
            key=key,
            value=value,
            created_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
            hit_count=0
        )
        
        self._save_entry(entry)
        logger.debug(f"Cached {key} (expires at: {expires_at.isoformat()})")
    
    def get_or_fetch(
        self, 
        key: str, 
        fetch_func: Callable[[], T], 
        ttl_seconds: Optional[int] = None
    ) -> Optional[T]:
        """Get from cache or fetch and cache if missing
        
        Args:
            key: Cache key
            fetch_func: Function to call to fetch the value if not cached
            ttl_seconds: Time-to-live in seconds
            
        Returns:
            The cached or fetched value, or None if fetch fails
        """
        value = self.get(key)
        if value is not None:
            return value
        
        try:
            value = fetch_func()
            if value is not None:
                self.set(key, value, ttl_seconds)
            return value
        except Exception as e:
            logger.error(f"Failed to fetch value for {key}: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """Delete a cache entry
        
        Args:
            key: Cache key
            
        Returns:
            True if entry was deleted, False if not found
        """
        cache_path = self._get_cache_path(key)
        
        # Remove from memory cache
        self._memory_cache.pop(key, None)
        
        if cache_path.exists():
            try:
                cache_path.unlink()
                logger.debug(f"Deleted cache entry for {key}")
                return True
            except OSError as e:
                logger.error(f"Failed to delete cache entry for {key}: {e}")
        return False
    
    def clear(self):
        """Clear all cache entries"""
        self._memory_cache.clear()
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
            except OSError as e:
                logger.error(f"Failed to delete cache file {cache_file}: {e}")
        logger.info(f"Cleared cache namespace: {self.namespace}")
    
    def cleanup_expired(self) -> int:
        """Remove all expired cache entries
        
        Returns:
            Number of entries removed
        """
        removed = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                entry = CacheEntry(**data)
                if entry.is_expired():
                    cache_file.unlink()
                    self._memory_cache.pop(entry.key, None)
                    removed += 1
            except (json.JSONDecodeError, OSError, TypeError):
                # Remove corrupted entries
                cache_file.unlink(missing_ok=True)
                removed += 1
        
        if removed > 0:
            logger.info(f"Cleaned up {removed} expired cache entries")
        return removed
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics
        
        Returns:
            Dictionary with cache statistics
        """
        total_entries = 0
        expired_entries = 0
        total_hits = 0
        
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                entry = CacheEntry(**data)
                total_entries += 1
                total_hits += entry.hit_count
                if entry.is_expired():
                    expired_entries += 1
            except (json.JSONDecodeError, OSError, TypeError):
                pass
        
        return {
            "namespace": self.namespace,
            "total_entries": total_entries,
            "expired_entries": expired_entries,
            "active_entries": total_entries - expired_entries,
            "total_hits": total_hits,
            "memory_cached": len(self._memory_cache)
        }


# Default cache TTL constants (in seconds)
class CacheTTL:
    """Standard TTL values for different cache types"""
    MINUTES_5 = 300
    MINUTES_15 = 900
    MINUTES_30 = 1800
    HOUR_1 = 3600
    HOURS_6 = 21600
    HOURS_12 = 43200
    DAY_1 = 86400
    DAYS_7 = 604800
    
    # Recommended TTLs for Splunkbase data
    SPLUNKBASE_VERSIONS = HOUR_1  # App version lists change infrequently
    SPLUNKBASE_APP_INFO = HOURS_6  # App metadata rarely changes
    SPLUNKBASE_COMPATIBILITY = DAY_1  # Compatibility info is very stable


def create_splunkbase_cache(work_dir: Path) -> PersistentCache:
    """Create a cache configured for Splunkbase API responses
    
    Args:
        work_dir: Working directory (cache stored in work_dir/cache/splunkbase/)
    
    Returns:
        Configured PersistentCache instance
    """
    return PersistentCache(
        cache_dir=work_dir / "cache",
        default_ttl_seconds=CacheTTL.SPLUNKBASE_VERSIONS,
        namespace="splunkbase"
    )
