import re
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

# Expected episode duration for Israeli youth series
EPISODE_DURATION = {
    "min": 8 * 60,       # 8 minutes (short format)
    "ideal_min": 20 * 60,  # 20 minutes
    "ideal_max": 50 * 60,  # 50 minutes
    "max": 70 * 60,      # 70 minutes (long format / finale)
}

# Hebrew + English keywords that indicate scam/summary/clip (not a full episode)
SCAM_KEYWORDS = [
    "תקציר", "קליפ", "הייליטס", "highlights", "trailer", "טריילר",
    "promo", "פרומו", "תמצית", "קצר", "behind the scenes", "מאחורי הקלעים",
    "bloopers", "teaser", "sneak peek", "extended preview",
    "ראיון", "interview", "making of",
]

# Quality score table
QUALITY_SCORES: Dict[str, float] = {
    "1080p": 10.0,
    "auto":  8.0,   # YouTube adaptive
    "720p":  7.0,
    "480p":  4.0,
    "360p":  2.0,
    "unknown": 5.0,  # neutral
}

# Base reliability score per domain (out of 10)
DOMAIN_BASE: Dict[str, float] = {
    "youtube.com":      8.0,
    "mako.co.il":       9.0,
    "keshet12.co.il":   9.0,
    "kan.org.il":       9.0,
    "reshet.tv":        8.5,
    "yes.co.il":        8.5,
    "hot.net.il":       8.5,
    "vimeo.com":        7.0,
    "dailymotion.com":  6.0,
    "ok.ru":            5.0,
    "t.me":             5.5,
    "streamtape.com":   4.5,
    "uqload.com":       4.0,
    "vod.co.il":        5.0,
    "drive.google.com": 5.0,
}


def score_result(
    result: Dict[str, Any],
    history: Optional[Dict] = None,
    episode_num: int = 1,
    series_name: str = "",
    season_num: int = 1,
) -> Tuple[float, float, float]:
    """
    Score a video result.
    Returns: (raw_score, history_bonus, final_score) — all 0-100.

    Breakdown (max 100 before history):
      Domain base         0-10
      Quality             0-10
      Free                0-8
      No ads              0-6
      Can embed           0-12
      Official source     0-8
      Duration valid      0-15
      Not scam/summary    0-10  (negative if scam)
      Episode # in title  0-5
      Hebrew subtitles    0-5
      View count          0-8
      Recency             0-5
      ─────────────────   0-102 (capped at 100)
    """
    score = 0.0

    domain = result.get("domain", "")

    # 1. Domain base score
    score += DOMAIN_BASE.get(domain, 4.0)

    # 2. Video quality
    quality = result.get("quality") or "unknown"
    score += QUALITY_SCORES.get(quality, 5.0)

    # 3. Is free?
    if result.get("is_free", True):
        score += 8.0

    # 4. Ads
    has_ads = result.get("has_ads")
    if has_ads is False:
        score += 6.0
    elif has_ads is None:
        score += 3.0  # unknown — partial credit

    # 5. Can embed directly in the website
    if result.get("can_embed", False):
        score += 12.0

    # 6. Official Israeli broadcaster
    if result.get("is_official", False):
        score += 8.0

    # 7. Duration validity
    duration = result.get("duration_seconds")
    score += _score_duration(duration)

    # 8. Scam / summary detection
    title = (result.get("title") or "").lower()
    description = (result.get("description") or "").lower()
    if any(kw in title for kw in SCAM_KEYWORDS):
        score -= 20.0  # heavy penalty for obvious summaries/trailers
    else:
        score += 10.0  # bonus for looking like a full episode

    # 9. Series name appears in title (critical check)
    if series_name:
        series_lower = series_name.lower().strip()
        if series_lower in title:
            score += 20.0  # strong boost — correct series confirmed
        else:
            score -= 25.0  # heavy penalty — probably wrong series

    # 9b. Season number matching
    season_patterns = re.findall(r'עונה\s*(\d+)', title)
    if season_patterns:
        if any(int(s) == season_num for s in season_patterns):
            score += 10.0   # correct season confirmed
        else:
            score -= 25.0   # wrong season — heavy penalty

    # 10. Episode number matching — bonus for correct, heavy penalty for wrong
    correct_ep = (
        f"פרק {episode_num}" in title or
        bool(re.search(rf'(?<!\d){re.escape(str(episode_num))}(?!\d)', title))
    )
    # Check if a DIFFERENT episode number is explicitly mentioned
    wrong_ep = False
    for m in re.findall(r'פרק\s*(\d+)', title):
        if int(m) != episode_num:
            wrong_ep = True
            break

    if correct_ep and not wrong_ep:
        score += 15.0   # strong boost — confirmed correct episode
    elif wrong_ep:
        score -= 30.0   # heavy penalty — clearly wrong episode

    # 10. Hebrew subtitles (hard to detect automatically — bonus if confirmed)
    if result.get("has_hebrew_subtitles", False):
        score += 5.0

    # 11. View count (credibility signal)
    view_count = result.get("view_count") or 0
    if view_count >= 100_000:
        score += 8.0
    elif view_count >= 10_000:
        score += 5.0
    elif view_count >= 1_000:
        score += 3.0
    elif view_count > 0:
        score += 1.0

    # 12. Upload recency
    score += _score_recency(result.get("upload_date") or "")

    raw_score = max(0.0, min(100.0, score))

    # 13. Historical performance bonus (-15 to +15)
    history_bonus = 0.0
    if history:
        total = history.get("total_uses", 0)
        successful = history.get("successful_plays", 0)
        if total >= 3:  # need at least 3 data points
            rate = successful / total
            history_bonus = (rate - 0.5) * 30.0  # maps [0, 1] → [-15, +15]
        # Also factor in avg quality rating from DB
        avg_q = history.get("avg_quality_score", 5.0)
        history_bonus += (avg_q - 5.0) * 1.0  # ±5 points based on quality

    final_score = max(0.0, min(100.0, raw_score + history_bonus))
    return raw_score, history_bonus, final_score


def _score_duration(duration_seconds: Optional[int]) -> float:
    """Return 0-15 based on how well the duration matches a typical episode."""
    if not duration_seconds:
        return 5.0  # unknown — neutral

    if EPISODE_DURATION["ideal_min"] <= duration_seconds <= EPISODE_DURATION["ideal_max"]:
        return 15.0  # perfect
    elif EPISODE_DURATION["min"] <= duration_seconds <= EPISODE_DURATION["max"]:
        return 8.0   # acceptable
    elif duration_seconds < EPISODE_DURATION["min"]:
        # Very short — probably a clip
        ratio = duration_seconds / EPISODE_DURATION["min"]
        return max(0.0, ratio * 5.0)
    else:
        # Very long — maybe a compilation?
        return 4.0


def _score_recency(upload_date: str) -> float:
    """Return 0-5 based on how recently the video was uploaded."""
    if not upload_date:
        return 2.0
    try:
        if "T" in upload_date:
            dt = datetime.fromisoformat(upload_date.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(upload_date[:10], "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
        days_old = (datetime.now(timezone.utc) - dt).days
        if days_old < 30:
            return 5.0
        elif days_old < 180:
            return 3.0
        elif days_old < 365:
            return 2.0
        else:
            return 1.0
    except Exception:
        return 2.0
