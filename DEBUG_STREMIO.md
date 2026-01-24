# Debugging Stremio Recommendations

## Logging Status ✅

All critical paths are logged. Your changes include:

### 1. Niche Discovery Logs (tmdb.py)

```python
logger.info(f"Niche discovery for {media_type} {tmdb_id}: found {len(results)} items using keywords {keyword_filter}")
logger.debug(f"Niche discovery for {media_type} {tmdb_id}: fetched keywords={keywords}")
logger.warning(f"Niche discovery for {media_type} {tmdb_id}: no keywords found, using similar endpoint")
```

### 2. MDBList Retry Logs (mdblist.py)

```python
logger.info(f"MDBList 503, retrying... ({retry_count}/{max_retries})")
logger.warning(f"MDBList unavailable after {max_retries} retries, skipping enrichment")
```

### 3. Catalog Generation Logs (catalog.py)

```python
logger.info(f"Catalog {id} returned {len(metas)} items")
logger.warning(f"Skipping item without IMDB ID: {item.get('title', 'unknown')}")
logger.error(f"Error converting catalog {id}: {exc_info=True}")
```

### 4. Recommendation Pipeline Logs (recommendations.py)

```python
logger.info(f"Using {len(seeds)} loved items as seeds")
logger.info(f"Using {len(seeds)} recently watched items as seeds (after merge)")
logger.warning("MDBList unavailable, using shorter cache TTL")
```

---

## How to Diagnose Stremio Issues

### Step 1: Check Backend Logs

Look for these log patterns in your deployment logs:

```bash
# Check if niche discovery is working
grep "Niche discovery" logs.txt

# Expected: "Niche discovery for movie 603: found 20 items using keywords science fiction|dystopia|future"

# Check if MDBList is failing
grep "MDBList" logs.txt

# Expected (if failing): "MDBList unavailable after 2 retries, skipping enrichment"

# Check catalog generation
grep "Catalog.*returned" logs.txt

# Expected: "Catalog dynamic_movies_0 returned 45 items"
```

### Step 2: Test Catalog Endpoint Directly

```bash
# Replace {YOUR_TOKEN} with your actual token
curl https://recs.ediciones.nyc/{YOUR_TOKEN}/catalog/movie/dynamic_movies_0.json

# Should return JSON with "metas" array
# Example:
# {
#   "metas": [
#     {
#       "id": "tt0111161",
#       "type": "movie",
#       "name": "The Shawshank Redemption",
#       "poster": "https://...",
#       "posterShape": "poster"
#     }
#   ]
# }
```

### Step 3: Check Manifest Endpoint

```bash
# Verify catalogs are registered
curl https://recs.ediciones.nyc/{YOUR_TOKEN}/manifest.json

# Should show your catalogs:
# {
#   "id": "community.dynamic-recs",
#   "catalogs": [
#     {"type": "movie", "id": "dynamic_movies_0", "name": "🎬 Because you watched The Matrix"},
#     {"type": "movie", "id": "dynamic_movies_1", "name": "🎬 Recommended Movies #2"}
#   ]
# }
```

---

## Common Root Causes & Solutions

### Issue 1: Empty Catalog (No Recommendations Show Up)

**Root Cause**: IMDB IDs missing from niche discoveries

**Check**: Look for log: `"Skipping item without IMDB ID"`

**Solution**: The `_attach_external_ids()` method should enrich items. Verify logs show:

```
Catalog dynamic_movies_0 returned 45 items  # Should be > 0
```

**Debug Command**:

```bash
# Check if enrichment is working
grep "_attach_external_ids\|Skipping item without IMDB" logs.txt
```

---

### Issue 2: Stremio Shows Old/Cached Results

**Root Cause**: Stremio client caching or manifest not refreshed

**Solution**:

1. **Reinstall addon** in Stremio (remove and re-add)
2. **Clear Stremio cache**:
   - Windows: `%APPDATA%\stremio-server\stremio-cache`
   - Mac: `~/Library/Application Support/stremio-server/stremio-cache`
   - Linux: `~/.stremio-server/stremio-cache`

**Backend Fix**: Manifest already has no-cache headers:

```python
response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
```

---

### Issue 3: MDBList Failures Causing Empty Results

**Root Cause**: MDBList 503 errors prevent enrichment, but items should still work

**Check**: Look for: `"MDBList unavailable after 2 retries, skipping enrichment"`

**Expected Behavior**: Recommendations should still appear, just without MDBList ratings

**Verify**:

```bash
# Check if enrichment failures are graceful
grep "mdblist_available\|using shorter cache TTL" logs.txt

# Should see: "MDBList unavailable, using shorter cache TTL"
# Catalog should still return items (using TMDB ratings only)
```

