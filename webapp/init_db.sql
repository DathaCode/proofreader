-- ═══════════════════════════════════════════════════════════════
-- Sinhala Proofreader — PostgreSQL schema
-- Runs automatically on first `docker compose up` (empty data volume).
-- ═══════════════════════════════════════════════════════════════

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── USERS ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username        VARCHAR(50)  UNIQUE NOT NULL,
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(20)  NOT NULL DEFAULT 'user'
                    CHECK (role IN ('user','admin','moderator')),
    is_active       BOOLEAN NOT NULL DEFAULT true,
    is_approved     BOOLEAN NOT NULL DEFAULT false,
    full_name       VARCHAR(100),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login      TIMESTAMPTZ,
    login_count     INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT valid_email CHECK (email ~* '^[^@]+@[^@]+\.[^@]+$')
);

-- Default admin user (password: admin1234 — CHANGE AFTER FIRST LOGIN).
-- NOTE: this is a plain (unsalted) SHA-256 hex digest. auth.hash_password()
-- produces exactly the same digest so this seeded login works.
INSERT INTO users (username, email, password_hash, role,
                   is_active, is_approved, full_name)
VALUES (
    'admin',
    'admin@sinhalaproof.local',
    encode(sha256('admin1234'::bytea), 'hex'),
    'admin', true, true, 'System Administrator'
) ON CONFLICT DO NOTHING;

-- ── USER SESSIONS ───────────────────────────────────
CREATE TABLE IF NOT EXISTS user_sessions (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token VARCHAR(128) UNIQUE NOT NULL,
    ip_address    INET,
    user_agent    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at    TIMESTAMPTZ NOT NULL,
    last_activity TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active     BOOLEAN NOT NULL DEFAULT true
);
CREATE INDEX IF NOT EXISTS idx_sessions_token  ON user_sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_sessions_user   ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON user_sessions(is_active, expires_at);

-- ── CORRECTIONS ─────────────────────────────────────
-- `type` accepts the proofreading engine's own error types
-- (grammar_discord / encoding_error) as well as the short forms.
CREATE TABLE IF NOT EXISTS corrections (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    wrong       TEXT UNIQUE NOT NULL,
    correct     TEXT NOT NULL,
    type        VARCHAR(20) NOT NULL DEFAULT 'spelling'
                CHECK (type IN ('spelling','grammar','grammar_discord',
                                'encoding','encoding_error','punctuation')),
    lang        VARCHAR(5) NOT NULL DEFAULT 'si',
    count       INTEGER NOT NULL DEFAULT 1,
    confidence  FLOAT NOT NULL DEFAULT 0.75
                CHECK (confidence BETWEEN 0 AND 1),
    mode        VARCHAR(20) NOT NULL DEFAULT 'inject_only'
                CHECK (mode IN ('precheck','inject_only','disabled')),
    context     TEXT DEFAULT '',
    confirmed   BOOLEAN NOT NULL DEFAULT false,
    added_by    UUID REFERENCES users(id) ON DELETE SET NULL,
    source      VARCHAR(50) DEFAULT 'manual',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_corrections_mode  ON corrections(mode);
CREATE INDEX IF NOT EXISTS idx_corrections_count ON corrections(count DESC);
CREATE INDEX IF NOT EXISTS idx_corrections_wrong ON corrections(wrong);

-- ── PROOFREAD LOGS ──────────────────────────────────
CREATE TABLE IF NOT EXISTS proofread_logs (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id        UUID REFERENCES users(id) ON DELETE SET NULL,
    input_text     TEXT,
    corrected_text TEXT,
    errors_found   INTEGER DEFAULT 0,
    pre_fixed      INTEGER DEFAULT 0,
    gemini_errors  INTEGER DEFAULT 0,
    word_count     INTEGER DEFAULT 0,
    duration_ms    INTEGER DEFAULT 0,
    model_used     VARCHAR(50),
    lang           VARCHAR(5),           -- detected/forced text language (si/ta/en)
    ip_address     INET,
    status         VARCHAR(20) DEFAULT 'ok',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_logs_user ON proofread_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_logs_date ON proofread_logs(created_at DESC);

-- ── PASSWORD RESETS ─────────────────────────────────
CREATE TABLE IF NOT EXISTS password_resets (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reset_token VARCHAR(128) UNIQUE NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    used        BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_resets_token ON password_resets(reset_token);

-- ── APP CONFIG ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS app_config (
    key         VARCHAR(100) PRIMARY KEY,
    value       TEXT NOT NULL,
    description TEXT,
    updated_by  UUID REFERENCES users(id) ON DELETE SET NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO app_config (key, value, description) VALUES
    ('gemini_model',          'gemini-2.0-flash', 'Gemini model name'),
    ('confidence_threshold',  '0.75',  'Min confidence to show error'),
    ('max_errors_response',   '10',    'Max errors returned per request'),
    ('max_words_request',     '600',   'Max words per proofread request'),
    ('inject_top_n',          '40',    'Corrections to inject into prompt'),
    ('precheck_min_count',    '5',     'Corrections needed before precheck'),
    ('allow_registration',    'true',  'Allow public user registration'),
    ('require_approval',      'true',  'Admin must approve new users'),
    ('session_timeout_hours', '8',     'Session expiry in hours'),
    ('rate_limit_per_min',    '10',    'Max requests per user per minute'),
    ('max_concurrent',        '4',     'Simultaneous Gemini calls'),
    ('request_timeout',       '60',    'Gemini request timeout (seconds)')
ON CONFLICT (key) DO NOTHING;
