"""
חיפוש שיר פתיחה של סדרה ב-YouTube.
מנסה קודם YouTube Data API, ואם quota נגמר — עובר ל-yt-dlp.
"""
import asyncio
import os
import httpx
from typing import Optional, Dict, Any

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEO_URL = "https://www.googleapis.com/youtube/v3/videos"


async def find_theme_song(series_name: str) -> Optional[Dict[str, Any]]:
    # נסה קודם YouTube API
    if YOUTUBE_API_KEY:
        try:
            result = await _find_via_api(series_name)
            if result:
                print(f"Theme song via API: {result['title']}")
                return result
        except Exception as e:
            print(f"YouTube API failed ({e}), falling back to yt-dlp")

    # fallback — yt-dlp
    print("Theme song: using yt-dlp fallback")
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _find_sync, series_name)


async def _find_via_api(series_name: str) -> Optional[Dict[str, Any]]:
    """חיפוש דרך YouTube Data API."""
    queries = [
        f"{series_name} שיר פתיחה",
        f"{series_name} theme song",
    ]
    candidates = []
    seen_ids: set = set()

    async with httpx.AsyncClient() as client:
        for query in queries:
            resp = await client.get(
                YOUTUBE_SEARCH_URL,
                params={
                    "key": YOUTUBE_API_KEY,
                    "q": query,
                    "type": "video",
                    "part": "snippet",
                    "maxResults": 5,
                    "relevanceLanguage": "iw",
                },
                timeout=10,
            )
            data = resp.json()

            # אם quota נגמר — זרוק exception כדי לעבור ל-yt-dlp
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

            details = await client.get(
                YOUTUBE_VIDEO_URL,
                params={"key": YOUTUBE_API_KEY, "id": ",".join(new_ids), "part": "contentDetails,statistics,snippet,status"},
                timeout=10,
            )
            for item in details.json().get("items", []):
                vid_id = item["id"]
                snippet = item.get("snippet", {})
                stats = item.get("statistics", {})
                status = item.get("status", {})
                if status.get("privacyStatus") != "public":
                    continue
                import re
                duration = _parse_duration(item.get("contentDetails", {}).get("duration", "PT0S"))
                view_count = int(stats.get("viewCount", 0))
                title = snippet.get("title", "")
                channel = snippet.get("channelTitle", "")
                score = _score(title, channel, series_name, duration, view_count)
                candidates.append({
                    "score": score,
                    "video_id": vid_id,
                    "url": f"https://www.youtube.com/watch?v={vid_id}",
                    "embed_url": f"https://www.youtube.com/embed/{vid_id}?autoplay=1",
                    "title": title,
                    "channel": channel,
                    "duration_seconds": duration,
                    "view_count": view_count,
                    "can_embed": status.get("embeddable", True),
                })

    if not candidates:
        return None
    best = max(candidates, key=lambda c: c["score"])
    best.pop("score")
    return best


def _parse_duration(duration: str) -> int:
    import re
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not match:
        return 0
    return int(match.group(1) or 0) * 3600 + int(match.group(2) or 0) * 60 + int(match.group(3) or 0)


def _find_sync(series_name: str) -> Optional[Dict[str, Any]]:
    try:
        import yt_dlp

        queries = [
            f"{series_name} שיר פתיחה",
            f"{series_name} פתיחה",
            f"{series_name} theme song",
        ]

        candidates = []
        seen_ids: set = set()

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "playlist_items": "1:5",
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for query in queries:
                try:
                    info = ydl.extract_info(f"ytsearch5:{query}", download=False)
                    entries = (info or {}).get("entries") or []

                    for entry in entries:
                        if not entry:
                            continue
                        vid_id = entry.get("id", "")
                        if not vid_id or len(vid_id) != 11 or vid_id in seen_ids:
                            continue
                        seen_ids.add(vid_id)

                        title = entry.get("title", "")
                        channel = entry.get("channel") or entry.get("uploader", "")
                        duration = int(entry.get("duration") or 0)
                        view_count = entry.get("view_count") or 0

                        score = _score(title, channel, series_name, duration, view_count)
                        candidates.append({
                            "score": score,
                            "video_id": vid_id,
                            "url": f"https://www.youtube.com/watch?v={vid_id}",
                            "embed_url": f"https://www.youtube.com/embed/{vid_id}?autoplay=1",
                            "title": title,
                            "channel": channel,
                            "duration_seconds": duration,
                            "view_count": view_count,
                            "can_embed": True,
                        })

                    # אם כבר יש מועמד טוב — עצור
                    if candidates and max(c["score"] for c in candidates) >= 40:
                        break

                except Exception as e:
                    print(f"yt-dlp theme song error for '{query}': {e}")

        if not candidates:
            return None

        best = max(candidates, key=lambda c: c["score"])
        best.pop("score")
        return best

    except Exception as e:
        print(f"find_theme_song error: {e}")
        return None


def _score(title: str, channel: str, series_name: str, duration: int, view_count: int) -> float:
    score = 0.0
    title_lower = title.lower()
    channel_lower = channel.lower()

    # שם הסדרה בכותרת
    if series_name.lower() in title_lower:
        score += 30.0

    # מילות מפתח של שיר פתיחה
    for kw in ["שיר פתיחה", "פתיחה", "theme", "opening", "intro", "soundtrack"]:
        if kw in title_lower:
            score += 25.0
            break

    # ערוץ רשמי
    for ch in ["keshet", "mako", "kann", "כאן", "reshet", "הוט", "yes", "ניקלודיאון"]:
        if ch in channel_lower:
            score += 20.0
            break

    # משך אידיאלי: 1-3 דקות
    if 60 <= duration <= 180:
        score += 15.0
    elif 30 <= duration <= 300:
        score += 8.0

    # פופולריות
    if view_count >= 100_000:
        score += 10.0
    elif view_count >= 10_000:
        score += 5.0

    return score
