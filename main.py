import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from agent import EpisodeSearchAgent
from database import SupabaseClient
from models import FeedbackRequest, SearchResponse

# ── App lifecycle ─────────────────────────────────────────────────────────────

agent: EpisodeSearchAgent
db: SupabaseClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent, db
    agent = EpisodeSearchAgent()
    db = SupabaseClient()
    yield


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
    force_refresh: bool = Query(False, description="חיפוש מחדש גם אם יש תוצאות שמורות"),
):
    """
    מחפש את הפרק הנדרש ממספר מקורות ומחזיר את הרשימה ממוינת לפי איכות.
    """
    # Try cache first
    if not force_refresh:
        cached = await db.get_cached_results(series, episode)
        if cached:
            return cached

    try:
        results = await agent.search(series, episode)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"שגיאה בחיפוש: {str(e)}")

    # Save to cache in the background
    import asyncio
    asyncio.create_task(db.cache_results(series, episode, results))

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


@app.get("/health", summary="בדיקת תקינות")
async def health():
    return {"status": "healthy", "message": "הסוכן פעיל"}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True,
    )
