"""
FastAPI application demonstrating ETag implementation with Redis caching.

This is the main application file that sets up the API endpoints
and demonstrates the performance difference between requests with
and without ETag optimization.
"""

from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
import uvicorn
import time
import asyncio
import logging
from typing import Optional

# Import our modules
from models import User, UserDatabase
from etag_service import ETagService
from cache_service import CacheService, initialize_cache, cleanup_cache
from metrics import MetricsCollector, initialize_metrics

# Configure logging
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ETag Implementation Demo",
    description="A demonstration of HTTP ETags with Redis caching for API performance optimization",
    version="1.0.0"
)

# Serve static files (test interface) - use parent directory
import os
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Initialize services
db = UserDatabase()
cache_service: Optional[CacheService] = None
etag_service: Optional[ETagService] = None
metrics: Optional[MetricsCollector] = None

@app.on_event("startup")
async def startup_event():
    """Initialize services on application startup."""
    global cache_service, etag_service, metrics
    
    print("🚀 Initializing ETag Demo services...")
    
    # Initialize cache service
    cache_service = await initialize_cache()
    
    # Initialize ETag service with cache and database
    etag_service = ETagService(cache_service=cache_service, db_service=db)
    
    # Initialize metrics collection
    metrics = initialize_metrics()
    
    print("✅ All services initialized successfully!")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup services on application shutdown."""
    print("📕 Shutting down services...")
    await cleanup_cache()
    print("✅ Cleanup completed!")


# Pydantic models for request validation
class UserCreate(BaseModel):
    name: str
    email: EmailStr


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None

@app.get("/")
async def root():
    """Simple test interface for the ETag demo."""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>ETag Demo - Simple Interface</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 1200px;
                margin: 20px auto;
                padding: 20px;
                background: #f5f5f5;
            }
            h1 {
                color: #333;
            }
            .controls {
                background: white;
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            button {
                background: #007bff;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                cursor: pointer;
                margin: 5px;
                font-size: 14px;
            }
            button:hover {
                background: #0056b3;
            }
            input {
                padding: 8px;
                border: 1px solid #ddd;
                border-radius: 4px;
                margin: 5px;
                width: 100px;
            }
            #metrics {
                background: white;
                padding: 20px;
                border-radius: 8px;
                margin-bottom: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            #results {
                background: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .result {
                padding: 10px;
                margin: 10px 0;
                border-radius: 4px;
                background: #e7f3ff;
                border-left: 4px solid #007bff;
            }
            pre {
                background: #f8f9fa;
                padding: 10px;
                border-radius: 4px;
                overflow-x: auto;
            }
        </style>
    </head>
    <body>
        <h1>🏷️ ETag Demo - Simple Test Interface</h1>
        
        <div class="controls">
            <h3>Test Controls</h3>
            <div>
                <label>User ID:</label>
                <input type="number" id="userId" value="5" placeholder="User ID">
                <br><br>
                <label>ETag (optional):</label>
                <input type="text" id="etag" placeholder="Leave empty for no If-None-Match" style="width: 300px;">
                <br><br>
                <button onclick="getUser()">Get User</button>
                <button onclick="loadTest()">Load Test (50 requests)</button>
            </div>
        </div>

        <div id="metrics">
            <h3>📊 Metrics</h3>
            <div id="metricsContent">Loading...</div>
        </div>

        <div id="results">
            <h3>📋 Results</h3>
        </div>

        <script>
            async function getUser() {
                const id = parseInt(document.getElementById('userId').value);
                const etag = document.getElementById('etag').value.trim();
                
                showResult(`Fetching user ${id}${etag ? ' with ETag: ' + etag : ' (no ETag)'}...`);
                
                const headers = {};
                if (etag) {
                    headers['If-None-Match'] = etag;
                }
                
                const start = performance.now();
                const response = await fetch(`/users/${id}`, { headers });
                const end = performance.now();
                
                if (response.status === 304) {
                    const receivedETag = response.headers.get('ETag');
                    showResult(`✅ GET /users/${id} with If-None-Match
Status: 304 Not Modified 🎉
ETag: ${receivedETag}
Time: ${(end-start).toFixed(2)}ms
💾 Cache HIT - No data transferred! Database query skipped!`);
                } else if (response.ok) {
                    const receivedETag = response.headers.get('ETag');
                    const data = await response.json();
                    
                    // Auto-fill the ETag field for next request
                    document.getElementById('etag').value = receivedETag;
                    
                    showResult(`✅ GET /users/${id}
Status: ${response.status} OK
ETag: ${receivedETag}
Time: ${(end-start).toFixed(2)}ms
Response: ${JSON.stringify(data, null, 2)}

💡 ETag saved! Click "Get User" again to test 304 response.`);
                } else if (response.status === 404) {
                    showResult(`❌ User ${id} not found`);
                } else {
                    showResult(`❌ Error: ${response.status}`);
                }
                
                // Refresh metrics
                await getMetrics();
            }

            async function loadTest() {
                const id = parseInt(document.getElementById('userId').value);
                showResult(`🚀 Starting load test: 50 requests to /users/${id}...`);
                
                const requestTimes = [];
                const promises = [];
                
                for (let i = 0; i < 50; i++) {
                    const requestStart = performance.now();
                    const promise = fetch(`/users/${id}`).then(response => {
                        const requestEnd = performance.now();
                        const duration = requestEnd - requestStart;
                        requestTimes.push(duration);
                        return response;
                    });
                    promises.push(promise);
                }
                
                const start = performance.now();
                await Promise.all(promises);
                const end = performance.now();
                
                const totalTime = end - start;
                const avgTime = totalTime / 50;
                
                // Create a summary of all request times
                const timesBreakdown = requestTimes.map((time, index) => 
                    `Request ${index + 1}: ${time.toFixed(2)}ms`
                ).join('\\n');
                
                showResult(`✅ Load test completed!
Total time: ${totalTime.toFixed(2)}ms
Average per request: ${avgTime.toFixed(2)}ms

Individual request times:
${timesBreakdown}`);
                
                // Refresh metrics
                await getMetrics();
            }

            async function getMetrics() {
                const response = await fetch('/metrics');
                const metrics = await response.json();
                document.getElementById('metricsContent').innerHTML = '<pre>' + JSON.stringify(metrics, null, 2) + '</pre>';
            }

            function showResult(text) {
                const div = document.createElement('div');
                div.className = 'result';
                div.textContent = new Date().toLocaleTimeString() + ':\\n' + text;
                div.style.whiteSpace = 'pre-wrap';
                document.getElementById('results').insertBefore(div, document.getElementById('results').firstChild);
            }

            // Auto-load metrics on start
            setTimeout(getMetrics, 1000);
        </script>
    </body>
    </html>
    """)

