-- Migration: Drop V7 legacy columns (replaced by V3 momentum system)
-- Date: 2024-12-24
--
-- Colonnes supprimées:
-- - current_level: remplacé par current_tier
-- - cooldown_remaining: remplacé par messages_since_climax
-- - messages_since_level_change: plus utilisé
--
-- Colonnes conservées:
-- - messages_this_session: utilisé par V3
-- - last_climax_at: utilisé par V8

-- Backup d'abord (optionnel, à exécuter manuellement si besoin)
-- CREATE TABLE users_backup_v7 AS SELECT * FROM users;

-- Suppression des colonnes V7 legacy
ALTER TABLE users DROP COLUMN IF EXISTS current_level;
ALTER TABLE users DROP COLUMN IF EXISTS cooldown_remaining;
ALTER TABLE users DROP COLUMN IF EXISTS messages_since_level_change;

-- Vérification
SELECT column_name FROM information_schema.columns
WHERE table_name = 'users'
ORDER BY ordinal_position;
