"""
Universal error boundary + timeout wrapper for LangGraph nodes.

Every node should be wrapped with @node(...) so that:
  - A per-node asyncio timeout prevents the graph from hanging on a hung API.
  - Uncaught exceptions become structured ErrorEntry items appended via the
    reducer on AgentState.errors instead of propagating up and aborting.
  - pipeline_status transitions are centralized: "failed" for fatal nodes,
    "partial" for non-fatal soft failures.

Contract:
  - Wrapped node functions return a PARTIAL state update (only the keys they
    modified). LangGraph composes these updates via the reducers declared on
    AgentState. Returning the whole state would double-count reducer fields.
  - On exception/timeout, the decorator returns its own partial update with
    `errors` and `pipeline_status`. It does NOT mutate state in place.
"""

import asyncio
import functools
import logging
import time
from typing import Any, Awaitable, Callable, Dict

from app.models.schemas import AgentState, ErrorEntry

logger = logging.getLogger(__name__)

# A "partial update" returned from a node. Empty dict means "no change".
NodeUpdate = Dict[str, Any]
NodeFn = Callable[[AgentState], Awaitable[NodeUpdate]]


def _error_update(name: str, exc_type: str, message: str, retryable: bool, fatal: bool, prior_status: str | None) -> NodeUpdate:
    entry: ErrorEntry = {
        "node": name,
        "type": exc_type,
        "message": message,
        "retryable": retryable,
    }
    update: NodeUpdate = {"errors": [entry]}
    if fatal:
        update["pipeline_status"] = "failed"
    elif prior_status not in ("failed", "timeout", "duplicate"):
        # Don't downgrade a hard fail back to "partial". Don't downgrade a
        # successful "duplicate" detection either — that's a positive outcome
        # we want to preserve even if a downstream node (e.g. persist) hiccups.
        update["pipeline_status"] = "partial"
    return update


def node(name: str, timeout: float = 15.0, fatal: bool = False) -> Callable[[NodeFn], NodeFn]:
    """
    Decorator factory for LangGraph node functions.

    Args:
        name:    Logical node name, recorded in error entries and log lines.
        timeout: Hard ceiling in seconds for the node's execution.
        fatal:   If True, any failure (timeout or exception) marks the entire
                 pipeline as "failed". If False, the failure is recorded but
                 the pipeline continues with pipeline_status="partial".
    """

    def decorator(fn: NodeFn) -> NodeFn:
        @functools.wraps(fn)
        async def wrapper(state: AgentState) -> NodeUpdate:
            # Safety net: if conditional edges ever fail to short-circuit, this
            # check prevents downstream nodes from re-doing work on a dead state.
            status = state.get("pipeline_status")
            if status in ("failed", "timeout"):
                return {}

            started = time.monotonic()
            try:
                result = await asyncio.wait_for(fn(state), timeout=timeout)
                elapsed = time.monotonic() - started
                logger.info("node=%s status=ok elapsed=%.2fs", name, elapsed)
                return result if isinstance(result, dict) else {}

            except asyncio.TimeoutError:
                elapsed = time.monotonic() - started
                logger.error(
                    "node=%s status=timeout elapsed=%.2fs limit=%.1fs",
                    name, elapsed, timeout,
                )
                return _error_update(
                    name=name,
                    exc_type="TimeoutError",
                    message=f"node exceeded {timeout:.1f}s",
                    retryable=True,
                    fatal=fatal,
                    prior_status=status,
                )

            except asyncio.CancelledError:
                # Outer pipeline timeout or upstream cancellation — propagate.
                raise

            except Exception as exc:
                elapsed = time.monotonic() - started
                logger.exception("node=%s status=error elapsed=%.2fs", name, elapsed)
                return _error_update(
                    name=name,
                    exc_type=type(exc).__name__,
                    message=str(exc),
                    retryable=False,
                    fatal=fatal,
                    prior_status=status,
                )

        return wrapper

    return decorator
