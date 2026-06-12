import asyncio
import logging
from typing import Any, Dict

from langgraph.graph import StateGraph, END

import app.graph.nodes.civic_water_node as civic_water_node
import app.graph.nodes.commute_node as commute_node
import app.graph.nodes.duplicate_node as duplicate_node
import app.graph.nodes.extract_node as extract_node
import app.graph.nodes.geocode_node as geocode_node
import app.graph.nodes.persist_node as persist_node
import app.graph.nodes.scoring_node as scoring_node
from app.models.schemas import AgentState

logger = logging.getLogger(__name__)

# Hard ceiling for an entire pipeline invocation. Beyond this we abort and
# return a structured timeout response rather than letting the worker hang.
PIPELINE_TIMEOUT_SEC = 60.0


def _route_after_extract(state: AgentState) -> str:
    """Continue only if the LLM gave us a parseable listing."""
    parsed = state.get("parsed_listing")
    if state.get("pipeline_status") == "failed" or parsed is None:
        return "end"
    if not getattr(parsed, "raw_location", None):
        return "end"
    return "geocode"


def _route_after_geocode(state: AgentState) -> str:
    """Continue only if we have usable coordinates."""
    if state.get("pipeline_status") == "failed":
        return "end"
    if state.get("latitude") is None or state.get("longitude") is None:
        return "end"
    return "duplicate"


def _route_after_duplicate(state: AgentState) -> str:
    """Short-circuit when the listing matches an existing one.

    On a dup hit, jump straight to persist (which records the detection with
    is_duplicate=True) and skip commute/civic/scoring entirely — those numbers
    already live on the canonical record at state['duplicate_of'].
    """
    if state.get("pipeline_status") == "duplicate":
        return "persist"
    return "commute"


def build_pipeline():
    """Build the LangGraph pipeline for the Namma Bengaluru ETL engine."""
    workflow = StateGraph(AgentState)

    workflow.add_node("extract", extract_node.process)
    workflow.add_node("geocode", geocode_node.process)
    workflow.add_node("duplicate", duplicate_node.process)
    workflow.add_node("commute", commute_node.process)
    workflow.add_node("civic_water", civic_water_node.process)
    workflow.add_node("scoring", scoring_node.process)
    workflow.add_node("persist", persist_node.process)

    workflow.set_entry_point("extract")

    # Fatal-stage routing: bail out early if extraction or geocoding gave us
    # nothing useful, instead of running 4 more nodes against an empty state.
    workflow.add_conditional_edges(
        "extract",
        _route_after_extract,
        {"geocode": "geocode", "end": END},
    )
    workflow.add_conditional_edges(
        "geocode",
        _route_after_geocode,
        {"duplicate": "duplicate", "end": END},
    )

    # Duplicate detected → jump straight to persist (records the dup detection,
    # skips commute/civic/scoring because those numbers exist on the original).
    workflow.add_conditional_edges(
        "duplicate",
        _route_after_duplicate,
        {"commute": "commute", "persist": "persist"},
    )

    # Remaining enrichment stages are best-effort: the per-node decorator
    # demotes them to "partial" on failure rather than aborting the pipeline.
    workflow.add_edge("commute", "civic_water")
    workflow.add_edge("civic_water", "scoring")
    workflow.add_edge("scoring", "persist")
    workflow.add_edge("persist", END)

    return workflow.compile()


pipeline = build_pipeline()


def _initial_state(
    raw_text: str, source_platform: str, source_msg_id: str
) -> Dict[str, Any]:
    """
    Seed the graph with explicit defaults for every key.

    AgentState is now `total=False`, so missing keys are technically allowed,
    but pre-populating keeps the response shape predictable for downstream
    HTTP consumers (no `KeyError` when serializing).
    """
    return {
        "raw_text": raw_text,
        "source_platform": source_platform,
        "source_msg_id": source_msg_id,
        "id": None,
        "parsed_listing": None,
        "latitude": None,
        "longitude": None,
        "geocode_confidence": None,
        "geocode_provider": None,
        "is_duplicate": False,
        "duplicate_of": None,
        "embedding": None,
        "gba_ward_name": None,
        "gba_corporation": None,
        "cauvery_stage": None,
        "water_risk_level": None,
        "commutes": {},
        "scorecard": None,
        "errors": [],
        "pipeline_status": "running",
    }


async def run_pipeline(
    raw_text: str,
    source_platform: str = "manual",
    source_msg_id: str = "",
) -> Dict[str, Any]:
    """Wrapper to run the compiled graph with a hard outer timeout."""
    state = _initial_state(raw_text, source_platform, source_msg_id)

    try:
        return await asyncio.wait_for(
            pipeline.ainvoke(state),
            timeout=PIPELINE_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        logger.error("pipeline timed out after %.1fs", PIPELINE_TIMEOUT_SEC)
        state["pipeline_status"] = "timeout"
        state["errors"].append({
            "node": "pipeline",
            "type": "TimeoutError",
            "message": f"pipeline exceeded {PIPELINE_TIMEOUT_SEC:.0f}s",
            "retryable": True,
        })
        return state
    except Exception as exc:
        logger.exception("pipeline raised unexpectedly")
        state["pipeline_status"] = "failed"
        state["errors"].append({
            "node": "pipeline",
            "type": type(exc).__name__,
            "message": str(exc),
            "retryable": False,
        })
        return state
