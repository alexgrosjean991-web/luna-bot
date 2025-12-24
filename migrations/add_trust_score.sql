-- Migration: Add trust_score column for Luna V7 trust system
-- Run this migration on the production database

-- Add trust_score column (default 50 = medium trust)
ALTER TABLE users ADD COLUMN IF NOT EXISTS trust_score INTEGER DEFAULT 50;

-- Add last_trust_update timestamp
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_trust_update TIMESTAMP WITH TIME ZONE;

-- Add luna_last_state for tracking Luna's emotional state
ALTER TABLE users ADD COLUMN IF NOT EXISTS luna_last_state VARCHAR(20) DEFAULT 'neutral';

-- Add unlocked_secrets as JSONB array
ALTER TABLE users ADD COLUMN IF NOT EXISTS unlocked_secrets JSONB DEFAULT '[]'::jsonb;

-- Index for trust_score queries
CREATE INDEX IF NOT EXISTS idx_users_trust_score ON users(trust_score);

-- Verify columns were added
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'users'
AND column_name IN ('trust_score', 'last_trust_update', 'luna_last_state', 'unlocked_secrets');