@app.get("/users/{user_id}")
async def get_user(user_id: int, request: Request, response: Response):
    """
    Get user with ETag support - OPTIMIZED VERSION.
    
    This endpoint demonstrates:
    1. Early ETag validation (before DB access)
    2. Database query only when necessary
    3. Cache hit/miss tracking
    4. Performance metrics collection
    
    Flow:
    - If client sends If-None-Match → validate from cache first
    - If ETag matches → return 304 (NO DATABASE HIT!)
    - If ETag doesn't match or missing → fetch from DB
    """
    start_time = time.time()
    
    
    if etag_service:
        client_etag = request.headers.get("If-None-Match")
        
        try:
            etag_result = await etag_service.validate_etag("user", user_id, client_etag)
            
            response.headers["ETag"] = etag_result.current_etag
            response.headers["Cache-Control"] = "private, must-revalidate"
            
            if etag_result.is_valid:
                response_time_ms = (time.time() - start_time) * 1000
                
                if metrics:
                    metrics.record_request(
                        endpoint=f"/users/{user_id}",
                        response_time_ms=response_time_ms,
                        cache_hit=etag_result.cache_hit,
                        status_code=304,
                        response_size_bytes=0
                    )
                
                response.status_code = 304
                return Response(status_code=304)
        
        except ValueError:
            raise HTTPException(status_code=404, detail="User not found")
        
        if etag_result.entity:
            user = etag_result.entity
            logger.debug(f"♻️  Reusing entity from ETag validation - NO second DB query!")
        else:
            logger.debug(f"🔍 ETag cache hit but need full data - querying DB")
            
            await asyncio.sleep(0.5)
            
            user = db.get_user(user_id)
            
            if user is None:
                raise HTTPException(status_code=404, detail="User not found")
        
        response_time_ms = (time.time() - start_time) * 1000
        user_dict = user.to_dict()
        
        if metrics:
            response_size = len(str(user_dict).encode('utf-8'))
            metrics.record_request(
                endpoint=f"/users/{user_id}",
                response_time_ms=response_time_ms,
                cache_hit=etag_result.cache_hit,
                status_code=200,
                response_size_bytes=response_size
            )
        
        return user_dict
    
    else:
        await asyncio.sleep(0.5)
        
        user = db.get_user(user_id)
        
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        
        response_time_ms = (time.time() - start_time) * 1000
        user_dict = user.to_dict()
        
        if metrics:
            response_size = len(str(user_dict).encode('utf-8'))
            metrics.record_request(
                endpoint=f"/users/{user_id}",
                response_time_ms=response_time_ms,
                cache_hit=False,
                status_code=200,
                response_size_bytes=response_size
            )
        
        return user_dict

