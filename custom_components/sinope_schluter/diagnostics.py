"""Diagnostics support for Schluter."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import SchluterConfigEntry

TO_REDACT = {CONF_PASSWORD, CONF_USERNAME}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SchluterConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data
    return {
        "entry_data": async_redact_data(entry.data, TO_REDACT),
        "coordinator_data": data.coordinator.data,
        "devices": [
            {
                "id": device["id"],
                "name": device["name"],
                "sku": device["sku"],
                "signature": device["signature"],
            }
            for device in data.api_client.gateway_data
        ],
    }
