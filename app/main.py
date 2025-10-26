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
from typing import Optional

# Import our modules
from models import User, UserDatabase
# from etag_service import ETagService
# from cache_service import CacheService
# from metrics import MetricsCollector

app = FastAPI(
    title="ETag Implementation Demo",
    description="A demonstration of HTTP ETags with Redis caching for API performance optimization",
    version="1.0.0"
)

# Serve static files (test interface)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize services
db = UserDatabase()
# etag_service = ETagService()
# cache_service = CacheService()
# metrics = MetricsCollector()


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
        <title>ETag Demo</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .container { max-width: 800px; margin: 0 auto; }
            button { margin: 10px; padding: 10px 20px; }
            .result { background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px; }
            .metrics { background: #e8f4f8; padding: 15px; border-radius: 5px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>ETag Implementation Demo</h1>
            <p>This demo shows the performance difference between API requests with and without ETag caching.</p>
            
            <h2>Test Controls</h2>
            <button onclick="createUser()">Create Test User</button>
            <button onclick="getUser()">Get User (Watch for ETags!)</button>
            <button onclick="updateUser()">Update User (Invalidates Cache)</button>
            <button onclick="loadTest()">Run Load Test</button>
            <button onclick="getMetrics()">Show Metrics</button>
            
            <h2>Results</h2>
            <div id="results"></div>
            
            <h2>Performance Metrics</h2>
            <div id="metrics" class="metrics">
                <p>Metrics will appear here...</p>
            </div>
        </div>
        
        <script>
            let userId = 1;
            
            async function createUser() {
                const response = await fetch('/users', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        name: 'Test User ' + Date.now(),
                        email: 'test' + Math.floor(Math.random() * 100) + '@example.com'
                    })
                });
                const result = await response.json();
                userId = result.id;
                showResult('User created: ' + JSON.stringify(result));
            }
            
            async function getUser() {
                const start = performance.now();
                const response = await fetch(`/users/${userId}`);
                const end = performance.now();
                
                const etag = response.headers.get('ETag');
                const status = response.status;
                const data = status === 304 ? 'Not Modified (Cached)' : await response.json();
                
                showResult(`GET /users/${userId} - Status: ${status} - ETag: ${etag} - Time: ${(end-start).toFixed(2)}ms - Data: ${JSON.stringify(data)}`);
            }
            
            async function updateUser() {
                const response = await fetch(`/users/${userId}`, {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        name: 'Updated User ' + Date.now(),
                        email: 'updated@example.com'
                    })
                });
                const result = await response.json();
                showResult('User updated: ' + JSON.stringify(result));
            }
            
            async function loadTest() {
                showResult('Running load test with 50 requests...');
                const promises = [];
                for (let i = 0; i < 50; i++) {
                    promises.push(fetch(`/users/${userId}`));
                }
                
                const start = performance.now();
                await Promise.all(promises);
                const end = performance.now();
                
                showResult(`Load test completed: 50 requests in ${(end-start).toFixed(2)}ms (${((end-start)/50).toFixed(2)}ms avg per request)`);
            }
            
            async function getMetrics() {
                const response = await fetch('/metrics');
                const metrics = await response.json();
                document.getElementById('metrics').innerHTML = '<pre>' + JSON.stringify(metrics, null, 2) + '</pre>';
            }
            
            function showResult(text) {
                const div = document.createElement('div');
                div.className = 'result';
                div.textContent = new Date().toLocaleTimeString() + ': ' + text;
                document.getElementById('results').appendChild(div);
                div.scrollIntoView();
            }
            
            // Auto-refresh metrics every 5 seconds
            setInterval(getMetrics, 5000);
        </script>
    </body>
    </html>
    """)

@app.get("/users/{user_id}")
async def get_user(user_id: int, request: Request):
    """
    Get user with ETag support.
    
    This endpoint demonstrates:
    1. ETag generation
    2. Conditional request handling (If-None-Match)
    3. Performance difference between cached and uncached responses
    """
    # Add artificial delay to simulate complex database query (50ms)
    await asyncio.sleep(0.01)
    
    # Get user from database
    user = db.get_user(user_id)
    
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    # TODO: Implement ETag logic
    # - Check If-None-Match header
    # - Validate ETag from cache
    # - Return 304 if not modified
    # - Return 200 with new ETag if modified
    
    return user.to_dict()

@app.get("/users")
async def get_all_users(limit: int = 100, offset: int = 0):
    """Get all users with pagination."""
    # Add artificial delay (30ms)
    await asyncio.sleep(0.03)
    
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
    """Create a new user."""
    # Add artificial delay to simulate database write (20ms)
    await asyncio.sleep(0.05)
    
    try:
        user = db.create_user(user_data.name, user_data.email)
    except Exception as e:
        # Handle duplicate email or other database errors
        raise HTTPException(status_code=400, detail=str(e))
    
    # TODO: Generate initial ETag and store in cache
    
    return user.to_dict()

@app.put("/users/{user_id}")
async def update_user(user_id: int, user_data: UserUpdate):
    """
    Update user and invalidate ETag cache.
    
    This demonstrates cache invalidation when data changes.
    """
    # Add artificial delay to simulate database update (30ms)
    await asyncio.sleep(0.05)
    
    # Update user in database
    user = db.update_user(
        user_id, 
        name=user_data.name, 
        email=user_data.email
    )
    
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    # TODO: Invalidate ETag cache and generate new ETag
    
    return user.to_dict()

@app.delete("/users/{user_id}")
async def delete_user(user_id: int):
    """Delete a user."""
    # Add artificial delay (20ms)
    await asyncio.sleep(0.02)
    
    deleted = db.delete_user(user_id)
    
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
    
    # TODO: Clean up ETag cache
    
    return {"message": "User deleted successfully", "id": user_id}

@app.get("/metrics")
async def get_metrics():
    """
    Get performance metrics showing ETag effectiveness.
    
    Returns cache hit rates, response times, and database query statistics.
    """
    # TODO: Implement full metrics collection
    # - Cache hit/miss rates
    # - Average response times
    # - Database queries saved
    # - Bandwidth savings
    
    # Basic metrics for now
    total_users = db.count_users()
    
    return {
        "database": {
            "total_users": total_users,
            "database_file": db.db_path
        },
        "cache": {
            "status": "Not implemented yet",
            "hit_rate": "0%"
        },
        "performance": {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "cache_hit_rate": "0%",
            "avg_response_time_cached": "0ms",
            "avg_response_time_uncached": "0ms",
            "database_queries_saved": 0,
            "bandwidth_saved_bytes": 0
        }
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