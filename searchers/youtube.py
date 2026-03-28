import httpx
import os
import re
from typing import List, Dict, Any

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEO_URL = "https://www.googleapis.com/youtube/v3/videos"


async def search_youtube(series_name: str, episode_num: int) -> List[Dict[str, Any]]:
    """Search YouTube for a specific Israeli series episode."""
    if not YOUTUBE_API_KEY:
        print("Warning: YOUTUBE_API_KEY not set")
        return []

    queries = [
        f"{series_name} פרק {episode_num} מלא",
        f"{series_name} פרק {episode_num} לצפייה ישירה",
    ]

    results = []
    seen_ids: set = set()

    async with httpx.AsyncClient() as client:
        for query in queries:
            try:
                search_resp = await client.get(
                    YOUTUBE_SEARCH_URL,
                    params={
                        "key": YOUTUBE_API_KEY,
                        "q": query,
                        "type": "video",
                        "part": "snippet",
                        "maxResults": 5,
                        "relevanceLanguage": "iw",
                        "videoDuration": "long",  # >20 minutes (full episodes)
                        "regionCode": "IL",
                    },
                    timeout=10,
                )
                data = search_resp.json()

                new_ids = []
                for item in data.get("items", []):
                    vid_id = item["id"].get("videoId")
                    if vid_id and vid_id not in seen_ids:
                        seen_ids.add(vid_id)
                        new_ids.append(vid_id)

                if not new_ids:
                    continue

                # Get full details: duration + stats
                details_resp = await client.get(
                    YOUTUBE_VIDEO_URL,
                    params={
                        "key": YOUTUBE_API_KEY,
                        "id": ",".join(new_ids),
                        "part": "contentDetails,statistics,snippet",
                    },
                    timeout=10,
                )
                details = details_resp.json()

                for item in details.get("items", []):
                    vid_id = item["id"]
                    snippet = item.get("snippet", {})
                    content = item.get("contentDetails", {})
                    stats = item.get("statistics", {})

                    duration = _parse_iso_duration(content.get("duration", "PT0S"))

                    results.append({
                        "source": "youtube",
                        "url": f"https://www.youtube.com/watch?v={vid_id}",
                        "embed_url": f"https://www.youtube.com/embed/{vid_id}",
                        "title": snippet.get("title", ""),
                        "description": snippet.get("description", "")[:300],
                        "channel": snippet.get("channelTitle", ""),
                        "duration_seconds": duration,
                        "view_count": int(stats.get("viewCount", 0)),
                        "upload_date": snippet.get("publishedAt", ""),
                        "domain": "youtube.com",
                        "can_embed": True,
                        "quality": "auto",  # YouTube auto-adjusts
                        "is_free": True,
                        "has_ads": True,
                    })

            except Exception as e:
                print(f"YouTube search error for query '{query}': {e}")

    return results


def _parse_iso_duration(duration: str) -> int:
    """Convert ISO 8601 duration string to seconds."""
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds
