import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from database import SupabaseClient
from models import SearchResponse, VideoResult
from scorer import score_result
from searchers import search_dailymotion, search_vimeo, search_youtube
from searchers.telegram_channels import search_telegram_channels
from verifier import verify_all


class EpisodeSearchAgent:
    def __init__(self):
        self.db = SupabaseClient()

    async def search(self, series: str, episode: int, season: int = 1) -> SearchResponse:
        """
        מחפש ב-4 מקורות במקביל, מאמת נגישות, מדרג ומחזיר.
        אין יותר Claude loop — מהיר פי 3-4.
        """

        # שלב 1: חפש בכל 4 המקורות במקביל
        results = await asyncio.gather(
            search_youtube(series, episode, season),
            search_dailymotion(series, episode, season),
            search_vimeo(series, episode, season),
            search_telegram_channels(series, episode, season),
            return_exceptions=True,
        )

        all_raw: List[Dict[str, Any]] = []
        for r in results:
            if isinstance(r, list):
                all_raw.extend(r)
            elif isinstance(r, Exception):
                print(f"Searcher error: {r}")

        print(f"  → נמצאו {len(all_raw)} תוצאות גולמיות")

        # שלב 2: אמת נגישות במקביל
        all_raw = await verify_all(all_raw)
        print(f"  → {len(all_raw)} עברו בדיקת נגישות")

        # שלב 3: דרג לפי גייטים + יתרונות
        scored: List[VideoResult] = []
        history_tasks = [
            self.db.get_source_history(r.get("domain", ""), series)
            for r in all_raw
        ]
        histories = await asyncio.gather(*history_tasks, return_exceptions=True)

        for raw, history in zip(all_raw, histories):
            if isinstance(history, Exception):
                history = None

            raw_score, history_bonus, final_score = score_result(
                raw, history, episode, series, season
            )
            if final_score <= 0:
                continue

            raw["raw_score"] = round(raw_score, 1)
            raw["history_bonus"] = round(history_bonus, 1)
            raw["final_score"] = round(final_score, 1)

            try:
                scored.append(VideoResult(**raw))
            except Exception as e:
                print(f"VideoResult error: {e}")

        # שלב 4: מיין והסר כפילויות
        scored.sort(key=lambda r: r.final_score, reverse=True)
        seen_urls: set = set()
        unique: List[VideoResult] = []
        for r in scored:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                unique.append(r)

        best = unique[0] if unique else None
        print(f"  → {len(unique)} תוצאות סופיות, הטוב ביותר: {best.domain if best else 'אין'}")

        return SearchResponse(
            series=series,
            episode=episode,
            results=unique[:10],
            best=best,
            cached=False,
            searched_at=datetime.now(timezone.utc),
        )
