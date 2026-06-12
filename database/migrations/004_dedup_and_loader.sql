-- Two unrelated additions bundled into one batch so the dedup feature and
-- the ward loader can both land in a single Supabase trip:
--
--   1. match_listings  - PostGIS + pgvector RPC used by duplicate_node to
--      detect cross-posted listings (cursorrules section 2: spatial cache
--      before any new processing).
--
--   2. insert_gba_ward / truncate_gba_wards - helper RPCs used by
--      scripts/load_gba_wards.py to populate the empty gba_wards table from
--      data/processed/wards_master.geojson.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;


-- ====================================================================
-- 1. pgvector + PostGIS duplicate detection
-- ====================================================================

-- HNSW index for fast cosine-similarity lookups on the embedding column.
-- HNSW is preferred over IVFFlat for small/medium tables because it doesn't
-- require parameter tuning relative to row count. Supabase has shipped
-- pgvector with HNSW support since mid-2024.
CREATE INDEX IF NOT EXISTS idx_rental_listings_embedding_hnsw
    ON rental_listings USING hnsw (embedding vector_cosine_ops);

-- Also index on (latitude, longitude) for the spatial radius filter below.
-- A proper PostGIS geometry column would be faster, but since the existing
-- table stores lat/lng as DECIMAL we build the geography on the fly.
CREATE INDEX IF NOT EXISTS idx_rental_listings_geo
    ON rental_listings (latitude, longitude)
    WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

-- Match listings within p_radius_m AND above p_similarity_threshold cosine
-- similarity. Vector passed as TEXT (e.g. '[0.1,0.2,...]') and cast inside
-- the function — PostgREST can't reliably serialize a JSON array of floats
-- to pgvector's binary representation, so the string-cast path is the
-- portable choice.
CREATE OR REPLACE FUNCTION match_listings(
    p_embedding TEXT,
    p_lat       DOUBLE PRECISION,
    p_lng       DOUBLE PRECISION,
    p_radius_m  INT   DEFAULT 500,
    p_similarity_threshold FLOAT DEFAULT 0.92
)
RETURNS TABLE (id UUID, similarity FLOAT, distance_m DOUBLE PRECISION) AS $$
DECLARE
    query_vec VECTOR(768) := p_embedding::VECTOR(768);
    query_pt  geography   := ST_SetSRID(ST_MakePoint(p_lng, p_lat), 4326)::geography;
BEGIN
    RETURN QUERY
    SELECT
        l.id,
        (1 - (l.embedding <=> query_vec))::FLOAT AS similarity,
        ST_Distance(
            ST_SetSRID(ST_MakePoint(l.longitude::FLOAT, l.latitude::FLOAT), 4326)::geography,
            query_pt
        ) AS distance_m
    FROM rental_listings l
    WHERE l.embedding IS NOT NULL
      AND l.latitude  IS NOT NULL
      AND l.longitude IS NOT NULL
      AND l.is_duplicate = FALSE
      AND ST_DWithin(
            ST_SetSRID(ST_MakePoint(l.longitude::FLOAT, l.latitude::FLOAT), 4326)::geography,
            query_pt,
            p_radius_m
          )
      AND (1 - (l.embedding <=> query_vec)) >= p_similarity_threshold
    ORDER BY l.embedding <=> query_vec
    LIMIT 1;
END;
$$ LANGUAGE plpgsql STABLE;


-- ====================================================================
-- 2. gba_wards loader helpers
-- ====================================================================

-- Truncate is gated to this specific table so the loader can't accidentally
-- nuke anything else.
CREATE OR REPLACE FUNCTION truncate_gba_wards()
RETURNS VOID AS $$
BEGIN
    TRUNCATE TABLE gba_wards RESTART IDENTITY;
END;
$$ LANGUAGE plpgsql;

-- Insert a single ward from raw GeoJSON. ST_GeomFromGeoJSON parses on the
-- server so we don't have to convert to WKT on the Python side.
-- ST_Multi() coerces both Polygon and MultiPolygon inputs to the
-- MultiPolygon column type declared in 002_gba_wards.sql.
CREATE OR REPLACE FUNCTION insert_gba_ward(
    p_ward_name        VARCHAR(120),
    p_gba_corporation  VARCHAR(80),
    p_cauvery_stage    VARCHAR(40),
    p_groundwater_risk VARCHAR(40),
    p_geojson          TEXT
)
RETURNS INT AS $$
DECLARE
    new_id INT;
BEGIN
    INSERT INTO gba_wards (ward_name, gba_corporation, cauvery_stage, groundwater_risk, geom)
    VALUES (
        p_ward_name,
        p_gba_corporation,
        p_cauvery_stage,
        p_groundwater_risk,
        ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(p_geojson), 4326))
    )
    RETURNING id INTO new_id;
    RETURN new_id;
END;
$$ LANGUAGE plpgsql;
