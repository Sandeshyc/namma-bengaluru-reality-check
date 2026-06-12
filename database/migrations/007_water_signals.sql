-- Persist the Tier-2 building-level water signals so we can re-score old
-- listings without re-running Gemini extraction. Five new BOOLEAN columns on
-- rental_listings + a new signature for insert_rental_listing.
--
-- Why redefine the RPC instead of CREATE OR REPLACE? Postgres treats functions
-- with different param counts as distinct overloads; we DROP the old one to
-- avoid shipping two versions that could be ambiguously resolved.

BEGIN;

-- ====================================================================
-- 1. New columns on rental_listings
-- ====================================================================

ALTER TABLE rental_listings
    ADD COLUMN IF NOT EXISTS cauvery_mentioned   BOOLEAN,
    ADD COLUMN IF NOT EXISTS borewell_mentioned  BOOLEAN,
    ADD COLUMN IF NOT EXISTS water_24x7          BOOLEAN,
    ADD COLUMN IF NOT EXISTS rwh_mentioned       BOOLEAN,
    ADD COLUMN IF NOT EXISTS tanker_mentioned    BOOLEAN;


-- ====================================================================
-- 2. Replace insert_rental_listing RPC with a wider signature
-- ====================================================================

-- Drop the v1 signature explicitly (Postgres doesn't auto-replace across
-- arg-count changes).
DROP FUNCTION IF EXISTS insert_rental_listing(
    TEXT, VARCHAR, VARCHAR,
    INT, INT, VARCHAR, TEXT,
    VARCHAR, TEXT[],
    DECIMAL, DECIMAL, DECIMAL, VARCHAR,
    JSONB,
    VARCHAR, VARCHAR, VARCHAR, VARCHAR,
    INT, BOOLEAN, UUID,
    TEXT
);

CREATE OR REPLACE FUNCTION insert_rental_listing(
    p_raw_text             TEXT,
    p_source_platform      VARCHAR(20),
    p_source_msg_id        VARCHAR(50),
    p_rent_amount          INT,
    p_security_deposit     INT,
    p_bhk_type             VARCHAR(20),
    p_raw_location         TEXT,
    p_preferred_gender     VARCHAR(10),
    p_restrictions         TEXT[],
    p_latitude             DECIMAL(9,6),
    p_longitude            DECIMAL(9,6),
    p_geocode_confidence   DECIMAL(3,2),
    p_geocode_provider     VARCHAR(20),
    p_commutes             JSONB,
    p_water_risk_level     VARCHAR(20),
    p_cauvery_stage        VARCHAR(40),
    p_gba_corporation      VARCHAR(50),
    p_gba_ward_name        VARCHAR(100),
    p_livability_score     INT,
    p_is_duplicate         BOOLEAN,
    p_duplicate_of         UUID,
    p_embedding            TEXT,
    p_cauvery_mentioned    BOOLEAN DEFAULT NULL,
    p_borewell_mentioned   BOOLEAN DEFAULT NULL,
    p_water_24x7           BOOLEAN DEFAULT NULL,
    p_rwh_mentioned        BOOLEAN DEFAULT NULL,
    p_tanker_mentioned     BOOLEAN DEFAULT NULL
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
        embedding,
        cauvery_mentioned, borewell_mentioned, water_24x7, rwh_mentioned, tanker_mentioned
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
        END,
        p_cauvery_mentioned, p_borewell_mentioned, p_water_24x7,
        p_rwh_mentioned, p_tanker_mentioned
    )
    RETURNING id INTO new_id;

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
