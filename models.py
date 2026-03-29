from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime


class VideoResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: str  # "youtube", "web", "telegram"
    url: str
    embed_url: Optional[str] = None
    title: str = ""
    description: str = ""
    quality: Optional[str] = None  # "1080p", "720p", "480p", "unknown"
    duration_seconds: Optional[int] = None
    has_hebrew_subtitles: bool = False
    is_free: bool = True
    has_ads: Optional[bool] = None
    is_official: bool = False
    view_count: Optional[int] = None
    upload_date: Optional[str] = None
    channel: Optional[str] = None
    domain: str = ""
    can_embed: bool = False
    raw_score: float = 0.0
    history_bonus: float = 0.0
    final_score: float = 0.0


class SearchResponse(BaseModel):
    series: str
    episode: int
    results: List[VideoResult]
    best: Optional[VideoResult] = None
    cached: bool = False
    searched_at: datetime


class FeedbackRequest(BaseModel):
    series: str
    episode: int
    season: int = 1
    url: str
    domain: str
    played_successfully: bool
    quality_rating: Optional[int] = None  # 1-10
    watch_duration_seconds: Optional[int] = None  # כמה שניות נצפה


class WatchProgressRequest(BaseModel):
    series: str
    episode: int
    season: int = 1
    url: str
    position_seconds: int  # מיקום נוכחי בסרטון
    duration_seconds: Optional[int] = None  # אורך כולל


class WatchProgressResponse(BaseModel):
    series: str
    episode: int
    season: int
    url: str
    position_seconds: int
    duration_seconds: Optional[int] = None
    last_watched: datetime


class AdminSourceStat(BaseModel):
    domain: str
    series_name: Optional[str] = None
    total_uses: int
    successful_plays: int
    failed_plays: int
    avg_quality_score: float
    success_rate: float
    last_used: Optional[str] = None
