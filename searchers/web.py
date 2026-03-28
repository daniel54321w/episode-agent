import httpx
import os
from typing import List, Dict, Any
from urllib.parse import urlparse

SERPER_API_KEY = os.getenv("SERPER_API_KEY")

# Known Israeli streaming/media domains and their properties
KNOWN_DOMAINS: Dict[str, Dict] = {
    "mako.co.il":       {"is_official": True,  "has_ads": True,  "can_embed": False, "quality": "720p"},
    "keshet12.co.il":   {"is_official": True,  "has_ads": True,  "can_embed": False, "quality": "720p"},
    "reshet.tv":        {"is_official": True,  "has_ads": True,  "can_embed": False, "quality": "720p"},
    "kan.org.il":       {"is_official": True,  "has_ads": False, "can_embed": False, "quality": "720p"},
    "yes.co.il":        {"is_official": True,  "has_ads": False, "can_embed": False, "quality": "1080p"},
    "hot.net.il":       {"is_official": True,  "has_ads": False, "can_embed": False, "quality": "1080p"},
    "vod.co.il":        {"is_official": False, "has_ads": True,  "can_embed": False, "quality": "480p"},
    "dailymotion.com":  {"is_official": False, "has_ads": True,  "can_embed": True,  "quality": "720p"},
    "ok.ru":            {"is_official": False, "has_ads": True,  "can_embed": True,  "quality": "480p"},
    "streamtape.com":   {"is_official": False, "has_ads": True,  "can_embed": True,  "quality": "720p"},
    "uqload.com":       {"is_official": False, "has_ads": True,  "can_embed": True,  "quality": "480p"},
    "vimeo.com":        {"is_official": False, "has_ads": False, "can_embed": True,  "quality": "1080p"},
    "drive.google.com": {"is_official": False, "has_ads": False, "can_embed": False, "quality": "unknown"},
}


async def search_web(series_name: str, episode_num: int) -> List[Dict[str, Any]]:
    """Search the web for episode streaming links using Serper API (Google)."""
    if not SERPER_API_KEY:
        print("Warning: SERPER_API_KEY not set")
        return []

    queries = [
        f"{series_name} פרק {episode_num} לצפייה ישירה מלא",
        f'"{series_name}" פרק {episode_num} צפייה אונליין',
    ]

    results = []
    seen_urls: set = set()

    async with httpx.AsyncClient() as client:
        for query in queries:
            try:
                resp = await client.post(
                    "https://google.serper.dev/search",
                    json={
                        "q": query,
                        "gl": "il",
                        "hl": "iw",
                        "num": 10,
                    },
                    headers={"X-API-KEY": SERPER_API_KEY},
                    timeout=10,
                )
                data = resp.json()

                for item in data.get("organic", []):
                    url = item.get("link", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)

                    parsed = urlparse(url)
                    domain = parsed.netloc.replace("www.", "")
                    domain_info = KNOWN_DOMAINS.get(domain, {})

                    results.append({
                        "source": "web",
                        "url": url,
                        "embed_url": None,
                        "title": item.get("title", ""),
                        "description": item.get("snippet", ""),
                        "domain": domain,
                        "can_embed": domain_info.get("can_embed", False),
                        "is_official": domain_info.get("is_official", False),
                        "has_ads": domain_info.get("has_ads", True),
                        "quality": domain_info.get("quality", "unknown"),
                        "is_free": True,
                        "duration_seconds": None,
                        "view_count": None,
                    })

            except Exception as e:
                print(f"Web search error for query '{query}': {e}")

    return results
