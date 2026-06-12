-- Spatial RPC pair for the commute cache table (already declared in schema.sql).
-- A route from within p_radius_m of a known origin/destination pair counts as
-- a cache hit, so we don't re-pay Ola Maps for every micro-variation of a
-- coordinate (esp. since geocoding precision is ~10m).

CREATE EXTENSION IF NOT EXISTS postgis;

-- Ensure the GIST index actually exists (schema.sql has it commented out).
CREATE INDEX IF NOT EXISTS idx_commute_cache_geom
    ON commute_cache USING GIST (source_location);

-- We also need the destination point on each row to make the radius lookup
-- meaningful. Add the column lazily so this migration is idempotent.
ALTER TABLE commute_cache
    ADD COLUMN IF NOT EXISTS dest_location GEOMETRY(Point, 4326);

CREATE INDEX IF NOT EXISTS idx_commute_cache_dest_geom
    ON commute_cache USING GIST (dest_location);

CREATE OR REPLACE FUNCTION lookup_commute_cache(
    p_origin_lat DOUBLE PRECISION,
    p_origin_lng DOUBLE PRECISION,
    p_dest_lat   DOUBLE PRECISION,
    p_dest_lng   DOUBLE PRECISION,
    p_radius_m   INT
)
RETURNS TABLE (commute_time_mins INT) AS $$
DECLARE
    origin_pt geography := ST_SetSRID(ST_MakePoint(p_origin_lng, p_origin_lat), 4326)::geography;
    dest_pt   geography := ST_SetSRID(ST_MakePoint(p_dest_lng,   p_dest_lat),   4326)::geography;
BEGIN
    RETURN QUERY
    SELECT c.commute_time_mins
      FROM commute_cache c
     WHERE c.dest_location IS NOT NULL
       AND ST_DWithin(c.source_location::geography, origin_pt, p_radius_m)
       AND ST_DWithin(c.dest_location::geography,   dest_pt,   p_radius_m)
     ORDER BY c.created_at DESC
     LIMIT 1;
END;
$$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE FUNCTION store_commute_cache(
    p_origin_lat DOUBLE PRECISION,
    p_origin_lng DOUBLE PRECISION,
    p_dest_lat   DOUBLE PRECISION,
    p_dest_lng   DOUBLE PRECISION,
    p_commute_time_mins INT
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO commute_cache (source_location, dest_location, commute_time_mins)
    VALUES (
        ST_SetSRID(ST_MakePoint(p_origin_lng, p_origin_lat), 4326),
        ST_SetSRID(ST_MakePoint(p_dest_lng,   p_dest_lat),   4326),
        p_commute_time_mins
    );
END;
$$ LANGUAGE plpgsql;
