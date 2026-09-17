import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

from app.schemas import CitizenProfile
from services.calle.exceptions import CalleAPIError, CalleAuthenticationError, CalleValidationError
from services.calle.prompts import CALLE_SYSTEM_PROMPT
from services.calle.schemas import CalleCallRequest, CalleCallResponse, CalleCallStatus, CalleWebhookEvent, CitizenCallProfile

load_dotenv()

logger = logging.getLogger("yojnasathi.calle")

# CALL-E stable error codes (see https://docs.heycall-e.com/errors) that mean
# the request itself was rejected and must not be retried unchanged.
_VALIDATION_ERROR_CODES = {
    "invalid_request",
    "invalid_phone",
    "invalid_recipient",
    "no_recipients",
    "result_schema_invalid",
    "recipient_result_schema_invalid",
    "variables_invalid",
    "unsupported_region",
    "unsupported_language",
    "policy_violation",
    "recipient_blocked",
}


class CalleService:
    """Thin wrapper around CALL-E REST APIs for outbound scheme-discovery calls."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        webhook_url: Optional[str] = None,
    ):
        if api_key is not None and not api_key.strip():
            raise CalleAuthenticationError("CALLE_API_KEY is required to use the CALL-E service.")

        self.api_key = (api_key or os.getenv("CALLE_API_KEY") or "").strip()
        self.base_url = (base_url or os.getenv("CALLE_BASE_URL") or "https://api.heycall-e.com").rstrip("/")
        self.webhook_url = webhook_url or os.getenv("CALLE_WEBHOOK_URL")
        # CALL-E delivers webhooks at-least-once: remember processed event ids
        # so duplicate deliveries never cause duplicate processing.
        self._seen_webhook_events: set = set()

    def validate_configured(self) -> None:
        # Re-read the environment in case dotenv was loaded after import.
        if not self.api_key:
            self.api_key = (os.getenv("CALLE_API_KEY") or "").strip()
        if not self.base_url:
            self.base_url = (os.getenv("CALLE_BASE_URL") or "https://api.heycall-e.com").rstrip("/")
        if not self.webhook_url:
            self.webhook_url = os.getenv("CALLE_WEBHOOK_URL") or None
        if not self.api_key:
            raise CalleAuthenticationError("CALLE_API_KEY is required to use the CALL-E service.")

    @staticmethod
    def normalize_phone_number(phone_number: str) -> str:
        raw = (phone_number or "").strip()
        if not raw:
            raise CalleValidationError("Phone number is required.")

        # Strip a leading trunk "0", spaces, dashes and brackets, keep digits.
        digits = re.sub(r"\D+", "", raw)
        if digits.startswith("0") and not digits.startswith("00"):
            digits = digits[1:]
        if digits.startswith("00"):
            digits = digits[2:]
        # Bare 10-digit Indian mobile number -> assume India (+91).
        if len(digits) == 10:
            digits = "91" + digits
        candidate = "+" + digits
        if re.fullmatch(r"\+[1-9]\d{7,14}", candidate):
            return candidate

        raise CalleValidationError("Invalid phone number. Use the format +91XXXXXXXXXX.")

    @staticmethod
    def _structured_result_schema() -> Dict[str, Any]:
        # Strictly limited to CALL-E's documented schema features
        # (type, properties, required, enum, description,
        # additionalProperties: false). Union types, oneOf/anyOf and null
        # types are NOT supported, so unknown values use "" or "unknown".
        # See https://docs.heycall-e.com/calls#structured-results
        return {
            "type": "object",
            "required": ["language", "need"],
            "properties": {
                "language": {
                    "type": "string",
                    "enum": ["en", "hi", "mr", "unknown"],
                    "description": "Citizen's preferred language. Use unknown if the call has no clear language evidence.",
                },
                "state": {
                    "type": "string",
                    "description": "Indian state mentioned by the citizen, e.g. Maharashtra. Use an empty string if not stated.",
                },
                "district": {
                    "type": "string",
                    "description": "District mentioned by the citizen. Use an empty string if not stated.",
                },
                "age": {
                    "type": "string",
                    "description": "Age in years as digits, e.g. 45. Use an empty string if not stated. Never guess.",
                },
                "gender": {
                    "type": "string",
                    "description": "Gender stated by the citizen, e.g. male, female. Use an empty string if not stated.",
                },
                "occupation": {
                    "type": "string",
                    "description": "Occupation stated by the citizen, e.g. farmer, student. Use an empty string if not stated.",
                },
                "farmer": {
                    "type": "string",
                    "enum": ["yes", "no", "unknown"],
                    "description": "Whether the citizen farms or cultivates crops. Use unknown if unclear.",
                },
                "student": {
                    "type": "string",
                    "enum": ["yes", "no", "unknown"],
                    "description": "Whether the citizen is a student. Use unknown if unclear.",
                },
                "annual_income": {
                    "type": "string",
                    "description": "Annual income or range stated by the citizen, e.g. 120000. Use an empty string if not stated. Never guess.",
                },
                "social_category": {
                    "type": "string",
                    "description": "Social category only if the citizen states it. Use an empty string otherwise.",
                },
                "disability": {
                    "type": "string",
                    "enum": ["yes", "no", "unknown"],
                    "description": "Whether the citizen mentions a disability. Use unknown if unclear.",
                },
                "need": {
                    "type": "string",
                    "description": "Citizen's stated assistance need, e.g. agriculture, education, health, housing, employment, business. Use unknown if unclear.",
                },
                "specific_need": {
                    "type": "string",
                    "description": "One sentence in the citizen's own terms describing what they need. Use an empty string if not stated.",
                },
                "evidence": {
                    "type": "string",
                    "description": "Short quote or paraphrase from the call supporting the profile. Use an empty string if unavailable.",
                },
            },
            "additionalProperties": False,
        }

    @staticmethod
    def _language_to_locale(language: Optional[str]) -> str:
        lang = (language or "en").strip().lower()
        mapping = {"en": "en-IN", "hi": "hi-IN", "mr": "mr-IN"}
        return mapping.get(lang, "en-IN")

    _scheme_catalog_cache: Optional[str] = None

    @classmethod
    def _load_scheme_catalog(cls) -> str:
        """Build a compact VERIFIED scheme catalog from data/schemes.json.

        The catalog is embedded in the call task so the voice agent can give
        complete scheme information without inventing facts. Returns "" when
        the data file is unavailable, so calls still work.
        """
        if cls._scheme_catalog_cache is not None:
            return cls._scheme_catalog_cache

        def _en(value: Any) -> str:
            if isinstance(value, dict):
                for key in ("en", "hi", "mr"):
                    if isinstance(value.get(key), str) and value[key].strip():
                        return value[key].strip()
                for item in value.values():
                    if isinstance(item, str) and item.strip():
                        return item.strip()
                return ""
            return str(value or "").strip()

        def _en_list(value: Any) -> List[str]:
            if isinstance(value, dict):
                for key in ("en", "hi", "mr"):
                    if isinstance(value.get(key), list):
                        return [str(i).strip() for i in value[key] if str(i).strip()]
                return []
            if isinstance(value, list):
                return [str(i).strip() for i in value if str(i).strip()]
            text = _en(value)
            return [text] if text else []

        def _clip(text: str, limit: int) -> str:
            text = re.sub(r"\s+", " ", text).strip()
            return text if len(text) <= limit else text[:limit].rstrip() + "..."

        catalog = ""
        try:
            data_path = Path(__file__).resolve().parent.parent.parent / "data" / "schemes.json"
            with open(data_path, "r", encoding="utf-8") as f:
                schemes = json.load(f)
            lines = []
            for s in schemes:
                if not isinstance(s, dict):
                    continue
                lines.append(
                    "- {name} [id={sid}, category={cat}, state={state}, dept={dept}]\n"
                    "  Benefits: {benefits}\n"
                    "  Eligibility: {elig}\n"
                    "  Apply: {url}".format(
                        name=_clip(_en(s.get("name")), 100),
                        sid=s.get("id"),
                        cat=s.get("category"),
                        state=s.get("state"),
                        dept=_clip(_en(s.get("department")), 80),
                        benefits=_clip("; ".join(_en_list(s.get("benefits"))), 500),
                        elig=_clip("; ".join(_en_list(s.get("eligibility"))), 500),
                        url=str(s.get("application_url") or "").strip(),
                    )
                )
            if lines:
                catalog = (
                    "VERIFIED SCHEME CATALOG (use ONLY these facts when informing the citizen):\n"
                    + "\n".join(lines)
                )
        except (OSError, ValueError) as exc:
            logger.warning("CALL-E scheme catalog unavailable: %s", exc)
            catalog = ""

        cls._scheme_catalog_cache = catalog
        return catalog

    @staticmethod
    def _build_scheme_call_task(phone_number: str, language: Optional[str] = None, initial_context: Optional[Dict[str, Any]] = None) -> str:
        normalized_lang = (language or (initial_context or {}).get("language") or "en").strip().lower()
        if normalized_lang not in {"en", "hi", "mr"}:
            normalized_lang = "en"

        lang_names = {"en": "English", "hi": "Hindi", "mr": "Marathi"}
        task = (
            f"YojnaSathi: Call {phone_number} and introduce yourself as YojnaSathi, "
            "the government scheme assistant. "
            "IMPORTANT: speak with a masculine male voice for the entire call, never a female voice. "
            f"Speak in {lang_names[normalized_lang]} (code: {normalized_lang}), "
            "switching to the citizen's preferred language if they use English, Hindi or Marathi. "
            "After understanding their need, inform them COMPLETELY about the most relevant schemes "
            "from the verified catalog below: benefit amount, who it is for, and where to apply. "
            + CALLE_SYSTEM_PROMPT.strip()
        )

        catalog = CalleService._load_scheme_catalog()
        if catalog:
            task += "\n\n" + catalog

        if initial_context:
            task += f" Additional context: {json.dumps(initial_context, ensure_ascii=False)}"

        return task

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        request_headers = {"Content-Type": "application/json"}
        if self.api_key:
            request_headers["Authorization"] = f"Bearer {self.api_key}"
        if headers:
            request_headers.update(headers)

        request_payload = json_body if json_body is not None else json
        url = f"{self.base_url}{path}"
        logger.info("CALL-E request: %s %s", method, url)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(method, url, headers=request_headers, json=request_payload)
                payload = response.json() if hasattr(response, "json") and response.content else {}
        except httpx.HTTPError as exc:
            raise CalleAPIError(f"CALL-E request failed: {exc}") from exc
        except ValueError as exc:
            raise CalleAPIError("CALL-E returned a non-JSON response.") from exc

        if hasattr(response, "status_code") and response.status_code >= 400:
            error_obj = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            code = str(error_obj.get("code") or payload.get("code") or "").strip()
            detail = (
                error_obj.get("message")
                or payload.get("message")
                or "CALL-E API request failed"
            )
            status_code = response.status_code
            if status_code == 401 or code == "unauthorized":
                raise CalleAuthenticationError(
                    f"CALL-E authentication failed ({status_code}): {detail}"
                )
            if code in _VALIDATION_ERROR_CODES or status_code in (400, 404, 422):
                raise CalleValidationError(f"CALL-E rejected the request ({status_code}/{code or 'no-code'}): {detail}")
            raise CalleAPIError(f"CALL-E API error ({status_code}/{code or 'no-code'}): {detail}")

        return payload

    async def create_call(self, payload: Dict[str, Any] | CalleCallRequest | None = None, **kwargs) -> CalleCallResponse:
        self.validate_configured()

        if isinstance(payload, CalleCallRequest):
            data = payload.model_dump(exclude_none=True)
        elif isinstance(payload, dict):
            data = payload.copy()
        else:
            data = dict(kwargs)

        if not data:
            raise CalleValidationError("CALL-E call payload is required.")

        phone_number = self.normalize_phone_number(str(data.get("phone_number") or ""))
        language = (data.get("language") or "en").strip().lower()
        if language not in {"en", "hi", "mr"}:
            language = "en"

        task = self._build_scheme_call_task(
            phone_number=phone_number,
            language=language,
            initial_context=data.get("initial_context") or {},
        )

        request_payload: Dict[str, Any] = {
            "task": task,
            "recipients": [
                {
                    "phones": [phone_number],
                    "locale": self._language_to_locale(language),
                    "region": "IN",
                }
            ],
            "result_schema": self._structured_result_schema(),
            "metadata": {
                "workflow": "yojnasathi_scheme_call",
                "language": language,
                "phone_number": phone_number,
            },
        }

        if self.webhook_url:
            request_payload["webhook_url"] = self.webhook_url

        request_headers = {"Idempotency-Key": f"yojnasathi-{uuid.uuid4().hex}"}
        provider_response = await self._request("POST", "/v1/calls", json=request_payload, headers=request_headers)
        if not isinstance(provider_response, dict):
            provider_response = provider_response.json() if hasattr(provider_response, "json") else {}
        call_id = provider_response.get("id") or provider_response.get("call_id")
        status = provider_response.get("status") or "queued"
        if not call_id:
            raise CalleAPIError("CALL-E accepted the request but returned no call id.")

        logger.info("CALL-E call created: id=%s status=%s", call_id, status)
        return CalleCallResponse(
            success=True,
            call_id=call_id,
            status=status,
            message="CALL-E call created successfully.",
            provider_response=provider_response,
        )

    async def create_scheme_call(
        self,
        phone_number: str,
        language: Optional[str] = None,
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> CalleCallResponse:
        normalized_phone = self.normalize_phone_number(phone_number)
        return await self.create_call(
            {
                "phone_number": normalized_phone,
                "language": language,
                "initial_context": initial_context or {},
            }
        )

    async def get_call(self, call_id: str) -> CalleCallStatus:
        self.validate_configured()
        if not call_id:
            raise CalleValidationError("A valid CALL-E call ID is required.")

        payload = await self._request("GET", f"/v1/calls/{call_id}")
        if not isinstance(payload, dict):
            payload = payload.json() if hasattr(payload, "json") else {}
        status = payload.get("status")
        structured_result = payload.get("structured_result")
        return CalleCallStatus(
            call_id=payload.get("id") or call_id,
            status=status,
            task=payload.get("task"),
            summary=payload.get("summary"),
            task_completed=payload.get("task_completed"),
            completion_confidence=payload.get("completion_confidence"),
            structured_result=structured_result if isinstance(structured_result, dict) else None,
            raw_response=payload,
        )

    async def cancel_call(self, call_id: str) -> Dict[str, Any]:
        raise CalleAPIError("CALL-E cancel support is not available in the currently documented API for this workflow.")

    def handle_webhook(self, payload: Dict[str, Any], headers: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise CalleValidationError("Webhook payload must be a JSON object.")

        event_id = (headers or {}).get("CALL-E-Event-Id") or payload.get("id")
        if not event_id:
            raise CalleValidationError("CALL-E webhook request is missing the event id header.")

        event_type = payload.get("type")
        event_data = payload.get("data") or {}

        if event_id and payload.get("id") and event_id != payload.get("id"):
            raise CalleValidationError("Mismatch between CALL-E event ID header and payload ID.")

        call_id = event_data.get("id") or payload.get("call_id")
        status = event_data.get("status") or "unknown"
        structured_result = event_data.get("structured_result") or {}
        if not structured_result:
            # Fall back to the first recipient result for single-citizen calls.
            recipients = event_data.get("recipients") or []
            if recipients and isinstance(recipients[0], dict):
                structured_result = recipients[0].get("structured_result") or {}

        profile = self._structured_result_to_profile(structured_result)

        # Idempotent handling: ignore duplicate deliveries of the same event.
        event_key = str(payload.get("id") or event_id)
        if event_key in self._seen_webhook_events:
            logger.info("CALL-E duplicate webhook ignored: event_id=%s call_id=%s", event_key, call_id)
            return {
                "success": True,
                "duplicate": True,
                "event_id": payload.get("id"),
                "event_type": event_type,
                "call_id": call_id,
                "status": status,
                "profile": profile.model_dump(exclude_none=True) if profile else {},
                "structured_result": structured_result,
                "summary": event_data.get("summary"),
            }
        self._seen_webhook_events.add(event_key)

        logger.info("CALL-E webhook received: type=%s call_id=%s status=%s", event_type, call_id, status)
        return {
            "success": True,
            "duplicate": False,
            "event_id": payload.get("id"),
            "event_type": event_type,
            "call_id": call_id,
            "status": status,
            "profile": profile.model_dump(exclude_none=True) if profile else {},
            "structured_result": structured_result,
            "summary": event_data.get("summary"),
        }

    @staticmethod
    def _tri_state(value: Any) -> Optional[bool]:
        """Map CALL-E yes/no/unknown (or legacy booleans) to True/False/None."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"yes", "true", "1"}:
                return True
            if normalized in {"no", "false", "0"}:
                return False
        return None

    @staticmethod
    def _optional_text(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _optional_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        match = re.search(r"\d+", str(value))
        return int(match.group(0)) if match else None

    @staticmethod
    def _structured_result_to_profile(structured_result: Optional[Dict[str, Any]]) -> Optional[CitizenCallProfile]:
        if not isinstance(structured_result, dict):
            return None

        return CitizenCallProfile(
            language=CalleService._optional_text(structured_result.get("language")),
            state=CalleService._optional_text(structured_result.get("state")),
            district=CalleService._optional_text(structured_result.get("district")),
            age=CalleService._optional_int(structured_result.get("age")),
            gender=CalleService._optional_text(structured_result.get("gender")),
            occupation=CalleService._optional_text(structured_result.get("occupation")),
            farmer=CalleService._tri_state(structured_result.get("farmer")),
            student=CalleService._tri_state(structured_result.get("student")),
            annual_income=CalleService._optional_text(structured_result.get("annual_income")),
            social_category=CalleService._optional_text(structured_result.get("social_category")),
            disability=CalleService._tri_state(structured_result.get("disability")),
            need=CalleService._optional_text(structured_result.get("need")),
            specific_need=CalleService._optional_text(structured_result.get("specific_need")),
        )

    @staticmethod
    def profile_to_matching_profile(data: Dict[str, Any]) -> CitizenProfile:
        income_value = data.get("annual_income")
        annual_income: Optional[float] = None
        if isinstance(income_value, (int, float)) and not isinstance(income_value, bool):
            annual_income = float(income_value)
        elif isinstance(income_value, str):
            digits = re.sub(r"[^\d.]", "", income_value)
            try:
                annual_income = float(digits) if digits else None
            except ValueError:
                annual_income = None
        return CitizenProfile(
            age=CalleService._optional_int(data.get("age")),
            gender=CalleService._optional_text(data.get("gender")),
            state=CalleService._optional_text(data.get("state")),
            occupation=CalleService._optional_text(data.get("occupation")),
            annual_income=annual_income,
            is_student=data.get("student") if isinstance(data.get("student"), bool) else CalleService._tri_state(data.get("student")),
            is_farmer=data.get("farmer") if isinstance(data.get("farmer"), bool) else CalleService._tri_state(data.get("farmer")),
            social_category=CalleService._optional_text(data.get("social_category")),
            needs=[data.get("need")] if CalleService._optional_text(data.get("need")) else None,
        )


calle_service = CalleService(
    api_key=os.getenv("CALLE_API_KEY"),
    base_url=os.getenv("CALLE_BASE_URL"),
    webhook_url=os.getenv("CALLE_WEBHOOK_URL"),
)
