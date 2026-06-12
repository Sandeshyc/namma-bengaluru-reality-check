-- Create user_searches table to store listing checks linked to authenticated users.
BEGIN;

CREATE TABLE IF NOT EXISTS user_searches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL, -- references auth.users(id) in Supabase Auth
    listing_id UUID NOT NULL REFERENCES rental_listings(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    UNIQUE(user_id, listing_id)
);

CREATE INDEX IF NOT EXISTS idx_user_searches_user ON user_searches(user_id);

COMMIT;
