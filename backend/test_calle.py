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


if __name__ == "__main__":
    unittest.main()
