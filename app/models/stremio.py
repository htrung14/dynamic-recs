"""
Stremio Protocol Models
Pydantic models for Stremio addon protocol
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class ManifestCatalog(BaseModel):
    """Catalog definition in manifest"""
    type: Literal["movie", "series"]
    id: str
    name: str
    extra: List[dict] = Field(default_factory=list)


class Manifest(BaseModel):
    """Stremio addon manifest"""
    id: str = "com.dynamic.recommendations"
    version: str = "1.0.0"
    name: str = "Dynamic Recommendations"
    description: str = "Personalized recommendations based on your watch history and loved items"
    
    resources: List[str] = ["catalog"]
    types: List[str] = ["movie", "series"]
    idPrefixes: List[str] = ["tt"]
    
    catalogs: List[ManifestCatalog]
    
    behaviorHints: dict = {
        "configurable": True,
        "configurationRequired": False,
        "adult": False,
        "p2p": False
    }


class MetaPoster(BaseModel):
    """Catalog item (poster) metadata"""
    id: str  # IMDB ID
    type: Literal["movie", "series"]
    name: str
    poster: Optional[str] = None
    posterShape: str = "poster"
    background: Optional[str] = None
    logo: Optional[str] = None
    description: Optional[str] = None
    releaseInfo: Optional[str] = None
    imdbRating: Optional[str] = None


class CatalogResponse(BaseModel):
    """Catalog endpoint response"""
    metas: List[MetaPoster]