---

### Issue 4: Niche Filter Too Strict (No Results)

**Root Cause**: `vote_count.lte=5000` + `vote_count.gte=50` + `vote_average.gte=7.0` filters out all results for some seeds

**Check**: Look for: `"Niche discovery for movie X: found 0 items"`

**Solution**: If many seeds return 0 items, you may need to relax filters:

```python
# In app/services/tmdb.py, line ~175
params = {
    "vote_count.gte": 20,        # Lower minimum (was 50)
    "vote_count.lte": 10000,     # Raise maximum (was 5000)
    "vote_average.gte": 6.5,     # Lower rating threshold (was 7.0)
}
```

**Test**: Run demo script to verify results:

```bash
python demo_niche_recs.py
```

---

### Issue 5: Keywords Not Working

**Root Cause**: TMDB keywords endpoint returns empty array for some movies

**Check**: Look for: `"no keywords found, using similar endpoint"`

**Expected Behavior**: Should fallback to `/similar` endpoint automatically

**Verify Fallback**:

```bash
grep "no keywords found" logs.txt
# If many movies have no keywords, similarity endpoint will be used
```

---

## Quick Diagnostic Checklist

Run through these checks in order:

- [ ] **Backend is running**: `curl https://recs.ediciones.nyc/health` returns `{"status":"ok"}`
- [ ] **Manifest loads**: `curl https://recs.ediciones.nyc/{TOKEN}/manifest.json` returns catalogs
- [ ] **Catalog has items**: `curl https://recs.ediciones.nyc/{TOKEN}/catalog/movie/dynamic_movies_0.json` returns non-empty `metas` array
- [ ] **Niche discovery logs present**: `grep "Niche discovery" logs.txt` shows results > 0
- [ ] **IMDB IDs attached**: `grep "Skipping item without IMDB" logs.txt` shows minimal skips (< 10%)
- [ ] **MDBList handling graceful**: `grep "MDBList unavailable" logs.txt` confirms fallback works
- [ ] **Stremio addon reinstalled**: Remove and re-add addon in Stremio to clear cache

---

## Recommended Next Steps

1. **Get fresh logs from production**:

   ```bash
   # SSH into your server or check your deployment platform
   # For Docker:
   docker-compose logs addon --tail=200

   # For Railway/Fly.io/etc:
   # Use platform-specific log viewer
   ```

2. **Test catalog endpoint directly**:

   ```bash
   curl -v https://recs.ediciones.nyc/{YOUR_TOKEN}/catalog/movie/dynamic_movies_0.json | jq '.metas | length'
   ```

   Should return a number > 0

3. **Check for IMDB ID issues**:

   ```bash
   curl https://recs.ediciones.nyc/{YOUR_TOKEN}/catalog/movie/dynamic_movies_0.json | jq '.metas[0]'
   ```

   Should show valid IMDB ID format: `"id": "tt0133093"`

4. **Verify in Stremio**:
   - Open Stremio
   - Remove addon if already installed
   - Re-add addon using configure URL
   - Navigate to Discover > Movies
   - Look for "🎬 Because you watched..." catalogs

---

## Example Debug Session

```bash
# 1. Check backend health
$ curl https://recs.ediciones.nyc/health
{"status":"ok","redis":"connected"}

# 2. Get manifest
$ curl https://recs.ediciones.nyc/{TOKEN}/manifest.json | jq '.catalogs | length'
10  # Good: 10 catalogs registered

# 3. Test first catalog
$ curl https://recs.ediciones.nyc/{TOKEN}/catalog/movie/dynamic_movies_0.json | jq '.metas | length'
45  # Good: 45 recommendations returned

# 4. Check first item structure
$ curl https://recs.ediciones.nyc/{TOKEN}/catalog/movie/dynamic_movies_0.json | jq '.metas[0]'
{
  "id": "tt0068646",
  "type": "movie",
  "name": "The Godfather",
  "poster": "https://image.tmdb.org/t/p/w500/3bhkrj58Vtu7enYsRolD1fZdja1.jpg",
  "posterShape": "poster",
  "description": "Spanning the years 1945 to 1955..."
}

# If all above work, issue is Stremio client cache
# Solution: Reinstall addon in Stremio
```

---

## Contact/Support

If you've verified all logs and API endpoints work but Stremio still doesn't show recommendations:

1. Check Stremio client logs:

   - Windows: `%APPDATA%\stremio\server-logs`
   - Mac: `~/Library/Logs/Stremio`
   - Linux: `~/.stremio-server/server-logs`

2. Look for addon request errors in Stremio logs

3. Try addon in Stremio Web (https://web.stremio.com) to isolate desktop client issues
