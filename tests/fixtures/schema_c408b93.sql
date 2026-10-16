CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE COLLATE NOCASE,
  email TEXT UNIQUE COLLATE NOCASE,
  display_name TEXT,
  pw_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'user',
  status TEXT NOT NULL DEFAULT 'active',
  must_change_pw INTEGER NOT NULL DEFAULT 0,
  initial_pw_hash TEXT,
  cad_quota INTEGER,
  created_at TEXT NOT NULL,
  last_login TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL, expires_at TEXT NOT NULL, last_seen TEXT, ip TEXT, ua TEXT
);
CREATE TABLE IF NOT EXISTS invites (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token_hash TEXT NOT NULL UNIQUE,
  email TEXT, role TEXT NOT NULL DEFAULT 'user', cad_quota INTEGER,
  created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
  used_at TEXT, used_by INTEGER REFERENCES users(id) ON DELETE SET NULL, revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS resets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token_hash TEXT NOT NULL UNIQUE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_by INTEGER, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, used_at TEXT
);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, user_id INTEGER, actor TEXT, action TEXT NOT NULL,
  detail TEXT, ip TEXT
);
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL, created_at TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0,
  ctrl_x REAL, ctrl_y REAL,
  color TEXT, material TEXT, transparent INTEGER, finish TEXT, material_user INTEGER NOT NULL DEFAULT 0, cad_check TEXT
);
CREATE TABLE IF NOT EXISTS photos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  filename TEXT, view TEXT NOT NULL DEFAULT 'top', format TEXT, status TEXT, max_err REAL,
  analysis TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS measurements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  photo_id INTEGER REFERENCES photos(id) ON DELETE SET NULL,
  seq INTEGER NOT NULL, label TEXT NOT NULL, kind TEXT NOT NULL,
  value REAL, unit TEXT NOT NULL DEFAULT 'mm', unc REAL, data TEXT,
  critical INTEGER NOT NULL DEFAULT 0, caliper REAL, fit TEXT,
  source TEXT NOT NULL DEFAULT 'user', accepted INTEGER NOT NULL DEFAULT 1, reason TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  name TEXT NOT NULL, request TEXT NOT NULL, status TEXT NOT NULL,
  messages TEXT NOT NULL DEFAULT '[]', current_version INTEGER, error TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  version INTEGER NOT NULL, trigger TEXT NOT NULL, request_text TEXT,
  code TEXT, claude_text TEXT, meta TEXT, status TEXT NOT NULL,
  error TEXT, result TEXT, checks TEXT, usage TEXT, seconds REAL, created_at TEXT NOT NULL,
  UNIQUE(job_id, version)
);
CREATE TABLE IF NOT EXISTS job_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  ts TEXT NOT NULL, level TEXT NOT NULL DEFAULT 'info', msg TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY, value TEXT, updated_at TEXT NOT NULL, updated_by INTEGER
);
CREATE TABLE IF NOT EXISTS parts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  photo_id INTEGER NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL, label TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'body',
  data TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'auto',
  scale REAL NOT NULL DEFAULT 1.0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_dims(
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  label TEXT NOT NULL, label_norm TEXT NOT NULL,
  grp TEXT NOT NULL, value REAL NOT NULL, job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL, dim_id TEXT,
  note TEXT, created_at TEXT NOT NULL,
  UNIQUE(project_id, label_norm));
CREATE INDEX IF NOT EXISTS ix_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS ix_photos_project ON photos(project_id);
CREATE INDEX IF NOT EXISTS ix_meas_project ON measurements(project_id);
CREATE INDEX IF NOT EXISTS ix_jobs_user ON jobs(user_id);
CREATE INDEX IF NOT EXISTS ix_jobs_project ON jobs(project_id);
CREATE INDEX IF NOT EXISTS ix_log_job ON job_log(job_id);
CREATE INDEX IF NOT EXISTS ix_parts_photo ON parts(photo_id);
-- Stand nach dem alten _migrate (c408b93): Spalte measurements.part_id und ihr Index
ALTER TABLE measurements ADD COLUMN part_id INTEGER REFERENCES parts(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_meas_part ON measurements(part_id);
