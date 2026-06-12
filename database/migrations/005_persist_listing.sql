-- Persistence layer for scored listings.
--
-- Two structural changes plus one RPC, all in a single transaction so the
-- schema stays consistent:
--
--   1. Normalize commutes: replace the five named `commute_*_mins` columns
--      with a child table `commute_results(listing_id, tech_park_id, minutes)`.
--      Adding a new tech park no longer requires a schema migration.
--
--   2. Drop the obsolete named columns. WARNING: existing data in those
--      columns is dropped with them. Run before significant ingestion.
--
--   3. Add `insert_rental_listing` RPC that atomically writes the parent
--      row + commute child rows in one transaction, returning the new UUID.

BEGIN;

-- ====================================================================
-- 1. New normalized child table
-- ====================================================================

CREATE TABLE IF NOT EXISTS commute_results (
    listing_id    UUID    NOT NULL REFERENCES rental_listings(id) ON DELETE CASCADE,
    tech_park_id  VARCHAR(50) NOT NULL,
    minutes       INT     NOT NULL CHECK (minutes >= 0),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (listing_id, tech_park_id)
    -- Intentionally no FK to tech_parks(id) so a new park ID in JSON doesn't
    -- crash inserts before someone runs seed_tech_parks.sql. Add the FK once
    -- your reference data is reliably seeded.
);

CREATE INDEX IF NOT EXISTS idx_commute_results_listing
    ON commute_results (listing_id);


-- ====================================================================
-- 2. Drop obsolete named commute columns
-- ====================================================================

ALTER TABLE rental_listings
    DROP COLUMN IF EXISTS commute_manyata_mins,
    DROP COLUMN IF EXISTS commute_whitefield_mins,
    DROP COLUMN IF EXISTS commute_ecity_mins,
    DROP COLUMN IF EXISTS commute_bagmane_mins,
    DROP COLUMN IF EXISTS commute_marathahalli_mins;


-- ====================================================================
-- 3. insert_rental_listing RPC
-- ====================================================================

-- Writes the listing row + iterates the commutes JSONB to insert child rows.
-- Embedding passed as TEXT (e.g. '[0.1,0.2,...]') and cast to VECTOR(768)
-- inside the function — same rationale as match_listings in migration 004.
CREATE OR REPLACE FUNCTION insert_rental_listing(
    p_raw_text            TEXT,
    p_source_platform     VARCHAR(20),
    p_source_msg_id       VARCHAR(50),
    p_rent_amount         INT,
    p_security_deposit    INT,
    p_bhk_type            VARCHAR(20),
    p_raw_location        TEXT,
    p_preferred_gender    VARCHAR(10),
    p_restrictions        TEXT[],
    p_latitude            DECIMAL(9,6),
    p_longitude           DECIMAL(9,6),
    p_geocode_confidence  DECIMAL(3,2),
    p_geocode_provider    VARCHAR(20),
    p_commutes            JSONB,           -- {"manyata": 30, "whitefield": 45, ...}
    p_water_risk_level    VARCHAR(20),
    p_cauvery_stage       VARCHAR(10),
    p_gba_corporation     VARCHAR(50),
    p_gba_ward_name       VARCHAR(100),
    p_livability_score    INT,
    p_is_duplicate        BOOLEAN,
    p_duplicate_of        UUID,
    p_embedding           TEXT             -- '[0.1,0.2,...]' or NULL
)
RETURNS UUID AS $$
DECLARE
    new_id   UUID;
    park_id  TEXT;
    park_min TEXT;
BEGIN
    INSERT INTO rental_listings (
        raw_text, source_platform, source_msg_id,
        rent_amount, security_deposit, bhk_type, raw_location,
        preferred_gender, restrictions,
        latitude, longitude, geocode_confidence, geocode_provider,
        water_risk_level, cauvery_stage, gba_corporation, gba_ward_name,
        livability_score, is_duplicate, duplicate_of,
        embedding
    ) VALUES (
        p_raw_text, p_source_platform, p_source_msg_id,
        p_rent_amount, p_security_deposit, p_bhk_type, p_raw_location,
        p_preferred_gender, p_restrictions,
        p_latitude, p_longitude, p_geocode_confidence, p_geocode_provider,
        p_water_risk_level, p_cauvery_stage, p_gba_corporation, p_gba_ward_name,
        p_livability_score, COALESCE(p_is_duplicate, FALSE), p_duplicate_of,
        CASE WHEN p_embedding IS NOT NULL AND p_embedding <> ''
             THEN p_embedding::VECTOR(768)
             ELSE NULL
        END
    )
    RETURNING id INTO new_id;

    -- Commute children. jsonb_each_text yields TEXT/TEXT pairs.
    IF p_commutes IS NOT NULL AND jsonb_typeof(p_commutes) = 'object' THEN
        FOR park_id, park_min IN
            SELECT key, value FROM jsonb_each_text(p_commutes)
        LOOP
            INSERT INTO commute_results (listing_id, tech_park_id, minutes)
            VALUES (new_id, park_id, park_min::INT)
            ON CONFLICT (listing_id, tech_park_id) DO NOTHING;
        END LOOP;
    END IF;

    RETURN new_id;
END;
$$ LANGUAGE plpgsql;

COMMIT;
