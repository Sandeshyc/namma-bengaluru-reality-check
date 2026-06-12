import os
from supabase import create_client, Client
import logging

logger = logging.getLogger(__name__)

_supabase: Client = None

def get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        if not url or not key:
            logger.warning("Supabase credentials not found. DB operations will fail.")
            return None
        try:
            _supabase = create_client(url, key)
            logger.info("Supabase client initialized.")
        except Exception as e:
            logger.error(f"Failed to init Supabase: {e}")
    return _supabase

def check_quota(api_name: str) -> dict:
    """Check API quota for a given service."""
    client = get_supabase()
    if not client: return {"count": 0, "status": "unknown"}
    try:
        # Simplistic check - in reality, we'd query the api_quota_tracker table
        res = client.table("api_quota_tracker").select("call_count").eq("api_name", api_name).execute()
        if res.data:
            return {"count": res.data[0]['call_count'], "status": "ok"}
    except Exception as e:
        logger.error(f"Quota check failed for {api_name}: {e}")
    return {"count": 0, "status": "unknown"}

def get_user_from_token(token: str) -> dict:
    """Retrieve user details from Supabase using JWT token."""
    client = get_supabase()
    if not client:
        return None
    try:
        user_res = client.auth.get_user(token)
        if user_res and user_res.user:
            return {
                "id": str(user_res.user.id),
                "email": user_res.user.email
            }
    except Exception as e:
        logger.error(f"Failed to retrieve user from token: {e}")
    return None

