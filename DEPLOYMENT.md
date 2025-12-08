# 🤖 Deployment Guide for Dynamic Recommendations

**Complete deployment instructions for deploying the Stremio addon via Docker, Docker Compose, or local development.**

## 📑 Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start (Docker Compose)](#quick-start-docker-compose)
- [Step-by-Step Deployment](#step-by-step-deployment)
- [Token Generation](#token-generation)
- [Docker Configuration](#docker-configuration)
- [Local Development](#local-development)
- [Production Deployment](#production-deployment)
- [Monitoring & Troubleshooting](#monitoring--troubleshooting)
- [Performance Tuning](#performance-tuning)
- [Quick Reference](#quick-reference)

---

## Prerequisites

- Docker and Docker Compose installed
- Python 3.9+ (for token generation)
- API Keys:
  - TMDB API Key (free at https://www.themoviedb.org/settings/api)
  - MDBList API Key (free at https://mdblist.com/api)

---

## Quick Start (Docker Compose)

The fastest way to get running in 2 minutes:

```bash
# Clone repository
git clone <repository-url> && cd dynamic-recs

# Generate secure token salt
TOKEN_SALT=$(python -c "import secrets; print(secrets.token_hex(32))")

# Create .env file
cp .env.example .env
echo "TOKEN_SALT=$TOKEN_SALT" >> .env
echo "BASE_URL=http://localhost:8000" >> .env

# Start services
docker-compose up -d

# Wait for services
sleep 5

# Verify health
curl http://localhost:8000/health | jq

# Open configuration
echo "✅ Configure at: http://localhost:8000/configure"
```

---

## Step-by-Step Deployment

### Step 1: Clone & Setup

```bash
# Clone the repository
git clone <repository-url>
cd dynamic-recs
```

### Step 2: Configure Environment

```bash
# Create .env file from example
cp .env.example .env

# Generate secure token salt
TOKEN_SALT=$(python -c "import secrets; print(secrets.token_hex(32))")
echo "TOKEN_SALT=$TOKEN_SALT" >> .env
echo "BASE_URL=http://localhost:8000" >> .env

# Add API keys (replace with actual keys)
echo "TMDB_API_KEY=your_actual_tmdb_key" >> .env
echo "MDBLIST_API_KEY=your_actual_mdblist_key" >> .env
```

### Step 3: Verify Docker Installation

```bash
# Check Docker is installed
docker --version || echo "❌ Docker not found - install from https://docker.com"
docker-compose --version || echo "❌ Docker Compose not found"

# Check Docker is running
docker ps || echo "❌ Docker daemon not running - start Docker Desktop"
```

---

## Step 4: Deploy with Docker Compose

```bash
# Build and start containers in detached mode
docker-compose up -d --build

# Verify containers are running
docker-compose ps

# Check addon logs
docker-compose logs addon

# Check Redis logs
docker-compose logs redis
```

**Expected Output:**

```
NAME                     IMAGE                    STATUS
dynamic-recs-addon       dynamic-recs-addon       Up (healthy)
dynamic-recs-redis       redis:7-alpine           Up (healthy)
```

---

## Step 5: Verify Deployment

```bash
# Wait for services to be healthy (max 30 seconds)
for i in {1..30}; do
  curl -f http://localhost:8000/health && echo "✅ Service is healthy" && break || sleep 1
done

# Test configuration endpoint
curl -I http://localhost:8000/configure

# Check if services are accessible
echo ""
echo "✅ Addon is running at: http://localhost:8000"
echo "✅ Configuration page: http://localhost:8000/configure"
echo "✅ Health endpoint: http://localhost:8000/health"
```

**Successful Health Check Response:**

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "base_url": "http://localhost:8000"
}
```

---

## Step 6: Monitor and Troubleshoot

### View Logs

```bash
# View live logs (all services)
docker-compose logs -f

# View addon logs only
docker-compose logs -f addon

# View last 100 lines
docker-compose logs --tail=100 addon
```

### Check Container Health

```bash
# Check status
docker-compose ps

# Check resource usage
docker stats dynamic-recs-addon dynamic-recs-redis
```

### Restart Services

```bash
# Restart addon only
docker-compose restart addon

# Restart all services
docker-compose restart

# Reload with new changes
docker-compose up -d --build
```

### Stop Services

```bash
# Stop all services (preserve data)
docker-compose down

# Stop and remove all data
docker-compose down -v
```

---

## Token Generation

### Web-Based (Easiest)

Navigate to `http://localhost:8000/configure` and:

1. Enter your Stremio auth key
2. Add optional API keys (TMDB, MDBList)
3. Click "Generate Install URL"
4. Copy and use the generated URL

### Command-Line (Automation)

```bash
# Interactive token generator
python generate_token.py

# Or use Python directly
python -c "
from app.models.config import UserConfig
from app.utils.token import encode_config

config = UserConfig(
    stremio_auth_key='YOUR_STREMIO_AUTH_KEY',
    tmdb_api_key='YOUR_TMDB_KEY',
    mdblist_api_key='YOUR_MDBLIST_KEY'
)
token = encode_config(config)
print(f'http://localhost:8000/{token}/manifest.json')
"
```

### API Endpoint

```bash
# POST request to generate token
curl -X POST http://localhost:8000/generate-token \
  -H "Content-Type: application/json" \
  -d '{
    "stremio_auth_key": "your_auth_key",
    "tmdb_api_key": "your_tmdb_key",
    "mdblist_api_key": "your_mdblist_key"
  }'
```

---

## Alternative: Local Development (Without Docker)

### Setup Virtual Environment

```bash
# Create virtual environment
python -m venv .venv

# Activate (macOS/Linux)
source .venv/bin/activate

# Activate (Windows)
# .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Start Redis

```bash
# Start Redis container
docker run -d --name dynamic-recs-redis -p 6379:6379 redis:7-alpine

# Verify Redis is running
docker ps | grep redis
```

### Start the Server

```bash
# Ensure .env is configured
cat .env

# Start FastAPI server
python main.py

# Server will be available at http://localhost:8000
```

### Run Tests

```bash
# Run unit tests (no Redis required)
pytest tests/ -v -m "not integration"

# Run all tests (Redis required)
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=app --cov-report=html
```

---

## Docker Configuration

### docker-compose.yml Overview

```yaml
version: "3.8"

services:
  addon:
    build: .
    ports:
      - "8000:8000"
    environment:
      - TOKEN_SALT=${TOKEN_SALT}
      - BASE_URL=${BASE_URL}
      - REDIS_URL=redis://redis:6379
      - TMDB_API_KEY=${TMDB_API_KEY}
      - MDBLIST_API_KEY=${MDBLIST_API_KEY}
    depends_on:
      - redis
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Environment Variables

| Variable                    | Description                     | Required                     | Example                   |
| --------------------------- | ------------------------------- | ---------------------------- | ------------------------- |
| `TOKEN_SALT`                | Secret for token signing (HMAC) | ✅ Yes                       | `$(openssl rand -hex 32)` |
| `BASE_URL`                  | Public URL of addon             | ✅ Yes                       | `http://localhost:8000`   |
| `REDIS_URL`                 | Redis connection URL            | ✅ Yes                       | `redis://redis:6379`      |
| `TMDB_API_KEY`              | TMDB API key                    | ❌ Optional                  | Get from themoviedb.org   |
| `MDBLIST_API_KEY`           | MDBList API key                 | ❌ Optional                  | Get from mdblist.com      |
| `CACHE_WARM_INTERVAL_HOURS` | Cache warming interval          | ❌ Optional (default: 3)     | `3`                       |
| `DEBUG`                     | Debug mode                      | ❌ Optional (default: False) | `False`                   |
| `LOG_LEVEL`                 | Logging level                   | ❌ Optional (default: INFO)  | `INFO`                    |

---

### Pre-Deployment Checklist

- [ ] **Domain & SSL**: Configure domain and obtain SSL certificate
- [ ] **Environment Variables**: Set production `BASE_URL` in `.env`
- [ ] **Token Security**: Ensure strong `TOKEN_SALT` (auto-generated)
- [ ] **API Keys**: Verify TMDB and MDBList keys are valid
- [ ] **Firewall**: Configure firewall rules (allow 80/443, block 8000)
- [ ] **Reverse Proxy**: Set up nginx/Caddy with SSL termination
- [ ] **Docker Restart**: Ensure `restart: unless-stopped` in docker-compose.yml
- [ ] **Monitoring**: Set up uptime monitoring and alerting
- [ ] **Backups**: Configure Redis data backups (if persistence needed)
- [ ] **Rate Limiting**: Configure at reverse proxy level

### Update BASE_URL for Production

```bash
# Edit .env file
sed -i.bak "s|BASE_URL=.*|BASE_URL=https://your-domain.com|" .env
rm .env.bak

# Restart services
docker-compose down
docker-compose up -d
```

### Example Nginx Configuration

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=addon:10m rate=10r/s;
    limit_req zone=addon burst=20 nodelay;
}
```

---

---

## Monitoring & Troubleshooting

### View Logs

```bash
# View all service logs
docker-compose logs

# View addon logs only (follow mode)
docker-compose logs -f addon

# View last 50 lines
docker-compose logs --tail=50 addon

# View specific timeframe
docker-compose logs --since 10m addon

# Search logs for errors
docker-compose logs addon | grep -i error
```

### Health Checks

- `GET /health` - Service health status
- `GET /configure` - Configuration UI
- `GET /{token}/manifest.json` - Addon manifest (requires valid token)
- `GET /{token}/catalog/{type}/{id}.json` - Catalog endpoint

### Test Health Endpoint

```bash
curl http://localhost:8000/health | jq
```

### Monitor with Watch

```bash
# Check health every 5 seconds
watch -n 5 'curl -s http://localhost:8000/health | jq'
```

### Health Checks

**Available Endpoints**

- `GET /health` - Service health status
- `GET /configure` - Configuration UI
- `GET /{token}/manifest.json` - Addon manifest (requires valid token)
- `GET /{token}/catalog/{type}/{id}.json` - Catalog endpoint

**Test Health Endpoint**

```bash
# Simple health check
curl http://localhost:8000/health | jq

# Check container health
docker-compose ps

# Verbose health check with timing
time curl -i http://localhost:8000/health

# Monitor continuously
watch -n 5 'curl -s http://localhost:8000/health | jq'
```

### Container Status

```bash
# List all services
docker-compose ps

# Check resource usage
docker stats

# Inspect addon logs
docker-compose logs -f --tail=100 addon
```

### Troubleshooting

**1. Port 8000 already in use**

```bash
# Find process using port
lsof -i :8000
# Or
netstat -an | grep 8000

# Kill the process
kill -9 <PID>
```

**2. Redis connection failed**

```bash
# Check Redis is running
docker ps | grep redis

# Check Redis logs
docker logs dynamic-recs-redis

# Restart Redis
docker restart dynamic-recs-redis
```

**3. Addon not starting**

```bash
# Check logs for errors
docker-compose logs addon

# Verify environment variables
docker exec dynamic-recs-addon env | grep -E 'TOKEN_SALT|BASE_URL|REDIS_URL'

# Rebuild and restart
docker-compose down
docker-compose up -d --build
```

**4. Tests failing**

```bash
# Check Python environment
which python
python --version

# Reinstall dependencies
pip install -r requirements.txt

# Run tests with verbose output
pytest tests/ -v --tb=long
```

---

## Maintenance Commands

### Update Application

```bash
# Pull latest changes
git pull

# Rebuild and restart
docker-compose down
docker-compose up -d --build
```

### Clear Redis Cache

```bash
# Clear all cache
docker exec dynamic-recs-redis redis-cli FLUSHALL

# Restart addon to repopulate
docker-compose restart addon
```

### View Redis Keys

```bash
# Connect to Redis CLI
docker exec -it dynamic-recs-redis redis-cli

# List all keys
KEYS *

# Get specific key
GET user:somekey:library

# Exit
exit
```

### Backup Redis Data

```bash
# Create backup
docker exec dynamic-recs-redis redis-cli SAVE

# Copy backup file
docker cp dynamic-recs-redis:/data/dump.rdb ./backup-$(date +%Y%m%d).rdb
```

## Performance Tuning

### Monitor Resource Usage

```bash
# Real-time container stats
docker stats

# Check specific container
docker stats dynamic-recs-addon

# Monitor with interval
watch -n 2 'docker stats --no-stream'
```

### Redis Optimization

```bash
# Check Redis memory usage
docker exec dynamic-recs-redis redis-cli INFO memory

# Check key count
docker exec dynamic-recs-redis redis-cli DBSIZE

# Monitor Redis commands
docker exec dynamic-recs-redis redis-cli MONITOR

# Analyze memory by key type
docker exec dynamic-recs-redis redis-cli --latency

# Set max memory policy (evict least recently used)
docker exec dynamic-recs-redis redis-cli CONFIG SET maxmemory 256mb
docker exec dynamic-recs-redis redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

### API Response Time Testing

```bash
# Test manifest endpoint (replace {TOKEN})
curl -w "Time: %{time_total}s\nCode: %{http_code}\n" \
  -o /dev/null -s http://localhost:8000/{TOKEN}/manifest.json

# Test catalog endpoint (replace {TOKEN})
time curl -s http://localhost:8000/{TOKEN}/catalog/movie/dynamic_movies_0.json > /dev/null

# Batch test with Apache Bench
ab -n 100 -c 10 http://localhost:8000/{TOKEN}/manifest.json
```

### Docker Container Optimization

```bash
# View current resource limits
docker inspect dynamic-recs-addon | jq '.[0].HostConfig | {Memory, MemorySwap, CpuShares}'

# Set memory limit
# Edit docker-compose.yml and add:
# deploy:
#   resources:
#     limits:
#       memory: 512M
#     reservations:
#       memory: 256M

# Rebuild with new limits
docker-compose up -d --build
```

### Cache Optimization

```bash
# Check cache hit rates
docker-compose logs addon | grep -i "cache\|hit\|miss"

# Clear and rebuild cache
docker exec dynamic-recs-redis redis-cli FLUSHALL
docker-compose restart addon

# Monitor cache warming
docker-compose logs -f addon | grep -i "warming\|refresh"
```

## Quick Reference

### Essential Commands

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# View logs (all services)
docker-compose logs -f

# Restart addon
docker-compose restart addon

# Rebuild after changes
docker-compose up -d --build

# Check service health
docker-compose ps

# Monitor resources
docker stats

# Clean up (remove containers & volumes)
docker-compose down -v
```

### One-Liners

```bash
# Quick deployment with health check
cp .env.example .env && \
TOKEN=$(python -c "import secrets; print(secrets.token_hex(32))") && \
echo "TOKEN_SALT=$TOKEN" >> .env && \
echo "BASE_URL=http://localhost:8000" >> .env && \
docker-compose up -d && \
sleep 5 && \
curl http://localhost:8000/health

# Test all endpoints
TOKEN="your_token_here" && \
curl http://localhost:8000/health && \
curl http://localhost:8000/configure && \
curl http://localhost:8000/$TOKEN/manifest.json

# View real-time logs
docker-compose logs -f addon

# Clear cache and rebuild
docker exec dynamic-recs-redis redis-cli FLUSHALL && \
docker-compose restart addon

# Perform health check with timing
watch -n 5 'curl -w "Status: %{http_code} | Time: %{time_total}s\n" http://localhost:8000/health'
```

### Emergency Commands

```bash
# Force stop all containers
docker-compose kill

# Reset everything (WARNING: removes data)
docker-compose down -v && docker-compose up -d --build

# View addon logs for errors
docker-compose logs addon | grep -E "(error|ERROR|Exception)"

# SSH into addon container
docker-compose exec addon /bin/bash

# Force restart Redis
docker-compose restart redis && sleep 2 && docker-compose restart addon
```

---

## Frequently Asked Questions

**Q: Are API keys required?**
A: TMDB and MDBList keys are optional but recommended for better recommendations and ratings.

**Q: Is Redis required?**
A: Yes, Redis is essential for caching and performance. It must be running for the addon to function.

**Q: Can I run without Docker?**
A: Yes, follow the Local Development section. You'll need Python 3.9+ and Redis running separately.

**Q: How do I get my Stremio auth key?**
A: Open https://web.stremio.com → DevTools Console → `copy(localStorage.getItem("authKey"))`

**Q: Can I self-host on a Raspberry Pi?**
A: Yes, it should work fine. Adjust resource limits in docker-compose.yml as needed.

**Q: How often should I restart services?**
A: Only when deploying updates or if experiencing issues. Let Docker manage restart policies.

**Q: Can I backup my Redis data?**
A: Yes, use the backup commands in the Maintenance section. You can also enable persistence in redis.conf.

---

## Support & Resources

For issues and questions:

- **Logs**: `docker-compose logs addon`
- **Environment**: `cat .env`
- **Docker Status**: `docker-compose ps`
- **Test Endpoint**: `curl http://localhost:8000/health`
- **Full Docs**: See README.md

**Helpful Commands:**

```bash
# Diagnose issues
docker-compose logs addon | tail -50
docker exec dynamic-recs-addon env
docker-compose ps
docker stats

# Get help
cat .env
docker-compose logs --help
curl --help
```

---

**Last Updated**: December 2024 | **Version**: 1.0.0
