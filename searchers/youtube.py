"""
חיפוש פרקים ב-YouTube.
מנסה קודם YouTube Data API, ואם quota נגמר — עובר ל-yt-dlp.
"""
import asyncio
import httpx
import os
import re
from typing import List, Dict, Any

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEO_URL = "https://www.googleapis.com/youtube/v3/videos"


async def search_youtube(series_name: str, episode_num: int, season_num: int = 1) -> List[Dict[str, Any]]:
    # נסה קודם YouTube API
    if YOUTUBE_API_KEY:
        try:
            results = await _search_via_api(series_name, episode_num, season_num)
            if results:
                print(f"YouTube API: {len(results)} results")
                return results
        except Exception as e:
            print(f"YouTube API failed ({e}), falling back to yt-dlp")

    # fallback — yt-dlp
    print("YouTube: using yt-dlp fallback")
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _search_ytdlp, series_name, episode_num, season_num)


# ── YouTube Data API ──────────────────────────────────────────────────────────

async def _search_via_api(series_name: str, episode_num: int, season_num: int) -> List[Dict[str, Any]]:
    queries = [
        f"{series_name} עונה {season_num} פרק {episode_num} מלא",
        f"{series_name} עונה {season_num} פרק {episode_num} לצפייה ישירה",
    ]

    results = []
    seen_ids: set = set()

    async with httpx.AsyncClient() as client:
        for query in queries:
            search_resp = await client.get(
                YOUTUBE_SEARCH_URL,
                params={
                    "key": YOUTUBE_API_KEY,
                    "q": query,
                    "type": "video",
                    "part": "snippet",
                    "maxResults": 5,
                    "relevanceLanguage": "iw",
                    "videoDuration": "long",
                    "regionCode": "IL",
                },
                timeout=10,
            )
            data = search_resp.json()

            # quota נגמר — עבור ל-yt-dlp
            if data.get("error", {}).get("errors", [{}])[0].get("reason") == "quotaExceeded":
                raise Exception("quotaExceeded")

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
                params={"key": YOUTUBE_API_KEY, "id": ",".join(new_ids), "part": "contentDetails,statistics,snippet,status"},
                timeout=10,
            )

            for item in details_resp.json().get("items", []):
                vid_id = item["id"]
                snippet = item.get("snippet", {})
                content = item.get("contentDetails", {})
                stats = item.get("statistics", {})
                status = item.get("status", {})

                if status.get("privacyStatus") != "public":
                    continue
                if "IL" in content.get("regionRestriction", {}).get("blocked", []):
                    continue
                if not await _is_youtube_accessible(client, vid_id):
                    continue

                can_embed = status.get("embeddable", True)
                duration = _parse_iso_duration(content.get("duration", "PT0S"))

                results.append({
                    "source": "youtube",
                    "url": f"https://www.youtube.com/watch?v={vid_id}",
                    "embed_url": f"https://www.youtube.com/embed/{vid_id}" if can_embed else None,
                    "title": snippet.get("title", ""),
                    "description": snippet.get("description", "")[:300],
                    "channel": snippet.get("channelTitle", ""),
                    "duration_seconds": duration,
                    "view_count": int(stats.get("viewCount", 0)),
                    "upload_date": snippet.get("publishedAt", ""),
                    "domain": "youtube.com",
                    "can_embed": can_embed,
                    "quality": "auto",
                    "is_free": True,
                    "has_ads": True,
                })

    return results


# ── yt-dlp fallback ───────────────────────────────────────────────────────────

def _search_ytdlp(series_name: str, episode_num: int, season_num: int) -> List[Dict[str, Any]]:
    try:
        import yt_dlp

        queries = [
            f"{series_name} עונה {season_num} פרק {episode_num} מלא",
            f"{series_name} עונה {season_num} פרק {episode_num}",
        ]

        results = []
        seen_ids: set = set()

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "playlist_items": "1:8",
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for query in queries:
                try:
                    info = ydl.extract_info(f"ytsearch8:{query}", download=False)
                    entries = (info or {}).get("entries") or []

                    for entry in entries:
                        if not entry:
                            continue
                        vid_id = entry.get("id", "")
                        if not vid_id or len(vid_id) != 11 or vid_id in seen_ids:
                            continue
                        seen_ids.add(vid_id)

                        duration = int(entry.get("duration") or 0)
                        # פרקים חייבים להיות לפחות 4 דקות
                        if duration < 240:
                            continue

                        results.append({
                            "source": "youtube",
                            "url": f"https://www.youtube.com/watch?v={vid_id}",
                            "embed_url": f"https://www.youtube.com/embed/{vid_id}",
                            "title": entry.get("title", ""),
                            "description": "",
                            "channel": entry.get("channel") or entry.get("uploader", ""),
                            "duration_seconds": duration,
                            "view_count": entry.get("view_count") or 0,
                            "upload_date": "",
                            "domain": "youtube.com",
                            "can_embed": True,
                            "quality": "auto",
                            "is_free": True,
                            "has_ads": True,
                        })

                except Exception as e:
                    print(f"yt-dlp episode search error for '{query}': {e}")

        print(f"yt-dlp YouTube: {len(results)} results")
        return results

    except Exception as e:
        print(f"yt-dlp fallback error: {e}")
        return []


# ── עזר ──────────────────────────────────────────────────────────────────────

async def _is_youtube_accessible(client: httpx.AsyncClient, video_id: str) -> bool:
    try:
        resp = await client.get(
            "https://www.youtube.com/oembed",
            params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
            timeout=5,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _parse_iso_duration(duration: str) -> int:
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not match:
        return 0
    return int(match.group(1) or 0) * 3600 + int(match.group(2) or 0) * 60 + int(match.group(3) or 0)
