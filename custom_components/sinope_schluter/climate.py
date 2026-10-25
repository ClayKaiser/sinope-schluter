"""
Support for Schluter DITRA-HEAT-E-RS1.
"""
import logging
from datetime import datetime, timezone

import voluptuous as vol

from .coordinator import SchluterCoordinator
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate.const import (
    PRESET_AWAY,
    PRESET_ECO,
    PRESET_NONE,
)

from homeassistant.const import (
    ATTR_TEMPERATURE,
    UnitOfTemperature,
)

from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import (
    DOMAIN,
    SUPPORTED_DEVICE_MODELS,
    ATTR_ACTIVE,
    ATTR_ALARM,
    ATTR_ALARM_1,
    ATTR_AWAY_SETPOINT,
    ATTR_BACKLIGHT,
    ATTR_DISPLAY_2,
    ATTR_EARLY_START,
    ATTR_FLOOR_AIR_LIMIT,
    ATTR_FLOOR_MAX,
    ATTR_FLOOR_MIN,
    ATTR_FLOOR_MODE,
    ATTR_FLOOR_SENSOR_TYPE,
    ATTR_FLOOR_TEMP,
    ATTR_KEYPAD,
    ATTR_OUTPUT_PERCENT_DISPLAY,
    ATTR_ROOM_SETPOINT,
    ATTR_ROOM_SETPOINT_MAX,
    ATTR_ROOM_SETPOINT_MIN,
    ATTR_ROOM_TEMPERATURE,
    ATTR_SETPOINT_MODE,
    ATTR_SHED_STATUS,
    ATTR_STATUS,
    ATTR_TEMP,
    ATTR_TIME,
    ATTR_VALUE,
    MODE_AUTO,
    MODE_AUTO_BYPASS,
    MODE_AWAY,
    MODE_FROST_PROTEC,
    MODE_MANUAL,
    MODE_OFF,
    SERVICE_SET_ACTIVATION,
    SERVICE_SET_AIR_FLOOR_MODE,
    SERVICE_SET_AUX_CYCLE_LENGTH,
    SERVICE_SET_BACKLIGHT,
    SERVICE_SET_CLIMATE_KEYPAD_LOCK,
    SERVICE_SET_CYCLE_LENGTH,
    SERVICE_SET_EARLY_START,
    SERVICE_SET_EM_HEAT,
    SERVICE_SET_SECOND_DISPLAY,
    SERVICE_SET_SETPOINT_MAX,
    SERVICE_SET_SETPOINT_MIN,
    SERVICE_SET_TEMPERATURE_FORMAT,
    SERVICE_SET_TIME_FORMAT,
    SERVICE_SET_ECO_STATUS,
)

_LOGGER = logging.getLogger(__name__)

SUPPORT_AUX_FLAGS = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.PRESET_MODE
    | ClimateEntityFeature.TURN_OFF
    | ClimateEntityFeature.TURN_ON
)

PERIOD_VALUE = {"15 sec", "5 min", "10 min", "15 min", "20 min", "25 min", "30 min"}

HA_TO_SCHLUTER_PERIOD = {
    '15 sec': 'short',
    '5 min': 'long5min',
    '10 min': 'long10min',
    '15 min': 'long15min',
    '20 min': 'long20min',
    '25 min': 'long25min',
    '30 min': 'long30min'
}

SUPPORTED_HVAC_MODES = [
    HVACMode.OFF,
    HVACMode.AUTO,
    HVACMode.HEAT,
]

PRESET_BYPASS = 'temporary'
PRESET_MODES = [
    PRESET_NONE,
    PRESET_AWAY,
    PRESET_ECO,
    PRESET_BYPASS,
]

IMPLEMENTED_DEVICE_MODEL = SUPPORTED_DEVICE_MODELS

SET_ACTIVATION_SCHEMA = {
    vol.Required(ATTR_ACTIVE): vol.In([True, False]),
}

SET_SECOND_DISPLAY_SCHEMA = {
    vol.Required(ATTR_DISPLAY_2): vol.In(["outsideTemperature", "default"]),
}

SET_BACKLIGHT_SCHEMA = {
    vol.Required(ATTR_BACKLIGHT): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=100)
    ),
}

