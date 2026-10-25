"""Sensor entities for the Schluter DITRA-HEAT-E-RS1 integration."""

import datetime
import logging
from datetime import datetime as dt

from .coordinator import SchluterCoordinator
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)

from homeassistant.const import UnitOfEnergy

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import (
    DOMAIN,
    SUPPORTED_DEVICE_MODELS,
)

_LOGGER = logging.getLogger(__name__)

IMPLEMENTED_THERMOSTAT_MODEL = SUPPORTED_DEVICE_MODELS

async def async_setup_entry(
    hass,
    entry,
    async_add_entities,
) -> None:
    """Set up the Schluter energy sensor."""
    data = hass.data[DOMAIN]["data"]

    entities = []
    for device_info in data.api_client.gateway_data:
        if "signature" in device_info and \
            "model" in device_info["signature"] and \
            device_info["signature"]["model"] in IMPLEMENTED_THERMOSTAT_MODEL:
            device_name = device_info["name"]
            device_sku = device_info["sku"]
            entities.append(
                SchluterEnergySensor(
                    data.coordinator, device_info, device_name, device_sku
                )
            )

    async_add_entities(entities)

class SchluterEnergySensor(CoordinatorEntity, SensorEntity):
    """Sensor for daily energy consumption from a thermostat."""

    _attr_has_entity_name = True
    _attr_name = "Daily Energy"

    def __init__(
        self,
        coordinator: SchluterCoordinator,
        device_info,
        name,
        sku,
    ):
        """Initialize the daily energy sensor."""
        super().__init__(coordinator)
        self._device_id = str(device_info["id"])
        self._device_name = name
        self._sku = sku
        self._attr_native_value = 0.0  # Initialize with 0 to keep entity available
        # Initialize last_reset to midnight UTC
        now_utc = dt.now(datetime.timezone.utc)
        self._attr_last_reset = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        self._attr_unique_id = f"{self._device_id}_daily_energy"
        self._last_energy_update = None
        _LOGGER.debug("Setting up daily energy sensor for %s: %s", self._attr_name, device_info)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group with thermostat entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=self._device_name,
            manufacturer="Schluter",
            model=self._sku,
        )

    @property
    def native_value(self):
        """Return the cumulative daily energy consumption in kWh."""
        return self._attr_native_value

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement."""
        return UnitOfEnergy.KILO_WATT_HOUR

    @property
    def device_class(self):
        """Return the device class."""
        return SensorDeviceClass.ENERGY

    @property
    def state_class(self):
        """Return the state class indicating this is a total aggregated value."""
        return SensorStateClass.TOTAL

    @property
    def last_reset(self):
        """Return midnight UTC for the current daily total."""
        return self._attr_last_reset

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:flash"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {
            'sku': self._sku,
            'id': self._device_id,
        }

    def _parse_iso_timestamp(self, iso_str):
        """Parse ISO 8601 timestamp string to datetime object."""
        if not isinstance(iso_str, str):
            _LOGGER.error("Invalid energy timestamp: %s", iso_str)
            return None

        try:
            if iso_str.endswith('Z'):
                iso_str = iso_str[:-1] + '+00:00'
            parsed = dt.fromisoformat(iso_str)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=datetime.timezone.utc)
            return parsed.astimezone(datetime.timezone.utc)
        except ValueError as err:
            _LOGGER.error("Failed to parse timestamp %s: %s", iso_str, err)
            return None

    async def async_added_to_hass(self):
        """Initialize energy state from the coordinator's first refresh."""
        await super().async_added_to_hass()
        self._update_from_coordinator()

    def _handle_coordinator_update(self):
        """Update energy state from coordinator data."""
        self._update_from_coordinator()
        super()._handle_coordinator_update()

    def _update_from_coordinator(self):
        """Update daily energy from data collected by the coordinator."""
        # Wait until the API has had time to publish the current hour's reading.
        now_utc = dt.now(datetime.timezone.utc)
        current_period = now_utc.replace(minute=0, second=0, microsecond=0)
        midnight_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

        if self._attr_last_reset != midnight_utc:
            self._attr_native_value = 0.0
            self._attr_last_reset = midnight_utc

        if now_utc.minute < 5:
            return  # Too early; wait for API to update

        device_data = self.coordinator.data.get(self._device_id, {})
        device_hourly_stats = device_data.get("hourly_stats")
        energy_updated_at = device_data.get("energy_updated_at")
        _LOGGER.debug("Hourly stats for %s: %s", self._attr_name, device_hourly_stats)
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
            self._attr_name,
            self._attr_native_value,
            len(today_entries),
        )
