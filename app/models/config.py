"""
User Configuration Models
Pydantic models for user-specific configuration
"""
from pydantic import BaseModel, Field, model_validator
from typing import Optional


class UserConfig(BaseModel):
    """User configuration embedded in addon URL"""
    stremio_auth_key: Optional[str] = Field(None, description="Stremio authentication key")
    stremio_username_enc: Optional[str] = Field(None, description="Encrypted Stremio username/email")
    stremio_password_enc: Optional[str] = Field(None, description="Encrypted Stremio password")
    tmdb_api_key: str = Field(..., description="TMDB API key (required)")
    mdblist_api_key: str = Field(..., description="MDBList API key (required)")
    num_rows: int = Field(5, ge=1, le=20, description="Number of recommendation rows")
    min_rating: float = Field(6.0, ge=0.0, le=10.0, description="Minimum rating filter")
    use_loved_items: bool = Field(True, description="Prioritize loved items over watch history")
    include_movies: bool = Field(True, description="Include movie recommendations")
    include_series: bool = Field(True, description="Include series recommendations")
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
