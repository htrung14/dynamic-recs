# 🤖 LLM Deployment Guide for Dynamic Recommendations

**Automated deployment instructions for AI agents and LLMs deploying this Stremio addon via terminal.**

---

## ⚠️ IMPORTANT: Token Generation Fix

**The web configuration page (`/configure`) has been updated to generate properly signed tokens.**

### What Changed?

- **OLD BEHAVIOR**: Frontend used `btoa()` client-side, creating unsigned base64 tokens
- **NEW BEHAVIOR**: Frontend calls `/generate-token` endpoint for server-signed tokens with HMAC
- **RESULT**: All tokens from the web UI now work correctly with the backend

### Alternative: Generate Tokens via Script

For command-line token generation or automation:

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

---

## Prerequisites

- Docker and Docker Compose installed
- Python 3.9+ (for token generation)
- API Keys:
  - TMDB API Key (free at https://www.themoviedb.org/settings/api)
  - MDBList API Key (free at https://mdblist.com/api)

---

## Step 1: Setup Environment

```bash
# Navigate to project directory
cd /path/to/dynamic-recs

# Create .env file from example
cp .env.example .env

# Generate secure token salt and update .env
TOKEN=$(python -c "import secrets; print(secrets.token_hex(32))")
sed -i.bak "s/TOKEN_SALT=.*/TOKEN_SALT=$TOKEN/" .env

# Update BASE_URL if deploying to production
# sed -i.bak "s|BASE_URL=.*|BASE_URL=https://your-domain.com|" .env

# Add API keys (replace with actual keys)
sed -i.bak "s/TMDB_API_KEY=.*/TMDB_API_KEY=your_actual_tmdb_key/" .env
sed -i.bak "s/MDBLIST_API_KEY=.*/MDBLIST_API_KEY=your_actual_mdblist_key/" .env

# Remove backup files
rm .env.bak
```

---

## Step 2: Verify Docker Installation

```bash
# Check Docker is installed
docker --version || echo "❌ Docker not found - install from https://docker.com"
docker-compose --version || echo "❌ Docker Compose not found"

# Check Docker is running
docker ps || echo "❌ Docker daemon not running - start Docker Desktop"
```

---

## Step 3: Deploy with Docker Compose

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

## Step 4: Verify Deployment

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

## Step 5: Monitor and Troubleshoot

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

## Production Deployment

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

## Health Check Endpoints

### Available Endpoints

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

---

## Troubleshooting

### Common Issues

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

---

## Performance Tuning

### Monitor Resource Usage

```bash
# Real-time stats
docker stats

# Check container resource limits
docker inspect dynamic-recs-addon | jq '.[0].HostConfig.Memory'
```

### Optimize Redis

```bash
# Check Redis memory usage
docker exec dynamic-recs-redis redis-cli INFO memory

# Set max memory (if needed)
docker exec dynamic-recs-redis redis-cli CONFIG SET maxmemory 256mb
docker exec dynamic-recs-redis redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

### Check API Response Times

```bash
# Test manifest endpoint (replace TOKEN with actual token)
time curl -s http://localhost:8000/TOKEN/manifest.json > /dev/null

# Test catalog endpoint
time curl -s http://localhost:8000/TOKEN/catalog/movie/dynamic_movies_0.json > /dev/null
```

---

## Success Indicators

✅ **Deployment Successful When:**

- Health endpoint returns 200 status
- Configuration page loads successfully
- Docker containers show "Up (healthy)" status
- No error logs in `docker-compose logs`
- Redis connection established
- Port 8000 accessible

✅ **Ready for Production When:**

- All tests passing
- SSL certificate configured
- Reverse proxy working
- Monitoring alerts configured
- Backup strategy implemented
- Rate limiting active

---

## Quick Reference

### One-Line Deploy

```bash
cp .env.example .env && python -c "import secrets; print(f\"TOKEN_SALT={secrets.token_hex(32)}\")" >> .env && docker-compose up -d --build && sleep 10 && curl http://localhost:8000/health
```

### One-Line Stop

```bash
docker-compose down
```

### One-Line Restart with Logs

```bash
docker-compose restart && docker-compose logs -f addon
```

### One-Line Health Check

```bash
curl -sf http://localhost:8000/health && echo "✅ Healthy" || echo "❌ Unhealthy"
```

---

## Support

For issues or questions:

- Check logs: `docker-compose logs addon`
- Review environment: `cat .env`
- Verify Docker: `docker-compose ps`
- Test endpoints manually with curl
- Review README.md for full documentation

**Common Questions:**

- API keys required: Yes, both TMDB and MDBList
- Redis required: Yes, for caching
- Docker required: Yes (or run locally with Python)
- Stremio auth key: Get from web.stremio.com console
