import operator
from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field
from typing_extensions import TypedDict

# --- Extraction Schemas ---

class RentalListingSchema(BaseModel):
    rent_amount: Optional[int] = Field(None, description="Monthly rent amount in INR")
    security_deposit: Optional[int] = Field(None, description="Security deposit in INR")
    bhk_type: Optional[str] = Field(None, description="BHK type (e.g., '1 BHK', '2 BHK', 'PG')")
    raw_location: str = Field(..., description="The raw, unnormalized location string extracted from text")
    preferred_gender: Optional[str] = Field(None, description="'Male', 'Female', 'Any'")
    restrictions: List[str] = Field(default_factory=list, description="List of restrictions (e.g., 'No non-veg', 'No pets')")

    # ---- Water-related building-level signals (Tier 2) ------------------
    # These boost or penalize the ward-derived water score when the listing
    # itself reveals what the building actually has. All Optional so the
    # extractor can return None when the text gives no signal either way.
    cauvery_mentioned: Optional[bool] = Field(
        None, description="True if listing explicitly mentions Cauvery / BWSSB / corporation water"
    )
    borewell_mentioned: Optional[bool] = Field(
        None, description="True if listing mentions a borewell / bore well as a water source"
    )
    water_24x7: Optional[bool] = Field(
        None, description="True if listing claims 24/7 / uninterrupted / round-the-clock water"
    )
    rwh_mentioned: Optional[bool] = Field(
        None, description="True if listing mentions RWH / rainwater harvesting"
    )
    tanker_mentioned: Optional[bool] = Field(
        None, description="True if listing mentions reliance on water tankers"
    )


# --- Response Schemas ---

WaterConfidence = Literal["high", "medium", "low"]


class WaterScoreBreakdown(BaseModel):
    """
    Decomposition of the 35-pt water score into its three sub-components,
    plus a confidence flag and human-readable rationale bullets. The total
    is `cauvery_supply + groundwater_resilience + building_signals`.
    """
    total: int = Field(0, description="Sum of sub-scores (0-35)")
    cauvery_supply: int = Field(0, description="0-17, derived from cauvery_stage")
    groundwater_resilience: int = Field(0, description="0-11, derived from water_risk_level")
    building_signals: int = Field(0, description="0-7, derived from listing-extracted signals")
    confidence: WaterConfidence = Field(
        "medium",
        description="How confident we are in the score: 'low' when ward data missing and listing silent",
    )
    rationale: List[str] = Field(
        default_factory=list,
        description="Human-readable bullets explaining each component of the score",
    )


class LivabilityScorecard(BaseModel):
    total_score: int = Field(0, description="Overall livability score (0-100)")
    commute_score: int = Field(0, description="Commute component score (0-40)")
    water_score: int = Field(0, description="Water component score (0-35)")
    water_breakdown: Optional[WaterScoreBreakdown] = Field(
        None, description="Sub-score breakdown + rationale for the water component"
    )
    financial_score: int = Field(0, description="Financial component score (0-15)")
    civic_score: int = Field(0, description="Civic component score (0-10)")

    red_flags: List[str] = Field(default_factory=list, description="Critical warnings")
    alternatives: List[Dict[str, str]] = Field(default_factory=list, description="Alternative neighborhood suggestions if score < 50")


class PipelineResponse(BaseModel):
    id: str
    parsed_listing: RentalListingSchema
    livability_scorecard: LivabilityScorecard


# --- LangGraph State ---

PipelineStatus = Literal[
    "running",      # in flight
    "success",      # every node clean, no errors recorded
    "partial",      # one or more non-fatal nodes soft-failed (scorecard still produced)
    "failed",       # a fatal node (extract or geocode) failed; pipeline aborted
    "timeout",      # outer wall-clock budget exhausted
    "duplicate",    # listing matched an existing record via pgvector + spatial join
]


class ErrorEntry(TypedDict):
    """Structured per-node error record appended to AgentState.errors."""
    node: str
    type: str
    message: str
    retryable: bool


def _merge_commutes(a: Dict[str, int], b: Dict[str, int]) -> Dict[str, int]:
    """Reducer for the commutes dict: right-hand side wins on key conflict."""
    return {**a, **b}


class AgentState(TypedDict, total=False):
    """
    Shared state for the LangGraph pipeline.

    Reducer-annotated fields combine partial updates from nodes instead of
    replacing them. This is what makes it safe for the decorator (and any
    future parallel branches) to emit small `{"errors": [...]}` updates
    without clobbering prior accumulated errors.

    Convention: nodes should return ONLY the keys they modify. Do not return
    the whole state — that would re-trigger reducers on already-present keys
    and double-count entries on accumulating fields.
    """

    # Inputs
    raw_text: str
    source_platform: str
    source_msg_id: str

    # Persisted record identity (set by persist_node after INSERT).
    id: Optional[str]

    # Extracted data
    parsed_listing: Optional[RentalListingSchema]

    # Geocoding data
    latitude: Optional[float]
    longitude: Optional[float]
    geocode_confidence: Optional[float]
    geocode_provider: Optional[str]

    # Duplicate check. embedding is populated by duplicate_node and re-used by
    # persist_node so we don't pay for a second Gemini embedding call.
    is_duplicate: bool
    duplicate_of: Optional[str]
    embedding: Optional[List[float]]

    # Spatial/Civic data
    gba_ward_name: Optional[str]
    gba_corporation: Optional[str]
    cauvery_stage: Optional[str]
    water_risk_level: Optional[str]

    # Commute data — reducer merges partial maps (future fan-out friendly).
    commutes: Annotated[Dict[str, int], _merge_commutes]

    # Final Scorecard
    scorecard: Optional[LivabilityScorecard]

    # Pipeline metadata — errors reducer concatenates lists.
    errors: Annotated[List[ErrorEntry], operator.add]
    pipeline_status: PipelineStatus


# Re-export for type-checking convenience
__all__ = [
    "AgentState",
    "ErrorEntry",
    "LivabilityScorecard",
    "PipelineResponse",
    "PipelineStatus",
    "RentalListingSchema",
    "WaterConfidence",
    "WaterScoreBreakdown",
]
