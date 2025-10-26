# ETag Implementation Demo - Setup Guide

This guide walks you through setting up the ETag demo project step by step.

## Prerequisites

### Required Software
- **Python 3.9+** - Check with `python --version`
- **Docker** - For running Redis easily
- **Git** - For version control

### Installation Links
- [Python](https://python.org/downloads/)
- [Docker Desktop](https://docs.docker.com/desktop/)
- [Git](https://git-scm.com/downloads)

## Step-by-Step Setup

### 1. Clone and Navigate
```bash
# If you cloned from a repository
git clone <repo-url>
cd etag-demo

# If you're starting from the created folder
cd ~/Desktop/Projects/etag-demo
```

### 2. Create Python Virtual Environment
```bash
# Create virtual environment
python -m venv venv

# Activate it (macOS/Linux)
source venv/bin/activate

# Activate it (Windows)
venv\Scripts\activate

# Your prompt should show (venv) now
```

### 3. Install Python Dependencies
```bash
# Install all required packages
pip install -r requirements.txt

# Verify installation
pip list
```

### 4. Start Redis
```bash
# Start Redis using Docker Compose
docker-compose up -d redis

# Verify Redis is running
docker ps

# Test Redis connection
redis-cli ping
# Should return: PONG
```

### 5. Initialize the Database
```bash
# This will be automated in the app, but for now:
cd app
python -c "
import sqlite3
conn = sqlite3.connect('users.db')
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')
conn.commit()
conn.close()
print('Database initialized!')
"
```

### 6. Start the Application
```bash
# From the app directory
python main.py

# You should see:
# 🚀 Starting ETag Demo Server...
# 📊 Visit http://localhost:8000 for the test interface
# 📚 API docs available at http://localhost:8000/docs
```

### 7. Test the Setup
Open your browser and go to:
- **Test Interface**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Metrics**: http://localhost:8000/metrics

## Development Workflow

### Phase 1: Basic Implementation
1. **Implement User Model** (`app/models.py`)
2. **Add Database Operations** (Create, Read, Update)
3. **Test Basic API** without ETags
4. **Measure Baseline Performance**

### Phase 2: ETag Features
1. **Implement ETag Service** (`app/etag_service.py`)
2. **Add Redis Cache Service** (`app/cache_service.py`)
3. **Add ETag Headers** to API responses
4. **Implement Conditional Requests** (If-None-Match)

### Phase 3: Testing and Metrics
1. **Add Performance Metrics** (`app/metrics.py`)
2. **Create Load Tests** (`tests/load_test.py`)
3. **Compare Performance** with and without ETags
4. **Document Results**

## Troubleshooting

### Common Issues

#### Redis Connection Failed
```bash
# Check if Redis is running
docker ps

# Restart Redis
docker-compose down
docker-compose up -d redis

# Check Redis logs
docker-compose logs redis
```

#### Python Module Not Found
```bash
# Make sure virtual environment is activated
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# Reinstall dependencies
pip install -r requirements.txt
```

#### Port 8000 Already in Use
```bash
# Find what's using port 8000
lsof -i :8000

# Kill the process (replace PID)
kill -9 <PID>

# Or use a different port
uvicorn app.main:app --port 8001
```

#### Permission Denied (macOS/Linux)
```bash
# Fix permissions
chmod +x app/main.py

# Or run with python explicitly
python app/main.py
```

## Verification Commands

### Check Everything is Working
```bash
# Test API endpoints
curl http://localhost:8000/metrics
curl http://localhost:8000/users/1

# Test Redis
redis-cli ping

# Check Python environment
pip list | grep fastapi
pip list | grep redis

# Check Docker
docker ps | grep redis
```

### Performance Testing
```bash
# Quick performance test
curl -w "Time: %{time_total}s\n" http://localhost:8000/users/1

# Load testing (install locust first)
pip install locust
cd tests
locust -f load_test.py --host=http://localhost:8000 --headless -u 10 -r 5 -t 30s
```

## Next Steps

Once everything is set up:

1. **Explore the Code**: Start with `app/main.py`
2. **Run the Test Interface**: Visit http://localhost:8000
3. **Check the TODO Comments**: See what needs to be implemented
4. **Start with Phase 1**: Implement basic user operations
5. **Add ETags Gradually**: Follow the implementation phases

## Development Tips

### Useful Commands
```bash
# Restart the server automatically on changes
uvicorn app.main:app --reload

# Run tests
pytest tests/

# Check code quality
flake8 app/
black app/

# Monitor Redis
redis-cli monitor
```

### Debugging
- Use `print()` statements liberally
- Check FastAPI logs in the terminal
- Use browser Developer Tools to inspect HTTP headers
- Monitor Redis with `redis-cli monitor`

### Git Workflow
```bash
# Initialize git repository
git init
git add .
git commit -m "Initial ETag demo setup"

# Create feature branches
git checkout -b feature/etag-implementation
git checkout -b feature/performance-metrics
```

---

**Ready to start building!** 🚀

Once you've completed the setup, move on to implementing the core features following the phases outlined in the main README.