@app.get("/users")
async def get_all_users(limit: int = 100, offset: int = 0):
    """Get all users with pagination."""

    users = db.get_all_users(limit=limit, offset=offset)
    total = db.count_users()
    
    return {
        "users": [user.to_dict() for user in users],
        "total": total,
        "limit": limit,
        "offset": offset
    }

@app.post("/users")
async def create_user(user_data: UserCreate):
    """Create a new user with initial ETag."""
    start_time = time.time()
    
    try:
        user = db.create_user(user_data.name, user_data.email)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Generate initial ETag and store in cache
    if etag_service and user.id:
        initial_etag = await etag_service.update_etag(
            "user", 
            user.id, 
            timestamp=user.created_at
        )
        print(f"👤 User {user.id} created - Initial ETag: {initial_etag}")
    
    # Record metrics
    if metrics:
        response_time_ms = (time.time() - start_time) * 1000
        user_dict = user.to_dict()
        response_size = len(str(user_dict).encode('utf-8'))
        
        metrics.record_request(
            endpoint="/users",
            response_time_ms=response_time_ms,
            cache_hit=False,  # New users are never cache hits
            status_code=201,
            response_size_bytes=response_size
        )
    
    return user.to_dict()

@app.put("/users/{user_id}")
async def update_user(user_id: int, user_data: UserUpdate):
    """
    Update user and invalidate ETag cache.
    
    This demonstrates cache invalidation when data changes.
    """
    start_time = time.time()
        
    # Invalidate ETag cache before updating
    if etag_service:
        await etag_service.invalidate_etag("user", user_id)
    
    # Update user in database
    user = db.update_user(
        user_id, 
        name=user_data.name, 
        email=user_data.email
    )
    
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Generate and cache new ETag after update
    if etag_service:
        new_etag = await etag_service.update_etag(
            "user", 
            user_id, 
            timestamp=user.updated_at
        )
        print(f"🔄 User {user_id} updated - New ETag: {new_etag}")
    
    # Record metrics
    if metrics:
        response_time_ms = (time.time() - start_time) * 1000
        user_dict = user.to_dict()
        response_size = len(str(user_dict).encode('utf-8'))
        
        metrics.record_request(
            endpoint=f"/users/{user_id}",
            response_time_ms=response_time_ms,
            cache_hit=False,  # Updates are never cache hits
            status_code=200,
            response_size_bytes=response_size
        )
    
    return user.to_dict()

@app.delete("/users/{user_id}")
async def delete_user(user_id: int):
    """Delete a user and clean up ETag cache."""
    deleted = db.delete_user(user_id)
    
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
    
    if etag_service:
        await etag_service.invalidate_etag("user", user_id)
        print(f"🗑️ User {user_id} deleted - ETag cache cleaned")
    
    return {"message": "User deleted successfully", "id": user_id}

@app.get("/metrics")
async def get_metrics():
    """
    Get performance metrics showing ETag effectiveness.
    
    Returns cache hit rates, response times, and database query statistics.
    """
    # Get database metrics
    total_users = db.count_users()
    
    # Get cache statistics
    cache_stats = {}
    if cache_service:
        cache_stats = await cache_service.get_cache_stats()
    else:
        cache_stats = {
            "connected": False,
            "status": "Cache service not available"
        }
    
    # Get performance metrics
    performance_metrics = {}
    performance_summary = {}
    if metrics:
        performance_metrics = metrics.get_metrics()
        performance_summary = metrics.get_performance_summary()
    else:
        performance_metrics = {
            "performance": {
                "total_requests": 0,
                "cache_hits": 0,
                "cache_misses": 0,
                "cache_hit_rate": "0%"
            }
        }
        performance_summary = {
            "summary": "Metrics collection not available"
        }
    
    return {
        "database": {
            "total_users": total_users,
            "database_file": db.db_path
        },
        "cache": cache_stats,
        "metrics": performance_metrics,
        "summary": performance_summary
    }

if __name__ == "__main__":
    print("🚀 Starting ETag Demo Server...")
    print("📊 Visit http://localhost:8000 for the test interface")
    print("📚 API docs available at http://localhost:8000/docs")
    
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=True,
        log_level="info"
    )