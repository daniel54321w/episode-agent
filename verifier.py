"""
בדיקת נגישות מקורות
====================
כל בדיקה רצה עם timeout קצר ובמקביל לשאר.
אם הבדיקה נכשלת — המקור נפסל.
"""

import asyncio
import httpx
from typing import Dict, Any


TIMEOUT = 6.0  # שניות מקסימום לכל בדיקה


async def verify_source(result: Dict[str, Any]) -> bool:
    """
    מחזיר True אם המקור נגיש ועובד, False אם לא.
    """
    domain = result.get("domain", "")
    url = result.get("url", "")
    embed_url = result.get("embed_url", "")

    if not url:
        return False

    try:
        if domain == "youtube.com":
            return await _verify_youtube(url)
        elif domain == "dailymotion.com":
            return await _verify_dailymotion(embed_url or url)
        elif domain == "t.me":
            return await _verify_head(url)
        else:
            return await _verify_head(url)
    except Exception:
        return True  # ספק לטובת המקור אם הבדיקה עצמה נכשלה


async def _verify_youtube(url: str) -> bool:
    """בדיקת YouTube דרך oEmbed API — אמינה ומהירה."""
    video_id = _extract_youtube_id(url)
    if not video_id:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.youtube.com/oembed",
                params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
                timeout=TIMEOUT,
            )
            return resp.status_code == 200
    except Exception:
        return False


async def _verify_dailymotion(url: str) -> bool:
    """בדיקת Dailymotion דרך ה-API שלהם."""
    video_id = _extract_dailymotion_id(url)
    if not video_id:
        return await _verify_head(url)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.dailymotion.com/video/{video_id}",
                params={"fields": "id,status,availability"},
                timeout=TIMEOUT,
            )
            if resp.status_code != 200:
                return False
            data = resp.json()
            # status "published" ו-availability "available" = עובד
            status = data.get("status", "")
            availability = data.get("availability", "")
            if status == "deleted" or availability == "not_available":
                return False
            return True
    except Exception:
        return True  # אם ה-API לא ענה — נניח שעובד


async def _verify_head(url: str) -> bool:
    """בדיקת HTTP HEAD בסיסית — מהירה."""
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.head(
                url,
                timeout=TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            # 200, 301, 302 = בסדר | 404, 410 = לא קיים | 403 = חסום (נניח בסדר)
            return resp.status_code not in (404, 410, 451)
    except Exception:
        return True  # timeout או שגיאת רשת — נניח בסדר


def _extract_youtube_id(url: str) -> str:
    """מחלץ video ID מ-URL של YouTube."""
    import re
    patterns = [
        r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return ""


def _extract_dailymotion_id(url: str) -> str:
    """מחלץ video ID מ-URL של Dailymotion."""
    import re
    m = re.search(r"dailymotion\.com/(?:video|embed/video)/([a-zA-Z0-9]+)", url)
    return m.group(1) if m else ""


async def verify_all(results: list) -> list:
    """
    מריץ בדיקות נגישות במקביל על כל התוצאות.
    מחזיר רק את אלה שעברו.
    """
    checks = [verify_source(r) for r in results]
    outcomes = await asyncio.gather(*checks, return_exceptions=True)

    verified = []
    for result, ok in zip(results, outcomes):
        if ok is True:
            verified.append(result)
        else:
            print(f"  ✗ לא נגיש: {result.get('domain')} — {result.get('title','')[:40]}")

    return verified
