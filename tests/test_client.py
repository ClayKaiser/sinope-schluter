"""Tests for the Schluter API client."""

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.sinope_schluter import SchluterApiClient
from custom_components.sinope_schluter.api import (
    SchluterApiError,
    SchluterRequestError,
    SchluterSessionExpired,
)
from custom_components.sinope_schluter.const import (
    ATTR_AUX_CONFIG,
    ATTR_AUX_CYCLE_LENGTH,
    ATTR_BACKLIGHT,
    ATTR_CYCLE_LENGTH,
    ATTR_DISPLAY_2,
    ATTR_EARLY_START,
    ATTR_FLOOR_MODE,
    ATTR_KEYPAD,
    ATTR_ROOM_SETPOINT,
    ATTR_ROOM_SETPOINT_MAX,
    ATTR_ROOM_SETPOINT_MIN,
    ATTR_SETPOINT_MODE,
    ATTR_SHED_STATUS,
    ATTR_TEMP,
    ATTR_TIME,
)


async def test_connect_filters_supported_devices(hass):
    supported_device = {"id": 1, "name": "Supported", "sku": "740"}
    unsupported_device = {"id": 2, "name": "Unsupported", "sku": "740"}
    client = SchluterApiClient(hass, AsyncMock(), "user@example.com", "secret")
    client._api.async_request_json = AsyncMock(
        side_effect=[
            {"session": "session-id", "account": {"id": 10}},
            [{"id": 20}, {"name": "missing id"}],
            [supported_device, unsupported_device, {"id": 3, "name": "incomplete"}],
            {"signature": {"model": 740}},
            {"signature": {"model": 999}},
        ]
    )

    await client.async_connect()

    assert client.gateway_data == [
        {**supported_device, "signature": {"model": 740}}
    ]
    assert client._headers == {"Session-Id": "session-id"}
    assert client._account == "10"


async def test_connect_skips_device_with_unavailable_signature(hass):
    client = SchluterApiClient(hass, AsyncMock(), "user@example.com", "secret")
    client._api.async_request_json = AsyncMock(
        side_effect=[
            {"session": "session-id", "account": {"id": 10}},
            [{"id": 20}],
            [{"id": 1, "name": "Thermostat", "sku": "740"}],
            {"errorCode": "DVCUNVLB"},
        ]
    )

    await client.async_connect()

    assert client.gateway_data == []


async def test_connect_rejects_incomplete_login_response(hass):
    client = SchluterApiClient(hass, AsyncMock(), "user@example.com", "secret")
    client._api.async_request_json = AsyncMock(return_value={"account": {"id": 10}})

    with pytest.raises(SchluterRequestError, match="incomplete login"):
        await client.async_connect()


@pytest.mark.parametrize(
    "responses",
    [
        [{"error": {"code": "AUTH", "message": "invalid"}}],
        [{"session": "session-id", "account": {"id": 10}}, {"error": {"code": "FAILED", "message": "locations unavailable"}}],
        [
            {"session": "session-id", "account": {"id": 10}},
            [{"id": 20}],
            {"error": {"code": "FAILED", "message": "devices unavailable"}},
        ],
    ],
)
async def test_connect_propagates_api_errors(hass, responses):
    client = SchluterApiClient(hass, AsyncMock(), "user@example.com", "secret")
    client._api.async_request_json = AsyncMock(side_effect=responses)

    with pytest.raises(SchluterApiError):
        await client.async_connect()


async def test_connect_skips_device_without_signature(hass):
    client = SchluterApiClient(hass, AsyncMock(), "user@example.com", "secret")
    client._api.async_request_json = AsyncMock(
        side_effect=[
            {"session": "session-id", "account": {"id": 10}},
            [{"id": 20}],
            [{"id": 1, "name": "Thermostat", "sku": "740"}],
            {},
        ]
    )

    await client.async_connect()

    assert client.gateway_data == []


async def test_reconnect_and_refresh_devices_reload_inventory(hass):
    client = SchluterApiClient(hass, AsyncMock(), "user@example.com", "secret")
    client._api.async_request_json = AsyncMock(
        side_effect=[
            {"session": "session-id", "account": {"id": 10}},
            [{"id": 20}],
            [],
            [{"id": 21}],
            [],
        ]
    )

    await client.async_reconnect()
    await client.async_refresh_devices()

    assert client._api.async_request_json.await_count == 5
    assert client._gateway_ids == ["21"]


async def test_hourly_energy_history_validation(hass):
    client = SchluterApiClient(hass, AsyncMock(), "user@example.com", "secret")
    client._api.async_request_json = AsyncMock(
        side_effect=[
            {"history": [{"date": "2025-01-01T00:00:00Z", "period": 12.5}]},
            {"history": None},
            {"history": [{"date": "invalid", "period": "12"}]},
            {},
            {"history": "invalid"},
        ]
    )

    assert await client.async_get_device_hourly_stats("1") == [
        {"date": "2025-01-01T00:00:00Z", "period": 12.5}
    ]
    assert await client.async_get_device_hourly_stats("1") is None
    with pytest.raises(SchluterRequestError, match="invalid hourly energy history"):
        await client.async_get_device_hourly_stats("1")
    with pytest.raises(SchluterRequestError, match="no hourly energy history"):
        await client.async_get_device_hourly_stats("1")
    with pytest.raises(SchluterRequestError, match="invalid hourly energy history"):
        await client.async_get_device_hourly_stats("1")


