CREATE TABLE IF NOT EXISTS task_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_name TEXT NOT NULL,
  source TEXT,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  items_in INTEGER DEFAULT 0,
  items_out INTEGER DEFAULT 0,
  error TEXT
);

CREATE TABLE IF NOT EXISTS articles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  source_type TEXT NOT NULL,
  url TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  content TEXT,
  author TEXT,
  published_at TEXT,
  published_at_raw TEXT,
  published_at_confidence REAL DEFAULT 0,
  discovered_at TEXT NOT NULL,
  keyword TEXT,
  relevance_score REAL DEFAULT 0,
  sentiment TEXT DEFAULT 'unknown',
  risk_level TEXT DEFAULT 'normal',
  event_key TEXT,
  status TEXT DEFAULT 'valid'
);

CREATE INDEX IF NOT EXISTS idx_articles_discovered_at ON articles(discovered_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source);
CREATE INDEX IF NOT EXISTS idx_task_runs_started_at ON task_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS source_health (
  source TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'unknown',
  last_attempt_at TEXT,
  last_success_at TEXT,
  success_count INTEGER DEFAULT 0,
  failure_count INTEGER DEFAULT 0,
  last_error TEXT,
  items_last_run INTEGER DEFAULT 0
);
