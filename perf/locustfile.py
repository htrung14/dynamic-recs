"""Locust load script for Stremio addon.
Usage:
  STREMIO_TOKEN="<token>" locust -f perf/locustfile.py --host http://localhost:8000
"""
import os
from locust import HttpUser, task, between

TOKEN = os.getenv("STREMIO_TOKEN", "")
ROWS = int(os.getenv("STREMIO_ROWS", "5"))


class StremioUser(HttpUser):
    wait_time = between(0.2, 1.0)

    def on_start(self):
        if not TOKEN:
            raise RuntimeError("Set STREMIO_TOKEN env var before running locust")

    @task(1)
    def manifest(self):
        self.client.get(f"/{TOKEN}/manifest.json")

    @task(3)
    def movie_catalog(self):
        row = 0
        self.client.get(f"/{TOKEN}/catalog/movie/dynamic_movies_{row}.json")

    @task(3)
    def series_catalog(self):
        row = 0
        self.client.get(f"/{TOKEN}/catalog/series/dynamic_series_{row}.json")

    @task(1)
    def sweep_rows(self):
        # Hit multiple rows to exercise cache spread
        for row in range(min(ROWS, 5)):
            self.client.get(f"/{TOKEN}/catalog/movie/dynamic_movies_{row}.json")
            self.client.get(f"/{TOKEN}/catalog/series/dynamic_series_{row}.json")
