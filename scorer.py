"""
מערכת ניקוד ודירוג מקורות
===========================

שני שלבים:
  1. תנאי סף (GATES)   — מקור שלא עומד בהם נפסל לחלוטין
  2. יתרונות (BONUSES) — צוברים נקודות; מי שיש לו יותר — גבוה יותר ברשימה
"""

import re
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

# ─── קבועים ───────────────────────────────────────────────────────────────────

EPISODE_DURATION = {
    "min":       4 * 60,   # 4 דקות — מינימום מוחלט
    "ideal_min": 18 * 60,  # 18 דקות — אורך פרק קצר
    "ideal_max": 55 * 60,  # 55 דקות — אורך פרק ארוך
    "max":       90 * 60,  # 90 דקות — מקסימום מוחלט
}

SCAM_KEYWORDS = [
    "תקציר", "קליפ", "הייליטס", "highlights", "trailer", "טריילר",
    "promo", "פרומו", "תמצית", "behind the scenes", "מאחורי הקלעים",
    "bloopers", "teaser", "sneak peek", "extended preview",
    "ראיון", "interview", "making of",
]

DOMAIN_BASE: Dict[str, float] = {
    "youtube.com":      10.0,
    "mako.co.il":       12.0,
    "keshet12.co.il":   12.0,
    "kan.org.il":       12.0,
    "reshet.tv":        11.0,
    "yes.co.il":         9.0,
    "hot.net.il":        9.0,
    "dailymotion.com":   8.0,
    "vimeo.com":         7.0,
    "ok.ru":             5.0,
    "t.me":              5.0,
    "streamtape.com":    4.0,
    "uqload.com":        3.0,
    "vod.co.il":         5.0,
    "drive.google.com":  4.0,
}

# דומיינים שגויים ידועים — נפסלים אוטומטית בסף
BLOCKED_DOMAINS = set()  # מתמלא דינמית מהיסטוריה


# ─── שלב 1: תנאי סף ────────────────────────────────────────────────────────────

def passes_gates(
    result: Dict[str, Any],
    series_name: str = "",
    episode_num: int = 1,
    season_num: int = 1,
    domain_history: Optional[Dict] = None,
) -> Tuple[bool, str]:
    """
    בודק תנאי סף. מחזיר (True, "") אם עובר, (False, סיבה) אם נפסל.

    תנאים מחייבים:
      T1. שם הסדרה מופיע בכותרת
      T2. אין מילות מפתח של תקצירים/טריילרים
      T3. אורך הוידאו — אם ידוע — בטווח 4–90 דקות
      T4. מספר פרק — אם מופיע בכותרת — תואם
      T5. מספר עונה — אם מופיע בכותרת — תואם
      T6. הדומיין לא נכשל ב-80%+ מהשימושים (מינימום 5 שימושים)
    """
    title = (result.get("title") or "").lower().strip()
    domain = result.get("domain", "")

    # T1 — שם הסדרה חייב להופיע בכותרת
    if series_name:
        if series_name.lower().strip() not in title:
            return False, f"T1: שם הסדרה '{series_name}' לא בכותרת"

    # T2 — לא תקציר/טריילר
    for kw in SCAM_KEYWORDS:
        if kw in title:
            return False, f"T2: מילת סינון '{kw}' בכותרת"

    # T3 — אורך בטווח תקין
    duration = result.get("duration_seconds")
    if duration is not None:
        if duration < EPISODE_DURATION["min"]:
            return False, f"T3: אורך קצר מדי ({duration//60} דק')"
        if duration > EPISODE_DURATION["max"]:
            return False, f"T3: אורך ארוך מדי ({duration//60} דק')"

    # T4 — מספר פרק: אם מופיע בכותרת — חייב להיות נכון
    episode_mentions = re.findall(r'פרק\s*(\d+)', title)
    if episode_mentions:
        if not any(int(m) == episode_num for m in episode_mentions):
            return False, f"T4: פרק שגוי בכותרת (מצוין {episode_mentions}, מחפש {episode_num})"

    # T5 — מספר עונה: אם מופיע בכותרת — חייב להיות נכון
    season_mentions = re.findall(r'עונה\s*(\d+)', title)
    if season_mentions:
        if not any(int(m) == season_num for m in season_mentions):
            return False, f"T5: עונה שגויה בכותרת (מצוין {season_mentions}, מחפש {season_num})"

    # T6 — היסטוריית דומיין: חסום אם כישלון > 80% (מינימום 5 שימושים)
    if domain_history:
        total = domain_history.get("total_uses", 0)
        failed = domain_history.get("failed_plays", 0)
        if total >= 5 and failed / total >= 0.8:
            return False, f"T6: דומיין {domain} נכשל ב-{int(failed/total*100)}% מהמקרים"

    return True, ""


# ─── שלב 2: ניקוד יתרונות ─────────────────────────────────────────────────────

def score_bonuses(
    result: Dict[str, Any],
    episode_num: int = 1,
    season_num: int = 1,
    domain_history: Optional[Dict] = None,
) -> Tuple[float, float, float]:
    """
    מחשב ניקוד יתרונות. מחזיר (raw_score, history_bonus, final_score) — סקלה 0–100.

    יתרונות (סה"כ מקסימום ~110, נחתך ל-100):
      B1.  בסיס דומיין                    0–12
      B2.  איכות וידאו                    0–12
      B3.  חינמי                          +10
      B4.  ללא פרסומות                    +8
      B5.  ניתן להטמעה ישירה              +15
      B6.  מקור רשמי ישראלי               +10
      B7.  אורך אידיאלי                   0–15
      B8.  מספר פרק מאושר בכותרת         +15
      B9.  מספר עונה מאושר בכותרת        +10
      B10. כתוביות עברית                  +5
      B11. מספר צפיות                     0–10
      B12. טריות                          0–6
      ──────────────────────────────────  0–128 → נחתך ל-100
      B13. בונוס היסטוריה                 -15 עד +15
    """
    score = 0.0
    title = (result.get("title") or "").lower()
    domain = result.get("domain", "")

    # B1 — בסיס דומיין
    score += DOMAIN_BASE.get(domain, 3.0)

    # B2 — איכות וידאו
    quality_scores = {"1080p": 12.0, "auto": 9.0, "720p": 8.0,
                      "480p": 4.0, "360p": 2.0, "unknown": 5.0}
    score += quality_scores.get(result.get("quality") or "unknown", 5.0)

    # B3 — חינמי
    if result.get("is_free", True):
        score += 10.0

    # B4 — ללא פרסומות
    has_ads = result.get("has_ads")
    if has_ads is False:
        score += 8.0
    elif has_ads is None:
        score += 3.0

    # B5 — ניתן להטמעה
    if result.get("can_embed", False):
        score += 15.0

    # B6 — מקור רשמי ישראלי
    if result.get("is_official", False):
        score += 10.0

    # B7 — אורך אידיאלי
    score += _score_duration(result.get("duration_seconds"))

    # B8 — מספר פרק מאושר בכותרת
    ep_mentions = re.findall(r'פרק\s*(\d+)', title)
    if ep_mentions and any(int(m) == episode_num for m in ep_mentions):
        score += 15.0

    # B9 — מספר עונה מאושר בכותרת
    season_mentions = re.findall(r'עונה\s*(\d+)', title)
    if season_mentions and any(int(m) == season_num for m in season_mentions):
        score += 10.0

    # B10 — כתוביות עברית
    if result.get("has_hebrew_subtitles", False):
        score += 5.0

    # B11 — מספר צפיות
    views = result.get("view_count") or 0
    if views >= 100_000:
        score += 10.0
    elif views >= 10_000:
        score += 6.0
    elif views >= 1_000:
        score += 3.0
    elif views > 0:
        score += 1.0

    # B12 — טריות
    score += _score_recency(result.get("upload_date") or "")

    raw_score = max(0.0, min(100.0, score))

    # B13 — בונוס היסטוריה (-15 עד +15)
    history_bonus = 0.0
    if domain_history:
        total = domain_history.get("total_uses", 0)
        successful = domain_history.get("successful_plays", 0)
        if total >= 3:
            rate = successful / total
            history_bonus += (rate - 0.5) * 30.0
        avg_q = domain_history.get("avg_quality_score", 5.0)
        history_bonus += (avg_q - 5.0) * 1.0
        history_bonus = max(-15.0, min(15.0, history_bonus))

    final_score = max(0.0, min(100.0, raw_score + history_bonus))
    return raw_score, history_bonus, final_score


# ─── פונקציה ראשית (תאימות לאחור) ────────────────────────────────────────────

def score_result(
    result: Dict[str, Any],
    history: Optional[Dict] = None,
    episode_num: int = 1,
    series_name: str = "",
    season_num: int = 1,
) -> Tuple[float, float, float]:
    """ממשק אחיד: מריץ gates + bonuses. מחזיר (0,0,0) אם נפסל בגייט."""
    passed, reason = passes_gates(result, series_name, episode_num, season_num, history)
    if not passed:
        print(f"  ✗ נפסל [{result.get('domain','')}] {reason}")
        return 0.0, 0.0, 0.0
    return score_bonuses(result, episode_num, season_num, history)


# ─── עזר ──────────────────────────────────────────────────────────────────────

def _score_duration(duration_seconds: Optional[int]) -> float:
    if not duration_seconds:
        return 5.0
    if EPISODE_DURATION["ideal_min"] <= duration_seconds <= EPISODE_DURATION["ideal_max"]:
        return 15.0
    elif EPISODE_DURATION["min"] <= duration_seconds <= EPISODE_DURATION["max"]:
        return 8.0
    return 0.0


def _score_recency(upload_date: str) -> float:
    if not upload_date:
        return 2.0
    try:
        if "T" in upload_date:
            dt = datetime.fromisoformat(upload_date.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(upload_date[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        days_old = (datetime.now(timezone.utc) - dt).days
        if days_old < 30:
            return 6.0
        elif days_old < 180:
            return 4.0
        elif days_old < 365:
            return 2.0
        return 1.0
    except Exception:
        return 2.0
