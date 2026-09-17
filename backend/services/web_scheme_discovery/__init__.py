"""Independent parallel web-scheme-discovery pipeline (Tavily).

This package is deliberately SEPARATE from the existing deterministic
``backend/app/matching.py`` engine, ``services/voice_agent/`` and
``services/calle/``. Nothing here is imported by the existing pipeline,
so a Tavily outage can never break local recommendations.
"""

from services.web_scheme_discovery.service import (
    WebSchemeDiscoveryService,
    discover_web_schemes,
    get_discovery_service,
)

__all__ = [
    "WebSchemeDiscoveryService",
    "discover_web_schemes",
    "get_discovery_service",
]
