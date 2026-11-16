"""Tests for the asynchronous Schluter HTTP transport."""

import sys
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import aiohttp

API_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "sinope_schluter"
    / "api.py"
)
API_SPEC = spec_from_file_location("sinope_schluter_api", API_PATH)
if API_SPEC is None or API_SPEC.loader is None:
    raise RuntimeError("Unable to load the Schluter API module")
API_MODULE = module_from_spec(API_SPEC)
sys.modules[API_SPEC.name] = API_MODULE
API_SPEC.loader.exec_module(API_MODULE)

SchluterApi = API_MODULE.SchluterApi
SchluterInvalidAuth = API_MODULE.SchluterInvalidAuth
SchluterRequestError = API_MODULE.SchluterRequestError


class FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                request_info=None,
                history=(),
                status=self.status,
            )

    async def json(self, *, content_type):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.request_args = None

    def request(self, method, url, **kwargs):
        self.request_args = (method, url, kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class SchluterApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_json_uses_response_and_shared_session(self):
        session = FakeSession(FakeResponse(200, {"ok": True}))
        api = SchluterApi(session, timeout=30)

        payload = await api.async_request_json(
            "POST",
            "https://schluterditraheat.com/api/login",
            json={"username": "user"},
            allow_redirects=False,
        )

        self.assertEqual(payload, {"ok": True})
        method, url, kwargs = session.request_args
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://schluterditraheat.com/api/login")
        self.assertEqual(kwargs["json"], {"username": "user"})
        self.assertFalse(kwargs["allow_redirects"])
        self.assertIsInstance(kwargs["timeout"], aiohttp.ClientTimeout)

    async def test_login_authentication_error_is_classified(self):
        session = FakeSession(FakeResponse(401, {}))
        api = SchluterApi(session, timeout=30)

        with self.assertRaises(SchluterInvalidAuth):
            await api.async_request_json(
                "POST", "https://schluterditraheat.com/api/login"
            )

    async def test_invalid_json_is_reported_as_request_error(self):
        session = FakeSession(FakeResponse(200, ValueError("invalid JSON")))
        api = SchluterApi(session, timeout=30)

        with self.assertRaisesRegex(SchluterRequestError, "invalid JSON"):
            await api.async_request_json(
                "GET", "https://schluterditraheat.com/api/devices"
            )

    async def test_client_errors_are_reported_as_request_errors(self):
        session = FakeSession(error=aiohttp.ClientError("connection failed"))
        api = SchluterApi(session, timeout=30)

        with self.assertRaisesRegex(SchluterRequestError, "connection failed"):
            await api.async_request_json(
                "GET", "https://schluterditraheat.com/api/devices"
            )


if __name__ == "__main__":
    unittest.main()
