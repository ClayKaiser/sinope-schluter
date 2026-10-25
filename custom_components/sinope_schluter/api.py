"""HTTP transport and response types for Schluter."""

from __future__ import annotations

from threading import RLock
from typing import Any, TypedDict
from urllib.parse import urlparse

import requests

JsonObject = dict[str, Any]
JsonValue = JsonObject | list[JsonObject]


DeviceInfo = TypedDict(
    "DeviceInfo",
    {
        "id": str | int,
        "name": str,
        "sku": str,
        "signature": JsonObject,
    },
)


class EnergyReading(TypedDict):
    """One hourly or daily energy history reading."""

    date: str
    period: int | float


class SchluterError(Exception):
    """Base exception for Schluter API failures."""


class SchluterRequestError(SchluterError):
    """Transport, HTTP status, or JSON decoding failure."""


class SchluterApiError(SchluterError):
    """Error returned in a Schluter API response."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{message} ({code})")
        self.code = code


class SchluterSessionExpired(SchluterApiError):
    """The current Schluter API session is no longer valid."""


class SchluterInvalidAuth(SchluterApiError):
    """The Schluter account rejected the supplied credentials."""


class SchluterDeviceError(SchluterApiError):
    """A failure confined to an individual device or location."""


class SchluterApi:
    """Own the HTTP session and normalize transport errors."""

    def __init__(self, timeout: int) -> None:
        self._session = requests.Session()
        self._timeout = timeout
        self._lock = RLock()

    def request_json(self, method: str, url: str, **kwargs: Any) -> JsonValue:
        """Issue a request and return a validated JSON object or list."""
        try:
            with self._lock:
                response = self._session.request(
                    method,
                    url,
                    timeout=self._timeout,
                    **kwargs,
                )
                response.raise_for_status()
                payload = response.json()
        except requests.HTTPError as err:
            response = err.response
            if (
                response is not None
                and response.status_code in {401, 403}
                and method.upper() == "POST"
                and urlparse(url).path.endswith("/api/login")
            ):
                raise SchluterInvalidAuth(
                    str(response.status_code),
                    "Schluter rejected the account credentials",
                ) from err
            raise SchluterRequestError(
                f"Schluter cloud request failed: {err}"
            ) from err
        except requests.RequestException as err:
            raise SchluterRequestError(f"Schluter cloud request failed: {err}") from err
        except ValueError as err:
            raise SchluterRequestError("Schluter cloud returned invalid JSON") from err

        if not isinstance(payload, (dict, list)):
            raise SchluterRequestError("Schluter cloud returned an unexpected JSON value")
        return payload

    def close(self) -> None:
        """Close the underlying HTTP session."""
        with self._lock:
            self._session.close()


def require_object(payload: JsonValue, context: str) -> JsonObject:
    """Require an object response where the API contract expects one."""
    if not isinstance(payload, dict):
        raise SchluterRequestError(f"Schluter cloud returned an invalid {context} response")
    return payload


def require_list(payload: JsonValue, context: str) -> list[JsonObject]:
    """Require a list of object responses where the API contract expects one."""
    if not isinstance(payload, list) or not all(
        isinstance(item, dict) for item in payload
    ):
        raise SchluterRequestError(f"Schluter cloud returned an invalid {context} response")
    return payload


def raise_for_api_error(response: JsonObject, context: str) -> None:
    """Convert API error responses to typed exceptions."""
    error = response.get("error")
    if not isinstance(error, dict):
        if "error" in response:
            raise SchluterRequestError(f"Schluter cloud returned a malformed {context} error")
        if "errorCode" in response:
            raise SchluterDeviceError(str(response["errorCode"]), context)
        return

    code = str(error.get("code", "UNKNOWN"))
    message = str(error.get("message", context))
    if code == "USRSESSEXP":
        raise SchluterSessionExpired(code, message)
    if code in {"DVCCOMMTO", "DVCUNVLB", "SVCERR"}:
        raise SchluterDeviceError(code, message)
    raise SchluterApiError(code, message)
