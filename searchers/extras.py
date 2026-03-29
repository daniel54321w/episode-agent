"""
חיפוש מאחורי הקלעים ופספוסים ב-YouTube.
מנסה קודם YouTube Data API, ואם quota נגמר — עובר ל-yt-dlp.
"""
import asyncio
import os
import httpx
from typing import List, Dict, Any

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


async def find_extras(series_name: str) -> Dict[str, List[Dict[str, Any]]]:
    # נסה קודם YouTube API
    if YOUTUBE_API_KEY:
        try:
            result = await _find_via_api(series_name)
            if result["bts"] or result["bloopers"]:
                print(f"Extras via API: {len(result['bts'])} bts, {len(result['bloopers'])} bloopers")
                return result
        except Exception as e:
            print(f"YouTube API failed ({e}), falling back to yt-dlp")

    # fallback — yt-dlp
    print("Extras: using yt-dlp fallback")
    bts, bloopers = await asyncio.gather(
        _search_ytdlp(f"{series_name} מאחורי הקלעים", series_name),
        _search_ytdlp(f"{series_name} פספוסים", series_name),
    )
    if not bts:
        bts = await _search_ytdlp(f"{series_name} behind the scenes", series_name)
    if not bloopers:
        bloopers = await _search_ytdlp(f"{series_name} NG blooper", series_name)

    print(f"Extras via yt-dlp: {len(bts)} bts, {len(bloopers)} bloopers")
    return {"bts": bts, "bloopers": bloopers}


async def _find_via_api(series_name: str) -> Dict[str, List[Dict[str, Any]]]:
    """חיפוש דרך YouTube Data API."""
    async with httpx.AsyncClient() as client:
        bts = await _search_api(client, f"{series_name} מאחורי הקלעים")
        bloopers = await _search_api(client, f"{series_name} פספוסים")
    return {"bts": bts, "bloopers": bloopers}


async def _search_api(client: httpx.AsyncClient, query: str) -> List[Dict[str, Any]]:
    resp = await client.get(
        YOUTUBE_SEARCH_URL,
        params={"key": YOUTUBE_API_KEY, "q": query, "type": "video", "part": "snippet", "maxResults": 4},
        timeout=10,
    )
    data = resp.json()
    if data.get("error", {}).get("errors", [{}])[0].get("reason") == "quotaExceeded":
        raise Exception("quotaExceeded")

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
    return results[:3]


async def _search_ytdlp(query: str, series_name: str) -> List[Dict[str, Any]]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _search_sync, query, series_name)


def _search_sync(query: str, series_name: str) -> List[Dict[str, Any]]:
    try:
        import yt_dlp

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "playlist_items": "1:6",
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch6:{query}", download=False)

        entries = (info or {}).get("entries") or []
        results = []
        series_lower = series_name.lower()

        for entry in entries:
            if not entry:
                continue

            vid_id = entry.get("id") or entry.get("url", "").split("v=")[-1]
            title = entry.get("title", "")
            channel = entry.get("channel") or entry.get("uploader", "")
            duration = entry.get("duration") or 0
            view_count = entry.get("view_count") or 0

            if not vid_id or len(vid_id) != 11:
                continue

            # סינון: שם הסדרה חייב להופיע בכותרת (בונוס) — לא חובה
            score = 0
            if series_lower in title.lower():
                score += 10
            score += min(view_count // 10000, 10)  # עד 10 נקודות לפי צפיות

            results.append({
                "video_id": vid_id,
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "embed_url": f"https://www.youtube.com/embed/{vid_id}?autoplay=1",
                "thumbnail_url": f"https://img.youtube.com/vi/{vid_id}/mqdefault.jpg",
                "title": title,
                "channel": channel,
                "duration_seconds": int(duration),
                "view_count": view_count,
                "can_embed": True,
                "_score": score,
            })

        # מיין לפי ניקוד
        results.sort(key=lambda r: r["_score"], reverse=True)
        for r in results:
            r.pop("_score", None)

        return results[:3]

    except Exception as e:
        print(f"yt-dlp search error for '{query}': {e}")
        return []
