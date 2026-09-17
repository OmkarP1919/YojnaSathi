import asyncio
import json
import unittest
from types import SimpleNamespace

from services.calle.exceptions import CalleAPIError, CalleAuthenticationError, CalleValidationError


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class TestCalleService(unittest.IsolatedAsyncioTestCase):
    async def test_create_call(self):
        from services.calle.service import CalleService

        service = CalleService(api_key="test-key")

        async def fake_request(method, url, json=None, headers=None):
            self.assertEqual(method, "POST")
            self.assertTrue(url.endswith("/calls"))
            self.assertEqual(json["task"].lower().find("yojnasathi"), 0)
            self.assertIn("result_schema", json)
            return _FakeResponse({"id": "call_123", "status": "queued"})

        service._request = fake_request
        result = await service.create_call({"phone_number": "+919876543210", "language": "hi"})
        self.assertTrue(result.success)
        self.assertEqual(result.call_id, "call_123")
        self.assertEqual(result.status, "queued")

    async def test_invalid_phone_number(self):
        from services.calle.service import CalleService

        service = CalleService(api_key="test-key")
        with self.assertRaises(CalleValidationError):
            await service.create_call({"phone_number": "12345"})

    async def test_missing_api_key(self):
        from services.calle.service import CalleService

        with self.assertRaises(CalleAuthenticationError):
            CalleService(api_key="")

    async def test_api_error(self):
        from services.calle.service import CalleService

        service = CalleService(api_key="test-key")

        async def fake_request(method, url, json=None, headers=None):
            raise CalleAPIError("provider returned an error")

        service._request = fake_request
        with self.assertRaises(CalleAPIError):
            await service.create_call({"phone_number": "+919876543210"})

    async def test_call_status(self):
        from services.calle.service import CalleService

        service = CalleService(api_key="test-key")

        async def fake_request(method, url, json=None, headers=None):
            self.assertEqual(method, "GET")
            self.assertTrue(url.endswith("/calls/call_123"))
            return _FakeResponse({"id": "call_123", "status": "in_progress"})

        service._request = fake_request
        result = await service.get_call("call_123")
        self.assertEqual(result.call_id, "call_123")
        self.assertEqual(result.status, "in_progress")

    async def test_webhook(self):
        from services.calle.service import CalleService

        service = CalleService(api_key="test-key")
        payload = {
            "id": "evt_123",
            "type": "call.completed",
            "created_at": "2026-06-08T18:30:00Z",
            "data": {
                "id": "call_123",
                "status": "completed",
                "task_completed": True,
                "structured_result": {"language": "hi", "need": "agriculture", "state": "Maharashtra"},
                "summary": "Citizen wants agriculture help.",
            },
        }
        result = service.handle_webhook(payload, {"CALL-E-Event-Id": "evt_123"})
        self.assertEqual(result["event_id"], "evt_123")
        self.assertEqual(result["call_id"], "call_123")
        self.assertEqual(result["status"], "completed")

    async def test_webhook_maps_and_matches_structured_result(self):
        from services.calle.service import CalleService

        service = CalleService(api_key="test-key")
        payload = {
            "id": "evt_match_1",
            "type": "call.completed",
            "data": {
                "id": "call_match_1",
                "status": "completed",
                "structured_result": {
                    "language": "en",
                    "need": "agriculture",
                    "state": "Maharashtra",
                    "farmer": "yes",
                    "age": "35",
                },
            },
        }
        result = service.handle_webhook(payload, {"CALL-E-Event-Id": "evt_match_1"})
        # Shared CitizenProfile conversion + canonical matching.
        matching_profile = result["matching_profile"]
        self.assertEqual(matching_profile["state"].lower(), "maharashtra")
        self.assertTrue(matching_profile["is_farmer"])
        self.assertEqual(result["matched_category"], "agriculture")
        self.assertGreater(result["matched_scheme_count"], 0)

        matched = result["matched_schemes"][0]
        # Authoritative scheme results carry the Phase 6 application guidance.
        self.assertIn("scheme", matched)
        self.assertIn("relevance_score", matched)
        scheme = matched["scheme"]
        self.assertIn(scheme["id"], {"pm-kisan", "pmfby"})
        guidance = scheme["application_guidance"]
        self.assertTrue(guidance["online_application"]["available"])
        self.assertEqual(guidance["online_application"]["portal_url"], scheme["application_url"])
        self.assertIsNotNone(guidance["documents_required"])

    async def test_webhook_duplicate_keeps_matched_schemes(self):
        from services.calle.service import CalleService

        service = CalleService(api_key="test-key")
        payload = {
            "id": "evt_dup_1",
            "type": "call.completed",
            "data": {
                "id": "call_dup_1",
                "status": "completed",
                "structured_result": {"need": "agriculture", "state": "Maharashtra", "farmer": "yes"},
            },
        }
        first = service.handle_webhook(payload, {"CALL-E-Event-Id": "evt_dup_1"})
        second = service.handle_webhook(payload, {"CALL-E-Event-Id": "evt_dup_1"})
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertGreater(second["matched_scheme_count"], 0)
        self.assertEqual(second["matched_schemes"], first["matched_schemes"])

    async def test_webhook_without_structured_result_returns_empty_matches(self):
        from services.calle.service import CalleService

        service = CalleService(api_key="test-key")
        payload = {
            "id": "evt_noresult",
            "type": "call.completed",
            "data": {"id": "call_noresult", "status": "completed"},
        }
        result = service.handle_webhook(payload, {"CALL-E-Event-Id": "evt_noresult"})
        self.assertEqual(result["matched_scheme_count"], 0)
        self.assertEqual(result["matched_schemes"], [])
        self.assertEqual(result["matching_profile"], {})

    async def test_call_status_returns_matched_schemes(self):
        from services.calle.service import CalleService

        service = CalleService(api_key="test-key")

        async def fake_request(method, url, json=None, headers=None):
            self.assertTrue(url.endswith("/calls/call_match_1"))
            return _FakeResponse(
                {
                    "id": "call_match_1",
                    "status": "completed",
                    "structured_result": {"need": "agriculture", "state": "Maharashtra", "farmer": "yes"},
                }
            )

        service._request = fake_request
        result = await service.get_call("call_match_1")
        self.assertEqual(result.status, "completed")
        self.assertGreater(len(result.matched_schemes), 0)
        self.assertEqual(result.structured_result["need"], "agriculture")
        scheme = result.matched_schemes[0].scheme
        self.assertIn("application_guidance", scheme.model_dump())

    async def test_call_status_without_structured_result_returns_empty_matches(self):
        from services.calle.service import CalleService

        service = CalleService(api_key="test-key")

        async def fake_request(method, url, json=None, headers=None):
            return _FakeResponse({"id": "call_pending", "status": "in_progress"})

        service._request = fake_request
        result = await service.get_call("call_pending")
        self.assertEqual(result.status, "in_progress")
        self.assertEqual(result.matched_schemes, [])

    async def test_build_task_includes_preferred_candidates(self):
        from services.calle.service import CalleService

        service = CalleService(api_key="test-key")
        task = service._build_scheme_call_task(
            "+919876543210",
            language="en",
            initial_context={"profile": {"need": "agriculture", "state": "Maharashtra", "farmer": "yes"}},
        )
        self.assertIn("YojnaSathi preferred candidates", task)
        self.assertIn("The final authoritative matching is computed by YojnaSathi after the call.", task)
        self.assertIn("pm-kisan", task)
        self.assertIn("pmfby", task)

    async def test_build_task_omits_preferred_without_profile(self):
        from services.calle.service import CalleService

        service = CalleService(api_key="test-key")
        task = service._build_scheme_call_task("+919876543210", language="en", initial_context=None)
        self.assertNotIn("preferred candidates", task)
        task_without_ids = service._build_scheme_call_task(
            "+919876543210",
            language="en",
            initial_context={"some": "context", "value": 1},
        )
        self.assertNotIn("preferred candidates", task_without_ids)

    async def test_match_uses_no_real_network(self):
        """Matching happens locally; the only outbound path is CALL-E's _request."""
        from services.calle.service import CalleService

        service = CalleService(api_key="test-key")
        matching_profile, category, results = service._match_structured_result(
            {"need": "agriculture", "state": "Maharashtra", "farmer": "yes"}
        )
        self.assertEqual(category, "agriculture")
        self.assertGreater(len(results), 0)
        self.assertTrue(matching_profile.is_farmer)


if __name__ == "__main__":
    unittest.main()
