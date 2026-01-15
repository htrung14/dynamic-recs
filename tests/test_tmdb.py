"""
Tests for TMDB client, including niche recommendations
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.tmdb import TMDBClient
from app.core.config import settings


@pytest.fixture
def tmdb_client():
    """Create TMDB client for testing"""
    client = TMDBClient(api_key="test_api_key_12345678")
    yield client


@pytest.fixture
def mock_keywords_response():
    """Mock keywords response from TMDB API"""
    return {
        "keywords": [
            {"id": 1721, "name": "fight"},
            {"id": 4344, "name": "support group"},
            {"id": 818, "name": "dystopia"},
            {"id": 10364, "name": "male friendship"},
            {"id": 4565, "name": "insomnia"}
        ]
    }


@pytest.fixture
def mock_discover_response():
    """Mock discover/movie response from TMDB API"""
    return {
        "page": 1,
        "results": [
            {
                "id": 1891,
                "title": "The Empire Strikes Back",
                "vote_average": 8.4,
                "vote_count": 4500,
                "release_date": "1980-05-21",
                "poster_path": "/path1.jpg"
            },
            {
                "id": 278,
                "title": "The Shawshank Redemption",
                "vote_average": 8.7,
                "vote_count": 3200,
                "release_date": "1994-09-23",
                "poster_path": "/path2.jpg"
            },
            {
                "id": 13,
                "title": "Forrest Gump",
                "vote_average": 8.5,
                "vote_count": 2800,
                "release_date": "1994-07-06",
                "poster_path": "/path3.jpg"
            }
        ],
        "total_pages": 5,
        "total_results": 87
    }


@pytest.fixture
def mock_tv_keywords_response():
    """Mock TV keywords response (uses 'results' key instead of 'keywords')"""
    return {
        "results": [
            {"id": 818, "name": "based on novel"},
            {"id": 4344, "name": "dystopia"},
            {"id": 1721, "name": "survival"}
        ]
    }


class TestTMDBKeywords:
    """Test keyword fetching functionality"""
    
    @pytest.mark.asyncio
    async def test_get_keywords_for_movie(self, tmdb_client, mock_keywords_response):
        """Test fetching keywords for a movie"""
        with patch.object(tmdb_client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_keywords_response
            
            keywords = await tmdb_client.get_keywords(550, "movie")
            
            assert len(keywords) == 5
            assert keywords[0]["name"] == "fight"
            assert keywords[0]["id"] == 1721
            mock_request.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_keywords_for_tv(self, tmdb_client, mock_tv_keywords_response):
        """Test fetching keywords for TV series (uses 'results' key)"""
        with patch.object(tmdb_client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_tv_keywords_response
            
            keywords = await tmdb_client.get_keywords(1396, "tv")
            
            assert len(keywords) == 3
            assert keywords[0]["name"] == "based on novel"
            mock_request.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_keywords_none_found(self, tmdb_client):
        """Test when no keywords are found"""
        with patch.object(tmdb_client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"keywords": []}
            
            keywords = await tmdb_client.get_keywords(999, "movie")
            
            assert keywords == []
    
    @pytest.mark.asyncio
    async def test_get_keywords_api_error(self, tmdb_client):
        """Test keyword fetch when API returns None"""
        with patch.object(tmdb_client, '_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = None
            
            keywords = await tmdb_client.get_keywords(550, "movie")
            
            assert keywords == []


class TestNicheRecommendations:
    """Test niche recommendation functionality"""
    
    @pytest.mark.asyncio
    async def test_get_niche_recommendations_success(
        self, 
        tmdb_client, 
        mock_keywords_response,
        mock_discover_response
    ):
        """Test successful niche recommendations with keywords"""
        with patch.object(tmdb_client, 'get_keywords', new_callable=AsyncMock) as mock_keywords:
            mock_keywords.return_value = mock_keywords_response["keywords"]
            
            with patch.object(tmdb_client, '_request', new_callable=AsyncMock) as mock_request:
                mock_request.return_value = mock_discover_response
                
                results = await tmdb_client.get_niche_recommendations(550, "movie")
                
                # Verify results
                assert len(results) == 3
                assert all(item.get("media_type") == "movie" for item in results)
                
                # Verify discover API was called with correct filters
                mock_request.assert_called_once()
                call_args = mock_request.call_args
                params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params")
                
                assert params["vote_count.gte"] == 50
                assert params["vote_count.lte"] == 5000
                assert params["vote_average.gte"] == 7.0
                assert params["sort_by"] == "vote_average.desc"
                assert "with_keywords" in params
                assert "|" in params["with_keywords"]  # OR logic
    
    @pytest.mark.asyncio
    async def test_niche_recommendations_top_5_keywords(
        self,
        tmdb_client,
        mock_keywords_response
    ):
        """Test that only top 5 keywords are used"""
        keywords = mock_keywords_response["keywords"] + [
            {"id": 9999, "name": "extra1"},
            {"id": 9998, "name": "extra2"}
        ]
        
        with patch.object(tmdb_client, 'get_keywords', new_callable=AsyncMock) as mock_keywords:
            mock_keywords.return_value = keywords
            
            with patch.object(tmdb_client, '_request', new_callable=AsyncMock) as mock_request:
                mock_request.return_value = {"results": []}
                
                await tmdb_client.get_niche_recommendations(550, "movie")
                
                call_args = mock_request.call_args
                params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params")
                keyword_ids = params["with_keywords"].split("|")
                
                # Should only use first 5 keywords
                assert len(keyword_ids) == 5
                assert "9999" not in keyword_ids
                assert "9998" not in keyword_ids
    
    @pytest.mark.asyncio
    async def test_niche_recommendations_no_keywords_fallback(self, tmdb_client):
        """Test fallback to similar endpoint when no keywords found"""
        with patch.object(tmdb_client, 'get_keywords', new_callable=AsyncMock) as mock_keywords:
            mock_keywords.return_value = []
            
            with patch.object(tmdb_client, '_request', new_callable=AsyncMock) as mock_request:
                mock_request.return_value = {
                    "results": [
                        {"id": 100, "title": "Similar Movie"}
                    ]
                }
                
                results = await tmdb_client.get_niche_recommendations(550, "movie")
                
                # Should call similar endpoint instead of discover
                call_args = mock_request.call_args
                endpoint = call_args[0][0]
                assert "/similar" in endpoint
                assert len(results) == 1
                assert results[0]["media_type"] == "movie"
    
    @pytest.mark.asyncio
    async def test_niche_recommendations_tv_series(
        self,
        tmdb_client,
        mock_tv_keywords_response
    ):
        """Test niche recommendations for TV series"""
        with patch.object(tmdb_client, 'get_keywords', new_callable=AsyncMock) as mock_keywords:
            mock_keywords.return_value = mock_tv_keywords_response["results"]
            
            with patch.object(tmdb_client, '_request', new_callable=AsyncMock) as mock_request:
                mock_request.return_value = {
                    "results": [
                        {"id": 200, "name": "Similar Series", "vote_average": 8.0}
                    ]
                }
                
                results = await tmdb_client.get_niche_recommendations(1396, "tv")
                
                # Verify discover/tv endpoint was used
                call_args = mock_request.call_args
                endpoint = call_args[0][0]
                assert endpoint == "/discover/tv"
                
                assert len(results) == 1
                assert results[0]["media_type"] == "tv"


class TestGetRecommendations:
    """Test that get_recommendations now uses niche method"""
    
    @pytest.mark.asyncio
    async def test_get_recommendations_redirects_to_niche(self, tmdb_client):
        """Test that get_recommendations now calls get_niche_recommendations"""
        with patch.object(
            tmdb_client, 
            'get_niche_recommendations', 
            new_callable=AsyncMock
        ) as mock_niche:
            mock_niche.return_value = [{"id": 1, "title": "Test"}]
            
            results = await tmdb_client.get_recommendations(550, "movie", page=1)
            
            # Verify it calls the niche method
            mock_niche.assert_called_once_with(550, "movie", 1)
            assert len(results) == 1


class TestNicheFiltersPreventBlockbusters:
    """Test that filters properly exclude blockbusters"""
    
    @pytest.mark.asyncio
    async def test_vote_count_filters(self, tmdb_client):
        """Test vote count filters are correctly applied"""
        with patch.object(tmdb_client, 'get_keywords', new_callable=AsyncMock) as mock_keywords:
            mock_keywords.return_value = [{"id": 1, "name": "test"}]
            
            with patch.object(tmdb_client, '_request', new_callable=AsyncMock) as mock_request:
                mock_request.return_value = {"results": []}
                
                await tmdb_client.get_niche_recommendations(550, "movie")
                
                call_args = mock_request.call_args
                params = call_args[0][1]
                
                # These filters are critical for avoiding blockbusters
                assert params["vote_count.lte"] == 5000, "Should filter out movies with >5000 votes"
                assert params["vote_count.gte"] == 50, "Should filter out garbage data"
                assert params["vote_average.gte"] == 7.0, "Should ensure quality"
    
    @pytest.mark.asyncio
    async def test_sorting_by_rating(self, tmdb_client):
        """Test that results are sorted by rating (not popularity)"""
        with patch.object(tmdb_client, 'get_keywords', new_callable=AsyncMock) as mock_keywords:
            mock_keywords.return_value = [{"id": 1, "name": "test"}]
            
            with patch.object(tmdb_client, '_request', new_callable=AsyncMock) as mock_request:
                mock_request.return_value = {"results": []}
                
                await tmdb_client.get_niche_recommendations(550, "movie")
                
                call_args = mock_request.call_args
                params = call_args[0][1]
                
                # Should sort by rating, not popularity
                assert params["sort_by"] == "vote_average.desc"
