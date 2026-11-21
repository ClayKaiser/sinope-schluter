"""Data update coordinator for Schluter."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from . import SchluterApiClient, SchluterConfigEntry
from .api import (
    JsonObject,
    SchluterDeviceError,
    SchluterError,
    SchluterInvalidAuth,
    SchluterRequestError,
    SchluterSessionExpired,
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

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(minutes=5)
ENERGY_UPDATE_INTERVAL = timedelta(minutes=30)
DEVICE_DISCOVERY_INTERVAL = timedelta(hours=1)
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


class SchluterCoordinator(DataUpdateCoordinator[dict[str, JsonObject]]):
    """Fetch shared data for Schluter thermostats."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SchluterConfigEntry,
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
        self._entry = entry
        self.client = client
        self._energy_updated_at: dict[str, float] = {}
        self._energy_data: dict[str, JsonObject] = {}
        self._devices_updated_at = time.monotonic()
        self._device_inventory_needs_reconcile = True
        self._unavailable_devices: set[str] = set()
        self._inactive_devices: set[str] = set()

    def set_device_active(self, device_id: str, active: bool) -> None:
        """Enable or pause polling for a thermostat."""
        if active:
            self._inactive_devices.discard(device_id)
        else:
            self._inactive_devices.add(device_id)
        self.hass.add_job(self.async_request_refresh)

    async def _async_update_data(self) -> dict[str, JsonObject]:
        """Fetch the latest state for each supported thermostat."""
        try:
            return await self._async_fetch_data()
        except SchluterInvalidAuth as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except SchluterRequestError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
        except SchluterError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="update_failed"
            ) from err

    async def _async_fetch_data(self) -> dict[str, JsonObject]:
        """Fetch data, reconnecting once if the API session expires."""
        for attempt in range(2):
            try:
                return await self._async_fetch_data_once()
            except SchluterSessionExpired:
                if attempt:
                    raise SchluterError("Schluter session expired after reconnecting")
                _LOGGER.warning("Schluter session expired; reconnecting")
                await self.client.async_reconnect()
                self._devices_updated_at = time.monotonic()
                self._device_inventory_needs_reconcile = True

        raise SchluterError("Unable to refresh Schluter data")

    async def _async_fetch_data_once(self) -> dict[str, JsonObject]:
        """Fetch data using the asynchronous API client."""
        now = time.monotonic()
        if now - self._devices_updated_at >= DEVICE_DISCOVERY_INTERVAL.total_seconds():
            await self.client.async_refresh_devices()
            self._devices_updated_at = now
            self._device_inventory_needs_reconcile = True

        if self._device_inventory_needs_reconcile:
            self._remove_stale_devices()
            self._device_inventory_needs_reconcile = False

        devices: dict[str, JsonObject] = {}
        device_count = 0
        request_failures = 0
        energy_interval = ENERGY_UPDATE_INTERVAL.total_seconds()

        for device in self.client.gateway_data:
            device_id = str(device["id"])
            if device_id in self._inactive_devices:
                if self.data is not None and device_id in self.data:
                    devices[device_id] = self.data[device_id]
                continue
            device_count += 1
            try:
                attributes = await self.client.async_get_device_attributes(
                    device_id, THERMOSTAT_ATTRIBUTES
                )
                raise_for_api_error(attributes, f"attributes for device {device_id}")
            except (SchluterDeviceError, SchluterRequestError) as err:
                if isinstance(err, SchluterRequestError):
                    request_failures += 1
                if device_id not in self._unavailable_devices:
                    _LOGGER.info(
                        "Schluter thermostat %s is unavailable: %s", device_id, err
                    )
                self._unavailable_devices.add(device_id)
                continue

            if device_id in self._unavailable_devices:
                _LOGGER.info("Schluter thermostat %s is available again", device_id)
                self._unavailable_devices.remove(device_id)

            device_data = {
                "attributes": attributes,
            }
            if now - self._energy_updated_at.get(device_id, 0.0) >= energy_interval:
                try:
                    hourly_stats = await self.client.async_get_device_hourly_stats(
                        device_id
                    )
                    if hourly_stats is not None:
                        for reading in hourly_stats:
                            if not isinstance(reading, dict):
                                raise SchluterRequestError(
                                    f"Invalid hourly energy entry for device {device_id}"
                                )
                    self._energy_data[device_id] = {
                        "hourly_stats": hourly_stats,
                        "energy_updated_at": datetime.now(UTC),
                    }
                    self._energy_updated_at[device_id] = now
                except (SchluterDeviceError, SchluterRequestError) as err:
                    _LOGGER.warning(
                        "Unable to refresh energy for device %s: %s", device_id, err
                    )
            device_data.update(self._energy_data.get(device_id, {}))
            devices[device_id] = device_data

        if device_count and not devices and request_failures == device_count:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            )
        if device_count and not devices:
            raise UpdateFailed("Unable to refresh any Schluter thermostats")
        return devices

    def _remove_stale_devices(self) -> None:
        """Remove registry devices missing from the complete cloud inventory."""
        device_registry = dr.async_get(self.hass)
        current_ids = {str(device["id"]) for device in self.client.gateway_data}
        for device_entry in dr.async_entries_for_config_entry(
            device_registry, self._entry.entry_id
        ):
            device_ids = {
                identifier[1]
                for identifier in device_entry.identifiers
                if identifier[0] == DOMAIN
            }
            if device_ids and device_ids.isdisjoint(current_ids):
                device_registry.async_remove_device(device_entry.id)
