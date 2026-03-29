"""
חיפוש מאחורי הקלעים ופספוסים ב-YouTube.
"""
import httpx
import os
import re
from typing import List, Dict, Any

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEO_URL = "https://www.googleapis.com/youtube/v3/videos"


async def find_extras(series_name: str) -> Dict[str, List[Dict[str, Any]]]:
    """מחזיר {"bts": [...], "bloopers": [...]} עם סרטוני YouTube."""
    async with httpx.AsyncClient() as client:
        bts, bloopers = await _search_both(client, series_name)
    return {"bts": bts, "bloopers": bloopers}


async def _search_both(client: httpx.AsyncClient, series_name: str):
    bts_queries = [
        f"{series_name} מאחורי הקלעים",
        f"{series_name} behind the scenes",
    ]
    bloopers_queries = [
        f"{series_name} פספוסים",
        f"{series_name} NG",
    ]

    bts = await _run_queries(client, bts_queries)
    bloopers = await _run_queries(client, bloopers_queries)
    return bts, bloopers


async def _run_queries(client: httpx.AsyncClient, queries: List[str]) -> List[Dict[str, Any]]:
    results = []
    seen_ids: set = set()

    for query in queries:
        if len(results) >= 4:
            break
        try:
            search_resp = await client.get(
                YOUTUBE_SEARCH_URL,
                params={
                    "key": YOUTUBE_API_KEY,
                    "q": query,
                    "type": "video",
                    "part": "snippet",
                    "maxResults": 8,
                },
                timeout=10,
            )
            data = search_resp.json()

            new_ids = [
                item["id"]["videoId"]
                for item in data.get("items", [])
                if item["id"].get("videoId") and item["id"]["videoId"] not in seen_ids
            ]
            seen_ids.update(new_ids)

            if not new_ids:
                continue

            details_resp = await client.get(
                YOUTUBE_VIDEO_URL,
                params={
                    "key": YOUTUBE_API_KEY,
                    "id": ",".join(new_ids),
                    "part": "contentDetails,statistics,snippet,status",
                },
                timeout=10,
            )
            details = details_resp.json()

            for item in details.get("items", []):
                vid_id = item["id"]
                snippet = item.get("snippet", {})
                content = item.get("contentDetails", {})
                stats = item.get("statistics", {})
                status = item.get("status", {})

                can_embed = status.get("embeddable", True)
                duration = _parse_duration(content.get("duration", "PT0S"))

                results.append({
                    "video_id": vid_id,
                    "url": f"https://www.youtube.com/watch?v={vid_id}",
                    "embed_url": f"https://www.youtube.com/embed/{vid_id}?autoplay=1" if can_embed else None,
                    "thumbnail_url": f"https://img.youtube.com/vi/{vid_id}/mqdefault.jpg",
                    "title": snippet.get("title", ""),
                    "channel": snippet.get("channelTitle", ""),
                    "duration_seconds": duration,
                    "view_count": int(stats.get("viewCount", 0)),
                    "can_embed": can_embed,
                })

                if len(results) >= 4:
                    break

        except Exception as e:
            print(f"Extras search error for '{query}': {e}")

    return results


async def _is_accessible(client: httpx.AsyncClient, video_id: str) -> bool:
    try:
        resp = await client.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=5,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _parse_duration(duration: str) -> int:
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds
