-- Run this in your Supabase SQL Editor

-- טבלת היסטוריית מקורות (לימוד)
CREATE TABLE IF NOT EXISTS source_history (
  id          SERIAL PRIMARY KEY,
  domain      TEXT UNIQUE NOT NULL,
  total_uses  INTEGER DEFAULT 0,
  successful_plays INTEGER DEFAULT 0,
  failed_plays     INTEGER DEFAULT 0,
  avg_quality_score FLOAT DEFAULT 5.0,
  last_used   TIMESTAMP WITH TIME ZONE,
  created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- טבלת cache לתוצאות חיפוש
CREATE TABLE IF NOT EXISTS search_cache (
  id           SERIAL PRIMARY KEY,
  series_name  TEXT NOT NULL,
  episode_num  INTEGER NOT NULL,
  results_json TEXT NOT NULL,
  cached_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(series_name, episode_num)
);

-- אינדקסים
CREATE INDEX IF NOT EXISTS idx_source_history_domain
  ON source_history(domain);

CREATE INDEX IF NOT EXISTS idx_search_cache_lookup
  ON search_cache(series_name, episode_num);

-- Row Level Security (RLS) — disable for service role
ALTER TABLE source_history DISABLE ROW LEVEL SECURITY;
ALTER TABLE search_cache   DISABLE ROW LEVEL SECURITY;
