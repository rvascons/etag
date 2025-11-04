"""
Redis Cache Service for ETag storage and retrieval.

This module provides:
1. Redis connection management with error handling
2. ETag storage with TTL for cache management
3. Async operations for FastAPI compatibility
4. Graceful fallback when Redis is unavailable
"""

import redis.asyncio as redis
import logging
import os
from typing import Optional
import json
from datetime import timedelta

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class CacheService:
    """
    Redis-based cache service for ETag storage.
    
    Provides fast ETag lookups and storage with automatic TTL management.
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379", ttl_hours: int = 24):
        """
        Initialize cache service.
        
        Args:
            redis_url: Redis connection URL
            ttl_hours: Time-to-live for cache entries in hours
        """
        self.redis_url = redis_url
        self.ttl = timedelta(hours=ttl_hours)
        self.redis_client: Optional[redis.Redis] = None
        self.is_connected = False
    
    async def connect(self) -> bool:
        """
        Establish Redis connection.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            
            # Test connection
            await self.redis_client.ping()
            self.is_connected = True
            logger.info("✅ Redis connection established")
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ Redis connection failed: {e}")
            logger.warning("📝 ETag service will work without cache (database only)")
            self.is_connected = False
            return False
    
    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()
            self.is_connected = False
            logger.info("📕 Redis connection closed")
    
    def _get_key(self, entity_type: str, entity_id: int) -> str:
        """
        Generate Redis key for ETag storage.
        
        Args:
            entity_type: Type of entity (e.g., 'user')
            entity_id: Entity identifier
            
        Returns:
            Redis key in format: etag:user:123
        """
        return f"etag:{entity_type}:{entity_id}"
    
    async def get_etag(self, entity_type: str, entity_id: int) -> Optional[str]:
        """
        Retrieve ETag from cache.
        
        Args:
            entity_type: Type of entity
            entity_id: Entity identifier
            
        Returns:
            ETag string if found, None otherwise
        """
        if not self.is_connected or not self.redis_client:
            return None
        
        try:
            key = self._get_key(entity_type, entity_id)
            etag = await self.redis_client.get(key)
            
            if etag:
                logger.debug(f"📋 Cache HIT: {key} → {etag}")
                return etag
            else:
                logger.debug(f"📋 Cache MISS: {key}")
                return None
                
        except Exception as e:
            logger.warning(f"⚠️ Cache get error for {entity_type}:{entity_id}: {e}")
            return None
    
    async def set_etag(self, entity_type: str, entity_id: int, etag: str) -> bool:
        """
        Store ETag in cache with TTL.
        
        Args:
            entity_type: Type of entity
            entity_id: Entity identifier
            etag: ETag string to store
            
        Returns:
            True if stored successfully, False otherwise
        """
        if not self.is_connected or not self.redis_client:
            return False
        
        try:
            key = self._get_key(entity_type, entity_id)
            
            # Store with TTL
            success = await self.redis_client.setex(
                key, 
                self.ttl, 
                etag
            )
            
            if success:
                logger.debug(f"💾 Cache SET: {key} → {etag}")
                return True
            else:
                logger.warning(f"⚠️ Cache set failed for {key}")
                return False
                
        except Exception as e:
            logger.warning(f"⚠️ Cache set error for {entity_type}:{entity_id}: {e}")
            return False
    
    async def delete_etag(self, entity_type: str, entity_id: int) -> bool:
        """
        Remove ETag from cache.
        
        Args:
            entity_type: Type of entity
            entity_id: Entity identifier
            
        Returns:
            True if deleted successfully, False otherwise
        """
        if not self.is_connected or not self.redis_client:
            return False
        
        try:
            key = self._get_key(entity_type, entity_id)
            deleted = await self.redis_client.delete(key)
            
            if deleted:
                logger.debug(f"🗑️ Cache DELETE: {key}")
                return True
            else:
                logger.debug(f"🗑️ Cache DELETE (not found): {key}")
                return False
                
        except Exception as e:
            logger.warning(f"⚠️ Cache delete error for {entity_type}:{entity_id}: {e}")
            return False
    
    async def clear_all_etags(self) -> bool:
        """
        Clear all ETag entries from cache.
        
        Useful for testing and cache cleanup.
        
        Returns:
            True if cleared successfully, False otherwise
        """
        if not self.is_connected or not self.redis_client:
            return False
        
        try:
            # Find all etag keys
            keys = await self.redis_client.keys("etag:*")
            
            if keys:
                deleted = await self.redis_client.delete(*keys)
                logger.info(f"🧹 Cleared {deleted} ETag entries from cache")
                return True
            else:
                logger.info("🧹 No ETag entries found to clear")
                return True
                
        except Exception as e:
            logger.warning(f"⚠️ Cache clear error: {e}")
            return False
    
    async def get_cache_stats(self) -> dict:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        if not self.is_connected or not self.redis_client:
            return {
                "connected": False,
                "etag_keys": 0,
                "memory_usage": "unknown"
            }
        
        try:
            # Get basic stats
            info = await self.redis_client.info()
            keys = await self.redis_client.keys("etag:*")
            
            return {
                "connected": True,
                "etag_keys": len(keys),
                "memory_usage": info.get("used_memory_human", "unknown"),
                "total_connections": info.get("total_connections_received", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0)
            }
            
        except Exception as e:
            logger.warning(f"⚠️ Cache stats error: {e}")
            return {
                "connected": False,
                "error": str(e)
            }
    
    async def health_check(self) -> bool:
        """
        Check if Redis is healthy.
        
        Returns:
            True if Redis is responding, False otherwise
        """
        if not self.is_connected or not self.redis_client:
            return False
        
        try:
            await self.redis_client.ping()
            return True
        except Exception:
            self.is_connected = False
            return False


# Global cache service instance
cache_service: Optional[CacheService] = None


async def get_cache_service() -> CacheService:
    """
    Get or create the global cache service instance.
    
    Returns:
        CacheService instance
    """
    global cache_service
    
    if cache_service is None:
        cache_service = CacheService()
        await cache_service.connect()
    
    return cache_service


async def initialize_cache() -> CacheService:
    """
    Initialize cache service and establish connection.
    
    Uses environment variables for configuration:
    - REDIS_HOST: Redis hostname (default: localhost)
    - REDIS_PORT: Redis port (default: 6379)
    
    Returns:
        CacheService instance
    """
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = os.getenv("REDIS_PORT", "6379")
    redis_url = f"redis://{redis_host}:{redis_port}"
    
    service = CacheService(redis_url=redis_url)
    await service.connect()
    return service


# Cleanup function for application shutdown
async def cleanup_cache() -> None:
    """Clean up cache service on application shutdown."""
    global cache_service
    
    if cache_service:
        await cache_service.disconnect()
        cache_service = None


# Example usage and testing
async def example_usage():
    """Example demonstrating cache service usage."""
    
    # Initialize cache
    cache = await initialize_cache()
    
    # Store ETag
    await cache.set_etag("user", 123, '"user-123-1698765432"')
    
    # Retrieve ETag
    etag = await cache.get_etag("user", 123)
    print(f"Retrieved ETag: {etag}")
    
    # Delete ETag
    await cache.delete_etag("user", 123)
    
    # Get stats
    stats = await cache.get_cache_stats()
    print(f"Cache stats: {stats}")
    
    # Cleanup
    await cache.disconnect()


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())