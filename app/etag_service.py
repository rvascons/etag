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
from typing import Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class ETagResult:
    """Result of ETag validation"""
    is_valid: bool
    current_etag: str
    cache_hit: bool = False

class ETagService:
    """
    Service for handling ETag generation and validation.
    
    Supports multiple ETag generation strategies:
    - Timestamp-based (fastest, good for timestamp tracking)
    - Hash-based (content-dependent, detects any change)
    - Version-based (database version numbers)
    """
    
    def __init__(self, cache_service=None):
        self.cache_service = cache_service
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
            return self._generate_hash_etag(content)
        elif self.strategy == "version":
            return self._generate_version_etag(entity_type, entity_id, version)
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
    
    def _generate_hash_etag(self, content: Dict[Any, Any]) -> str:
        """Generate ETag from content hash (most accurate)."""
        if content is None:
            content = {}
        
        # Serialize content consistently
        content_str = json.dumps(content, sort_keys=True, separators=(',', ':'))
        
        # Generate MD5 hash
        hash_obj = hashlib.md5(content_str.encode('utf-8'))
        etag_value = hash_obj.hexdigest()
        
        return f'"{etag_value}"'
    
    def _generate_version_etag(self, entity_type: str, entity_id: int, 
                              version: Optional[int] = None) -> str:
        """Generate ETag from version number."""
        if version is None:
            version = 1
        
        etag_value = f"{entity_type}-{entity_id}-v{version}"
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
            ETagResult with validation status and current ETag
        """
        if not client_etag:
            # No client ETag means we need to return full response
            current_etag = await self._get_current_etag(entity_type, entity_id)
            return ETagResult(is_valid=False, current_etag=current_etag)
        
        # Get current ETag from cache or generate new one
        current_etag = await self._get_current_etag(entity_type, entity_id)
        
        # Compare ETags
        is_valid = client_etag == current_etag
        
        return ETagResult(
            is_valid=is_valid,
            current_etag=current_etag,
            cache_hit=self.cache_service is not None
        )
    
    async def _get_current_etag(self, entity_type: str, entity_id: int) -> str:
        """Get current ETag for entity from cache or generate new one."""
        if self.cache_service:
            # Try to get from cache first
            cached_etag = await self.cache_service.get_etag(entity_type, entity_id)
            if cached_etag:
                return cached_etag
        
        # Generate new ETag if not in cache
        # In real implementation, this would get timestamp/version from database
        current_timestamp = time.time()
        etag = self.generate_etag(entity_type, entity_id, timestamp=current_timestamp)
        
        # Store in cache for next time
        if self.cache_service:
            await self.cache_service.set_etag(entity_type, entity_id, etag)
        
        return etag
    
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
    
    def set_strategy(self, strategy: str) -> None:
        """
        Set ETag generation strategy.
        
        Args:
            strategy: 'timestamp', 'hash', or 'version'
        """
        valid_strategies = ['timestamp', 'hash', 'version']
        if strategy not in valid_strategies:
            raise ValueError(f"Strategy must be one of: {valid_strategies}")
        
        self.strategy = strategy
    
    def get_weak_etag(self, strong_etag: str) -> str:
        """Convert strong ETag to weak ETag."""
        if strong_etag.startswith('W/"'):
            return strong_etag  # Already weak
        
        # Remove quotes and add W/ prefix
        etag_value = strong_etag.strip('"')
        return f'W/"{etag_value}"'


# TODO: Implementation examples and usage patterns

class ETagValidator:
    """
    Helper class for ETag validation in HTTP requests.
    
    Handles parsing of If-None-Match headers and ETag comparison.
    """
    
    @staticmethod
    def parse_if_none_match(header_value: Optional[str]) -> list[str]:
        """
        Parse If-None-Match header value.
        
        Args:
            header_value: Value of If-None-Match header
            
        Returns:
            List of ETag values
        """
        if not header_value:
            return []
        
        # Handle wildcard
        if header_value.strip() == "*":
            return ["*"]
        
        # Parse comma-separated ETags
        etags = []
        for etag in header_value.split(','):
            etag = etag.strip()
            if etag:
                etags.append(etag)
        
        return etags
    
    @staticmethod
    def etags_match(etag1: str, etag2: str) -> bool:
        """
        Compare two ETags for equality.
        
        Handles both strong and weak ETag comparisons.
        """
        # Normalize ETags (remove W/ prefix for comparison)
        normalized_etag1 = etag1.replace('W/', '').strip('"')
        normalized_etag2 = etag2.replace('W/', '').strip('"')
        
        return normalized_etag1 == normalized_etag2


# Example usage and testing functions
async def example_usage():
    """Example demonstrating ETag service usage."""
    
    # Initialize service (in real app, inject cache_service)
    etag_service = ETagService()
    
    # Generate ETag for a user
    user_etag = etag_service.generate_etag("user", 123, timestamp=time.time())
    print(f"Generated ETag: {user_etag}")
    
    # Validate ETag
    result = await etag_service.validate_etag("user", 123, user_etag)
    print(f"ETag valid: {result.is_valid}")
    
    # Update ETag after entity change
    new_etag = await etag_service.update_etag("user", 123, timestamp=time.time())
    print(f"New ETag: {new_etag}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_usage())