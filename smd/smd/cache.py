"""Simple caching layer for Steam API responses"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

from smd.storage.settings import get_setting
from smd.structs import Settings
from smd.utils import root_folder

logger = logging.getLogger(__name__)

CACHE_FILE = root_folder(outside_internal=True) / "api_cache.json"
DEFAULT_TTL = 3600  # 1 hour in seconds


class APICache:
    """Simple file-based cache for API responses"""
    
    def __init__(self):
        self.cache: dict[str, dict[str, Any]] = {}
        self.load()
    
    def load(self):
        """Load cache from disk"""
        try:
            if CACHE_FILE.exists():
                with CACHE_FILE.open("r", encoding="utf-8") as f:
                    self.cache = json.load(f)
                logger.debug(f"Loaded cache with {len(self.cache)} entries")
        except Exception as e:
            logger.error(f"Failed to load cache: {e}", exc_info=True)
            self.cache = {}
    
    def save(self):
        """Save cache to disk"""
        try:
            with CACHE_FILE.open("w", encoding="utf-8") as f:
                json.dump(self.cache, f)
            logger.debug(f"Saved cache with {len(self.cache)} entries")
        except Exception as e:
            logger.error(f"Failed to save cache: {e}", exc_info=True)
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired"""
        if key not in self.cache:
            return None
        
        entry = self.cache[key]
        timestamp = entry.get("timestamp", 0)
        ttl = entry.get("ttl", DEFAULT_TTL)
        
        # Check if expired
        if time.time() - timestamp > ttl:
            logger.debug(f"Cache expired for key: {key}")
            del self.cache[key]
            return None
        
        logger.debug(f"Cache hit for key: {key}")
        return entry.get("data")
    
    def set(self, key: str, data: Any, ttl: Optional[int] = None):
        """Set cached value with TTL"""
        if ttl is None:
            ttl = DEFAULT_TTL
        
        self.cache[key] = {
            "data": data,
            "timestamp": time.time(),
            "ttl": ttl
        }
        logger.debug(f"Cached data for key: {key} (TTL: {ttl}s)")
        self.save()
    
    def invalidate(self, key: Optional[str] = None):
        """Invalidate cache entry or entire cache"""
        if key is None:
            # Clear entire cache
            self.cache = {}
            logger.info("Invalidated entire cache")
        elif key in self.cache:
            del self.cache[key]
            logger.info(f"Invalidated cache for key: {key}")
        self.save()
    
    def cleanup_expired(self):
        """Remove all expired entries"""
        current_time = time.time()
        expired_keys = []
        
        for key, entry in self.cache.items():
            timestamp = entry.get("timestamp", 0)
            ttl = entry.get("ttl", DEFAULT_TTL)
            if current_time - timestamp > ttl:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.cache[key]
        
        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")
            self.save()


# Global cache instance
_cache_instance: Optional[APICache] = None


def get_cache() -> APICache:
    """Get or create global cache instance"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = APICache()
    return _cache_instance
