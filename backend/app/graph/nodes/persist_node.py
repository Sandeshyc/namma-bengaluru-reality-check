import asyncio
import logging
from typing import Any, Dict, Iterable, List, Optional

from app.graph.nodes._decorator import node
from app.models.schemas import AgentState
from app.services.supabase_client import get_supabase

logger = logging.getLogger(__name__)


def _vector_to_pg_literal(vec: Optional[Iterable[float]]) -> Optional[str]:
    """pgvector string literal '[0.1,0.2,...]' or None if there's no vector."""
    if vec is None:
        return None
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"


def _restrictions(parsed) -> List[str]:
    """Pydantic List[str] field — defensive against the field being missing."""
    if parsed is None:
        return []
    raw = getattr(parsed, "restrictions", None) or []
    return [str(r) for r in raw]


@node("persist", timeout=8.0, fatal=False)
async def process(state: AgentState) -> Dict[str, Any]:
    """
    Write the finalized listing (including commute children and embedding)
    into rental_listings via the insert_rental_listing RPC.

    This node runs at the very end of the graph, on BOTH the success path
    (post-scoring) and the duplicate path. Persisting duplicate detections
    too lets us track how often dedup fires for analytics; the is_duplicate
    flag keeps them out of future match_listings results.
    """
    client = get_supabase()
    if client is None:
        logger.warning("Supabase client not configured; skipping persist.")
        return {}

    parsed = state.get("parsed_listing")
    scorecard = state.get("scorecard")
    embedding = state.get("embedding")

    params = {
        "p_raw_text": state.get("raw_text"),
        "p_source_platform": state.get("source_platform") or "manual",
        "p_source_msg_id": state.get("source_msg_id") or "",
        "p_rent_amount": getattr(parsed, "rent_amount", None) if parsed else None,
        "p_security_deposit": getattr(parsed, "security_deposit", None) if parsed else None,
        "p_bhk_type": getattr(parsed, "bhk_type", None) if parsed else None,
        "p_raw_location": getattr(parsed, "raw_location", None) if parsed else None,
        "p_preferred_gender": getattr(parsed, "preferred_gender", None) if parsed else None,
        "p_restrictions": _restrictions(parsed),
        "p_latitude": state.get("latitude"),
        "p_longitude": state.get("longitude"),
        "p_geocode_confidence": state.get("geocode_confidence"),
        "p_geocode_provider": state.get("geocode_provider"),
        "p_commutes": state.get("commutes") or {},
        "p_water_risk_level": state.get("water_risk_level"),
        "p_cauvery_stage": state.get("cauvery_stage"),
        "p_gba_corporation": state.get("gba_corporation"),
        "p_gba_ward_name": state.get("gba_ward_name"),
        "p_livability_score": getattr(scorecard, "total_score", None) if scorecard else None,
        "p_is_duplicate": bool(state.get("is_duplicate")),
        "p_duplicate_of": state.get("duplicate_of"),
        "p_embedding": _vector_to_pg_literal(embedding),
        # Tier-2 building-level water signals extracted from the listing text.
        # All Optional[bool] — None means "the listing was silent".
        "p_cauvery_mentioned": getattr(parsed, "cauvery_mentioned", None) if parsed else None,
        "p_borewell_mentioned": getattr(parsed, "borewell_mentioned", None) if parsed else None,
        "p_water_24x7": getattr(parsed, "water_24x7", None) if parsed else None,
        "p_rwh_mentioned": getattr(parsed, "rwh_mentioned", None) if parsed else None,
        "p_tanker_mentioned": getattr(parsed, "tanker_mentioned", None) if parsed else None,
    }

    try:
        res = await asyncio.to_thread(
            lambda: client.rpc("insert_rental_listing", params).execute()
        )
    except Exception as e:
        # Don't take down the whole pipeline if the DB hiccups — the scorecard
        # is still valid in-memory and worth returning. Decorator records the
        # structured error and (thanks to the duplicate-protection rule) won't
        # downgrade a "duplicate" status to "partial".
        logger.error("insert_rental_listing RPC failed: %s", e)
        raise  # decorator catches it, marks pipeline status appropriately

    new_id = res.data if not isinstance(res.data, (list, dict)) else (
        res.data[0] if isinstance(res.data, list) and res.data else
        res.data.get("id") if isinstance(res.data, dict) else None
    )
    if not new_id:
        logger.error("insert_rental_listing returned no id: %r", res.data)
        return {}

    logger.info("Persisted listing id=%s (is_duplicate=%s)", new_id, params["p_is_duplicate"])
    return {"id": str(new_id)}