SET_CLIMATE_KEYPAD_LOCK_SCHEMA = {
    vol.Required(ATTR_KEYPAD): vol.In(["locked", "unlocked"]),
}

SET_TIME_FORMAT_SCHEMA = {
    vol.Required(ATTR_TIME): vol.All(
        vol.Coerce(int), vol.Range(min=12, max=24)
    ),
}

SET_TEMPERATURE_FORMAT_SCHEMA = {
    vol.Required(ATTR_TEMP): vol.In(["celsius", "fahrenheit"]),
}

SET_EARLY_START_SCHEMA = {
    vol.Required(ATTR_EARLY_START): vol.In(["on", "off"]),
}

SET_SETPOINT_MAX_SCHEMA = {
    vol.Required(ATTR_ROOM_SETPOINT_MAX): vol.All(
        vol.Coerce(float), vol.Range(min=10, max=30)
    ),
}

SET_SETPOINT_MIN_SCHEMA = {
    vol.Required(ATTR_ROOM_SETPOINT_MIN): vol.All(
        vol.Coerce(float), vol.Range(min=5, max=24)
    ),
}

SET_AIR_FLOOR_MODE_SCHEMA = {
    vol.Required(ATTR_FLOOR_MODE): vol.In(["airByFloor", "floor"]),
}

SET_CYCLE_LENGTH_SCHEMA = {
    vol.Required(ATTR_VALUE): vol.All(
        cv.ensure_list, [vol.In(PERIOD_VALUE)]
    ),
}

SET_AUX_CYCLE_LENGTH_SCHEMA = {
    vol.Required(ATTR_VALUE): vol.All(
        cv.ensure_list, [vol.In(PERIOD_VALUE)]
    ),
}

SET_ECO_STATUS_SCHEMA = {
    vol.Required(ATTR_STATUS): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=1)
    ),
}

SET_EM_HEAT_SCHEMA = {
    vol.Required(ATTR_VALUE): vol.In(["on", "off"]),
}

async def async_setup_entry(
    hass,
    entry,
    async_add_entities,
) -> None:
    """Set up the Schluter thermostats."""
    data = hass.data[DOMAIN]["data"]

    entities = []
    for device_info in data.api_client.gateway_data:
        if "signature" in device_info and \
            "model" in device_info["signature"] and \
            device_info["signature"]["model"] in IMPLEMENTED_DEVICE_MODEL:
            device_name = device_info["name"]
            device_sku = device_info["sku"]
            entities.append(
                SchluterThermostat(
                    data.coordinator, data, device_info, device_name, device_sku
                )
            )

    async_add_entities(entities)

    platform = entity_platform.async_get_current_platform()
    entity_services = (
        (
            SERVICE_SET_ACTIVATION,
            SET_ACTIVATION_SCHEMA,
            "set_activation",
            ATTR_ACTIVE,
            "active",
            False,
        ),
        (
            SERVICE_SET_SECOND_DISPLAY,
            SET_SECOND_DISPLAY_SCHEMA,
            "set_second_display",
            ATTR_DISPLAY_2,
            "display",
            False,
        ),
        (
            SERVICE_SET_BACKLIGHT,
            SET_BACKLIGHT_SCHEMA,
            "set_backlight",
            ATTR_BACKLIGHT,
            "level",
            False,
        ),
        (
            SERVICE_SET_CLIMATE_KEYPAD_LOCK,
            SET_CLIMATE_KEYPAD_LOCK_SCHEMA,
            "set_keypad_lock",
            ATTR_KEYPAD,
            "lock",
            False,
        ),
        (
            SERVICE_SET_EARLY_START,
            SET_EARLY_START_SCHEMA,
            "set_early_start",
            ATTR_EARLY_START,
            "start",
            False,
        ),
        (
            SERVICE_SET_TIME_FORMAT,
            SET_TIME_FORMAT_SCHEMA,
            "set_time_format",
            ATTR_TIME,
            "time",
            False,
        ),
        (
            SERVICE_SET_TEMPERATURE_FORMAT,
            SET_TEMPERATURE_FORMAT_SCHEMA,
            "set_temperature_format",
            ATTR_TEMP,
            "temp",
            False,
        ),
        (
            SERVICE_SET_SETPOINT_MAX,
            SET_SETPOINT_MAX_SCHEMA,
            "set_setpoint_max",
            ATTR_ROOM_SETPOINT_MAX,
            "temp",
            False,
        ),
        (
            SERVICE_SET_SETPOINT_MIN,
            SET_SETPOINT_MIN_SCHEMA,
            "set_setpoint_min",
            ATTR_ROOM_SETPOINT_MIN,
            "temp",
            False,
        ),
        (
            SERVICE_SET_AIR_FLOOR_MODE,
            SET_AIR_FLOOR_MODE_SCHEMA,
            "set_air_floor_mode",
            ATTR_FLOOR_MODE,
            "mode",
            False,
        ),
        (
            SERVICE_SET_CYCLE_LENGTH,
            SET_CYCLE_LENGTH_SCHEMA,
            "set_cycle_length",
            ATTR_VALUE,
            "length",
            True,
        ),
        (
            SERVICE_SET_AUX_CYCLE_LENGTH,
            SET_AUX_CYCLE_LENGTH_SCHEMA,
            "set_aux_cycle_length",
            ATTR_VALUE,
            "length",
            True,
        ),
        (
            SERVICE_SET_ECO_STATUS,
            SET_ECO_STATUS_SCHEMA,
            "set_eco_status",
            ATTR_STATUS,
            "status",
            False,
        ),
        (
            SERVICE_SET_EM_HEAT,
            SET_EM_HEAT_SCHEMA,
            "set_em_heat",
            ATTR_VALUE,
            None,
            False,
        ),
    )
    for (
        service_name,
        schema,
        method_name,
        field,
        value_key,
        first_value,
    ) in entity_services:
        platform.async_register_entity_service(
            service_name,
            schema,
            _entity_service_handler(
                hass,
                method_name,
                field,
                value_key,
                first_value=first_value,
            ),
        )


