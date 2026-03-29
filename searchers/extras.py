"""
חיפוש מאחורי הקלעים ופספוסים ב-YouTube.
"""
import httpx
import os
from typing import List, Dict, Any

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


async def find_extras(series_name: str) -> Dict[str, List[Dict[str, Any]]]:
    """מחזיר {"bts": [...], "bloopers": [...]} עם סרטוני YouTube."""
    if not YOUTUBE_API_KEY:
        print("Warning: YOUTUBE_API_KEY not set")
        return {"bts": [], "bloopers": []}

    async with httpx.AsyncClient() as client:
        bts = await _search(client, f"{series_name} מאחורי הקלעים")
        if not bts:
            bts = await _search(client, f"{series_name} behind the scenes")

        bloopers = await _search(client, f"{series_name} פספוסים")
        if not bloopers:
            bloopers = await _search(client, f"{series_name} NG")

    print(f"Extras for '{series_name}': {len(bts)} bts, {len(bloopers)} bloopers")
    return {"bts": bts, "bloopers": bloopers}


async def _search(client: httpx.AsyncClient, query: str) -> List[Dict[str, Any]]:
    try:
        resp = await client.get(
            YOUTUBE_SEARCH_URL,
            params={
                "key": YOUTUBE_API_KEY,
                "q": query,
                "type": "video",
                "part": "snippet",
                "maxResults": 4,
            },
            timeout=10,
        )
        data = resp.json()
        print(f"YouTube search '{query}': {len(data.get('items', []))} results, error={data.get('error')}")

        results = []
        for item in data.get("items", []):
            vid_id = item.get("id", {}).get("videoId")
            if not vid_id:
                continue
            snippet = item.get("snippet", {})
            results.append({
                "video_id": vid_id,
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "embed_url": f"https://www.youtube.com/embed/{vid_id}?autoplay=1",
                "thumbnail_url": snippet.get("thumbnails", {}).get("medium", {}).get("url", f"https://img.youtube.com/vi/{vid_id}/mqdefault.jpg"),
                "title": snippet.get("title", ""),
                "channel": snippet.get("channelTitle", ""),
                "duration_seconds": 0,
                "can_embed": True,
            })
        return results

    except Exception as e:
        print(f"Extras search error for '{query}': {e}")
        return []
