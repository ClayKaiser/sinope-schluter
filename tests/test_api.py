"""Tests for the asynchronous Schluter HTTP transport."""

import unittest
from types import SimpleNamespace

import aiohttp

from custom_components.sinope_schluter.api import (
    SchluterApi,
    SchluterApiError,
    SchluterDeviceError,
    SchluterInvalidAuth,
    SchluterRequestError,
    SchluterSessionExpired,
    raise_for_api_error,
    require_list,
    require_object,
)


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
                request_info=SimpleNamespace(real_url="https://schluterditraheat.com"),
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

    async def test_timeout_and_non_json_values_are_reported(self):
        timeout_api = SchluterApi(
            FakeSession(error=TimeoutError()), timeout=30
        )
        with self.assertRaises(SchluterRequestError):
            await timeout_api.async_request_json(
                "GET", "https://schluterditraheat.com/api/devices"
            )

        invalid_api = SchluterApi(FakeSession(FakeResponse(200, 42)), timeout=30)
        with self.assertRaisesRegex(SchluterRequestError, "unexpected JSON"):
            await invalid_api.async_request_json(
                "GET", "https://schluterditraheat.com/api/devices"
            )

    async def test_non_login_http_errors_are_request_errors(self):
        api = SchluterApi(FakeSession(FakeResponse(403, {})), timeout=30)
        with self.assertRaises(SchluterRequestError):
            await api.async_request_json(
                "GET", "https://schluterditraheat.com/api/devices"
            )

    def test_require_object_and_list_validate_payloads(self):
        self.assertEqual(require_object({"ok": True}, "response"), {"ok": True})
        self.assertEqual(require_list([{"id": 1}], "response"), [{"id": 1}])
        with self.assertRaises(SchluterRequestError):
            require_object([], "response")
        with self.assertRaises(SchluterRequestError):
            require_list([{"id": 1}, None], "response")

    def test_api_errors_are_converted_to_typed_exceptions(self):
        raise_for_api_error({"ok": True}, "response")
        with self.assertRaises(SchluterRequestError):
            raise_for_api_error({"error": "malformed"}, "response")
        with self.assertRaises(SchluterDeviceError):
            raise_for_api_error({"errorCode": "DVCUNVLB"}, "response")
        with self.assertRaises(SchluterSessionExpired):
            raise_for_api_error(
                {"error": {"code": "USRSESSEXP", "message": "expired"}},
                "response",
            )
        with self.assertRaises(SchluterDeviceError):
            raise_for_api_error(
                {"error": {"code": "DVCUNVLB", "message": "offline"}},
                "response",
            )
        with self.assertRaises(SchluterApiError):
            raise_for_api_error(
                {"error": {"code": "UNKNOWN", "message": "failed"}},
                "response",
            )


if __name__ == "__main__":
    unittest.main()
