"""
Metrics Collection for ETag Performance Tracking.

This module provides:
1. Performance metrics collection
2. Cache hit/miss tracking  
3. Response time measurement
4. Database query counting
5. Bandwidth savings calculation
"""

import time
import threading
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class RequestMetrics:
    """Individual request metrics."""
    timestamp: float
    endpoint: str
    response_time_ms: float
    cache_hit: bool
    status_code: int
    response_size_bytes: int = 0


@dataclass 
class AggregatedMetrics:
    """Aggregated performance metrics."""
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_response_time_ms: float = 0.0
    cached_response_time_ms: float = 0.0  # Sum of cached response times
    uncached_response_time_ms: float = 0.0  # Sum of uncached response times
    total_response_size_bytes: int = 0
    database_queries_saved: int = 0
    response_304_count: int = 0  # Not Modified responses
    response_200_count: int = 0  # Full responses
    
    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.cache_hits / self.total_requests) * 100
    
    @property
    def avg_response_time_ms(self) -> float:
        """Calculate average response time."""
        if self.total_requests == 0:
            return 0.0
        return self.total_response_time_ms / self.total_requests
    
    @property
    def avg_response_time_cached_ms(self) -> float:
        """Calculate average response time for cached requests."""
        if self.cache_hits == 0:
            return 0.0
        return self.cached_response_time_ms / self.cache_hits
    
    @property
    def avg_response_time_uncached_ms(self) -> float:
        """Calculate average response time for uncached requests."""
        if self.cache_misses == 0:
            return 0.0
        return self.uncached_response_time_ms / self.cache_misses
    
    @property
    def bandwidth_saved_bytes(self) -> int:
        """Calculate bandwidth saved by 304 responses."""
        # Estimate average response size and multiply by 304 responses
        if self.response_200_count == 0:
            return 0
        
        avg_response_size = self.total_response_size_bytes / self.response_200_count
        return int(avg_response_size * self.response_304_count)
    
    @property
    def bandwidth_saved_percentage(self) -> float:
        """Calculate bandwidth savings percentage."""
        total_potential_bytes = self.total_response_size_bytes + self.bandwidth_saved_bytes
        if total_potential_bytes == 0:
            return 0.0
        return (self.bandwidth_saved_bytes / total_potential_bytes) * 100
    
    @property
    def avg_response_size_304_bytes(self) -> float:
        """Calculate average response size for 304 responses (should be 0 or near 0)."""
        # 304 responses have no body, so this should always be 0
        return 0.0
    
    @property
    def avg_response_size_200_bytes(self) -> float:
        """Calculate average response size for 200 responses."""
        if self.response_200_count == 0:
            return 0.0
        return self.total_response_size_bytes / self.response_200_count


