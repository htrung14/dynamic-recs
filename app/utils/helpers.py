"""
Helper Utilities
General purpose utility functions
"""
from typing import List, Dict, Any
from collections import Counter


def deduplicate_recommendations(
    recommendations: List[Dict[str, Any]],
    key: str = "id"
) -> List[Dict[str, Any]]:
    """
    Remove duplicate items from recommendations list
    
    Args:
        recommendations: List of recommendation items
        key: Key to use for deduplication
        
    Returns:
        Deduplicated list maintaining original order
    """
    seen = set()
    result = []
    
    for item in recommendations:
        item_key = item.get(key)
        if item_key and item_key not in seen:
            seen.add(item_key)
            result.append(item)
    
    return result


def score_by_frequency(
    items: List[str],
    max_score: float = 1.0
) -> Dict[str, float]:
    """
    Score items based on frequency of occurrence
    
    Args:
        items: List of item identifiers
        max_score: Maximum score to assign
        
    Returns:
        Dictionary mapping item IDs to frequency scores
    """
    if not items:
        return {}
    
    counter = Counter(items)
    max_count = max(counter.values())
    
    return {
        item: (count / max_count) * max_score
        for item, count in counter.items()
    }


def merge_ratings(
    imdb_rating: float = 0.0,
    tmdb_rating: float = 0.0,
    mdblist_rating: float = 0.0
) -> float:
    """
    Merge multiple ratings into a single score
    
    Args:
        imdb_rating: IMDB rating (0-10)
        tmdb_rating: TMDB rating (0-10)
        mdblist_rating: MDBList aggregate rating (0-10)
        
    Returns:
        Weighted average rating
    """
    ratings = []
    weights = []
    
    if imdb_rating > 0:
        ratings.append(imdb_rating)
        weights.append(0.4)
    
    if tmdb_rating > 0:
        ratings.append(tmdb_rating)
        weights.append(0.3)
    
    if mdblist_rating > 0:
        ratings.append(mdblist_rating)
        weights.append(0.3)
    
    if not ratings:
        return 0.0
    
    total_weight = sum(weights)
    weighted_sum = sum(r * w for r, w in zip(ratings, weights))
    
    return weighted_sum / total_weight


def sanitize_title(title: str) -> str:
    """
    Sanitize title for safe display
    
    Args:
        title: Original title
        
    Returns:
        Sanitized title
    """
    if not title:
        return ""
    
    return title.strip()[:200]  # Limit length
