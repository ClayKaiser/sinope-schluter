"""Shared entity helpers for Schluter devices."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import DeviceInfo as SchluterDeviceInfo
from .const import DOMAIN
from .coordinator import SchluterCoordinator


class SchluterEntity(CoordinatorEntity[SchluterCoordinator]):
    """Base entity for a Schluter thermostat."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SchluterCoordinator,
        device_info: SchluterDeviceInfo,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._device_id = str(device_info["id"])
        self._device_name = device_info["name"]
        self._sku = device_info["sku"]

    @property
    def available(self) -> bool:
        """Return whether the cloud and this thermostat are available."""
        return (
            super().available
            and self.coordinator.data is not None
            and self._device_id in self.coordinator.data
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group related entities."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=self._device_name,
            manufacturer="Schluter",
            model=self._sku,
        )