class MetricsCollector:
    """
    Thread-safe metrics collector for ETag performance tracking.
    
    Collects and aggregates performance metrics to demonstrate
    the effectiveness of ETag caching.
    """
    
    def __init__(self, max_history: int = 1000):
        """
        Initialize metrics collector.
        
        Args:
            max_history: Maximum number of individual requests to keep in history
        """
        self.max_history = max_history
        self.request_history: list[RequestMetrics] = []
        self.aggregated = AggregatedMetrics()
        self.start_time = time.time()
        self._lock = threading.Lock()
    
    def record_request(self, endpoint: str, response_time_ms: float, 
                      cache_hit: bool, status_code: int, 
                      response_size_bytes: int = 0) -> None:
        """
        Record metrics for a single request.
        
        Args:
            endpoint: API endpoint called
            response_time_ms: Response time in milliseconds  
            cache_hit: Whether this was a cache hit
            status_code: HTTP status code (200, 304, etc.)
            response_size_bytes: Size of response body in bytes
        """
        with self._lock:
            # Create request metrics
            request_metric = RequestMetrics(
                timestamp=time.time(),
                endpoint=endpoint,
                response_time_ms=response_time_ms,
                cache_hit=cache_hit,
                status_code=status_code,
                response_size_bytes=response_size_bytes
            )
            
            # Add to history (with rotation)
            self.request_history.append(request_metric)
            if len(self.request_history) > self.max_history:
                self.request_history.pop(0)
            
            # Update aggregated metrics
            self.aggregated.total_requests += 1
            self.aggregated.total_response_time_ms += response_time_ms
            
            if cache_hit:
                self.aggregated.cache_hits += 1
                self.aggregated.cached_response_time_ms += response_time_ms
                if status_code == 304:
                    self.aggregated.database_queries_saved += 1
            else:
                self.aggregated.cache_misses += 1
                self.aggregated.uncached_response_time_ms += response_time_ms
            
            if status_code == 304:
                self.aggregated.response_304_count += 1
            elif status_code == 200:
                self.aggregated.response_200_count += 1
                self.aggregated.total_response_size_bytes += response_size_bytes
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current performance metrics.
        
        Returns:
            Dictionary with comprehensive metrics
        """
        with self._lock:
            uptime_seconds = time.time() - self.start_time
            
            return {
                "summary": {
                    "total_requests": self.aggregated.total_requests,
                    "cache_hits": self.aggregated.cache_hits,
                    "cache_misses": self.aggregated.cache_misses,
                    "avg_response_time_cached": f"{self.aggregated.avg_response_time_cached_ms:.2f} ms",
                    "avg_response_time_uncached": f"{self.aggregated.avg_response_time_uncached_ms:.2f} ms",
                    "avg_response_size_304": f"{self.aggregated.avg_response_size_304_bytes:.2f} bytes",
                    "avg_response_size_200": f"{self.aggregated.avg_response_size_200_bytes:.2f} bytes",
                    "database_queries_saved": self.aggregated.database_queries_saved,
                    "bandwidth_saved": f"{self.aggregated.bandwidth_saved_bytes:,} bytes ({self.aggregated.bandwidth_saved_percentage:.1f}%)"
                },
                "details": {
                    "cache_hit_rate": f"{self.aggregated.cache_hit_rate:.1f}%",
                    "status_200_count": self.aggregated.response_200_count,
                    "status_304_count": self.aggregated.response_304_count,
                    "total_response_size_bytes": self.aggregated.total_response_size_bytes,
                    "uptime": str(timedelta(seconds=int(uptime_seconds))),
                    "requests_per_second": f"{self.aggregated.total_requests / max(uptime_seconds, 1):.2f}"
                }
            }
    
    def get_recent_requests(self, limit: int = 10) -> list[Dict[str, Any]]:
        """
        Get recent request history.
        
        Args:
            limit: Maximum number of recent requests to return
            
        Returns:
            List of recent request metrics
        """
        with self._lock:
            recent = self.request_history[-limit:] if self.request_history else []
            
            return [
                {
                    "timestamp": datetime.fromtimestamp(req.timestamp).isoformat(),
                    "endpoint": req.endpoint,
                    "response_time_ms": req.response_time_ms,
                    "cache_hit": req.cache_hit,
                    "status_code": req.status_code,
                    "response_size_bytes": req.response_size_bytes
                }
                for req in reversed(recent)
            ]
    
    def reset_metrics(self) -> None:
        """Reset all metrics to initial state."""
        with self._lock:
            self.request_history.clear()
            self.aggregated = AggregatedMetrics()
            self.start_time = time.time()
    
    def get_performance_summary(self) -> Dict[str, str]:
        """
        Get a human-readable performance summary.
        
        Returns:
            Dictionary with key performance indicators
        """
        with self._lock:
            if self.aggregated.total_requests == 0:
                return {
                    "summary": "No requests recorded yet",
                    "cache_effectiveness": "Unknown",
                    "performance_improvement": "Unknown"
                }
            
            cache_rate = self.aggregated.cache_hit_rate
            
            if cache_rate > 80:
                cache_effectiveness = "Excellent"
            elif cache_rate > 60:
                cache_effectiveness = "Good"
            elif cache_rate > 40:
                cache_effectiveness = "Fair"
            else:
                cache_effectiveness = "Poor"
            
            # Estimate performance improvement
            if cache_rate > 0:
                # Assume cached requests are 10x faster
                improvement_factor = 1 + (cache_rate / 100) * 9
                performance_improvement = f"{improvement_factor:.1f}x faster"
            else:
                performance_improvement = "No improvement"
            
            return {
                "summary": f"{self.aggregated.total_requests} requests, {cache_rate:.1f}% cache hit rate",
                "cache_effectiveness": cache_effectiveness,
                "performance_improvement": performance_improvement,
                "bandwidth_saved": f"{self.aggregated.bandwidth_saved_percentage:.1f}%",
                "db_queries_saved": str(self.aggregated.database_queries_saved)
            }


# Global metrics collector instance
metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """
    Get or create the global metrics collector instance.
    
    Returns:
        MetricsCollector instance
    """
    global metrics_collector
    
    if metrics_collector is None:
        metrics_collector = MetricsCollector()
    
    return metrics_collector


def initialize_metrics() -> MetricsCollector:
    """
    Initialize metrics collection.
    
    Returns:
        MetricsCollector instance
    """
    global metrics_collector
    metrics_collector = MetricsCollector()
    return metrics_collector


# Convenience functions for common operations
def record_cache_hit(endpoint: str, response_time_ms: float, 
                    status_code: int = 304) -> None:
    """Record a cache hit."""
    collector = get_metrics_collector()
    collector.record_request(endpoint, response_time_ms, True, status_code)


def record_cache_miss(endpoint: str, response_time_ms: float, 
                     response_size_bytes: int = 0, status_code: int = 200) -> None:
    """Record a cache miss."""
    collector = get_metrics_collector()
    collector.record_request(endpoint, response_time_ms, False, status_code, response_size_bytes)


# Example usage
if __name__ == "__main__":
    # Example metrics collection
    collector = MetricsCollector()
    
    # Simulate some requests
    collector.record_request("/users/1", 15.0, False, 200, 150)  # Cache miss
    collector.record_request("/users/1", 1.5, True, 304, 0)     # Cache hit
    collector.record_request("/users/2", 12.0, False, 200, 145) # Cache miss
    collector.record_request("/users/1", 1.2, True, 304, 0)     # Cache hit
    
    # Print metrics
    import json
    print(json.dumps(collector.get_metrics(), indent=2))
    print("\nPerformance Summary:")
    print(json.dumps(collector.get_performance_summary(), indent=2))