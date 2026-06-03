CREATE TABLE IF NOT EXISTS account_state (
    id INTEGER PRIMARY KEY,
    high_watermark DOUBLE PRECISION NOT NULL
);

INSERT INTO account_state (id, high_watermark)
VALUES (1, 0.0)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS trade_oracle_audit_events (
    event_id TEXT PRIMARY KEY,
    created_at_utc TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    run_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    status TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_trade_oracle_audit_events_created_at
    ON trade_oracle_audit_events(created_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_trade_oracle_audit_events_thread_id
    ON trade_oracle_audit_events(thread_id, created_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_trade_oracle_audit_events_run_id
    ON trade_oracle_audit_events(run_id, created_at_utc DESC);

CREATE TABLE IF NOT EXISTS trade_oracle_benchmark_events (
    event_id TEXT PRIMARY KEY,
    created_at_utc TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    cycle_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    execution_backend TEXT NOT NULL,
    benchmark_variant TEXT NOT NULL,
    status TEXT NOT NULL,
    decision TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_trade_oracle_benchmark_events_created_at
    ON trade_oracle_benchmark_events(created_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_trade_oracle_benchmark_events_cycle_id
    ON trade_oracle_benchmark_events(cycle_id, created_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_trade_oracle_benchmark_events_run_id
    ON trade_oracle_benchmark_events(run_id, created_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_trade_oracle_benchmark_events_thread_id
    ON trade_oracle_benchmark_events(thread_id, created_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_trade_oracle_benchmark_events_variant
    ON trade_oracle_benchmark_events(benchmark_variant, created_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_trade_oracle_benchmark_events_symbol
    ON trade_oracle_benchmark_events(symbol, created_at_utc DESC);

CREATE TABLE IF NOT EXISTS trade_oracle_pending_reviews (
    thread_id TEXT PRIMARY KEY,
    cycle_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    benchmark_variant TEXT NOT NULL,
    review_status TEXT NOT NULL,
    review_action TEXT NOT NULL,
    telegram_chat_id TEXT NOT NULL,
    telegram_message_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    candidate JSONB NOT NULL DEFAULT '{}'::jsonb,
    review_context JSONB NOT NULL DEFAULT '{}'::jsonb,
    account_state JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at_utc TIMESTAMPTZ NOT NULL,
    updated_at_utc TIMESTAMPTZ NOT NULL,
    reviewer TEXT NOT NULL,
    review_notes TEXT NOT NULL,
    cycle_outcome TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trade_oracle_pending_reviews_status
    ON trade_oracle_pending_reviews(review_status, updated_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_trade_oracle_pending_reviews_cycle
    ON trade_oracle_pending_reviews(cycle_id, updated_at_utc DESC);

CREATE TABLE IF NOT EXISTS trade_oracle_forward_journal (
    cycle_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    benchmark_variant TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    workflow_name TEXT NOT NULL,
    stage TEXT NOT NULL,
    outcome TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    pending_review BOOLEAN NOT NULL DEFAULT FALSE,
    transmit_succeeded BOOLEAN NOT NULL DEFAULT FALSE,
    benchmark_event_count INTEGER NOT NULL DEFAULT 0,
    thread_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at_utc TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trade_oracle_forward_journal_updated
    ON trade_oracle_forward_journal(updated_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_trade_oracle_forward_journal_outcome
    ON trade_oracle_forward_journal(outcome, updated_at_utc DESC);

CREATE TABLE IF NOT EXISTS trade_oracle_daemon_checkpoints (
    checkpoint_key TEXT PRIMARY KEY,
    checkpoint_value JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at_utc TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trade_oracle_daemon_checkpoints_updated
    ON trade_oracle_daemon_checkpoints(updated_at_utc DESC);
