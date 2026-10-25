"""Data update coordinator for Schluter."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import (
    JsonObject,
    SchluterDeviceError,
    SchluterInvalidAuth,
    SchluterRequestError,
    SchluterSessionExpired,
    SchluterError,
    raise_for_api_error,
)
from .const import (
    ATTR_ALARM,
    ATTR_ALARM_1,
    ATTR_AUX_CONFIG,
    ATTR_AUX_OUTPUT_STAGE,
    ATTR_AUX_WATTAGE_OVERRIDE,
    ATTR_AWAY_SETPOINT,
    ATTR_BACKLIGHT_MODE,
    ATTR_DISPLAY_2,
    ATTR_EARLY_START,
    ATTR_FLOOR_AIR_LIMIT,
    ATTR_FLOOR_MAX,
    ATTR_FLOOR_MIN,
    ATTR_FLOOR_MODE,
    ATTR_FLOOR_SENSOR_TYPE,
    ATTR_FLOOR_SETPOINT,
    ATTR_FLOOR_SETPOINT_MAX,
    ATTR_FLOOR_SETPOINT_MIN,
    ATTR_FLOOR_TEMP,
    ATTR_KEYPAD,
    ATTR_OUTPUT_PERCENT_DISPLAY,
    ATTR_ROOM_SETPOINT,
    ATTR_ROOM_SETPOINT_MAX,
    ATTR_ROOM_SETPOINT_MIN,
    ATTR_ROOM_TEMPERATURE,
    ATTR_RSSI,
    ATTR_SETPOINT_MODE,
    ATTR_SHED_STATUS,
    ATTR_TEMP,
    ATTR_TIME,
    ATTR_WATTAGE,
    DOMAIN,
)
from . import SchluterApiClient

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(minutes=5)
ENERGY_UPDATE_INTERVAL = timedelta(minutes=30)
THERMOSTAT_ATTRIBUTES = [
    ATTR_SETPOINT_MODE,
    ATTR_RSSI,
    ATTR_ROOM_SETPOINT,
    ATTR_OUTPUT_PERCENT_DISPLAY,
    ATTR_ROOM_TEMPERATURE,
    ATTR_ROOM_SETPOINT_MIN,
    ATTR_ROOM_SETPOINT_MAX,
    ATTR_ALARM,
    ATTR_AWAY_SETPOINT,
    ATTR_EARLY_START,
    ATTR_KEYPAD,
    ATTR_DISPLAY_2,
    ATTR_TIME,
    ATTR_TEMP,
    ATTR_BACKLIGHT_MODE,
    ATTR_FLOOR_MODE,
    ATTR_AUX_CONFIG,
    ATTR_AUX_WATTAGE_OVERRIDE,
    ATTR_FLOOR_MAX,
    ATTR_FLOOR_MIN,
    ATTR_FLOOR_AIR_LIMIT,
    ATTR_FLOOR_SETPOINT_MAX,
    ATTR_FLOOR_SETPOINT_MIN,
    ATTR_FLOOR_SETPOINT,
    ATTR_FLOOR_TEMP,
    ATTR_FLOOR_SENSOR_TYPE,
    ATTR_ALARM_1,
    ATTR_AUX_OUTPUT_STAGE,
    ATTR_WATTAGE,
    ATTR_SHED_STATUS,
]


class SchluterCoordinator(DataUpdateCoordinator):
    """Fetch shared data for Schluter thermostats."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SchluterApiClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self._energy_updated_at: dict[str, float] = {}
        self._energy_data: dict[str, JsonObject] = {}

    async def _async_update_data(self) -> dict[str, JsonObject]:
        """Fetch the latest state for each supported thermostat."""
        try:
            return await self.hass.async_add_executor_job(self._fetch_data)
        except SchluterInvalidAuth as err:
            raise ConfigEntryAuthFailed(
                "Schluter rejected the account credentials"
            ) from err
        except SchluterError as err:
            raise UpdateFailed(f"Unable to update Schluter data: {err}") from err

    def _fetch_data(self) -> dict[str, JsonObject]:
        """Fetch data, reconnecting once if the API session expires."""
        for attempt in range(2):
            try:
                return self._fetch_data_once()
            except SchluterSessionExpired:
                if attempt:
                    raise SchluterError("Schluter session expired after reconnecting")
                _LOGGER.warning("Schluter session expired; reconnecting")
                self.client.reconnect()

        raise SchluterError("Unable to refresh Schluter data")

    def _fetch_data_once(self) -> dict[str, JsonObject]:
        """Fetch data using the blocking API client."""
        now = time.monotonic()
        devices: dict[str, JsonObject] = {}
        device_count = 0
        energy_interval = ENERGY_UPDATE_INTERVAL.total_seconds()

        for device in self.client.gateway_data:
            device_count += 1
            device_id = str(device["id"])
            try:
                attributes = self.client.get_device_attributes(
                    device_id, THERMOSTAT_ATTRIBUTES
                )
                raise_for_api_error(attributes, f"attributes for device {device_id}")
            except (SchluterDeviceError, SchluterRequestError) as err:
                _LOGGER.warning(
                    "Unable to refresh device %s attributes: %s", device_id, err
                )
                continue

            device_data = {
                "attributes": attributes,
            }
            if now - self._energy_updated_at.get(device_id, 0.0) >= energy_interval:
                try:
                    hourly_stats = self.client.get_device_hourly_stats(device_id)
                    if hourly_stats is not None:
                        for reading in hourly_stats:
                            if not isinstance(reading, dict):
                                raise SchluterRequestError(
                                    f"Invalid hourly energy entry for device {device_id}"
                                )
                    self._energy_data[device_id] = {
                        "hourly_stats": hourly_stats,
                        "energy_updated_at": datetime.now(timezone.utc),
                    }
                    self._energy_updated_at[device_id] = now
                except (SchluterDeviceError, SchluterRequestError) as err:
                    _LOGGER.warning(
                        "Unable to refresh energy for device %s: %s", device_id, err
                    )
            device_data.update(self._energy_data.get(device_id, {}))
            devices[device_id] = device_data

        if device_count and not devices:
            raise UpdateFailed("Unable to refresh any Schluter thermostats")
        return devices