def _entity_service_handler(
    hass, method_name, field, value_key, *, first_value=False
):
    """Create an entity service that invokes the blocking Schluter API off-loop."""

    async def async_handle(entity, service_call):
        value = service_call.data[field]

        def call_service():
            if method_name == "set_em_heat":
                if value == "on":
                    entity.turn_em_heat_on()
                else:
                    entity.turn_em_heat_off()
                return

            if first_value:
                value_to_set = value[0]
            else:
                value_to_set = value
            getattr(entity, method_name)(
                {"id": entity.unique_id, value_key: value_to_set}
            )

        await hass.async_add_executor_job(call_service)
        entity.async_write_ha_state()

    return async_handle

def schluter_to_ha(value):
    keys = [k for k, v in HA_TO_SCHLUTER_PERIOD.items() if v == value]
    if keys:
        return keys[0]
    return None

def temp_format_to_ha(value):
    if value == "celsius":
        return UnitOfTemperature.CELSIUS
    else:
        return UnitOfTemperature.FAHRENHEIT

class SchluterThermostat(CoordinatorEntity, ClimateEntity):
    """Implementation of a Schluter thermostat."""

    _attr_has_entity_name = True
    _attr_name = "Thermostat"
    _enable_turn_on_off_backwards_compatibility = False
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator: SchluterCoordinator, data, device_info, name, sku):
        """Initialize."""
        super().__init__(coordinator)
        self._name = name
        self._sku = sku
        self._client = data.api_client
        self._id = str(device_info["id"])
        self._model = device_info["signature"]["model"]
        self._active = True
        self._wattage = 0
        self._min_temp = 0
        self._max_temp = 0
        self._target_temp = None
        self._cur_temp = None
        self._cur_temp_before = None
        self._rssi = None
        self._early_start = None
        self._operation_mode = None
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
        self._away_temp = None
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
        self._today_energy_kwh = None
        self._hour_energy_kwh = None
        self._temperature_format = UnitOfTemperature.CELSIUS
        self._is_low_voltage = False
        self._is_floor = True
        _LOGGER.debug("Setting up %s: %s", self._name, device_info)

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
                now_utc = datetime.now(timezone.utc)
                midnight_utc = now_utc.replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                total_wh = 0
                for reading in device_hourly_stats:
                    try:
                        reading_time = datetime.fromisoformat(
                            reading["date"].replace("Z", "+00:00")
                        )
                    except (KeyError, ValueError):
                        _LOGGER.warning(
                            "Invalid hourly energy timestamp for %s: %s",
                            self._name,
                            reading,
                        )
                        continue
                    if reading_time.tzinfo is None:
                        reading_time = reading_time.replace(tzinfo=timezone.utc)
                    if reading_time.astimezone(timezone.utc) >= midnight_utc:
                        total_wh += reading["period"]
                self._today_energy_kwh = round(total_wh / 1000, 3)

    @property
    def unique_id(self):
        """Return unique ID based on the cloud API device ID."""
        return self._id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group with other entities."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._id)},
            name=self._name,
            manufacturer="Schluter",
            model=self._sku,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def extra_state_attributes(self):
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
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_AUX_FLAGS

    @property
    def is_em_heat(self):
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
    def temperature_unit(self):
        """Return the unit of measurement."""
        return UnitOfTemperature.CELSIUS

    @property
    def hvac_mode(self):
        """Return current operation"""
        if self._operation_mode == MODE_OFF:
            return HVACMode.OFF
        elif self._operation_mode in [MODE_AUTO, MODE_AUTO_BYPASS]:
            return HVACMode.AUTO
        else:
            return HVACMode.HEAT

    @property
    def hvac_modes(self):
        """Return the list of available operation modes."""
        return SUPPORTED_HVAC_MODES

    @property
    def current_temperature(self) -> float:
        """Return the current temperature."""
        return self._cur_temp

    @property
    def target_temperature(self) -> float:
        """Return the temperature we try to reach."""
        return self._target_temp

    @property
    def preset_modes(self):
        """Return available preset modes."""
        return PRESET_MODES

    @property
    def preset_mode(self):
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
    def hvac_action(self):
        """Return current HVAC action."""
        if self._operation_mode == MODE_OFF:
            return HVACAction.OFF
        elif self._heat_level == 0:
            return HVACAction.IDLE
        else:
            return HVACAction.HEATING

    @property
    def is_on(self):
        """Return True if mode = HVACMode.HEAT or HVACMode.AUTO."""
        if self._operation_mode == HVACMode.HEAT or self._operation_mode == HVACMode.AUTO:
            return True
        return False

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

    def set_activation(self, value):
        """Activate or deactivate polling for a missing thermostat."""
        self._active = value["active"]

    def turn_on(self):
        """Turn the thermostat to HVACMode.heat on."""
        self._client.set_setpoint_mode(self._id, MODE_MANUAL)
        self._operation_mode = HVACMode.HEAT

    def turn_off(self):
        """Turn the thermostat to HVACMode.off."""
        self._client.set_setpoint_mode(self._id, MODE_OFF)
        self._operation_mode = HVACMode.OFF

    def set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        self._client.set_temperature(self._id, temperature)
        self._target_temp = temperature

    def set_second_display(self, value):
        """ Set thermostat second display between outside and setpoint temperature. """
        display = value["display"]
        entity = value["id"]
        if display == "default":
            display_command = "default"
            display_name = "Setpoint"
        else:
            display_command = "outsideTemperature"
            display_name = "Outside"
        self._client.set_second_display(
            entity, display_command)
        self._display_2 = display_name

    def set_backlight(self, value):
        """ Set thermostat backlight intensity when idle, 0 = off, 100 = always on. """
        level = value["level"]
        entity = value["id"]
        self._client.set_backlight(
            entity, level)
        self._backlight = level

    def set_keypad_lock(self, value):
        """ Lock or unlock device's keypad, «locked» = Locked, «unlocked» = Unlocked. """
        lock = value["lock"]
        entity = value["id"]
        _LOGGER.debug("lock.data.before = %s", lock)
        self._client.set_keypad_lock(
            entity, lock)
        self._keypad = lock

    def set_early_start(self, value):
        """set early start heating for thermostat, On = early start set to on, Off = set to Off"""
        """This function is not available for Ouellet OTH3600-GA-GT"""
        if self._sku == "OTH3600-GA-GT":
            self._early_start = None
        else:
            start = value["start"]
            entity = value["id"]
            self._client.set_early_start(
                entity, start)
            self._early_start = start

    def set_time_format(self, value):
        """set time format 12h or 24h"""
        time = value["time"]
        entity = value["id"]
        if time == 12:
            time_commande = "12h"
        else:
            time_commande = "24h"
        self._client.set_time_format(
            entity, time_commande)
        self._time_format = time_commande

    def set_temperature_format(self, value):
        """set temperature format celsius or fahrenheit"""
        temp = value["temp"]
        entity = value["id"]
        self._client.set_temperature_format(
            entity, temp)
        if temp == "celsius":
            self._temperature_format = UnitOfTemperature.CELSIUS
        else:
            self._temperature_format = UnitOfTemperature.FAHRENHEIT

    def set_setpoint_max(self, value):
        """set maximum setpoint temperature"""
        temp = value["temp"]
        entity = value["id"]
        self._client.set_setpoint_max(
            entity, temp)
        self._max_temp = temp

    def set_setpoint_min(self, value):
        """set minimum setpoint temperature"""
        temp = value["temp"]
        entity = value["id"]
        self._client.set_setpoint_min(
            entity, temp)
        self._min_temp = temp

    def set_air_floor_mode(self, value):
        """ set ambiant or floor temperature control"""
        mode = value["mode"]
        entity = value["id"]
        self._client.set_air_floor_mode(
            entity, mode)
        self._floor_mode = mode

    def set_eco_status(self, value):
        """ set eco status on/off"""
        status = value["status"]
        entity = value["id"]
        self._client.set_eco_status(
            entity, status)
        self._shed_stat_temp = status

    def set_hvac_mode(self, hvac_mode):
        """Set new hvac mode."""
        if hvac_mode == HVACMode.OFF:
            self._client.set_setpoint_mode(self._id, MODE_OFF)
        elif hvac_mode == HVACMode.HEAT:
            self._client.set_setpoint_mode(self._id, MODE_MANUAL)
        elif hvac_mode == HVACMode.AUTO:
            self._client.set_setpoint_mode(self._id, MODE_AUTO)
        else:
            _LOGGER.error("Unable to set hvac mode: %s.", hvac_mode)
        self._operation_mode = hvac_mode

    def set_preset_mode(self, preset_mode):
        """Activate a preset."""
        if preset_mode == self.preset_mode:
            return
        if preset_mode == PRESET_AWAY:
            self._client.set_setpoint_mode(self._id, MODE_AWAY)
        elif preset_mode == PRESET_BYPASS:
            if self._operation_mode == MODE_AUTO:
                self._client.set_setpoint_mode(self._id, MODE_AUTO_BYPASS)
        elif preset_mode == PRESET_ECO:
            self._client.set_setpoint_mode(self._id, MODE_FROST_PROTEC)
        elif preset_mode == PRESET_NONE:
            # Re-apply current hvac_mode without any preset
            self.set_hvac_mode(self.hvac_mode)
        else:
            _LOGGER.error("Unable to set preset mode: %s.", preset_mode)
        self._operation_mode = preset_mode

    def set_cycle_length(self, value):
        """Set main cycle length for low voltage thermostats"""
        val = value["length"]
        entity = value["id"]
        length = [v for k, v in HA_TO_SCHLUTER_PERIOD.items() if k == val][0]
        self._client.set_cycle_length(
            entity, length)
        self._cycle_length = length

    def set_aux_cycle_length(self, value):
        """Set auxiliary cycle length for low voltage thermostats"""
        val = value["length"]
        entity = value["id"]
        length = [v for k, v in HA_TO_SCHLUTER_PERIOD.items() if k == val][0]
        if length == "short":
            output = "shortCycle"
        else:
            output = "longCycle"
        self._client.set_aux_cycle_length(
            entity, output, length)
        self._aux_cycle_config = output
        self._aux_cycle_length = length

    def turn_em_heat_on(self):
        """Turn emergency heater on."""
        self._em_heat = "slave"
        self._client.set_em_heat(
            self._id, self._em_heat, self._aux_cycle_length, self._is_floor)

    def turn_em_heat_off(self):
        """Turn emergency heater off."""
        self._em_heat = "off"
        self._client.set_em_heat(
            self._id, "off", self._aux_cycle_length, self._is_floor)
