import logging
import os

from langchain_google_genai import ChatGoogleGenerativeAI

from app.graph.nodes._decorator import node
from app.models.schemas import AgentState, RentalListingSchema
from app.services.cache import get_extraction_cache, set_extraction_cache
from app.services.llm_throttle import throttle

logger = logging.getLogger(__name__)

LLM_TIMEOUT_SEC = 10
LLM_MAX_RETRIES = 2

# Bumped whenever the prompt template changes — invalidates the prompt_cache
# without manual SQL.
#   v1: initial schema (rent, deposit, bhk, location, gender, restrictions)
#   v2: + water-related building signals (cauvery, borewell, 24x7, RWH, tanker)
PROMPT_VERSION = "v2"

_PROMPT_TEMPLATE = """
You are an expert real estate data extractor for Bengaluru.

Extract from this rental listing. Convert rent strings (e.g. '25k') to integer (25000).
Identify the raw location string as accurately as possible (e.g. 'Near Manyata, Nagavara').

Also extract these water-related signals as true/false/null. Use null only when the
text gives no signal in either direction. Match common phrasings, including Kannada
or transliterated variants:
- cauvery_mentioned: mentions 'Cauvery', 'BWSSB', 'corporation water'
- borewell_mentioned: mentions 'borewell', 'bore well', 'bore-well'
- water_24x7: claims '24/7 water', 'uninterrupted', 'round the clock', 'always available'
- rwh_mentioned: mentions 'RWH', 'rainwater harvesting', 'rain water harvesting'
- tanker_mentioned: mentions reliance on water tankers (esp. summer / May-June)

Raw Listing:
{raw_text}
"""


@node("extract", timeout=15.0, fatal=True)
async def process(state: AgentState) -> dict:
    """Extract structured data from raw listing text using Gemini."""
    raw_text = state.get("raw_text", "")
    logger.info("Extracting structured data via Gemini.")

    # Step 1: Cache lookup (cursorrules section 2 — mandatory before LLM hit).
    cached = await get_extraction_cache(raw_text, PROMPT_VERSION)
    if cached:
        return {"parsed_listing": RentalListingSchema(**cached)}

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY missing. Returning dummy extraction.")
        return {
            "parsed_listing": RentalListingSchema(
                raw_location="Indiranagar",
                rent_amount=25000,
                bhk_type="1 BHK",
            )
        }

    # Step 2: Throttle outbound LLM call (cursorrules section 2 — min spacing).
    await throttle("gemini")

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        temperature=0,
        api_key=api_key,
        timeout=LLM_TIMEOUT_SEC,
        max_retries=LLM_MAX_RETRIES,
    )
    structured_llm = llm.with_structured_output(RentalListingSchema)

    prompt = _PROMPT_TEMPLATE.format(raw_text=raw_text)

    # The decorator owns try/except + timeout. Any LLM-side failure becomes a
    # structured error and trips fatal=True, which the conditional edge in
    # pipeline.py uses to short-circuit straight to END.
    extracted = await structured_llm.ainvoke(prompt)

    # Step 3: Write back to cache so the next identical raw_text is a hit.
    await set_extraction_cache(raw_text, PROMPT_VERSION, extracted.model_dump())

    return {"parsed_listing": extracted}
