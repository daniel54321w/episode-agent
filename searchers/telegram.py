import httpx
import os
from typing import List, Dict, Any

SERPER_API_KEY = os.getenv("SERPER_API_KEY")

# Known Israeli youth series Telegram channels (public)
# Add channel usernames here as you discover them
KNOWN_TELEGRAM_CHANNELS = [
    # e.g. "israel_youth_series", "israeli_shows"
    # These will be searched via web search since Telegram Bot API
    # doesn't support searching within channels without being a member
]


async def search_telegram(series_name: str, episode_num: int) -> List[Dict[str, Any]]:
    """
    Search for Telegram links to the episode.
    Uses Google via Serper to find public Telegram channel posts.
    """
    if not SERPER_API_KEY:
        print("Warning: SERPER_API_KEY not set")
        return []

    results = []
    seen_urls: set = set()

    queries = [
        f"site:t.me {series_name} פרק {episode_num}",
        f"telegram {series_name} פרק {episode_num} download",
    ]

    async with httpx.AsyncClient() as client:
        for query in queries:
            try:
                resp = await client.post(
                    "https://google.serper.dev/search",
                    json={
                        "q": query,
                        "gl": "il",
                        "hl": "iw",
                        "num": 5,
                    },
                    headers={"X-API-KEY": SERPER_API_KEY},
                    timeout=10,
                )
                data = resp.json()

                for item in data.get("organic", []):
                    url = item.get("link", "")
                    if not url or url in seen_urls:
                        continue

                    # Only include actual Telegram links
                    if "t.me" not in url and "telegram" not in url.lower():
                        continue

                    seen_urls.add(url)

                    results.append({
                        "source": "telegram",
                        "url": url,
                        "embed_url": None,
                        "title": item.get("title", ""),
                        "description": item.get("snippet", ""),
                        "domain": "t.me",
                        "can_embed": False,
                        "is_official": False,
                        "has_ads": False,  # Telegram has no ads
                        "quality": "unknown",
                        "is_free": True,
                        "duration_seconds": None,
                        "view_count": None,
                    })

            except Exception as e:
                print(f"Telegram search error for query '{query}': {e}")

    return results
