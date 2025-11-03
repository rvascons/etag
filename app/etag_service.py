"""
ETag Service - Core ETag generation and validation logic.

This module handles:
1. ETag generation using different strategies (timestamp, hash, version)
2. ETag validation for conditional requests
3. Cache integration for fast ETag lookups
"""

import time
import hashlib
import json
import asyncio
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

# Configure logging
logger = logging.getLogger(__name__)

@dataclass
class ETagResult:
    """Result of ETag validation"""
    is_valid: bool
    current_etag: str
    cache_hit: bool = False
    entity: Optional[Any] = None  # The fetched entity (if retrieved from DB)

class ETagService:
    """
    Service for handling ETag generation and validation.
    
    Supports multiple ETag generation strategies:
    - Timestamp-based (fastest, good for timestamp tracking)
    - Hash-based (content-dependent, detects any change)
    - Version-based (database version numbers)
    """
    
    def __init__(self, cache_service=None, db_service=None):
        """
        Initialize ETag service.
        
        Args:
            cache_service: CacheService instance for ETag caching
            db_service: Database service for fetching entity timestamps
        """
        self.cache_service = cache_service
        self.db_service = db_service
        self.strategy = "timestamp"  # Default strategy
    
    def generate_etag(self, entity_type: str, entity_id: int, 
                     content: Optional[Dict[Any, Any]] = None,
                     timestamp: Optional[float] = None,
                     version: Optional[int] = None) -> str:
        """
        Generate ETag using the configured strategy.
        
        Args:
            entity_type: Type of entity (e.g., 'user', 'product')
            entity_id: Unique identifier for the entity
            content: Content to hash (for hash-based strategy)
            timestamp: Last modified timestamp (for timestamp-based)
            version: Version number (for version-based)
            
        Returns:
            Strong ETag string (e.g., '"1697198400"')
        """
        if self.strategy == "timestamp":
            return self._generate_timestamp_etag(entity_type, entity_id, timestamp)
        elif self.strategy == "hash":
            raise NotImplementedError()
        elif self.strategy == "version":
            raise NotImplementedError()
        else:
            raise ValueError(f"Unknown ETag strategy: {self.strategy}")
    
    def _generate_timestamp_etag(self, entity_type: str, entity_id: int, 
                                timestamp: Optional[float] = None) -> str:
        """Generate ETag from timestamp (fastest method)."""
        if timestamp is None:
            timestamp = time.time()
        
        # Format: "entitytype-id-timestamp"
        etag_value = f"{entity_type}-{entity_id}-{int(timestamp)}"
        return f'"{etag_value}"'
    
    async def validate_etag(self, entity_type: str, entity_id: int, 
                           client_etag: Optional[str]) -> ETagResult:
        """
        Validate client ETag against current entity state.
        
        Args:
            entity_type: Type of entity
            entity_id: Entity identifier
            client_etag: ETag from client's If-None-Match header
            
        Returns:
            ETagResult with validation status, current ETag, and entity (if fetched)
            
        Raises:
            ValueError: If entity does not exist
        """
        # Get current ETag from cache or generate new one
        # This will raise ValueError if entity doesn't exist
        # Also returns the entity if it was fetched from DB (cache miss)
        current_etag, cache_hit, entity = await self._get_current_etag(entity_type, entity_id)
        logger.debug(f"Received Etag: {client_etag}")
        if not client_etag:
            # No client ETag means we need to return full response
            return ETagResult(
                is_valid=False, 
                current_etag=current_etag, 
                cache_hit=cache_hit,
                entity=entity
            )
        
        # Compare ETags
        is_valid = client_etag == current_etag
        
        return ETagResult(
            is_valid=is_valid,
            current_etag=current_etag,
            cache_hit=cache_hit,
            entity=entity  # Include entity (will be None if cache hit)
        )
    
    async def _get_current_etag(self, entity_type: str, entity_id: int) -> tuple[str, bool, Optional[Any]]:
        """
        Get current ETag for entity from cache or generate new one.
        
        Returns:
            Tuple of (etag, cache_hit_bool, entity_object)
            - If cache hit: entity_object is None (not fetched from DB)
            - If cache miss: entity_object is the fetched entity
            
        Raises:
            ValueError: If entity does not exist in database
        """
        cache_hit = False
        entity = None
        
        if self.cache_service:
            # Try to get from cache first
            cached_etag = await self.cache_service.get_etag(entity_type, entity_id)
            if cached_etag:
                logger.debug(f"🎯 ETag cache HIT: {entity_type}:{entity_id}")
                return cached_etag, True, None  # No entity fetched on cache hit
        
        # Cache miss - generate new ETag from database
        logger.debug(f"📊 ETag cache MISS: {entity_type}:{entity_id} - generating from DB")
        
        if entity_type == "user" and self.db_service:
            # Add artificial delay to simulate database read
            await asyncio.sleep(0.5)
            
            # Get user from database to get updated_at timestamp
            user = self.db_service.get_user(entity_id)
            
            # IMPORTANT: Don't generate ETag for non-existent entities!
            if not user:
                raise ValueError(f"User {entity_id} does not exist - cannot generate ETag")
            
            # Store the entity to return it
            entity = user
            
            # Generate ETag from user's updated_at timestamp
            if user.updated_at:
                etag = self.generate_etag(entity_type, entity_id, timestamp=user.updated_at)
            else:
                # Fallback to created_at or current time
                raise ValueError(f"User {user.id} malformed") 
        else:
            raise NotImplementedError(f"Not Implemented for entity type: {entity_type}")
        
        # Store in cache for next time
        if self.cache_service:
            await self.cache_service.set_etag(entity_type, entity_id, etag)
        
        return etag, False, entity  # Return entity on cache miss
    
    async def invalidate_etag(self, entity_type: str, entity_id: int) -> None:
        """
        Invalidate ETag cache for an entity.
        
        Called when entity is updated to ensure cache consistency.
        """
        if self.cache_service:
            await self.cache_service.delete_etag(entity_type, entity_id)
    
    async def update_etag(self, entity_type: str, entity_id: int, 
                         content: Optional[Dict[Any, Any]] = None,
                         timestamp: Optional[float] = None,
                         version: Optional[int] = None) -> str:
        """
        Generate and cache new ETag for entity.
        
        Called after entity updates to maintain cache consistency.
        """
        # Generate new ETag
        new_etag = self.generate_etag(
            entity_type, entity_id, 
            content=content, 
            timestamp=timestamp, 
            version=version
        )
        
        # Update cache
        if self.cache_service:
            await self.cache_service.set_etag(entity_type, entity_id, new_etag)
        
        return new_etag