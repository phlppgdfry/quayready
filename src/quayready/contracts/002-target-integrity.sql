-- Add checked migration history to existing E1 target databases; retain every effect.
BEGIN IMMEDIATE;
CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, checksum TEXT NOT NULL, applied_at_ms INTEGER NOT NULL) STRICT;
PRAGMA user_version=2;
COMMIT;
