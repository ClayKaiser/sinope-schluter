"""Schluter DITRA-HEAT-E-RS1 support."""

from __future__ import annotations

import asyncio
import logging
from typing import cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
import homeassistant.helpers.config_validation as cv

from .api import (
    DeviceInfo,
    EnergyReading,
    JsonObject,
    SchluterApi,
    SchluterApiError,
    SchluterDeviceError,
    SchluterInvalidAuth,
    SchluterRequestError,
    SchluterSessionExpired,
    SchluterError,
    raise_for_api_error,
    require_list,
    require_object,
)
from .const import (
    DOMAIN,
    SUPPORTED_DEVICE_MODELS,
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
    ATTR_SIGNATURE,
    ATTR_TIME,
    ATTR_TEMP,
    STARTUP_MESSAGE,
)
PLATFORMS = [Platform.CLIMATE, Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)

REQUESTS_TIMEOUT = 30
SESSION_LIMIT_RETRY_DELAY = 5 * 60
HOST = "https://schluterditraheat.com"
LOGIN_URL = "{}/api/login".format(HOST)
LOCATIONS_URL = "{}/api/locations?account$id=".format(HOST)
GATEWAY_DEVICE_URL = "{}/api/devices?location$id=".format(HOST)
DEVICE_DATA_URL = "{}/api/device/".format(HOST)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Schluter from a config entry."""
    _LOGGER.info(STARTUP_MESSAGE)

    hass.data.setdefault(DOMAIN, {})

    data = SchluterData()
    try:
        data.api_client = await hass.async_add_executor_job(
            SchluterApiClient,
            entry.data["username"],
            entry.data["password"],
        )
    except SchluterInvalidAuth as err:
        raise ConfigEntryAuthFailed("Schluter rejected the account credentials") from err
    except SchluterError as err:
        if isinstance(err, SchluterApiError) and err.code == "ACCSESSEXC":
            _LOGGER.warning(
                "Schluter rejected the login because too many sessions are active; "
                "deferring the Home Assistant setup retry for 5 minutes"
            )
            await asyncio.sleep(SESSION_LIMIT_RETRY_DELAY)
        raise ConfigEntryNotReady(f"Unable to connect to Schluter: {err}") from err

    from .coordinator import SchluterCoordinator

    try:
        data.coordinator = SchluterCoordinator(hass, entry, data.api_client)
        await data.coordinator.async_config_entry_first_refresh()
        hass.data[DOMAIN]["data"] = data
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True
    except Exception:
        hass.data[DOMAIN].pop("data", None)
        await hass.async_add_executor_job(data.api_client.close)
        raise


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Schluter platforms."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    data = hass.data[DOMAIN].pop("data", None)
    if data is not None:
        await hass.async_add_executor_job(data.api_client.close)
    return True


class SchluterData:
    """Get the latest data and update the states."""

    def __init__(self):
        """Initialize shared Schluter data."""
        self.api_client: SchluterApiClient
        self.coordinator = None

class SchluterApiClient:

    def __init__(
        self,
        email: str,
        password: str,
        timeout: int = REQUESTS_TIMEOUT,
    ) -> None:
        """Initialize the client object."""
        self._email = email
        self._password = password
        self._gateway_ids: list[str] = []
        self._account: str | None = None
        self.gateway_data: list[DeviceInfo] = []
        self._headers: dict[str, str] | None = None
        self._api = SchluterApi(timeout)
        try:
            self.__post_login_page()
            self.__get_network()
            self.__get_gateway_data()
        except Exception:
            self._api.close()
            raise

    def close(self) -> None:
        """Close the HTTP session."""
        self._api.close()

    def reconnect(self) -> None:
        self.__post_login_page()
        self.__get_network()
        self.__get_gateway_data()

    def __post_login_page(self) -> None:
        """Log in to Schluter."""
        data = require_object(
            self._api.request_json(
                "POST",
                LOGIN_URL,
                json={
                    "username": self._email,
                    "password": self._password,
                    "interface": "schluter",
                    "stayConnected": 1,
                },
                allow_redirects=False,
            ),
            "login",
        )
        _LOGGER.debug("Login response: %s", data)
        if "error" in data:
            raise_for_api_error(data, "login")
        try:
            self._headers = {"Session-Id": data["session"]}
            self._account = str(data["account"]["id"])
        except (KeyError, TypeError) as err:
            raise SchluterRequestError(
                "Schluter returned an incomplete login response"
            ) from err
        _LOGGER.debug("Successfully logged in to: %s", self._account)

    def __get_network(self) -> None:
        """Get all location IDs associated with the account."""
        payload = self._api.request_json(
            "GET",
            LOCATIONS_URL + str(self._account),
            headers=self._headers,
        )
        if isinstance(payload, dict):
            raise_for_api_error(payload, "locations")
        networks = require_list(payload, "locations")
        self._gateway_ids = [
            str(network["id"]) for network in networks if network.get("id") is not None
        ]
        _LOGGER.debug("Number of locations found on Schluter: %s", len(networks))
        _LOGGER.debug("networks: %s", networks)

    def __get_gateway_data(self) -> None:
        """Get supported thermostat devices from every account location."""
        self.gateway_data = []
        for gateway_id in self._gateway_ids:
            payload = self._api.request_json(
                "GET",
                GATEWAY_DEVICE_URL + gateway_id,
                headers=self._headers,
            )
            if isinstance(payload, dict):
                raise_for_api_error(payload, f"devices for location {gateway_id}")
            devices = require_list(payload, f"devices for location {gateway_id}")
            for device in devices:
                device_id = device.get("id")
                if (
                    not isinstance(device_id, (str, int))
                    or not isinstance(device.get("name"), str)
                    or not isinstance(device.get("sku"), str)
                ):
                    _LOGGER.warning("Skipping incomplete device record: %s", device)
                    continue
                try:
                    signature_data = self.get_device_attributes(
                        device_id, [ATTR_SIGNATURE]
                    )
                    raise_for_api_error(
                        signature_data, f"device {device_id} signature"
                    )
                except SchluterDeviceError as err:
                    _LOGGER.warning(
                        "Skipping unavailable device %s: %s", device_id, err
                    )
                    continue
                signature = signature_data.get(ATTR_SIGNATURE)
                if not isinstance(signature, dict):
                    _LOGGER.debug("Skipping device without a signature: %s", device_id)
                    continue
                device[ATTR_SIGNATURE] = signature
                if signature.get("model") in SUPPORTED_DEVICE_MODELS:
                    self.gateway_data.append(cast(DeviceInfo, device))

        _LOGGER.debug("Supported Schluter thermostats found: %s", len(self.gateway_data))

    def get_device_attributes(
        self, device_id: str | int, attributes: list[str]
    ) -> JsonObject:
        """Get device attributes."""
        payload = self._api.request_json(
            "GET",
            f"{DEVICE_DATA_URL}{device_id}/attribute?attributes={','.join(attributes)}",
            headers=self._headers,
        )
        return require_object(payload, f"attributes for device {device_id}")

    def get_device_hourly_stats(
        self, device_id: str | int
    ) -> list[EnergyReading] | None:
        """Get device power consumption (in Wh) for the last 24 hours."""
        return self._get_hourly_energy_stats(device_id)

    def _get_hourly_energy_stats(
        self, device_id: str | int
    ) -> list[EnergyReading] | None:
        """Fetch and validate hourly energy history."""
        period = "hourly"
        payload = self._api.request_json(
            "GET",
            f"{DEVICE_DATA_URL}{device_id}/consumption/hourly",
            headers=self._headers,
        )
        response = require_object(payload, f"{period} energy for device {device_id}")
        if "history" not in response:
            raise_for_api_error(response, f"{period} energy for device {device_id}")
            raise SchluterRequestError(
                f"Schluter returned no {period} energy history for device {device_id}"
            )
        history = response["history"]
        if history is None:
            return None
        if not isinstance(history, list):
            raise SchluterRequestError(
                f"Schluter returned invalid {period} energy history for device {device_id}"
            )
        readings: list[EnergyReading] = []
        for item in history:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("date"), str)
                or not isinstance(item.get("period"), (int, float))
            ):
                raise SchluterRequestError(
                    f"Schluter returned invalid {period} energy history for device {device_id}"
                )
            readings.append(
                {"date": item["date"], "period": item["period"]}
            )
        return readings

    def set_setpoint_mode(self, device_id, mode):
        """Set thermostat operation mode."""
        data = {ATTR_SETPOINT_MODE: mode}
        self.set_device_attributes(device_id, data)

    def set_temperature(self, device_id, temperature):
        """Set device temperature."""
        data = {ATTR_ROOM_SETPOINT: temperature}
        self.set_device_attributes(device_id, data)

    def set_keypad_lock(self, device_id, lock):
        """Set device keyboard locked/unlocked."""
        data = {ATTR_KEYPAD: lock}
        _LOGGER.debug("lock.data = %s", data)
        self.set_device_attributes(device_id, data)

    def set_early_start(self, device_id, start):
        """Set device early start heating on / off."""
        data = {ATTR_EARLY_START: start}
        _LOGGER.debug("start.data = %s", data)
        self.set_device_attributes(device_id, data)

    def set_second_display(self, device_id, display):
        """Set device second display for outside temperature or setpoint temperature."""
        data = {ATTR_DISPLAY_2: display}
        _LOGGER.debug("display.data = %s", data)
        self.set_device_attributes(device_id, data)

    def set_time_format(self, device_id, time):
        """Set device time format 12h or 24h."""
        data = {ATTR_TIME: time}
        _LOGGER.debug("time.data = %s", data)
        self.set_device_attributes(device_id, data)

    def set_temperature_format(self, device_id, temp):
        """Set device temperature format: celsius or fahrenheit."""
        data = {ATTR_TEMP: temp}
        _LOGGER.debug("temperature.data = %s", data)
        self.set_device_attributes(device_id, data)

    def set_backlight(self, device_id, level):
        """ Set backlight intensity when idle """
        data = {ATTR_BACKLIGHT: level}
        _LOGGER.debug("backlight.data = %s", data)
        self.set_device_attributes(device_id, data)

    def set_setpoint_min(self, device_id, temp):
        """Set device setpoint minimum temperature."""
        data = {ATTR_ROOM_SETPOINT_MIN: temp}
        _LOGGER.debug("setpointMin.data = %s", data)
        self.set_device_attributes(device_id, data)

    def set_setpoint_max(self, device_id, temp):
        """Set device setpoint maximum temperature."""
        data = {ATTR_ROOM_SETPOINT_MAX: temp}
        _LOGGER.debug("setpointMax.data = %s", data)
        self.set_device_attributes(device_id, data)

    def set_em_heat(self, device_id, heat, cycle, floor):
        """Set floor and low voltage thermostats emergency heating slave/off."""
        if floor:
            data = {ATTR_AUX_CONFIG: heat}
        else:
            if heat == "off":
                data = {ATTR_AUX_CONFIG: heat}
            else:
                data = {ATTR_AUX_CONFIG: heat, ATTR_AUX_CYCLE_LENGTH: cycle}
        _LOGGER.debug("em_heat.data = %s", data)
        self.set_device_attributes(device_id, data)

    def set_cycle_length(self, device_id, length):
        """Set low voltage thermostats main heating cycle."""
        data = {ATTR_CYCLE_LENGTH: length}
        _LOGGER.debug("cycle.data = %s", data)
        self.set_device_attributes(device_id, data)

    def set_aux_cycle_length(self, device_id, output, length):
        """Set low voltage thermostats auxiliary heating output and cycle."""
        data = {ATTR_AUX_CONFIG: output, ATTR_AUX_CYCLE_LENGTH: length}
        _LOGGER.debug("aux_cycle.data = %s", data)
        self.set_device_attributes(device_id, data)

    def set_eco_status(self, device_id, status):
        """Set thermostats eco status on/off."""
        data = {ATTR_SHED_STATUS:{"temperature": status,"power":0,"optOut":0}}
        _LOGGER.debug("Eco.data = %s", data)
        self.set_device_attributes(device_id, data)

    def set_air_floor_mode(self, device_id, mode):
        """Set ambiant or floor temperature control for floor thermostats."""
        data = {ATTR_FLOOR_MODE: mode}
        _LOGGER.debug("airFloorMode.data = %s", data)
        self.set_device_attributes(device_id, data)

    def set_device_attributes(self, device_id: str | int, data: JsonObject) -> None:
        """Set devices attributes."""
        for attempt in range(3):
            response = require_object(
                self._api.request_json(
                    "PUT",
                    f"{DEVICE_DATA_URL}{device_id}/attribute",
                    json=data,
                    headers=self._headers,
                ),
                f"attribute update for device {device_id}",
            )
            try:
                raise_for_api_error(response, f"attribute update for device {device_id}")
            except SchluterSessionExpired:
                raise
            except SchluterApiError:
                if attempt == 2:
                    raise
                _LOGGER.debug(
                    "Retrying Schluter attribute update for device %s (attempt %s)",
                    device_id,
                    attempt + 2,
                )
                continue
            self._request_coordinator_refresh()
            return

    def _request_coordinator_refresh(self):
        """Refresh entities after a successful command."""
        integration_data = self.hass.data.get(DOMAIN, {}).get("data")
        coordinator = getattr(integration_data, "coordinator", None)
        if coordinator is not None:
            self.hass.add_job(coordinator.async_request_refresh)
