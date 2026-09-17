"""Tavily search client (httpx, no extra SDK dependency).

Official contract (docs.tavily.com, Search API):
    POST https://api.tavily.com/search
    Headers: Authorization: Bearer <TAVILY_API_KEY>, Content-Type: application/json
    Body (only documented fields used):
        query (required), search_depth, max_results, include_answer,
        topic, exclude_domains
    Response: { query, results: [{title, url, content, score, ...}], ... }

Privacy: only the minimum fields needed to formulate a query are sent
(state, occupation/role words, need words). Exact age/income/disability
values are NEVER placed in query strings.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

from services.web_scheme_discovery.exceptions import (
    MissingApiKeyError,
    TavilyAPIError,
)
from services.web_scheme_discovery.schemas import TavilyResultItem, WebDiscoveryProfile

logger = logging.getLogger("yojnasathi.web_discovery.tavily")

TAVILY_SEARCH_URL = "https://api.tavily.com/search"

# Noise domains excluded from every query (documented exclude_domains field).
DEFAULT_EXCLUDE_DOMAINS = [
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "reddit.com",
    "quora.com",
    "tiktok.com",
]

VALID_DEPTHS = {"basic", "advanced", "fast", "ultra-fast"}


def get_tavily_api_key() -> str:
    key = (os.environ.get("TAVILY_API_KEY") or "").strip()
    if not key:
        raise MissingApiKeyError(
            "TAVILY_API_KEY is not configured. Web discovery is unavailable; "
            "local recommendations continue to work."
        )
    return key


def get_tavily_defaults() -> Dict[str, Any]:
    try:
        max_results = int(os.environ.get("TAVILY_MAX_RESULTS", "5"))
    except ValueError:
        max_results = 5
    max_results = max(1, min(max_results, 10))
    depth = (os.environ.get("TAVILY_SEARCH_DEPTH", "basic") or "basic").strip().lower()
    if depth not in VALID_DEPTHS:
        depth = "basic"
    country = (os.environ.get("TAVILY_COUNTRY", "india") or "").strip().lower() or None
    raw_domains = (os.environ.get("TAVILY_INCLUDE_DOMAINS", "") or "").strip()
    include_domains = [d.strip() for d in raw_domains.split(",") if d.strip()] or None
    return {
        "max_results": max_results,
        "search_depth": depth,
        "country": country,
        "include_domains": include_domains,
    }


def _profile_terms(profile: WebDiscoveryProfile) -> Dict[str, str]:
    """Extract only query-safe terms (no exact age/income/disability)."""
    state = (profile.state or "").strip()
    occupation = (profile.occupation or "").strip().lower()
    need = (profile.need or "").replace("_", " ").strip().lower()
    specific = (profile.specific_need or "").replace("_", " ").strip().lower()
    social = (profile.social_category or "").strip()
    role_words: List[str] = []
    if profile.farmer or occupation in {"farmer", "agriculture", "kisan"}:
        role_words.append("farmer")
    if profile.student or occupation == "student":
        role_words.append("student")
    if (profile.gender or "").strip().lower() in {"female", "woman"}:
        role_words.append("women")
    if social:
        role_words.append(social)
    return {
        "state": state,
        "occupation": occupation,
        "need": need,
        "specific": specific,
        "roles": " ".join(role_words).strip(),
    }


def build_search_queries(profile: WebDiscoveryProfile) -> List[str]:
    """Generate 3-6 targeted queries covering central + state government."""
    t = _profile_terms(profile)
    state = t["state"] or "India"
    need_phrase = t["specific"] or t["need"] or "welfare"
    occupation = t["occupation"] or t["roles"] or "citizen"
    roles = t["roles"]

    queries: List[str] = []
    # 1. state + occupation + government scheme
    queries.append(f"{state} {occupation} government scheme".strip())
    # 2. state + specific need + subsidy
    queries.append(f"{state} {need_phrase} subsidy scheme".strip())
    # 3. occupation + need + financial assistance
    queries.append(f"{occupation} {need_phrase} financial assistance government scheme".strip())
    # 4. central government + need
    queries.append(f"central government {need_phrase} scheme India".strip())
    # 5. state government + need
    if state.lower() != "india":
        queries.append(f"{state} government {need_phrase} scheme".strip())
    else:
        queries.append(f"government {need_phrase} scheme official portal".strip())
    # 6. demographic-specific official scheme query (only if roles add signal)
    if roles and roles.lower() not in need_phrase.lower():
        queries.append(f"official government scheme {roles} {need_phrase}".strip())

    # Deduplicate, cap at 6, drop empties.
    seen: set[str] = set()
    out: List[str] = []
    for q in queries:
        q = " ".join(q.split())
        if q and q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
        if len(out) >= 6:
            break
    return out[:6] if len(out) >= 3 else out


class TavilyClient:
    """Thin httpx wrapper. `_post` is injectable for mocked tests."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ):
        self.api_key = (api_key if api_key is not None else (os.environ.get("TAVILY_API_KEY") or "")).strip()
        if timeout_seconds is not None:
            self.timeout_seconds = timeout_seconds
        else:
            try:
                self.timeout_seconds = float(os.environ.get("TAVILY_TIMEOUT_SECONDS", "15.0"))
            except ValueError:
                self.timeout_seconds = 15.0

    def _post(self, url: str, payload: Dict[str, Any], headers: Dict[str, str]) -> httpx.Response:
        return httpx.post(url, json=payload, headers=headers, timeout=self.timeout_seconds)

    def search(
        self,
        query: str,
        max_results: Optional[int] = None,
        search_depth: Optional[str] = None,
    ) -> List[TavilyResultItem]:
        if not self.api_key:
            raise MissingApiKeyError(
                "TAVILY_API_KEY is not configured. Web discovery is unavailable."
            )
        defaults = get_tavily_defaults()
        payload: Dict[str, Any] = {
            "query": query,
            "search_depth": search_depth or defaults["search_depth"],
            "max_results": max_results or defaults["max_results"],
            "include_answer": False,
            "topic": "general",
            "exclude_domains": DEFAULT_EXCLUDE_DOMAINS,
        }
        # India-scoping (documented fields): country boosts Indian sources so
        # US/EU farm-subsidy pages stop outranking .gov.in scheme pages.
        # include_domains is set only when explicitly configured via env.
        if defaults.get("country"):
            payload["country"] = defaults["country"]
        if defaults.get("include_domains"):
            payload["include_domains"] = defaults["include_domains"]
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = self._post(TAVILY_SEARCH_URL, payload, headers)
        except MissingApiKeyError:
            raise
        except Exception as exc:
            raise TavilyAPIError(f"Tavily request failed: {exc}") from exc

        if resp.status_code == 401:
            raise TavilyAPIError("Tavily authentication failed (401).", status_code=401)
        if resp.status_code == 429:
            raise TavilyAPIError("Tavily rate limit exceeded (429).", status_code=429)
        if resp.status_code >= 400:
            raise TavilyAPIError(
                f"Tavily search failed with status {resp.status_code}.",
                status_code=resp.status_code,
            )
        try:
            data = resp.json()
        except Exception as exc:
            raise TavilyAPIError("Tavily returned malformed JSON.") from exc
        raw_results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(raw_results, list):
            raise TavilyAPIError("Tavily returned a malformed search payload.")
        items: List[TavilyResultItem] = []
        for raw in raw_results:
            if not isinstance(raw, dict):
                continue
            try:
                items.append(
                    TavilyResultItem(
                        title=str(raw.get("title") or ""),
                        url=str(raw.get("url") or ""),
                        content=str(raw.get("content") or ""),
                        score=float(raw.get("score") or 0.0),
                    )
                )
            except Exception:
                continue
        return items
