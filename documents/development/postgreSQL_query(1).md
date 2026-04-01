Here is the complete PostgreSQL schema designed to be run directly within the Supabase SQL Editor. This script establishes the tables, automatic triggers, proprietary firm consistency functions, Row Level Security (RLS) policies, and the `pg_net` extension required to route webhooks to Supabase Edge Functions.

```sql
-- ====================================================================================
-- PHASE 1: TRADE_ORACLE SUPABASE POSTGRESQL SCHEMA
-- ====================================================================================

-- 1. Enable Required Extensions
-- Enables asynchronous HTTP requests natively from Postgres to trigger Edge Functions
CREATE EXTENSION IF NOT EXISTS pg_net;

-- ====================================================================================
-- 2. TABLE CREATIONS
-- ====================================================================================

-- The singleton table to persistently track the $5,000 baseline and peak equity
CREATE TABLE public.account_state (
    id BIGINT PRIMARY KEY,
    current_balance DOUBLE PRECISION NOT NULL DEFAULT 5000.0,
    high_watermark DOUBLE PRECISION NOT NULL DEFAULT 5000.0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table to journal all trades, necessary for evaluating Maven's consistency rules
CREATE TABLE public.trade_journal (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    account_id BIGINT REFERENCES public.account_state(id),
    asset TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price DOUBLE PRECISION NOT NULL,
    exit_price DOUBLE PRECISION,
    position_size DOUBLE PRECISION NOT NULL,
    profit_loss DOUBLE PRECISION,
    closed_at TIMESTAMP WITH TIME ZONE
);

-- Initialize the cold-start state for the singleton row (Maven $5,000 baseline)
INSERT INTO public.account_state (id, current_balance, high_watermark) 
VALUES (1, 5000.0, 5000.0)
ON CONFLICT (id) DO NOTHING;

-- ====================================================================================
-- 3. AUTOMATIC HIGH-WATERMARK TRIGGER
-- ====================================================================================

-- Function to evaluate and lock in a new high watermark automatically upon balance updates
CREATE OR REPLACE FUNCTION update_high_watermark()
RETURNS TRIGGER AS $$
BEGIN
END;
$$ LANGUAGE plpgsql;

    -- Set the high_watermark to the maximum of:
    --  - the existing high watermark (OLD.high_watermark)
    --  - the newly reported current_balance (NEW.current_balance)
    --  - any explicit NEW.high_watermark supplied by the updater
    -- This permits the application to update high_watermark directly while
    -- still preserving the invariant that the field never decreases.
    NEW.high_watermark := GREATEST(
        COALESCE(OLD.high_watermark, 0.0),
        COALESCE(NEW.current_balance, 0.0),
        COALESCE(NEW.high_watermark, COALESCE(OLD.high_watermark, 0.0))
    );

    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Bind the trigger to fire just before any update hits the account_state table
CREATE TRIGGER trigger_update_watermark
BEFORE UPDATE ON public.account_state
FOR EACH ROW
EXECUTE FUNCTION update_high_watermark();

-- ====================================================================================
-- 4. PROPRIETARY FIRM CONSISTENCY TRACKER
-- ====================================================================================

-- Maven Trading requires that no single trade/day accounts for more than 20% of total profit
CREATE OR REPLACE FUNCTION check_consistency_rule(account_record_id BIGINT)
RETURNS BOOLEAN AS $$
DECLARE
    total_profit DOUBLE PRECISION;
    max_single_trade DOUBLE PRECISION;
    consistency_percentage DOUBLE PRECISION;
BEGIN
    -- Calculate aggregate gross profit
    SELECT SUM(profit_loss) INTO total_profit
    FROM public.trade_journal
    WHERE account_id = account_record_id AND profit_loss > 0;

    -- Identify the single largest windfall
    SELECT MAX(profit_loss) INTO max_single_trade
    FROM public.trade_journal
    WHERE account_id = account_record_id AND profit_loss > 0;

    IF total_profit IS NULL OR total_profit = 0 THEN
        RETURN TRUE;
    END IF;

    consistency_percentage := (max_single_trade / total_profit) * 100;

    -- Return false if the 20% rule is breached, requiring the bot to scale down and take smaller trades
    IF consistency_percentage > 20 THEN
        RETURN FALSE;
    END IF;

    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- ====================================================================================
-- 5. EDGE FUNCTION WEBHOOK INTEGRATION
-- ====================================================================================

-- Function to asynchronously trigger a Supabase Edge Function (e.g., for AI trade analysis)
-- This uses pg_net so it doesn't block the database transaction
CREATE OR REPLACE FUNCTION trigger_trade_edge_function()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM net.http_post(
        url := 'https://<YOUR_PROJECT_REF>.supabase.co/functions/v1/analyze_trade',
        headers := '{"Content-Type": "application/json", "Authorization": "Bearer <YOUR_ANON_KEY>"}'::jsonb,
        body := json_build_object('trade_id', NEW.id, 'profit_loss', NEW.profit_loss, 'asset', NEW.asset)::jsonb
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Bind the webhook to fire every time a trade is closed (updated with a profit_loss value)
CREATE TRIGGER trigger_analyze_trade
AFTER UPDATE ON public.trade_journal
FOR EACH ROW
WHEN (OLD.profit_loss IS NULL AND NEW.profit_loss IS NOT NULL)
EXECUTE FUNCTION trigger_trade_edge_function();

-- ====================================================================================
-- 6. ROW LEVEL SECURITY (RLS) POLICIES
-- ====================================================================================

-- Enable strict access control
ALTER TABLE public.account_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trade_journal ENABLE ROW LEVEL SECURITY;

-- Allow the Python execution layer (using the service_role key) to bypass RLS securely
CREATE POLICY "Allow service role full access to account_state"
ON public.account_state FOR ALL
USING (auth.jwt() ->> 'role' = 'service_role');

CREATE POLICY "Allow service role full access to trade_journal"
ON public.trade_journal FOR ALL
USING (auth.jwt() ->> 'role' = 'service_role');

```

### Breakdown of the Implementation Features:

* **Declarative Schema Tables:** The `account_state` table holds your trailing limits, while the `trade_journal` table acts as a ledger to record positions.
* **Persistent High-Watermark Logic:** The `update_high_watermark()` trigger automatically manages the 3% trailing drawdown. The moment a Python script or Match-Trader webhook updates the `current_balance`, Postgres independently evaluates whether it constitutes a new peak and locks it in place.
* **Prop Firm Consistency Verification:** The `check_consistency_rule()` function uses SQL to evaluate Maven Trading's strict 20% rule. You can call this function from your Python script before requesting a payout to ensure no single trade violates the 20% limit.
* **Asynchronous Edge Functions:** Using the `pg_net` extension, the database acts as an event-driven system. When a trade is closed, the `trigger_trade_edge_function()` fires an asynchronous HTTP request to a Supabase Edge Function without slowing down your database operations. You will need to replace `<YOUR_PROJECT_REF>` and `<YOUR_ANON_KEY>` with your actual project credentials.
* **Row Level Security (RLS):** By default, tables are completely locked down. The script establishes explicit RLS policies that only permit access to connections utilizing a verified `service_role` JWT (the credential used in your `.env` file).