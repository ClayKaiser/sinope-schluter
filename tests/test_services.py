"""Tests for globally registered Schluter actions."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import (
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sinope_schluter import async_setup
from custom_components.sinope_schluter.api import SchluterError
from custom_components.sinope_schluter.const import (
    ATTR_ACTIVE,
    ATTR_BACKLIGHT,
    ATTR_DISPLAY_2,
    ATTR_EARLY_START,
    ATTR_FLOOR_MODE,
    ATTR_KEYPAD,
    ATTR_ROOM_SETPOINT_MAX,
    ATTR_ROOM_SETPOINT_MIN,
    ATTR_STATUS,
    ATTR_TEMP,
    ATTR_TIME,
    ATTR_VALUE,
    DOMAIN,
    SERVICE_SET_ACTIVATION,
    SERVICE_SET_AIR_FLOOR_MODE,
    SERVICE_SET_AUX_CYCLE_LENGTH,
    SERVICE_SET_BACKLIGHT,
    SERVICE_SET_CLIMATE_KEYPAD_LOCK,
    SERVICE_SET_CYCLE_LENGTH,
    SERVICE_SET_EARLY_START,
    SERVICE_SET_ECO_STATUS,
    SERVICE_SET_EM_HEAT,
    SERVICE_SET_SECOND_DISPLAY,
    SERVICE_SET_SETPOINT_MAX,
    SERVICE_SET_SETPOINT_MIN,
    SERVICE_SET_TEMPERATURE_FORMAT,
    SERVICE_SET_TIME_FORMAT,
)
from custom_components.sinope_schluter.services import _async_execute_action

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


async def test_actions_registered_during_integration_setup(hass):
    service_names = (
        SERVICE_SET_ACTIVATION,
        SERVICE_SET_AIR_FLOOR_MODE,
        SERVICE_SET_AUX_CYCLE_LENGTH,
        SERVICE_SET_BACKLIGHT,
        SERVICE_SET_CLIMATE_KEYPAD_LOCK,
        SERVICE_SET_CYCLE_LENGTH,
        SERVICE_SET_EARLY_START,
        SERVICE_SET_ECO_STATUS,
        SERVICE_SET_EM_HEAT,
        SERVICE_SET_SECOND_DISPLAY,
        SERVICE_SET_SETPOINT_MAX,
        SERVICE_SET_SETPOINT_MIN,
        SERVICE_SET_TEMPERATURE_FORMAT,
        SERVICE_SET_TIME_FORMAT,
    )

    assert await async_setup(hass, {})
    assert all(hass.services.has_service(DOMAIN, name) for name in service_names)


async def test_action_targets_loaded_thermostat(hass):
    await async_setup(hass, {})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "user@example.com", "password": "secret"},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.sinope_schluter.SchluterApiClient.async_connect",
        new_callable=AsyncMock,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)

    registry_entry = er.async_get(hass).async_get_or_create(
        "climate",
        DOMAIN,
        "thermostat-id",
        config_entry=entry,
    )
    with patch.object(
        entry.runtime_data.api_client, "async_set_backlight", new_callable=AsyncMock
    ) as set_backlight:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_BACKLIGHT,
            {"entity_id": registry_entry.entity_id, ATTR_BACKLIGHT: 35},
            blocking=True,
        )

    set_backlight.assert_awaited_once_with("thermostat-id", 35)

    with patch.object(
        entry.runtime_data.api_client, "async_set_early_start", new_callable=AsyncMock
    ) as set_early_start:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_EARLY_START,
            {"entity_id": registry_entry.entity_id, ATTR_EARLY_START: "on"},
            blocking=True,
        )

    set_early_start.assert_awaited_once_with("thermostat-id", "on")

    entry.runtime_data.api_client.gateway_data = [
        {"id": "thermostat-id", "name": "Thermostat", "sku": "OTH3600-GA-GT"}
    ]
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_EARLY_START,
            {"entity_id": registry_entry.entity_id, ATTR_EARLY_START: "on"},
            blocking=True,
        )


@pytest.mark.parametrize(
    ("service_name", "attribute", "value", "method", "expected"),
    [
        (SERVICE_SET_SECOND_DISPLAY, ATTR_DISPLAY_2, "default", "async_set_second_display", ("device", "default")),
        (SERVICE_SET_BACKLIGHT, ATTR_BACKLIGHT, 45, "async_set_backlight", ("device", 45)),
        (SERVICE_SET_CLIMATE_KEYPAD_LOCK, ATTR_KEYPAD, "locked", "async_set_keypad_lock", ("device", "locked")),
        (SERVICE_SET_EARLY_START, ATTR_EARLY_START, "on", "async_set_early_start", ("device", "on")),
        (SERVICE_SET_TIME_FORMAT, ATTR_TIME, 12, "async_set_time_format", ("device", "12h")),
        (SERVICE_SET_TIME_FORMAT, ATTR_TIME, 24, "async_set_time_format", ("device", "24h")),
        (SERVICE_SET_TEMPERATURE_FORMAT, ATTR_TEMP, "celsius", "async_set_temperature_format", ("device", "celsius")),
        (SERVICE_SET_SETPOINT_MAX, ATTR_ROOM_SETPOINT_MAX, 28, "async_set_setpoint_max", ("device", 28)),
        (SERVICE_SET_SETPOINT_MIN, ATTR_ROOM_SETPOINT_MIN, 7, "async_set_setpoint_min", ("device", 7)),
        (SERVICE_SET_AIR_FLOOR_MODE, ATTR_FLOOR_MODE, "floor", "async_set_air_floor_mode", ("device", "floor")),
        (SERVICE_SET_CYCLE_LENGTH, ATTR_VALUE, ["15 sec"], "async_set_cycle_length", ("device", "short")),
        (SERVICE_SET_AUX_CYCLE_LENGTH, ATTR_VALUE, ["5 min"], "async_set_aux_cycle_length", ("device", "longCycle", "long5min")),
        (SERVICE_SET_ECO_STATUS, ATTR_STATUS, 1, "async_set_eco_status", ("device", 1)),
        (SERVICE_SET_EM_HEAT, ATTR_VALUE, "on", "async_set_em_heat", ("device", "slave", None, True)),
    ],
)
async def test_action_dispatches_to_api(
    service_name, attribute, value, method, expected
):
    client = Mock()
    api_method = AsyncMock()
    setattr(client, method, api_method)

    await _async_execute_action(
        client, Mock(), service_name, "device", {attribute: value}
    )

    api_method.assert_awaited_once_with(*expected)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, ("device", True)), (False, ("device", False))],
)
async def test_activation_action_updates_coordinator(value, expected):
    coordinator = Mock()

    await _async_execute_action(
        Mock(), coordinator, SERVICE_SET_ACTIVATION, "device", {ATTR_ACTIVE: value}
    )

    coordinator.set_device_active.assert_called_once_with(*expected)


async def test_action_translates_api_errors():
    client = Mock()
    client.async_set_backlight = AsyncMock(
        side_effect=SchluterError("Schluter command failed")
    )

    with pytest.raises(HomeAssistantError):
        await _async_execute_action(
            client,
            Mock(),
            SERVICE_SET_BACKLIGHT,
            "device",
            {ATTR_BACKLIGHT: 45},
        )


async def test_action_requires_a_target(hass):
    await async_setup(hass, {})

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_BACKLIGHT,
            {"area_id": "missing-area", ATTR_BACKLIGHT: 45},
            blocking=True,
        )


async def test_action_rejects_unknown_entity(hass):
    await async_setup(hass, {})

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_BACKLIGHT,
            {"entity_id": "climate.missing", ATTR_BACKLIGHT: 45},
            blocking=True,
        )
