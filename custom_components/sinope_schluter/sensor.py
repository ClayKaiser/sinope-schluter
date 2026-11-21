"""Sensor entities for the Schluter DITRA-HEAT-E-RS1 integration."""

import datetime
import logging
from datetime import datetime as dt

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SchluterConfigEntry
from .api import DeviceInfo as SchluterDeviceInfo
from .coordinator import SchluterCoordinator
from .entity import SchluterEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SchluterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Schluter energy sensor."""
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
            entities.append(SchluterEnergySensor(data.coordinator, device_info))
        known_devices.update(new_device_ids)
        async_add_entities(entities)

    _add_new_devices()
    entry.async_on_unload(data.coordinator.async_add_listener(_add_new_devices))


class SchluterEnergySensor(SchluterEntity, SensorEntity):
    """Sensor for daily energy consumption from a thermostat."""

    _attr_has_entity_name = True
    _attr_translation_key = "daily_energy"

    def __init__(
        self,
        coordinator: SchluterCoordinator,
        device_info: SchluterDeviceInfo,
    ) -> None:
        """Initialize the daily energy sensor."""
        super().__init__(coordinator, device_info)
        self._attr_native_value: float = 0.0
        # Initialize last_reset to midnight UTC
        now_utc = dt.now(datetime.UTC)
        self._attr_last_reset: datetime.datetime = now_utc.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        self._attr_unique_id = f"{self._device_id}_daily_energy"
        self._last_energy_update: datetime.datetime | None = None
        _LOGGER.debug("Setting up daily energy sensor for %s", self._device_name)

    @property
    def native_value(self) -> float:
        """Return the cumulative daily energy consumption in kWh."""
        return self._attr_native_value

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return UnitOfEnergy.KILO_WATT_HOUR

    @property
    def device_class(self) -> SensorDeviceClass:
        """Return the device class."""
        return SensorDeviceClass.ENERGY

    @property
    def state_class(self) -> SensorStateClass:
        """Return the state class indicating this is a total aggregated value."""
        return SensorStateClass.TOTAL

    @property
    def last_reset(self) -> datetime.datetime:
        """Return midnight UTC for the current daily total."""
        return self._attr_last_reset

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return the state attributes."""
        return {
            'sku': self._sku,
            'id': self._device_id,
        }

    def _parse_iso_timestamp(self, iso_str: str) -> datetime.datetime | None:
        """Parse ISO 8601 timestamp string to datetime object."""
        if not isinstance(iso_str, str):
            _LOGGER.error("Invalid energy timestamp: %s", iso_str)
            return None

        try:
            if iso_str.endswith('Z'):
                iso_str = iso_str[:-1] + '+00:00'
            parsed = dt.fromisoformat(iso_str)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=datetime.UTC)
            return parsed.astimezone(datetime.UTC)
        except ValueError as err:
            _LOGGER.error("Failed to parse timestamp %s: %s", iso_str, err)
            return None

    async def async_added_to_hass(self) -> None:
        """Initialize energy state from the coordinator's first refresh."""
        await super().async_added_to_hass()
        self._update_from_coordinator()

    def _handle_coordinator_update(self) -> None:
        """Update energy state from coordinator data."""
        self._update_from_coordinator()
        super()._handle_coordinator_update()

    def _update_from_coordinator(self) -> None:
        """Update daily energy from data collected by the coordinator."""
        # Wait until the API has had time to publish the current hour's reading.
        now_utc = dt.now(datetime.UTC)
        current_period = now_utc.replace(minute=0, second=0, microsecond=0)
        midnight_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

        if self._attr_last_reset != midnight_utc:
            self._attr_native_value = 0.0
            self._attr_last_reset = midnight_utc

        if now_utc.minute < 5:
            return  # Too early; wait for API to update

        coordinator_data = self.coordinator.data
        if coordinator_data is None:
            return
        device_data = coordinator_data.get(self._device_id, {})
        device_hourly_stats = device_data.get("hourly_stats")
        energy_updated_at = device_data.get("energy_updated_at")
        _LOGGER.debug("Hourly stats for %s: %s", self._device_name, device_hourly_stats)
        if (
            not isinstance(energy_updated_at, datetime.datetime)
            or energy_updated_at < current_period
            or energy_updated_at == self._last_energy_update
        ):
            return

        today_entries = []
        for entry in device_hourly_stats or []:
            parsed_time = self._parse_iso_timestamp(entry.get("date"))
            if parsed_time is not None and parsed_time >= midnight_utc:
                today_entries.append(entry)

        total_wh = sum(entry["period"] for entry in today_entries)
        self._attr_native_value = round(total_wh / 1000, 3)
        self._attr_last_reset = midnight_utc
        self._last_energy_update = energy_updated_at
        _LOGGER.debug(
            "Updated cumulative daily energy for %s: %s kWh (%d entries since midnight)",
            self._device_name,
            self._attr_native_value,
            len(today_entries),
        )
