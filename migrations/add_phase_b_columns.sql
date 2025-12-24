-- Phase B: Gates + Investments
-- Run: docker exec luna_postgres psql -U luna -d luna_db -f /migrations/add_phase_b_columns.sql

-- Gates déclenchées (liste JSON)
ALTER TABLE users ADD COLUMN IF NOT EXISTS gates_triggered JSONB DEFAULT '[]'::jsonb;

-- Investment tracking
ALTER TABLE users ADD COLUMN IF NOT EXISTS investment_score INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS secrets_shared_count INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS compliments_given INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS questions_about_luna INTEGER DEFAULT 0;

-- Segment utilisateur
ALTER TABLE users ADD COLUMN IF NOT EXISTS user_segment VARCHAR(20) DEFAULT 'casual';
