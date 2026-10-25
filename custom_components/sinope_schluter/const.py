"""Constants for Schluter component."""

import json
import pathlib

# Base component constants, some loaded directly from the manifest
_LOADER_PATH = pathlib.Path(__loader__.path)
_MANIFEST_PATH = _LOADER_PATH.parent / "manifest.json"
with pathlib.Path.open(_MANIFEST_PATH, encoding="Latin1") as json_file:
    data = json.load(json_file)
NAME = f"{data['name']}"
DOMAIN = f"{data['domain']}"
VERSION = f"{data['version']}"
ISSUE_URL = f"{data['issue_tracker']}"
REQUIRE = "2025.1.1"
DOC_URL = f"{data['documentation']}"

SUPPORTED_DEVICE_MODELS = {740}

STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME} ({DOMAIN})
Version: {VERSION}
Requirement: Home Assistant minimum version {REQUIRE}
This is a custom integration!
If you have any issues with this you need to open an issue here: {ISSUE_URL}
Documentation: {DOC_URL}
-------------------------------------------------------------------
"""

ATTR_ACTIVE = "active"
ATTR_ALARM = "alarmsActive0"
ATTR_ALARM_1 = "alarmsActive1"
ATTR_AUX_CYCLE_LENGTH = "auxOutputCycleLength"
ATTR_AUX_CONFIG = "auxOutputConfig"
ATTR_AUX_OUTPUT_STAGE = "auxOutputStage"
ATTR_AUX_WATTAGE_OVERRIDE = "auxWattageOverride"
ATTR_AWAY_SETPOINT = "roomSetpointAway"
ATTR_BACKLIGHT = "backlightIntensityIdle"
ATTR_BACKLIGHT_MODE = "backlightAdaptive"
ATTR_CYCLE_LENGTH = "cycleLength"
ATTR_DISPLAY_2 = "secondaryDisplay"
ATTR_EARLY_START = "earlyStart"
ATTR_FLOOR_AIR_LIMIT = "floorMaxAirTemperature"
ATTR_FLOOR_MAX = "floorLimitHigh"
ATTR_FLOOR_MIN = "floorLimitLow"
ATTR_FLOOR_MODE = "airFloorMode"
ATTR_FLOOR_SENSOR_TYPE = "floorSensorType"
ATTR_FLOOR_SETPOINT = "floorSetpoint"
ATTR_FLOOR_SETPOINT_MAX = "floorSetpointMax"
ATTR_FLOOR_SETPOINT_MIN = "floorSetpointMin"
ATTR_FLOOR_TEMP = "floorTemperature"
ATTR_KEYPAD = "lockKeypad"
ATTR_OUTPUT_PERCENT_DISPLAY = "outputPercentDisplay"
ATTR_ROOM_SETPOINT = "roomSetpoint"
ATTR_ROOM_SETPOINT_MAX = "roomSetpointMax"
ATTR_ROOM_SETPOINT_MIN = "roomSetpointMin"
ATTR_ROOM_TEMPERATURE = "roomTemperature"
ATTR_RSSI = "rssi"
ATTR_SETPOINT_MODE = "setpointMode"
ATTR_SHED_STATUS = "shedStatus"
ATTR_SIGNATURE = "signature"
ATTR_STATUS = "status"
ATTR_TEMP = "temperatureFormat"
ATTR_TIME = "timeFormat"
ATTR_VALUE = "value"
ATTR_WATTAGE = "wattage"

MODE_AUTO = "auto"
MODE_AUTO_BYPASS = "autoBypass"
MODE_MANUAL = "manual"
MODE_AWAY = "away"
MODE_OFF = "off"
MODE_FROST_PROTEC = "frostProtection"

SERVICE_SET_ACTIVATION = "set_activation"
SERVICE_SET_CLIMATE_KEYPAD_LOCK = "set_climate_keypad_lock"
SERVICE_SET_SECOND_DISPLAY = "set_second_display"
SERVICE_SET_BACKLIGHT = "set_backlight"
SERVICE_SET_EARLY_START = "set_early_start"
SERVICE_SET_TIME_FORMAT = "set_time_format"
SERVICE_SET_TEMPERATURE_FORMAT = "set_temperature_format"
SERVICE_SET_SETPOINT_MAX = "set_setpoint_max"
SERVICE_SET_SETPOINT_MIN = "set_setpoint_min"
SERVICE_SET_AIR_FLOOR_MODE = "set_air_floor_mode"
SERVICE_SET_AUX_CYCLE_LENGTH = "set_aux_cycle_length"
SERVICE_SET_CYCLE_LENGTH = "set_cycle_length"
SERVICE_SET_ECO_STATUS = "set_eco_status"
SERVICE_SET_EM_HEAT = "set_em_heat"
