# AGENTS.md

## Project Overview

Python 3.9+ FastAPI Stremio addon for personalized movie/series recommendations. Uses Redis for caching, aiohttp for async external API calls (TMDB, MDBList, Stremio). Dockerized with `docker-compose`.

## Key Commands

```bash
# Run locally (needs Redis running)
python main.py                       # starts on :8000 with reload

# Docker
docker-compose up -d --build         # full stack with Redis
docker-compose logs addon            # view addon logs
docker-compose down -v               # stop + remove volumes

# Tests
pytest                               # runs all, outputs coverage to htmlcov/
pytest tests/test_token.py           # single file
pytest -k "test_name"                # single test
pytest --no-cov                      # skip coverage (faster)

# Code quality
black app tests                      # format
mypy app                             # type check
pylint app                           # lint
```

## Architecture

```
main.py → app/core/app.py (create_app) → FastAPI with lifespan
app/api/endpoints/   → manifest, catalog, configure, health routers
app/services/        → recommendations, stremio, tmdb, cache, background
app/models/          → config (UserConfig), stremio models
app/utils/           → token (encode/decode), crypto, helpers, rate_limiter
static/              → frontend assets for /configure page
```

Entry point: `main.py` calls `create_app()` which wires up routers, middleware, and starts background cache warming on startup.

## Test Setup

- `pytest.ini`: `asyncio_mode = auto` — async tests run without `@pytest.mark.asyncio`
- Tests use `fakeredis` (no real Redis needed)
- Fixtures in `tests/conftest.py`: `fake_redis`, `sample_user_config`, `sample_tmdb_movie`, `sample_stremio_library`
- Coverage configured for `app/` directory only

## Gotchas

- `TOKEN_SALT` is required for production but defaults to a random value in dev — never hardcode it in `.env` you commit
- `.env` is gitignored; `.env.example` is the template
- Redis is required even for local dev: `docker run -d -p 6379:6379 redis:7-alpine`
- Background cache warming runs on startup (every 3h by default) — if Redis is empty, first catalog request is slow
- User config is encoded in the URL token, not stored server-side — `TOKEN_SALT` must match between config page and addon
- The app warns at startup if `BASE_URL` is HTTP in non-localhost/non-debug mode
- `uvicorn` runs with `reload=True` in dev — use Docker for production
- Python 3.11 in Dockerfile, 3.9+ minimum per README
