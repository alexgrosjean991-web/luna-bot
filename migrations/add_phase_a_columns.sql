-- Phase A: AHA moment + Intent detection
-- Run this on production: docker exec luna_postgres psql -U luna -d luna_db -f /migrations/add_phase_a_columns.sql

-- Intent de l'utilisateur (lonely/horny/curious)
ALTER TABLE users ADD COLUMN IF NOT EXISTS user_intent VARCHAR(20) DEFAULT NULL;

-- AHA moment déclenché
ALTER TABLE users ADD COLUMN IF NOT EXISTS aha_triggered BOOLEAN DEFAULT FALSE;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_users_intent ON users(user_intent);
