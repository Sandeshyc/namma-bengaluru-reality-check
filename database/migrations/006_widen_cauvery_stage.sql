-- Widen rental_listings.cauvery_stage from VARCHAR(10) to VARCHAR(40).
--
-- The original schema.sql declared this as VARCHAR(10), but the actual
-- values produced by app/services/water_data.py routinely overflow:
--   "Cauvery Stage 1"        (15 chars)
--   "Stage 4 Phase 2"        (15 chars)
--   "Cauvery Stage 4 Phase 1" (~23 chars)
--
-- Symptom before this migration:
--   postgrest.exceptions.APIError: 'value too long for type character
--   varying(10)', 'code': '22001'
--
-- Widening a VARCHAR is a metadata-only change in Postgres — no table
-- rewrite, instant on any table size. Safe to run during traffic.

ALTER TABLE rental_listings
    ALTER COLUMN cauvery_stage TYPE VARCHAR(40);
