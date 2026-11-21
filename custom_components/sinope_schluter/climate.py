"""
Support for Schluter DITRA-HEAT-E-RS1.
"""
import logging
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    PRESET_AWAY,
    PRESET_ECO,
    PRESET_NONE,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import (
    ATTR_TEMPERATURE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SchluterConfigEntry, SchluterData
from .api import DeviceInfo as SchluterDeviceInfo
from .api import SchluterError
from .const import (
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
    MODE_AUTO,
    MODE_AUTO_BYPASS,
    MODE_AWAY,
    MODE_FROST_PROTEC,
    MODE_MANUAL,
    MODE_OFF,
)
from .coordinator import SchluterCoordinator
from .entity import SchluterEntity

_LOGGER = logging.getLogger(__name__)

SUPPORT_AUX_FLAGS = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.PRESET_MODE
    | ClimateEntityFeature.TURN_OFF
    | ClimateEntityFeature.TURN_ON
)

SUPPORTED_HVAC_MODES = [
    HVACMode.OFF,
    HVACMode.AUTO,
    HVACMode.HEAT,
]

PRESET_BYPASS = "temporary"
PRESET_MODES = [PRESET_NONE, PRESET_AWAY, PRESET_ECO, PRESET_BYPASS]

PARALLEL_UPDATES = 1

