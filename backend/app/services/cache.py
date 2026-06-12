"""
SHA256-keyed prompt cache for LLM extraction calls.

Lives in Supabase (table `prompt_cache`, RPCs `lookup_prompt_cache` and
`store_prompt_cache`). Falls back to a no-op when Supabase isn't configured so
local dev / mock runs don't crash.
"""

import asyncio
import hashlib
import json
import logging
from typing import Any, Dict, Optional

from app.services.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def hash_payload(text: str) -> str:
    """Stable hex digest used as the cache primary key."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def get_extraction_cache(
    raw_text: str, prompt_version: str
) -> Optional[Dict[str, Any]]:
    """Return the cached extraction JSON or None on miss / config error."""
    client = get_supabase()
    if not client:
        return None

    sha = hash_payload(raw_text)
    try:
        # supabase-py is sync; offload so the event loop keeps moving.
        res = await asyncio.to_thread(
            lambda: client.rpc(
                "lookup_prompt_cache",
                {"p_sha256": sha, "p_prompt_version": prompt_version},
            ).execute()
        )
        if res and res.data:
            row = res.data[0] if isinstance(res.data, list) else res.data
            payload = row.get("response_json") if isinstance(row, dict) else None
            if payload:
                logger.info("prompt_cache HIT sha=%s..", sha[:8])
                return payload if isinstance(payload, dict) else json.loads(payload)
    except Exception as e:
        # Cache miss/RPC-missing is non-fatal; log at debug to avoid noise.
        logger.debug("prompt_cache lookup failed (non-fatal): %s", e)
    return None


async def set_extraction_cache(
    raw_text: str, prompt_version: str, payload: Dict[str, Any]
) -> None:
    client = get_supabase()
    if not client:
        return

    sha = hash_payload(raw_text)
    try:
        await asyncio.to_thread(
            lambda: client.rpc(
                "store_prompt_cache",
                {
                    "p_sha256": sha,
                    "p_prompt_version": prompt_version,
                    "p_response_json": payload,
                },
            ).execute()
        )
        logger.info("prompt_cache STORE sha=%s..", sha[:8])
    except Exception as e:
        logger.debug("prompt_cache store failed (non-fatal): %s", e)
