import httpx
from typing import List, Dict, Any

DAILYMOTION_API = "https://api.dailymotion.com/videos"


async def search_dailymotion(series_name: str, episode_num: int, season_num: int = 1) -> List[Dict[str, Any]]:
    """Search Dailymotion for Israeli series episodes using their public API."""
    queries = [
        f"{series_name} עונה {season_num} פרק {episode_num}",
        f"{series_name} פרק {episode_num}",
    ]

    results = []
    seen_ids: set = set()

    async with httpx.AsyncClient() as client:
        for query in queries:
            try:
                resp = await client.get(
                    DAILYMOTION_API,
                    params={
                        "search": query,
                        "fields": "id,title,description,duration,views_total,created_time,embed_url,url,allow_embed",
                        "limit": 5,
                        "language": "he",
                        "sort": "relevance",
                    },
                    timeout=10,
                )
                data = resp.json()

                for item in data.get("list", []):
                    vid_id = item.get("id")
                    if not vid_id or vid_id in seen_ids:
                        continue

                    # Skip non-embeddable videos
                    if not item.get("allow_embed", True):
                        continue

                    seen_ids.add(vid_id)

                    results.append({
                        "source": "web",
                        "url": item.get("url") or f"https://www.dailymotion.com/video/{vid_id}",
                        "embed_url": item.get("embed_url") or f"https://www.dailymotion.com/embed/video/{vid_id}",
                        "title": item.get("title", ""),
                        "description": (item.get("description") or "")[:300],
                        "channel": "Dailymotion",
                        "duration_seconds": item.get("duration"),
                        "view_count": item.get("views_total", 0),
                        "upload_date": str(item.get("created_time", "")),
                        "domain": "dailymotion.com",
                        "can_embed": True,
                        "is_official": False,
                        "has_ads": True,
                        "quality": "720p",
                        "is_free": True,
                    })

            except Exception as e:
                print(f"Dailymotion search error for query '{query}': {e}")

    return results
