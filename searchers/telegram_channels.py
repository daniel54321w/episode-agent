"""
חיפוש בערוצי טלגרם ציבוריים ישראלים דרך Telethon (MTProto).
דורש: TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION ב-.env / Railway.

הוסף ערוצים ידועים לרשימה PUBLIC_CHANNELS.
"""
import os
import asyncio
from typing import List, Dict, Any, Optional

TELEGRAM_API_ID   = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_SESSION  = os.getenv("TELEGRAM_SESSION")

# ── רשימת ערוצים ציבוריים ישראלים ──────────────────────────────────────────
# הוסף username של ערוץ (ללא @) או קישור t.me/xxxxx
PUBLIC_CHANNELS: List[str] = [
    # דוגמה: "israeliseries", "hamakoil"
    # הוסף כאן את שמות הערוצים שלך
]


async def search_telegram_channels(
    series_name: str,
    episode_num: int,
    season_num: int = 1,
) -> List[Dict[str, Any]]:
    """חיפוש בערוצי טלגרם ציבוריים ומחזיר קישורים לפרקים."""
    if not all([TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION]):
        print("Warning: Telegram credentials not set — skipping Telegram search")
        return []

    if not PUBLIC_CHANNELS:
        print("Warning: PUBLIC_CHANNELS list is empty — add channel usernames")
        return []

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.tl.types import InputMessagesFilterVideo
    except ImportError:
        print("Warning: telethon not installed")
        return []

    query = f"{series_name} עונה {season_num} פרק {episode_num}"
    results = []

    try:
        client = TelegramClient(
            StringSession(TELEGRAM_SESSION),
            int(TELEGRAM_API_ID),
            TELEGRAM_API_HASH,
        )
        await client.connect()

        tasks = [
            _search_channel(client, channel, query, series_name, episode_num, season_num)
            for channel in PUBLIC_CHANNELS
        ]
        channel_results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in channel_results:
            if isinstance(res, list):
                results.extend(res)

        await client.disconnect()

    except Exception as e:
        print(f"Telegram MTProto error: {e}")

    return results


async def _search_channel(
    client,
    channel: str,
    query: str,
    series_name: str,
    episode_num: int,
    season_num: int,
) -> List[Dict[str, Any]]:
    """חיפוש בערוץ בודד."""
    results = []
    try:
        from telethon.tl.types import InputMessagesFilterVideo, MessageMediaDocument, MessageMediaPhoto

        messages = await client.get_messages(
            channel,
            search=query,
            limit=5,
            filter=InputMessagesFilterVideo,
        )

        for msg in messages:
            if not msg:
                continue

            # קישור ישיר להודעה
            url = f"https://t.me/{channel}/{msg.id}"

            # פרטי הקובץ אם יש
            duration = None
            if hasattr(msg, "media") and hasattr(msg.media, "document"):
                doc = msg.media.document
                for attr in doc.attributes:
                    if hasattr(attr, "duration"):
                        duration = int(attr.duration)

            title = (msg.message or "")[:100] or f"{series_name} עונה {season_num} פרק {episode_num}"

            results.append({
                "source": "telegram",
                "url": url,
                "embed_url": None,
                "title": title,
                "description": msg.message or "",
                "channel": channel,
                "domain": "t.me",
                "can_embed": False,
                "is_official": False,
                "has_ads": False,
                "quality": "unknown",
                "is_free": True,
                "duration_seconds": duration,
                "view_count": getattr(msg, "views", None),
                "upload_date": msg.date.isoformat() if msg.date else None,
            })

    except Exception as e:
        print(f"Error searching channel {channel}: {e}")

    return results
