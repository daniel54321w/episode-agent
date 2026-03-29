import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from agent import EpisodeSearchAgent
from database import SupabaseClient
from models import (
    AdminSourceStat,
    FeedbackRequest,
    SearchResponse,
    WatchProgressRequest,
    WatchProgressResponse,
)

# ── App lifecycle ─────────────────────────────────────────────────────────────

agent: EpisodeSearchAgent
db: SupabaseClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent, db
    agent = EpisodeSearchAgent()
    db = SupabaseClient()
    # הפעל cache refresh ברקע כל שעה
    import asyncio
    asyncio.create_task(_background_cache_refresh())
    yield


async def _background_cache_refresh():
    """מרענן קאש ישן ברקע כל 60 דקות."""
    import asyncio
    while True:
        await asyncio.sleep(3600)  # המתן שעה
        try:
            stale = await db.get_stale_cache_entries(older_than_hours=20)
            print(f"[cache-refresh] {len(stale)} רשומות ישנות לרענון")
            for entry in stale:
                try:
                    results = await agent.search(
                        entry["series_name"],
                        entry["episode_num"],
                        entry.get("season_num", 1),
                    )
                    await db.cache_results(
                        entry["series_name"],
                        entry["episode_num"],
                        results,
                        entry.get("season_num", 1),
                    )
                    print(f"[cache-refresh] רוענן: {entry['series_name']} פרק {entry['episode_num']}")
                    await asyncio.sleep(5)  # השהייה בין חיפושים
                except Exception as e:
                    print(f"[cache-refresh] שגיאה: {e}")
        except Exception as e:
            print(f"[cache-refresh] שגיאה כללית: {e}")


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="סוכן חיפוש פרקים — Israeli Youth Series Agent",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — update allow_origins to your Lovable domain in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routes ────────────────────────────────────────────────────────────────────


@app.get("/api/search", response_model=SearchResponse, summary="חיפוש פרק")
async def search_episode(
    series: str = Query(..., description="שם הסדרה בעברית, לדוגמה: החממה"),
    episode: int = Query(..., ge=1, description="מספר הפרק"),
    season: int = Query(1, ge=1, description="מספר העונה (ברירת מחדל: 1)"),
    force_refresh: bool = Query(False, description="חיפוש מחדש גם אם יש תוצאות שמורות"),
):
    """
    מחפש את הפרק הנדרש ממספר מקורות ומחזיר את הרשימה ממוינת לפי איכות.
    """
    # Try cache first
    if not force_refresh:
        cached = await db.get_cached_results(series, episode, season)
        if cached:
            return cached

    try:
        results = await agent.search(series, episode, season)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"שגיאה בחיפוש: {str(e)}")

    # Save to cache in the background
    import asyncio
    asyncio.create_task(db.cache_results(series, episode, results, season))

    return results


@app.post("/api/feedback", summary="שלח משוב על תוצאה")
async def submit_feedback(
    feedback: FeedbackRequest,
    background_tasks: BackgroundTasks,
):
    """
    שלח משוב האם הפרק עבד — הסוכן לומד ומשפר את הדירוג לפעמים הבאות.
    """
    background_tasks.add_task(db.update_source_score, feedback)
    return {"status": "ok", "message": "תודה! המשוב נשמר"}


@app.get("/api/theme-song", summary="שיר פתיחה של סדרה")
async def get_theme_song(
    series: str = Query(..., description="שם הסדרה"),
    force_refresh: bool = Query(False, description="חפש מחדש גם אם יש שמור"),
):
    """
    מחזיר שיר פתיחה לסדרה.
    בפעם הראשונה מחפש ב-YouTube ושומר לתמיד.
    בפעמים הבאות מחזיר מהקאש מיידית.
    """
    # קאש קבוע — בדוק קודם
    if not force_refresh:
        cached = await db.get_theme_song(series)
        if cached:
            return {**cached, "cached": True}

    # חפש ב-YouTube
    from searchers.theme_song import find_theme_song
    song = await find_theme_song(series)

    if not song:
        raise HTTPException(status_code=404, detail=f"לא נמצא שיר פתיחה עבור '{series}'")

    # שמור לתמיד
    import asyncio
    asyncio.create_task(db.save_theme_song(series, song))

    return {**song, "cached": False}


@app.post("/api/watch-progress", summary="שמור התקדמות צפייה")
async def save_watch_progress(req: WatchProgressRequest):
    """
    שומר את המיקום הנוכחי בסרטון. קריאה כל 30 שניות מהפלייר.
    אם המשתמש צפה >60 שניות — שולח פידבק אוטומטי.
    """
    await db.save_watch_progress(
        req.series, req.episode, req.season,
        req.url, req.position_seconds, req.duration_seconds
    )

    # פידבק אוטומטי אם צפה >60 שניות
    if req.position_seconds >= 60:
        from models import FeedbackRequest as FB
        auto_feedback = FB(
            series=req.series,
            episode=req.episode,
            season=req.season,
            url=req.url,
            domain=_extract_domain(req.url),
            played_successfully=True,
            watch_duration_seconds=req.position_seconds,
        )
        import asyncio
        asyncio.create_task(db.update_source_score(auto_feedback))

    return {"status": "ok"}


@app.get("/api/watch-progress", summary="קבל התקדמות צפייה")
async def get_watch_progress(
    series: str = Query(...),
    episode: int = Query(...),
    season: int = Query(1),
):
    """מחזיר מאיפה המשתמש עצר בפרק הזה."""
    progress = await db.get_watch_progress(series, episode, season)
    if not progress:
        return {"position_seconds": 0}
    return progress


@app.get("/api/watch-history", summary="היסטוריית צפייה")
async def get_watch_history():
    """מחזיר את כל הפרקים שנצפו, מהחדש לישן."""
    history = await db.get_all_watch_history()
    return {"history": history}


@app.get("/api/admin/sources", response_model=list[AdminSourceStat], summary="סטטיסטיקות מקורות")
async def get_admin_sources(
    admin_key: str = Query(..., description="מפתח אדמין"),
):
    """דשבורד אדמין — רשימת כל המקורות עם אחוזי הצלחה."""
    import os
    if admin_key != os.getenv("ADMIN_KEY", "admin123"):
        raise HTTPException(status_code=403, detail="אין גישה")
    stats = await db.get_source_stats()
    return stats


@app.get("/health", summary="בדיקת תקינות")
async def health():
    return {"status": "healthy", "message": "הסוכן פעיל"}


def _extract_domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True,
    )