@pytest.mark.parametrize(
    ("method_name", "arguments", "expected"),
    [
        ("async_set_setpoint_mode", ("1", "auto"), {ATTR_SETPOINT_MODE: "auto"}),
        ("async_set_temperature", ("1", 21.5), {ATTR_ROOM_SETPOINT: 21.5}),
        ("async_set_keypad_lock", ("1", "locked"), {ATTR_KEYPAD: "locked"}),
        ("async_set_early_start", ("1", "on"), {ATTR_EARLY_START: "on"}),
        ("async_set_second_display", ("1", "default"), {ATTR_DISPLAY_2: "default"}),
        ("async_set_time_format", ("1", "24h"), {ATTR_TIME: "24h"}),
        (
            "async_set_temperature_format",
            ("1", "celsius"),
            {ATTR_TEMP: "celsius"},
        ),
        ("async_set_backlight", ("1", 50), {ATTR_BACKLIGHT: 50}),
        ("async_set_setpoint_min", ("1", 10.0), {ATTR_ROOM_SETPOINT_MIN: 10.0}),
        ("async_set_setpoint_max", ("1", 25.0), {ATTR_ROOM_SETPOINT_MAX: 25.0}),
        ("async_set_cycle_length", ("1", "long5min"), {ATTR_CYCLE_LENGTH: "long5min"}),
        (
            "async_set_aux_cycle_length",
            ("1", "longCycle", "long5min"),
            {ATTR_AUX_CONFIG: "longCycle", ATTR_AUX_CYCLE_LENGTH: "long5min"},
        ),
        (
            "async_set_eco_status",
            ("1", 1),
            {ATTR_SHED_STATUS: {"temperature": 1, "power": 0, "optOut": 0}},
        ),
        ("async_set_air_floor_mode", ("1", "floor"), {ATTR_FLOOR_MODE: "floor"}),
    ],
)
async def test_attribute_setters_delegate_to_attribute_update(
    hass, method_name, arguments, expected
):
    client = SchluterApiClient(hass, AsyncMock(), "user@example.com", "secret")
    client.async_set_device_attributes = AsyncMock()

    await getattr(client, method_name)(*arguments)

    client.async_set_device_attributes.assert_awaited_once_with("1", expected)


@pytest.mark.parametrize(
    ("heat", "cycle", "floor", "expected"),
    [
        ("slave", "short", True, {ATTR_AUX_CONFIG: "slave"}),
        ("off", None, False, {ATTR_AUX_CONFIG: "off"}),
        (
            "slave",
            "short",
            False,
            {ATTR_AUX_CONFIG: "slave", ATTR_AUX_CYCLE_LENGTH: "short"},
        ),
    ],
)
async def test_emergency_heat_attribute_selection(hass, heat, cycle, floor, expected):
    client = SchluterApiClient(hass, AsyncMock(), "user@example.com", "secret")
    client.async_set_device_attributes = AsyncMock()

    await client.async_set_em_heat("1", heat, cycle, floor)

    client.async_set_device_attributes.assert_awaited_once_with("1", expected)


async def test_low_voltage_emergency_heat_requires_cycle_length(hass):
    client = SchluterApiClient(hass, AsyncMock(), "user@example.com", "secret")
    client.async_set_device_attributes = AsyncMock()

    with pytest.raises(SchluterRequestError, match="cycle length is required"):
        await client.async_set_em_heat("1", "slave", None, False)

    client.async_set_device_attributes.assert_not_awaited()


async def test_attribute_update_retries_api_errors_and_refreshes_entities(hass):
    client = SchluterApiClient(hass, AsyncMock(), "user@example.com", "secret")
    client._api.async_request_json = AsyncMock(
        side_effect=[
            {"error": {"code": "UNKNOWN", "message": "retry"}},
            {"ok": True},
        ]
    )
    client._request_coordinator_refresh = Mock()

    await client.async_set_device_attributes("1", {"roomSetpoint": 21})

    assert client._api.async_request_json.await_count == 2
    client._request_coordinator_refresh.assert_called_once_with()


async def test_attribute_update_does_not_retry_expired_session(hass):
    client = SchluterApiClient(hass, AsyncMock(), "user@example.com", "secret")
    client._api.async_request_json = AsyncMock(
        return_value={"error": {"code": "USRSESSEXP", "message": "expired"}}
    )

    with pytest.raises(SchluterSessionExpired):
        await client.async_set_device_attributes("1", {"roomSetpoint": 21})

    assert client._api.async_request_json.await_count == 1


async def test_attribute_update_raises_after_retries_are_exhausted(hass):
    client = SchluterApiClient(hass, AsyncMock(), "user@example.com", "secret")
    client._api.async_request_json = AsyncMock(
        return_value={"error": {"code": "UNKNOWN", "message": "failed"}}
    )

    with pytest.raises(SchluterApiError):
        await client.async_set_device_attributes("1", {"roomSetpoint": 21})

    assert client._api.async_request_json.await_count == 3


async def test_coordinator_refresh_callback_is_scheduled(hass):
    client = SchluterApiClient(hass, AsyncMock(), "user@example.com", "secret")
    callback = Mock()
    hass.add_job = Mock()
    client.set_coordinator_refresh_callback(callback)

    client._request_coordinator_refresh()

    hass.add_job.assert_called_once_with(callback)


async def test_device_attributes_require_object_response(hass):
    client = SchluterApiClient(hass, AsyncMock(), "user@example.com", "secret")
    client._api.async_request_json = AsyncMock(return_value=[])

    with pytest.raises(SchluterRequestError, match="invalid attributes"):
        await client.async_get_device_attributes("1", ["roomTemperature"])
