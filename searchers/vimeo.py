import httpx
import os
import re
from typing import List, Dict, Any

SERPER_API_KEY = os.getenv("SERPER_API_KEY")


async def search_vimeo(series_name: str, episode_num: int, season_num: int = 1) -> List[Dict[str, Any]]:
    """Search Vimeo for Israeli series episodes via Google (Serper) + Vimeo oEmbed."""
    if not SERPER_API_KEY:
        return []

    queries = [
        f'site:vimeo.com "{series_name}" עונה {season_num} פרק {episode_num}',
        f'site:vimeo.com "{series_name}" פרק {episode_num}',
    ]

    results = []
    seen_ids: set = set()

    async with httpx.AsyncClient() as client:
        for query in queries:
            try:
                resp = await client.post(
                    "https://google.serper.dev/search",
                    json={"q": query, "gl": "il", "hl": "iw", "num": 5},
                    headers={"X-API-KEY": SERPER_API_KEY},
                    timeout=10,
                )
                data = resp.json()

                for item in data.get("organic", []):
                    url = item.get("link", "")
                    if "vimeo.com" not in url:
                        continue

                    video_id = _extract_vimeo_id(url)
                    if not video_id or video_id in seen_ids:
                        continue
                    seen_ids.add(video_id)

                    # Get video details via Vimeo oEmbed (no API key needed)
                    meta = await _get_vimeo_meta(client, video_id)
                    if not meta:
                        continue

                    results.append({
                        "source": "web",
                        "url": f"https://vimeo.com/{video_id}",
                        "embed_url": f"https://player.vimeo.com/video/{video_id}",
                        "title": meta.get("title") or item.get("title", ""),
                        "description": item.get("snippet", ""),
                        "channel": meta.get("author_name", ""),
                        "duration_seconds": meta.get("duration"),
                        "view_count": None,
                        "upload_date": None,
                        "domain": "vimeo.com",
                        "can_embed": True,
                        "is_official": False,
                        "has_ads": False,
                        "quality": "1080p",
                        "is_free": True,
                    })

            except Exception as e:
                print(f"Vimeo search error: {e}")

    return results


async def _get_vimeo_meta(client: httpx.AsyncClient, video_id: str) -> Dict:
    """Fetch video metadata via Vimeo oEmbed API."""
    try:
        resp = await client.get(
            "https://vimeo.com/api/oembed.json",
            params={"url": f"https://vimeo.com/{video_id}"},
            timeout=6,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}


def _extract_vimeo_id(url: str) -> str:
    m = re.search(r"vimeo\.com/(\d+)", url)
    return m.group(1) if m else ""
