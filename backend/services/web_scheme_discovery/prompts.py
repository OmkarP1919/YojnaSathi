"""LLM prompt templates for extraction (strict, evidence-grounded).

The default pipeline uses the deterministic heuristic extractor and does
NOT call an LLM, so web discovery works offline in tests and never
invents facts. These prompts exist for an optional future LLM-assisted
extraction path and document the grounding contract.
"""

EXTRACTION_SYSTEM_PROMPT = """You are a precise information-extraction assistant for Indian government schemes.

STRICT RULES:
1. Extract ONLY facts explicitly present in the provided source content.
2. NEVER invent benefits, amounts, income limits, age limits, deadlines, URLs, or eligibility conditions.
3. If a field is not present in the sources, output null for it — do NOT guess.
4. Every benefit, eligibility item, and URL must be traceable to a quoted source snippet.
5. Output STRICT JSON matching the requested schema. No markdown, no commentary.
6. Never claim the citizen is definitely eligible. Use "may be relevant" phrasing only.
7. If the source indicates discontinued/closed/expired/subsumed, set active_status to "inactive".
8. If the source does not establish current status, set active_status to "unknown" — never assume "active".
"""

EXTRACTION_USER_TEMPLATE = """Source results (title, url, content snippet):
{source_blocks}

Citizen context (for relevance only, NOT for inventing facts):
{profile_summary}

Extract ONE government scheme as strict JSON with keys:
scheme_name, scheme_type, government_level, state, description, benefits[],
eligibility[], exclusions[], application_process[], documents_required[],
application_url, source_url, source_urls[], active_status.
Use null/[] when unknown. Quote evidence per field in a separate 'evidence' list.
"""
