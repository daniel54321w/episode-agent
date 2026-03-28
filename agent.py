import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

import anthropic

from database import SupabaseClient
from models import SearchResponse, VideoResult
from scorer import score_result
from searchers import search_dailymotion, search_telegram, search_web, search_youtube
from verifier import verify_all

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

SYSTEM_PROMPT = """\
אתה סוכן חיפוש חכם לסדרות נוער ישראליות.
תפקידך: לחפש פרקים ממספר מקורות ולדרג אותם לפי איכות.

קריטריונים לדירוג (חשיבות יורדת):
1. ניתן להטמעה (embed) ישירה באתר — החשוב ביותר
2. מקור רשמי של ערוץ ישראלי (מאקו, כאן, רשת, קשת)
3. איכות וידאו גבוהה (720p/1080p)
4. ללא פרסומות
5. חינמי
6. אורך פרק תקין (לא תקציר/טריילר)
7. אמינות המקור לאורך זמן

לאחר חיפוש, תסכם את ממצאיך ותצביע על המקור הטוב ביותר.
"""

# Tool definitions for Claude
TOOLS = [
    {
        "name": "search_youtube",
        "description": "חיפוש פרקים ביוטיוב. מחזיר וידאואים עם מידע על אורך, צפיות ותאריך העלאה.",
        "input_schema": {
            "type": "object",
            "properties": {
                "series_name": {"type": "string", "description": "שם הסדרה בעברית"},
                "episode_num": {"type": "integer", "description": "מספר הפרק"},
            },
            "required": ["series_name", "episode_num"],
        },
    },
    {
        "name": "search_web",
        "description": "חיפוש ברשת — אתרי סטרימינג ישראלים (מאקו, כאן, רשת, קשת) ומקורות נוספים.",
        "input_schema": {
            "type": "object",
            "properties": {
                "series_name": {"type": "string"},
                "episode_num": {"type": "integer"},
            },
            "required": ["series_name", "episode_num"],
        },
    },
    {
        "name": "search_telegram",
        "description": "חיפוש ערוצי טלגרם ציבוריים עם פרקים של הסדרה.",
        "input_schema": {
            "type": "object",
            "properties": {
                "series_name": {"type": "string"},
                "episode_num": {"type": "integer"},
            },
            "required": ["series_name", "episode_num"],
        },
    },
    {
        "name": "search_dailymotion",
        "description": "חיפוש ב-Dailymotion — מקור אמין עם אפשרות הטמעה ישירה. חפש תמיד!",
        "input_schema": {
            "type": "object",
            "properties": {
                "series_name": {"type": "string", "description": "שם הסדרה בעברית"},
                "episode_num": {"type": "integer", "description": "מספר הפרק"},
            },
            "required": ["series_name", "episode_num"],
        },
    },
    {
        "name": "get_source_history",
        "description": "קבל נתוני אמינות היסטוריים על דומיין מסויים מהמאגר שלנו.",
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "כתובת הדומיין, לדוגמה: youtube.com"},
            },
            "required": ["domain"],
        },
    },
]


class EpisodeSearchAgent:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        self.db = SupabaseClient()

    async def _execute_tool(
        self, tool_name: str, tool_input: Dict[str, Any], season: int = 1
    ) -> Any:
        """Dispatch tool calls to the appropriate searcher or DB function."""
        if tool_name == "search_youtube":
            return await search_youtube(
                tool_input["series_name"], tool_input["episode_num"], season
            )
        elif tool_name == "search_web":
            return await search_web(
                tool_input["series_name"], tool_input["episode_num"]
            )
        elif tool_name == "search_telegram":
            return await search_telegram(
                tool_input["series_name"], tool_input["episode_num"]
            )
        elif tool_name == "search_dailymotion":
            return await search_dailymotion(
                tool_input["series_name"], tool_input["episode_num"], season
            )
        elif tool_name == "get_source_history":
            return await self.db.get_source_history(tool_input["domain"])
        return None

    async def search(self, series: str, episode: int, season: int = 1) -> SearchResponse:
        """
        Run the agentic search loop:
        1. Claude decides which tools to use
        2. Tools run in parallel when Claude requests multiple at once
        3. Results are scored and returned sorted
        """
        all_raw_results: List[Dict[str, Any]] = []

        messages = [
            {
                "role": "user",
                "content": (
                    f"חפש את הסדרה **{series}** עונה **{season}** פרק **{episode}**.\n\n"
                    "חשוב מאוד: חפש רק תוצאות מהעונה הנכונה!\n\n"
                    "בצע את הצעדים הבאים:\n"
                    "1. חפש ביוטיוב\n"
                    "2. חפש ב-Dailymotion (חובה! מקור אמין עם הטמעה ישירה)\n"
                    "3. חפש ברשת (אתרי סטרימינג)\n"
                    "4. חפש בטלגרם\n"
                    "5. לכל דומיין שמצאת — בדוק את ההיסטוריה שלו\n"
                    "6. סכם את הממצאים והמלץ על המקור הטוב ביותר"
                ),
            }
        ]

        # Agentic loop
        while True:
            response = await self.client.messages.create(
                model="claude-opus-4-6",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                break
            if response.stop_reason != "tool_use":
                break

            # Collect all tool_use blocks from this response
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

            # Execute all tool calls in parallel
            tasks = [
                self._execute_tool(b.name, b.input, season) for b in tool_use_blocks
            ]
            tool_outputs = await asyncio.gather(*tasks, return_exceptions=True)

            # Build tool_result messages
            tool_results = []
            for block, output in zip(tool_use_blocks, tool_outputs):
                if isinstance(output, Exception):
                    print(f"Tool {block.name} error: {output}")
                    output = []

                # Collect raw search results for scoring later
                if block.name in ("search_youtube", "search_web", "search_telegram", "search_dailymotion"):
                    if isinstance(output, list):
                        all_raw_results.extend(output)

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(output or [], ensure_ascii=False),
                    }
                )

            messages.append({"role": "user", "content": tool_results})

        # Verify all sources are actually accessible (parallel, fast)
        print(f"  → בודק נגישות {len(all_raw_results)} מקורות...")
        all_raw_results = await verify_all(all_raw_results)
        print(f"  → {len(all_raw_results)} מקורות עברו בדיקת נגישות")

        # Score all collected results
        scored: List[VideoResult] = []
        for raw in all_raw_results:
            domain = raw.get("domain", "")
            history = await self.db.get_source_history(domain)
            raw_score, history_bonus, final_score = score_result(raw, history, episode, series, season)

            raw["raw_score"] = round(raw_score, 1)
            raw["history_bonus"] = round(history_bonus, 1)
            raw["final_score"] = round(final_score, 1)


            try:
                scored.append(VideoResult(**raw))
            except Exception as e:
                print(f"VideoResult creation error: {e} — raw: {raw}")

        # Remove results that failed gates (score == 0) or are too low
        scored = [r for r in scored if r.final_score > 0]

        # Sort and deduplicate
        scored.sort(key=lambda r: r.final_score, reverse=True)
        seen_urls: set = set()
        unique: List[VideoResult] = []
        for r in scored:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                unique.append(r)

        best = unique[0] if unique else None

        return SearchResponse(
            series=series,
            episode=episode,
            results=unique[:10],
            best=best,
            cached=False,
            searched_at=datetime.now(timezone.utc),
        )
