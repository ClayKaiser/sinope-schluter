"""Tests for Schluter climate, sensor, and shared entity behavior."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.climate import ClimateEntityFeature
from homeassistant.components.climate.const import (
    PRESET_AWAY,
    PRESET_ECO,
    PRESET_NONE,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sinope_schluter import SchluterApiClient
from custom_components.sinope_schluter.api import (
    SchluterApiError,
)
from custom_components.sinope_schluter.climate import (
    PRESET_BYPASS,
    SchluterThermostat,
)
from custom_components.sinope_schluter.const import (
    ATTR_ALARM,
    ATTR_ALARM_1,
    ATTR_AWAY_SETPOINT,
    ATTR_FLOOR_AIR_LIMIT,
    ATTR_FLOOR_MAX,
    ATTR_FLOOR_MIN,
    ATTR_FLOOR_MODE,
    ATTR_FLOOR_SENSOR_TYPE,
    ATTR_FLOOR_TEMP,
    ATTR_OUTPUT_PERCENT_DISPLAY,
    ATTR_ROOM_SETPOINT,
    ATTR_ROOM_SETPOINT_MAX,
    ATTR_ROOM_SETPOINT_MIN,
    ATTR_ROOM_TEMPERATURE,
    ATTR_SETPOINT_MODE,
    ATTR_SHED_STATUS,
    ATTR_TEMP,
    ATTR_TIME,
    DOMAIN,
    MODE_MANUAL,
    MODE_OFF,
)
from custom_components.sinope_schluter.coordinator import SchluterCoordinator
from custom_components.sinope_schluter.sensor import SchluterEnergySensor

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

DEVICE = {
    "id": "thermostat-1",
    "name": "Thermostat",
    "sku": "740",
    "signature": {"model": 740},
}
ATTRIBUTES = {
    ATTR_ROOM_TEMPERATURE: {"value": 21.5},
    ATTR_SETPOINT_MODE: MODE_MANUAL,
    ATTR_ROOM_SETPOINT: 22,
    ATTR_OUTPUT_PERCENT_DISPLAY: {"percent": 35},
    ATTR_FLOOR_MODE: "floor",
    ATTR_FLOOR_MAX: {"value": 30},
    ATTR_FLOOR_MIN: {"value": 5},
    ATTR_FLOOR_SENSOR_TYPE: "10k",
    ATTR_ROOM_SETPOINT_MIN: 5,
    ATTR_ROOM_SETPOINT_MAX: 30,
    ATTR_AWAY_SETPOINT: 15,
    ATTR_TIME: "24h",
    ATTR_TEMP: "celsius",
    ATTR_FLOOR_AIR_LIMIT: {"value": 35},
    ATTR_FLOOR_TEMP: {"value": 24, "error": None},
    ATTR_ALARM: {"type": "none", "severity": 0, "duration": 0},
    ATTR_ALARM_1: {"type": "none", "severity": 0, "duration": 0},
    ATTR_SHED_STATUS: {"temperature": 1, "power": 0, "optOut": 0},
}


async def test_entities_update_state_and_run_climate_commands(hass):
    async def connect(client):
        client.gateway_data = [DEVICE]

    async def get_attributes(client, device_id, attributes):
        return ATTRIBUTES

    async def get_energy(client, device_id):
        return []

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "user@example.com", "password": "secret"},
    )
    entry.add_to_hass(hass)
    with (
        patch.object(SchluterApiClient, "async_connect", new=connect),
        patch.object(
            SchluterApiClient, "async_get_device_attributes", new=get_attributes
        ),
        patch.object(
            SchluterApiClient, "async_get_device_hourly_stats", new=get_energy
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)

    data = entry.runtime_data
    coordinator = data.coordinator
    energy_time = datetime.now(UTC).replace(minute=10, second=0, microsecond=0)
    coordinator.async_set_updated_data(
        {
            DEVICE["id"]: {
                "attributes": ATTRIBUTES,
                "hourly_stats": [
                    {"date": "invalid timestamp", "period": 50},
                    {
                        "date": (energy_time - timedelta(days=1)).isoformat(),
                        "period": 900,
                    },
                    {"date": energy_time.isoformat(), "period": 1500},
                ],
                "energy_updated_at": energy_time,
            }
        }
    )

    climate = SchluterThermostat(
        coordinator, data, DEVICE, DEVICE["name"], DEVICE["sku"]
    )
    climate._update_from_coordinator()
    assert climate.available
    assert climate.unique_id == DEVICE["id"]
    assert climate.native_current_temperature == 21.5
    assert climate.native_target_temperature == 22.0
    assert climate.min_temp == 5.0
    assert climate.max_temp == 30.0
    assert climate.hvac_mode == HVACMode.HEAT
    assert climate.hvac_modes == [HVACMode.OFF, HVACMode.AUTO, HVACMode.HEAT]
    assert climate.hvac_action == HVACAction.HEATING
    assert climate.supported_features == (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )
    assert climate.temperature_unit == UnitOfTemperature.CELSIUS
    assert climate.preset_mode == PRESET_NONE
    assert climate.preset_modes == [PRESET_NONE, PRESET_AWAY, PRESET_ECO, PRESET_BYPASS]
    assert climate.is_on
    assert not climate.is_em_heat
    assert climate.swing_mode is None
    assert climate.swing_modes is None
    assert climate.swing_horizontal_mode is None
    assert climate.swing_horizontal_modes is None
    attributes = climate.extra_state_attributes
    assert attributes["floor_temperature"] == 24
    assert attributes["daily_kwh"] == 1.5
    assert attributes["hourly_kwh"] == 1.5
    assert attributes["id"] == DEVICE["id"]
    assert climate.device_info["manufacturer"] == "Schluter"

    client = data.api_client
    client.async_set_temperature = AsyncMock()
    client.async_set_setpoint_mode = AsyncMock()
    with pytest.raises(ServiceValidationError):
        await climate.async_set_temperature(**{ATTR_TEMPERATURE: None})
    await climate.async_set_temperature(**{ATTR_TEMPERATURE: 24})
    client.async_set_temperature.assert_awaited_once_with(DEVICE["id"], 24)
    assert climate.native_target_temperature == 24

    await climate.async_set_hvac_mode(HVACMode.OFF)
    client.async_set_setpoint_mode.assert_awaited_with(DEVICE["id"], MODE_OFF)
    assert climate.hvac_mode == HVACMode.OFF
    assert not climate.is_on
    await climate.async_turn_on()
    await climate.async_turn_off()
    assert client.async_set_setpoint_mode.await_count == 3

    with pytest.raises(ServiceValidationError):
        await climate.async_set_hvac_mode("invalid")
    await climate.async_set_hvac_mode(HVACMode.AUTO)
    assert climate.hvac_mode == HVACMode.AUTO
    await climate.async_set_preset_mode(PRESET_BYPASS)
    assert climate.preset_mode == PRESET_BYPASS
    await climate.async_set_preset_mode(PRESET_AWAY)
    assert climate.preset_mode == PRESET_AWAY
    await climate.async_set_preset_mode(PRESET_ECO)
    assert climate.preset_mode == PRESET_ECO
    await climate.async_set_preset_mode(PRESET_NONE)
    assert climate.preset_mode == PRESET_NONE

    sensor = SchluterEnergySensor(coordinator, DEVICE)
    fixed_now = datetime(2025, 1, 2, 12, 10, tzinfo=UTC)
    coordinator.async_set_updated_data(
        {
            DEVICE["id"]: {
                "attributes": ATTRIBUTES,
                "hourly_stats": [
                    {"date": fixed_now.isoformat(), "period": 1200},
                    {
                        "date": (fixed_now - timedelta(days=1)).isoformat(),
                        "period": 900,
                    },
                    {"date": "invalid timestamp", "period": 50},
                ],
                "energy_updated_at": fixed_now,
            }
        }
    )
    with patch("custom_components.sinope_schluter.sensor.dt") as datetime_type:
        datetime_type.now.return_value = fixed_now
        datetime_type.fromisoformat.side_effect = datetime.fromisoformat
        sensor._update_from_coordinator()
    assert sensor.native_value == 1.2
    assert sensor.last_reset == datetime(2025, 1, 2, tzinfo=UTC)
    assert sensor.native_unit_of_measurement == "kWh"
    assert sensor.device_class.value == "energy"
    assert sensor.state_class.value == "total"
    assert sensor.extra_state_attributes == {"sku": "740", "id": DEVICE["id"]}

    coordinator.async_set_updated_data({})
    assert not climate.available
    assert not sensor.available


@pytest.mark.parametrize(
    "attributes",
    [
        {"errorCode": "ReadTimeout"},
        {"errorCode": "unknown"},
        {"error": {"code": "DVCCOMMTO"}},
        {"error": {"code": "SVCINVREQ"}},
        {"error": {"code": "DVCUNVLB"}},
        {"error": {"code": "SVCERR"}},
        {"error": {"code": "unknown"}},
    ],
)
async def test_climate_logs_device_errors(hass, attributes):
    async def connect(client):
        client.gateway_data = [DEVICE]

    async def get_attributes(client, device_id, requested):
        return ATTRIBUTES

    async def get_energy(client, device_id):
        return None

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "user@example.com", "password": "secret"},
    )
    entry.add_to_hass(hass)
    with (
        patch.object(SchluterApiClient, "async_connect", new=connect),
        patch.object(
            SchluterApiClient, "async_get_device_attributes", new=get_attributes
        ),
        patch.object(
            SchluterApiClient, "async_get_device_hourly_stats", new=get_energy
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)

    climate = SchluterThermostat(
        entry.runtime_data.coordinator,
        entry.runtime_data,
        DEVICE,
        DEVICE["name"],
        DEVICE["sku"],
    )
    entry.runtime_data.coordinator.async_set_updated_data(
        {DEVICE["id"]: {"attributes": attributes}}
    )
    climate._update_from_coordinator()
    assert climate.available
    assert climate.native_current_temperature is None
    assert climate.native_target_temperature is None


async def test_climate_command_errors_are_translated(hass):
    async def connect(client):
        client.gateway_data = [DEVICE]

    async def get_attributes(client, device_id, requested):
        return ATTRIBUTES

    async def get_energy(client, device_id):
        return None

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "user@example.com", "password": "secret"},
    )
    entry.add_to_hass(hass)
    with (
        patch.object(SchluterApiClient, "async_connect", new=connect),
        patch.object(
            SchluterApiClient, "async_get_device_attributes", new=get_attributes
        ),
        patch.object(
            SchluterApiClient, "async_get_device_hourly_stats", new=get_energy
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)

    climate = SchluterThermostat(
        entry.runtime_data.coordinator,
        entry.runtime_data,
        DEVICE,
        DEVICE["name"],
        DEVICE["sku"],
    )
    climate._client.async_set_temperature = AsyncMock(
        side_effect=SchluterApiError("FAILED", "failed")
    )

    with pytest.raises(HomeAssistantError):
        await climate.async_set_temperature(**{ATTR_TEMPERATURE: 20})

    with pytest.raises(ServiceValidationError):
        await climate.async_set_preset_mode("unsupported")


async def test_sensor_timestamp_parser_handles_iso_variants(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    sensor = SchluterEnergySensor(
        SchluterCoordinator(hass, entry, AsyncMock()), DEVICE
    )

    assert sensor._parse_iso_timestamp("2025-01-02T12:00:00Z") == datetime(
        2025, 1, 2, 12, tzinfo=UTC
    )
    assert sensor._parse_iso_timestamp("2025-01-02T12:00:00") == datetime(
        2025, 1, 2, 12, tzinfo=UTC
    )
    assert sensor._parse_iso_timestamp(None) is None


async def test_sensor_skips_early_and_missing_coordinator_updates(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    sensor = SchluterEnergySensor(
        SchluterCoordinator(hass, entry, AsyncMock()), DEVICE
    )

    early = datetime(2025, 1, 2, 0, 3, tzinfo=UTC)
    with patch("custom_components.sinope_schluter.sensor.dt") as datetime_type:
        datetime_type.now.return_value = early
        sensor._update_from_coordinator()

    assert sensor.last_reset == datetime(2025, 1, 2, tzinfo=UTC)
    assert sensor.native_value == 0

    later = datetime(2025, 1, 2, 12, 10, tzinfo=UTC)
    with patch("custom_components.sinope_schluter.sensor.dt") as datetime_type:
        datetime_type.now.return_value = later
        sensor._update_from_coordinator()

    assert sensor.native_value == 0
