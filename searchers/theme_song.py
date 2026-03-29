"""
חיפוש שיר פתיחה / נושא של סדרה ב-YouTube.
מחזיר את התוצאה הטובה ביותר — סרטון קצר, נגיש, עם כותרת תואמת.
"""
import httpx
import os
import re
from typing import Optional, Dict, Any

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEO_URL = "https://www.googleapis.com/youtube/v3/videos"

# משקלי עדיפות לבחירת התוצאה הטובה ביותר
_TITLE_KEYWORDS = [
    "שיר פתיחה", "פתיחה", "תמה", "theme", "opening", "intro",
    "soundtrack", "מנגינה", "מוזיקה", "ost",
]

# ערוצים רשמיים ידועים — מקבלים עדיפות
_OFFICIAL_CHANNELS = {
    "keshet12": True, "mako": True, "kann": True, "כאן": True,
    "reshet": True, "הוט": True, "yes": True,
}


async def find_theme_song(series_name: str) -> Optional[Dict[str, Any]]:
    """
    מחפש את שיר הפתיחה של הסדרה ב-YouTube.
    מחזיר dict עם url, embed_url, title, channel — או None אם לא נמצא.
    """
    if not YOUTUBE_API_KEY:
        print("Warning: YOUTUBE_API_KEY not set — cannot search theme song")
        return None

    # שאילתות לפי סדר עדיפות
    queries = [
        f"{series_name} שיר פתיחה",
        f"{series_name} פתיחה",
        f"{series_name} theme song",
        f"{series_name} intro",
    ]

    candidates = []
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
                        "videoDuration": "short",  # שירי פתיחה הם קצרים (<4 דקות)
                        "regionCode": "IL",
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

                # שלוף פרטים מלאים
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

                    if status.get("privacyStatus") != "public":
                        continue
                    region_restriction = content.get("regionRestriction", {})
                    if "IL" in region_restriction.get("blocked", []):
                        continue

                    # בדוק נגישות בפועל
                    if not await _is_accessible(client, vid_id):
                        continue

                    can_embed = status.get("embeddable", True)
                    duration = _parse_iso_duration(content.get("duration", "PT0S"))

                    title = snippet.get("title", "")
                    channel = snippet.get("channelTitle", "")
                    score = _score_candidate(title, channel, series_name, duration, stats)

                    candidates.append({
                        "score": score,
                        "url": f"https://www.youtube.com/watch?v={vid_id}",
                        "embed_url": f"https://www.youtube.com/embed/{vid_id}?autoplay=1" if can_embed else None,
                        "video_id": vid_id,
                        "title": title,
                        "channel": channel,
                        "duration_seconds": duration,
                        "view_count": int(stats.get("viewCount", 0)),
                        "can_embed": can_embed,
                    })

            except Exception as e:
                print(f"Theme song search error for '{query}': {e}")

            # אם כבר יש מועמד טוב — אל תמשיך לשאילתות נוספות
            if candidates and max(c["score"] for c in candidates) >= 80:
                break

    if not candidates:
        return None

    # בחר את המועמד עם הניקוד הגבוה ביותר
    best = max(candidates, key=lambda c: c["score"])
    best.pop("score")
    return best


def _score_candidate(title: str, channel: str, series_name: str, duration: int, stats: dict) -> float:
    score = 10.0  # ציון בסיס — כל תוצאה מקבלת נקודות
    title_lower = title.lower()
    channel_lower = channel.lower()

    # שם הסדרה בכותרת — בונוס גדול (לא חובה)
    if series_name.lower() in title_lower:
        score += 40.0

    # מילות מפתח של שיר פתיחה
    for kw in _TITLE_KEYWORDS:
        if kw in title_lower:
            score += 30.0
            break

    # ערוץ רשמי
    for ch_keyword in _OFFICIAL_CHANNELS:
        if ch_keyword in channel_lower:
            score += 25.0
            break

    # משך אידיאלי לשיר פתיחה: 1-3 דקות
    if 60 <= duration <= 180:
        score += 20.0
    elif 30 <= duration <= 240:
        score += 10.0

    # פופולריות
    views = int(stats.get("viewCount", 0))
    if views >= 100_000:
        score += 15.0
    elif views >= 10_000:
        score += 8.0
    elif views >= 1_000:
        score += 3.0

    return score


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


def _parse_iso_duration(duration: str) -> int:
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds
