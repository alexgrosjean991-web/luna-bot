-- Phase C: Churn Prediction + Win-back
-- Run: cat migrations/add_phase_c_columns.sql | docker exec -i luna_postgres psql -U luna -d luna_db

-- Churn tracking
ALTER TABLE users ADD COLUMN IF NOT EXISTS churn_risk VARCHAR(20) DEFAULT 'low';
ALTER TABLE users ADD COLUMN IF NOT EXISTS churn_score FLOAT DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_churn_check TIMESTAMP WITH TIME ZONE DEFAULT NULL;

-- Win-back tracking
ALTER TABLE users ADD COLUMN IF NOT EXISTS winback_stage VARCHAR(20) DEFAULT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_winback_at TIMESTAMP WITH TIME ZONE DEFAULT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS winback_attempts INTEGER DEFAULT 0;

-- User timing profile
ALTER TABLE users ADD COLUMN IF NOT EXISTS peak_hours JSONB DEFAULT '[]'::jsonb;
ALTER TABLE users ADD COLUMN IF NOT EXISTS active_days JSONB DEFAULT '[]'::jsonb;
ALTER TABLE users ADD COLUMN IF NOT EXISTS avg_response_time FLOAT DEFAULT NULL;
