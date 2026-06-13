"""
Tests for StremioClient._progress_from_state — the pure helper that
derives watch progress from a Stremio libraryItem ``state`` dict.

All tests are pure unit tests (no network, no mocks needed).
"""
import pytest
from app.services.stremio import StremioClient


class TestProgressFromState:
    """Unit tests for StremioClient._progress_from_state."""

    def test_ratio_when_duration_and_offset_present(self):
        state = {"duration": 4000, "timeOffset": 2000}
        assert StremioClient._progress_from_state(state) == pytest.approx(0.5)

    def test_ratio_capped_at_one(self):
        state = {"duration": 1000, "timeOffset": 9999}
        assert StremioClient._progress_from_state(state) == pytest.approx(1.0)

    def test_watched_via_flagged_watched(self):
        state = {
            "duration": 4284000,
            "timeOffset": 0,
            "timesWatched": 2,
            "flaggedWatched": 1,
            "lastWatched": "2026-01-28T03:49:49Z",
        }
        assert StremioClient._progress_from_state(state) == pytest.approx(1.0)

    def test_watched_via_times_watched_only(self):
        state = {"timesWatched": 1}
        assert StremioClient._progress_from_state(state) == pytest.approx(1.0)

    def test_watched_via_last_watched_only(self):
        state = {"lastWatched": "2026-01-01T00:00:00Z"}
        assert StremioClient._progress_from_state(state) == pytest.approx(1.0)

    def test_empty_state_returns_none(self):
        assert StremioClient._progress_from_state({}) is None

    def test_all_zeros_returns_none(self):
        state = {"duration": 0, "timeOffset": 0, "timesWatched": 0}
        assert StremioClient._progress_from_state(state) is None

    def test_watched_empty_string_not_truthy(self):
        """The 'watched' field is an empty string in real data — must not
        be confused with a boolean True."""
        state = {"watched": "", "duration": 0, "timeOffset": 0}
        assert StremioClient._progress_from_state(state) is None

    def test_ratio_partial_progress(self):
        state = {"duration": 10000, "timeOffset": 3500}
        assert StremioClient._progress_from_state(state) == pytest.approx(0.35)
