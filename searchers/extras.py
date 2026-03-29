"""
חיפוש מאחורי הקלעים ופספוסים ב-YouTube דרך yt-dlp (ללא API key).
"""
import asyncio
from typing import List, Dict, Any


async def find_extras(series_name: str) -> Dict[str, List[Dict[str, Any]]]:
    bts, bloopers = await asyncio.gather(
        _search(f"{series_name} מאחורי הקלעים", series_name),
        _search(f"{series_name} פספוסים", series_name),
    )

    # אם לא נמצא — נסה בשאילתה חלופית
    if not bts:
        bts = await _search(f"{series_name} behind the scenes", series_name)
    if not bloopers:
        bloopers = await _search(f"{series_name} NG blooper", series_name)

    print(f"Extras for '{series_name}': {len(bts)} bts, {len(bloopers)} bloopers")
    return {"bts": bts, "bloopers": bloopers}


async def _search(query: str, series_name: str) -> List[Dict[str, Any]]:
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
