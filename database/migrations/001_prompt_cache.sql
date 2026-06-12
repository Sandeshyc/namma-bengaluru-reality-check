-- Prompt cache for the extract_node Gemini calls.
-- Satisfies cursorrules section 2: every LLM hit must first attempt a
-- cryptographic lookup against a cache table.
--
-- Keyed on SHA256(raw_text + ":" + prompt_version) so prompt edits invalidate
-- cleanly without manual cache busts.

CREATE TABLE IF NOT EXISTS prompt_cache (
    sha256          CHAR(64) PRIMARY KEY,
    prompt_version  VARCHAR(16) NOT NULL,
    response_json   JSONB NOT NULL,
    hit_count       INT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prompt_cache_last_used
    ON prompt_cache (last_used_at);

-- TTL: drop cache entries older than 30 days on every insert (Supabase free
-- tier discipline). Cheap because the table stays small.
CREATE OR REPLACE FUNCTION prune_old_prompt_cache()
RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM prompt_cache WHERE last_used_at < NOW() - INTERVAL '30 days';
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS prune_old_prompt_cache_trigger ON prompt_cache;
CREATE TRIGGER prune_old_prompt_cache_trigger
AFTER INSERT ON prompt_cache
FOR EACH STATEMENT
EXECUTE FUNCTION prune_old_prompt_cache();

-- Lookup RPC: returns the cached row and bumps the hit counter atomically.
CREATE OR REPLACE FUNCTION lookup_prompt_cache(
    p_sha256 CHAR(64),
    p_prompt_version VARCHAR(16)
)
RETURNS TABLE (response_json JSONB) AS $$
BEGIN
    RETURN QUERY
    UPDATE prompt_cache
       SET hit_count = hit_count + 1,
           last_used_at = NOW()
     WHERE sha256 = p_sha256
       AND prompt_version = p_prompt_version
    RETURNING prompt_cache.response_json;
END;
$$ LANGUAGE plpgsql;

-- Upsert RPC: writes the cache entry, no-op on conflict (first writer wins).
CREATE OR REPLACE FUNCTION store_prompt_cache(
    p_sha256 CHAR(64),
    p_prompt_version VARCHAR(16),
    p_response_json JSONB
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO prompt_cache (sha256, prompt_version, response_json)
    VALUES (p_sha256, p_prompt_version, p_response_json)
    ON CONFLICT (sha256) DO NOTHING;
END;
$$ LANGUAGE plpgsql;
