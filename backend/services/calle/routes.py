import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, status

from services.calle.exceptions import CalleAPIError, CalleAuthenticationError, CalleValidationError
from services.calle.service import calle_service

logger = logging.getLogger("yojnasathi.calle.routes")
router = APIRouter(prefix="/api/calle", tags=["CALL-E"])


@router.post("/call")
async def create_call_endpoint(request: Dict[str, Any]):
    try:
        payload = request or {}
        if not isinstance(payload, dict):
            raise CalleValidationError("Request body must be a JSON object.")

        result = await calle_service.create_scheme_call(
            phone_number=str(payload.get("phone_number") or ""),
            language=payload.get("language"),
            initial_context=payload.get("initial_context"),
        )
        return {"success": True, "call_id": result.call_id, "status": result.status}
    except CalleAuthenticationError as exc:
        logger.warning("CALL-E API key missing for call request")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except CalleValidationError as exc:
        logger.warning("Invalid CALL-E call request: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except CalleAPIError as exc:
        logger.exception("CALL-E provider call failure")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/call/{call_id}")
async def get_call_status_endpoint(call_id: str):
    try:
        result = await calle_service.get_call(call_id)
        return {
            "call_id": result.call_id,
            "status": result.status,
            "task_completed": result.task_completed,
            "structured_result": result.structured_result,
            "matched_scheme_count": len(result.matched_schemes),
            "matched_schemes": [match.model_dump() for match in result.matched_schemes],
        }
    except CalleAuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except CalleValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except CalleAPIError as exc:
        logger.exception("CALL-E status lookup failed for: %s", call_id)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/webhook")
async def webhook_endpoint(request: Request):
    try:
        payload = await request.json()
        event_id = request.headers.get("CALL-E-Event-Id")
        result = calle_service.handle_webhook(payload, {"CALL-E-Event-Id": event_id})
        return {
            "success": True,
            "received": True,
            "duplicate": result.get("duplicate", False),
            "call_id": result.get("call_id"),
            "status": result.get("status"),
            "profile": result.get("profile"),
            "structured_result": result.get("structured_result"),
            "summary": result.get("summary"),
            "matching_profile": result.get("matching_profile"),
            "matched_category": result.get("matched_category"),
            "matched_scheme_count": result.get("matched_scheme_count", 0),
            "matched_schemes": result.get("matched_schemes", []),
        }
    except CalleValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - unexpected runtime guard
        logger.exception("CALL-E webhook handling failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Webhook processing failed") from exc
