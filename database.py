import os
from typing import Optional, Dict, Any
from datetime import datetime, timezone

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("DB_SERVICE_KEY")

_supabase_client = None


def _get_client():
    global _supabase_client
    if _supabase_client is None and SUPABASE_URL and SUPABASE_KEY:
        from supabase import create_client
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


class SupabaseClient:
    """Handles source learning history and search result caching."""

    def __init__(self):
        self.client = _get_client()
        if not self.client:
            print("Warning: Supabase not configured — learning and caching disabled")

    # ── Source history (learning) ─────────────────────────────────────────────

    async def get_source_history(
        self, domain: str, series_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        מחזיר היסטוריה בשתי רמות:
          - אם series_name נמסר: מחזיר {"series": {...}, "global": {...}}
          - אחרת: מחזיר רק גלובלי
        """
        if not self.client or not domain:
            return None
        try:
            result = (
                self.client.table("source_history")
                .select("*")
                .eq("domain", domain)
                .execute()
            )
            rows = result.data or []

            global_row = next((r for r in rows if r.get("series_name") is None), None)
            series_row = None
            if series_name:
                series_row = next(
                    (r for r in rows if r.get("series_name") == series_name), None
                )

            if series_row or global_row:
                return {"series": series_row, "global": global_row}
        except Exception as e:
            print(f"DB get_source_history error: {e}")
        return None

    async def update_source_score(self, feedback) -> None:
        """Update domain reliability at both series-level and global-level."""
        if not self.client:
            return
        series = getattr(feedback, "series", None)
        # עדכן ברמת הסדרה
        if series:
            await self._upsert_history(feedback, series_name=series)
        # עדכן ברמה גלובלית
        await self._upsert_history(feedback, series_name=None)

    async def _upsert_history(self, feedback, series_name: Optional[str]) -> None:
        """Insert or update one row in source_history."""
        try:
            rows = (
                self.client.table("source_history")
                .select("*")
                .eq("domain", feedback.domain)
                .execute()
            ).data or []

            if series_name is None:
                existing = next((r for r in rows if r.get("series_name") is None), None)
            else:
                existing = next(
                    (r for r in rows if r.get("series_name") == series_name), None
                )

            scaled_q = min((feedback.quality_rating or 5) * 2, 10) if feedback.quality_rating else None

            if existing:
                total = existing["total_uses"] + 1
                successful = existing["successful_plays"] + (1 if feedback.played_successfully else 0)
                failed = existing.get("failed_plays", 0) + (0 if feedback.played_successfully else 1)
                avg_q = existing.get("avg_quality_score", 5.0)
                if scaled_q:
                    avg_q = (avg_q * (total - 1) + scaled_q) / total

                self.client.table("source_history").update({
                    "total_uses": total,
                    "successful_plays": successful,
                    "failed_plays": failed,
                    "avg_quality_score": round(avg_q, 2),
                    "last_used": datetime.now(timezone.utc).isoformat(),
                }).eq("id", existing["id"]).execute()
            else:
                self.client.table("source_history").insert({
                    "domain": feedback.domain,
                    "series_name": series_name,
                    "total_uses": 1,
                    "successful_plays": 1 if feedback.played_successfully else 0,
                    "failed_plays": 0 if feedback.played_successfully else 1,
                    "avg_quality_score": scaled_q or 5.0,
                    "last_used": datetime.now(timezone.utc).isoformat(),
                }).execute()
        except Exception as e:
            print(f"DB _upsert_history error ({series_name}): {e}")

    # ── Search result cache ───────────────────────────────────────────────────

    async def get_cached_results(self, series: str, episode: int, season: int = 1):
        if not self.client:
            return None
        try:
            result = (
                self.client.table("search_cache")
                .select("*")
                .eq("series_name", series)
                .eq("episode_num", episode)
                .eq("season_num", season)
                .execute()
            )
            if not result.data:
                return None

            row = result.data[0]
            cached_at = datetime.fromisoformat(row["cached_at"])
            if cached_at.tzinfo is None:
                cached_at = cached_at.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - cached_at).total_seconds() / 3600

            if age_hours < 24:
                from models import SearchResponse
                response = SearchResponse.model_validate_json(row["results_json"])
                response.cached = True
                return response
        except Exception as e:
            print(f"DB get_cached_results error: {e}")
        return None

    async def cache_results(self, series: str, episode: int, results, season: int = 1) -> None:
        if not self.client:
            return
        try:
            self.client.table("search_cache").upsert(
                {
                    "series_name": series,
                    "episode_num": episode,
                    "season_num": season,
                    "results_json": results.model_dump_json(),
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="series_name,episode_num,season_num",
            ).execute()
        except Exception as e:
            print(f"DB cache_results error: {e}")
