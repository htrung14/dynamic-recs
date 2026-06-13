"""
User Configuration Models
Pydantic models for user-specific configuration
"""
import hashlib
from pydantic import BaseModel, Field, model_validator
from typing import Optional


class UserConfig(BaseModel):
    """User configuration embedded in addon URL"""
    stremio_auth_key: Optional[str] = Field(None, description="Stremio authentication key")
    stremio_username_enc: Optional[str] = Field(None, description="Encrypted Stremio username/email")
    stremio_password_enc: Optional[str] = Field(None, description="Encrypted Stremio password")
    tmdb_api_key: str = Field(..., description="TMDB API key (required)")
    num_rows: int = Field(5, ge=1, le=20, description="Number of recommendation rows")
    min_rating: float = Field(6.0, ge=0.0, le=10.0, description="Minimum rating filter")
    use_loved_items: bool = Field(True, description="Prioritize loved items over watch history")
    include_movies: bool = Field(True, description="Include movie recommendations")
    include_series: bool = Field(True, description="Include series recommendations")
    exclude_anime: bool = Field(True, description="Exclude anime content from recommendations")
    exclude_indian: bool = Field(True, description="Exclude Indian/Bollywood content from recommendations")
    stremio_loved_token: Optional[str] = Field(
        None,
        description="Token for official Stremio loved addon; falls back to server default if unset",
    )

    @model_validator(mode="after")
    def validate_auth_source(self):
        if not self.stremio_auth_key and not (
            self.stremio_username_enc and self.stremio_password_enc
        ):
            raise ValueError("Provide either stremio_auth_key or username/password credentials")
        return self

    @staticmethod
    def _short_hash(parts: tuple) -> str:
        """Stable short hash for cache-key fingerprints."""
        raw = "|".join(str(p) for p in parts)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]

    def cache_fingerprint(self) -> str:
        """Fingerprint of fields that change the ranked recommendation output.

        Folded into the recs cache key so toggling any of these takes effect
        immediately instead of being masked by a stale cache entry.
        """
        return self._short_hash((
            self.min_rating,
            self.exclude_anime,
            self.exclude_indian,
            self.include_movies,
            self.include_series,
        ))

    def taste_fingerprint(self) -> str:
        """Fingerprint of fields that change the taste-profile sample.

        Only ``exclude_indian`` filters which watched items feed the profile;
        rating/anime gates are applied later, not during profile construction.
        """
        return self._short_hash((self.exclude_indian,))
