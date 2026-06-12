-- GBA ward polygons + spatial lookup RPC.
-- Replaces the in-memory shapely linear scan in app/services/spatial.py with
-- a single PostGIS ST_Contains() call (cursorrules section 1: spatial joins
-- must live in PostGIS, not in Python memory).

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS gba_wards (
    id                SERIAL PRIMARY KEY,
    ward_name         VARCHAR(120) NOT NULL,
    gba_corporation   VARCHAR(80),
    cauvery_stage     VARCHAR(40),
    groundwater_risk  VARCHAR(40),
    geom              GEOMETRY(MultiPolygon, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_gba_wards_geom
    ON gba_wards USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_gba_wards_name
    ON gba_wards (ward_name);

-- Lookup RPC: ST_Contains is the spatial-index-aware way to answer
-- "which ward contains this point?". Returns at most one row.
CREATE OR REPLACE FUNCTION lookup_gba_ward(
    p_lat DOUBLE PRECISION,
    p_lng DOUBLE PRECISION
)
RETURNS TABLE (
    ward_name         VARCHAR(120),
    gba_corporation   VARCHAR(80),
    cauvery_stage     VARCHAR(40),
    groundwater_risk  VARCHAR(40)
) AS $$
BEGIN
    RETURN QUERY
    SELECT w.ward_name, w.gba_corporation, w.cauvery_stage, w.groundwater_risk
      FROM gba_wards w
     WHERE ST_Contains(
              w.geom,
              ST_SetSRID(ST_MakePoint(p_lng, p_lat), 4326)
           )
     LIMIT 1;
END;
$$ LANGUAGE plpgsql STABLE;