async def async_setup_entry(
    hass: HomeAssistant,
    entry: SchluterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Schluter thermostats."""
    data = entry.runtime_data

    known_devices: set[str] = set()

    @callback
    def _add_new_devices() -> None:
        current_devices = {
            str(device["id"]): device for device in data.api_client.gateway_data
        }
        known_devices.intersection_update(current_devices)
        new_device_ids = current_devices.keys() - known_devices
        if not new_device_ids:
            return

        entities = []
        for device_id in new_device_ids:
            device_info = current_devices[device_id]
            device_name = device_info["name"]
            device_sku = device_info["sku"]
            entities.append(
                SchluterThermostat(
                    data.coordinator, data, device_info, device_name, device_sku
                )
            )
        known_devices.update(new_device_ids)
        async_add_entities(entities)

    _add_new_devices()
    entry.async_on_unload(data.coordinator.async_add_listener(_add_new_devices))

class SchluterThermostat(SchluterEntity, ClimateEntity):
    """Implementation of a Schluter thermostat."""

    _attr_has_entity_name = True
    _attr_translation_key = "thermostat"
    _enable_turn_on_off_backwards_compatibility = False
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        coordinator: SchluterCoordinator,
        data: SchluterData,
        device_info: SchluterDeviceInfo,
        name: str,
        sku: str,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, device_info)
        self._name = name
        self._client = data.api_client
        self._id = self._device_id
        self._model = device_info["signature"]["model"]
        self._active = True
        self._wattage = 0
        self._min_temp: float = 0
        self._max_temp: float = 0
        self._target_temp: float | None = None
        self._cur_temp: float | None = None
        self._cur_temp_before: float | None = None
        self._rssi = None
        self._early_start = None
        self._operation_mode: str | None = None
        self._heat_level = 0
        self._floor_mode = None
        self._em_heat = None
        self._aux_wattage = None
        self._floor_air_limit = None
        self._floor_max = None
        self._floor_min = None
        self._floor_setpoint = None
        self._floor_temperature = None
        self._floor_temp_error = None
        self._floor_setpoint_max = None
        self._floor_setpoint_min = None
        self._away_temp: float | None = None
        self._keypad = "unlocked"
        self._display_2 = None
        self._backlight = None
        self._sensor_type = None
        self._cycle_length = None
        self._aux_cycle_config = None
        self._aux_cycle_length = None
        self._aux_output_stage = None
        self._pump_protec_freq = None
        self._pump_protec_duration = None
        self._alarm_0_type = None
        self._alarm_0_severity = None
        self._alarm_0_duration = None
        self._alarm_1_type = None
        self._alarm_1_severity = None
        self._alarm_1_duration = None
        self._time_format = "24h"
        self._shed_stat_temp = 0
        self._shed_stat_power = 0
        self._shed_stat_optout = 0
        self._today_energy_kwh: float | None = None
        self._hour_energy_kwh: float | None = None
        self._temperature_format = UnitOfTemperature.CELSIUS
        self._is_low_voltage = False
        self._is_floor = True
        _LOGGER.debug("Setting up %s: %s", self._name, device_info)

    async def _async_command(self, command: Awaitable[None]) -> None:
        """Run an API command and expose failures as Home Assistant errors."""
        try:
            await command
        except SchluterError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="command_failed"
            ) from err

    def _handle_coordinator_update(self) -> None:
        """Update thermostat state from the shared coordinator data."""
        self._update_from_coordinator()
        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """Initialize state from the coordinator's first refresh."""
        await super().async_added_to_hass()
        self._update_from_coordinator()

    def _update_from_coordinator(self) -> None:
        """Apply coordinator data to this thermostat."""
        if self._active:
            device_state = self.coordinator.data.get(self._id)
            if device_state is None:
                return
            device_data = device_state["attributes"]
            _LOGGER.debug("Device data for %s: %s", self._name, device_data)
            if "error" not in device_data:
                if "errorCode" not in device_data:
                    self._cur_temp_before = self._cur_temp
                    # roomTemperature
                    self._cur_temp = float(device_data[ATTR_ROOM_TEMPERATURE]["value"]) if \
                        device_data[ATTR_ROOM_TEMPERATURE]["value"] != None else self._cur_temp_before
                    # setpointMode
                    self._operation_mode = device_data[ATTR_SETPOINT_MODE]
                    # roomSetpoint
                    self._target_temp = float(device_data[ATTR_ROOM_SETPOINT]) if \
                        device_data[ATTR_SETPOINT_MODE] != MODE_OFF else 0.0
                    # outputPercentDisplay
                    if ATTR_OUTPUT_PERCENT_DISPLAY in device_data:
                        self._heat_level = device_data[ATTR_OUTPUT_PERCENT_DISPLAY]["percent"]
                    # airFloorMode
                    if ATTR_FLOOR_MODE in device_data:
                        self._floor_mode = device_data[ATTR_FLOOR_MODE]
                    # floorLimitHigh
                    if ATTR_FLOOR_MAX in device_data:
                        self._floor_max = device_data[ATTR_FLOOR_MAX]["value"]
                    # floorLimitLow
                    if ATTR_FLOOR_MIN in device_data:
                        self._floor_min = device_data[ATTR_FLOOR_MIN]["value"]
                    # floorSensorType
                    if ATTR_FLOOR_SENSOR_TYPE in device_data:
                        self._sensor_type = device_data[ATTR_FLOOR_SENSOR_TYPE]
                    # roomSetpointMin
                    if ATTR_ROOM_SETPOINT_MIN in device_data:
                        self._min_temp = float(device_data[ATTR_ROOM_SETPOINT_MIN])
                    # roomSetpointMax
                    if ATTR_ROOM_SETPOINT_MAX in device_data:
                        self._max_temp = float(device_data[ATTR_ROOM_SETPOINT_MAX])
                    # roomSetpointAway
                    if ATTR_AWAY_SETPOINT in device_data:
                        self._away_temp = float(device_data[ATTR_AWAY_SETPOINT])
                    # timeFormat
                    self._time_format = device_data[ATTR_TIME]
                    # temperatureFormat
                    self._temperature_format = device_data[ATTR_TEMP]
                    # floorMaxAirTemperature
                    if ATTR_FLOOR_AIR_LIMIT in device_data:
                        self._floor_air_limit = device_data[ATTR_FLOOR_AIR_LIMIT]["value"]
                    # floorTemperature
                    if ATTR_FLOOR_TEMP in device_data:
                        self._floor_temperature = device_data[ATTR_FLOOR_TEMP]["value"]
                        self._floor_temp_error = device_data[ATTR_FLOOR_TEMP]["error"]
                    if ATTR_ALARM in device_data:
                        self._alarm_0_type = device_data[ATTR_ALARM]["type"]
                        self._alarm_0_severity = device_data[ATTR_ALARM]["severity"]
                        self._alarm_0_duration = device_data[ATTR_ALARM]["duration"]
                    if ATTR_ALARM_1 in device_data:
                        self._alarm_1_type = device_data[ATTR_ALARM_1]["type"]
                        self._alarm_1_severity = device_data[ATTR_ALARM_1]["severity"]
                        self._alarm_1_duration = device_data[ATTR_ALARM_1]["duration"]
                    if ATTR_SHED_STATUS in device_data:
                        self._shed_stat_temp = device_data[ATTR_SHED_STATUS]["temperature"]
                        self._shed_stat_power = device_data[ATTR_SHED_STATUS]["power"]
                        self._shed_stat_optout = device_data[ATTR_SHED_STATUS]["optOut"]
                else:
                    if device_data["errorCode"] == "ReadTimeout":
                        _LOGGER.warning("Error in reading device %s: (%s), too slow to respond or busy.", self._name, device_data)
                    else:
                        _LOGGER.warning("Unknown errorCode, device: %s, error: %s", self._name, device_data)
            else:
                if device_data["error"]["code"] == "DVCCOMMTO":
                    _LOGGER.warning("Cannot update %s: %s. Device is busy or does not respond quickly enough.", self._name, device_data)
                elif device_data["error"]["code"] == "SVCINVREQ":
                    _LOGGER.warning("Invalid or malformed request to Schluter cloud, %s:", device_data)
                elif device_data["error"]["code"] == "DVCUNVLB":
                    _LOGGER.warning("Device %s unavailable during a Schluter cloud update, %s:", self._name, device_data)
                elif device_data["error"]["code"] == "SVCERR":
                    _LOGGER.warning("Device %s statistics unavailables, %s:", self._name, device_data)
                else:
                    _LOGGER.warning("Unknown error, device: %s, error: %s", self._name, device_data)
            device_hourly_stats = device_state.get("hourly_stats")
            if device_hourly_stats is not None:
                if device_hourly_stats:
                    self._hour_energy_kwh = round(
                        device_hourly_stats[-1]["period"] / 1000, 3
                    )
                now_utc = datetime.now(UTC)
                midnight_utc = now_utc.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                total_wh = 0
                for reading in device_hourly_stats:
                    try:
                        reading_time = datetime.fromisoformat(
                            reading["date"]
                        )
                    except (KeyError, ValueError):
                        _LOGGER.warning(
                            "Invalid hourly energy timestamp for %s: %s",
                            self._name,
                            reading,
                        )
                        continue
                    if reading_time.tzinfo is None:
                        reading_time = reading_time.replace(tzinfo=UTC)
                    if reading_time.astimezone(UTC) >= midnight_utc:
                        total_wh += reading["period"]
                self._today_energy_kwh = round(total_wh / 1000, 3)

    @property
    def unique_id(self) -> str:
        """Return unique ID based on the cloud API device ID."""
        return self._id

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        data = {'sensor_mode': self._floor_mode,
                    'floor_sensor_type': self._sensor_type,
                    'floor_setpoint': self._floor_setpoint,
                    'floor_temperature': self._floor_temperature,
                    'floor_temp_error': self._floor_temp_error,
                    'floor_air_limit': self._floor_air_limit,
                    'floor_temp_max': self._floor_max,
                    'floor_temp_min': self._floor_min,
                    'floor_setpoint_max': self._floor_setpoint_max,
                    'floor_setpoint_min': self._floor_setpoint_min,
                    'heat_level': self._heat_level,
                    'pi_heating_demand': self._heat_level,
                    'wattage': self._wattage,
                    'hourly_kwh': self._hour_energy_kwh,
                    'daily_kwh': self._today_energy_kwh,
                    'rssi': self._rssi,
                    'keypad': self._keypad,
                    'away_setpoint': self._away_temp,
                    'setpoint_max': self._max_temp,
                    'setpoint_min': self._min_temp,
                    'early_start': self._early_start,
                    'sec._display': self._display_2,
                    'backlight': self._backlight,
                    'time_format': self._time_format,
                    'temperature_format': self._temperature_format,
                    'alarm0_type': self._alarm_0_type,
                    'alarm0_severity': self._alarm_0_severity,
                    'alarm0_duration': self._alarm_0_duration,
                    'alarm1_type': self._alarm_1_type,
                    'alarm1_severity': self._alarm_1_severity,
                    'alarm1_duration': self._alarm_1_duration,
                    'sku': self._sku,
                    'model': self._model,
                    'id': str(self._id)}
        return {key: value for key, value in data.items() if value is not None}

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the list of supported features."""
        return SUPPORT_AUX_FLAGS

    @property
    def is_em_heat(self) -> bool:
        """Return True if em_heat is active."""
        return self._em_heat in ["slave", "shortCycle", "longCycle"]

    @property
    def min_temp(self) -> float:
        """Return the min temperature."""
        return self._min_temp

    @property
    def max_temp(self) -> float:
        """Return the max temperature."""
        return self._max_temp

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current operation"""
        if self._operation_mode == MODE_OFF:
            return HVACMode.OFF
        elif self._operation_mode in [MODE_AUTO, MODE_AUTO_BYPASS]:
            return HVACMode.AUTO
        else:
            return HVACMode.HEAT

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the list of available operation modes."""
        return SUPPORTED_HVAC_MODES

    @property
    def native_current_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._cur_temp

    @property
    def native_target_temperature(self) -> float | None:
        """Return the temperature we try to reach."""
        return self._target_temp

    @property
    def preset_modes(self) -> list[str]:
        """Return available preset modes."""
        return PRESET_MODES

    @property
    def preset_mode(self) -> str:
        """Return current preset mode."""
        if self._operation_mode in [MODE_AUTO_BYPASS]:
            return PRESET_BYPASS
        elif self._operation_mode == MODE_AWAY:
            return PRESET_AWAY
        elif self._operation_mode == MODE_FROST_PROTEC:
            return PRESET_ECO
        else:
            return PRESET_NONE

    @property
    def hvac_action(self) -> HVACAction:
        """Return current HVAC action."""
        if self._operation_mode == MODE_OFF:
            return HVACAction.OFF
        elif self._heat_level == 0:
            return HVACAction.IDLE
        else:
            return HVACAction.HEATING

    @property
    def is_on(self) -> bool:
        """Return whether the thermostat is in a mode other than off."""
        return self._operation_mode not in (None, MODE_OFF)

    @property
    def swing_mode(self) -> str | None:
        """Return the fan vertical swing setting."""
        return None

    @property
    def swing_modes(self) -> list[str] | None:
        """Return availables vertical swing modes."""
        return None

    @property
    def swing_horizontal_mode(self) -> str | None:
        """Return the fan swing setting."""
        return None

    @property
    def swing_horizontal_modes(self) -> list[str] | None:
        """Return available horizontal swing modes"""
        return None

    async def async_turn_on(self) -> None:
        """Turn the thermostat to HVACMode.heat on."""
        await self._async_command(
            self._client.async_set_setpoint_mode(self._id, MODE_MANUAL)
        )
        self._operation_mode = MODE_MANUAL

    async def async_turn_off(self) -> None:
        """Turn the thermostat to HVACMode.off."""
        await self._async_command(
            self._client.async_set_setpoint_mode(self._id, MODE_OFF)
        )
        self._operation_mode = MODE_OFF

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_command"
            )
        await self._async_command(
            self._client.async_set_temperature(self._id, temperature)
        )
        self._target_temp = temperature

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new hvac mode."""
        if hvac_mode == HVACMode.OFF:
            mode = MODE_OFF
        elif hvac_mode == HVACMode.HEAT:
            mode = MODE_MANUAL
        elif hvac_mode == HVACMode.AUTO:
            mode = MODE_AUTO
        else:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_command"
            )
        await self._async_command(self._client.async_set_setpoint_mode(self._id, mode))
        self._operation_mode = mode

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Activate a preset."""
        if preset_mode == self.preset_mode:
            return
        if preset_mode == PRESET_AWAY:
            mode = MODE_AWAY
        elif preset_mode == PRESET_BYPASS:
            if self._operation_mode == MODE_AUTO:
                mode = MODE_AUTO_BYPASS
            else:
                return
        elif preset_mode == PRESET_ECO:
            mode = MODE_FROST_PROTEC
        elif preset_mode == PRESET_NONE:
            # Re-apply current hvac_mode without any preset
            await self.async_set_hvac_mode(self.hvac_mode)
            return
        else:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_command"
            )
        await self._async_command(self._client.async_set_setpoint_mode(self._id, mode))
        self._operation_mode = mode
