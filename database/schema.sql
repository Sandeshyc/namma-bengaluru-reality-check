-- Enable extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;

-- Core listings table
CREATE TABLE IF NOT EXISTS rental_listings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    source_platform VARCHAR(20),     -- 'telegram' | 'manual'
    source_msg_id VARCHAR(50),
    raw_text TEXT NOT NULL,
    rent_amount INT,
    security_deposit INT,
    bhk_type VARCHAR(20),
    raw_location TEXT,
    preferred_gender VARCHAR(10),
    restrictions TEXT[],
    latitude DECIMAL(9,6),
    longitude DECIMAL(9,6),
    geocode_confidence DECIMAL(3,2),
    geocode_provider VARCHAR(20),    -- 'locationiq' | 'mappls' | 'google_maps'
    -- Commute results live in a normalized child table `commute_results`
    -- (see database/migrations/005_persist_listing.sql) keyed on
    -- (listing_id, tech_park_id). This keeps adding a tech park to the JSON
    -- file from requiring a schema migration.
    water_risk_level VARCHAR(20),    -- 'low' | 'medium' | 'high' | 'critical'
    cauvery_stage VARCHAR(40),       -- 'Cauvery Stage 1' / 'Stage 4 Phase 2' etc.
    gba_corporation VARCHAR(50),
    gba_ward_name VARCHAR(100),
    livability_score INT,
    is_duplicate BOOLEAN DEFAULT FALSE,
    duplicate_of UUID REFERENCES rental_listings(id),
    embedding VECTOR(768),            -- Gemini embedding dimension
    -- Building-level water signals extracted from listing text (Tier 2 of
    -- the water scoring rework). All nullable: NULL means "listing was silent".
    cauvery_mentioned BOOLEAN,
    borewell_mentioned BOOLEAN,
    water_24x7 BOOLEAN,
    rwh_mentioned BOOLEAN,
    tanker_mentioned BOOLEAN
);

-- Spatial commute cache (PostGIS)
CREATE TABLE IF NOT EXISTS commute_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tech_park_name VARCHAR(50),
    source_location GEOMETRY(Point, 4326),
    commute_time_mins INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
-- CREATE INDEX idx_commute_cache_geom ON commute_cache USING GIST (source_location);

-- API quota tracking
CREATE TABLE IF NOT EXISTS api_quota_tracker (
    id SERIAL PRIMARY KEY,
    api_name VARCHAR(30),         -- 'ola_maps' | 'locationiq' | 'gemini'
    call_count INT DEFAULT 0,
    period_start TIMESTAMPTZ DEFAULT DATE_TRUNC('month', NOW()),
    UNIQUE(api_name, period_start)
);

-- Tech Parks reference table (Optional, but good for structured reference)
CREATE TABLE IF NOT EXISTS tech_parks (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    latitude DECIMAL(9,6) NOT NULL,
    longitude DECIMAL(9,6) NOT NULL
);

-- Normalized commute results child table (one row per (listing, park)).
-- Replaces the previous denormalized commute_* columns.
CREATE TABLE IF NOT EXISTS commute_results (
    listing_id    UUID    NOT NULL REFERENCES rental_listings(id) ON DELETE CASCADE,
    tech_park_id  VARCHAR(50) NOT NULL,
    minutes       INT     NOT NULL CHECK (minutes >= 0),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (listing_id, tech_park_id)
);
CREATE INDEX IF NOT EXISTS idx_commute_results_listing
    ON commute_results (listing_id);

-- Data retention policy: auto-delete listings > 90 days
-- (Critical: Supabase free tier = 500MB. With pgvector embeddings ~6KB/row
--  + PostGIS overhead, we can store ~40K-60K listings. Pruning is essential.)
CREATE OR REPLACE FUNCTION prune_old_listings()
RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM rental_listings WHERE created_at < NOW() - INTERVAL '90 days';
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Set up trigger for pruning on insert
DROP TRIGGER IF EXISTS prune_old_listings_trigger ON rental_listings;
CREATE TRIGGER prune_old_listings_trigger
AFTER INSERT ON rental_listings
FOR EACH STATEMENT
EXECUTE FUNCTION prune_old_listings();
