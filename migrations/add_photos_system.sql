-- Migration: Add photos system columns
-- Run with: psql -U luna -d luna_db -f migrations/add_photos_system.sql

-- Photos sent history (JSON array with path, type, sent_at)
ALTER TABLE users ADD COLUMN IF NOT EXISTS photos_sent JSONB DEFAULT '[]'::jsonb;

-- Last photo sent timestamp
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_photo_at TIMESTAMP WITH TIME ZONE DEFAULT NULL;

-- Total photos count
ALTER TABLE users ADD COLUMN IF NOT EXISTS photos_count INTEGER DEFAULT 0;

-- Verify columns
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'users'
AND column_name IN ('photos_sent', 'last_photo_at', 'photos_count');
