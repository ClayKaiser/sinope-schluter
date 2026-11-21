"""Actions for the Schluter integration."""

from collections.abc import Mapping
from functools import partial
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import service, target

from . import SchluterApiClient, SchluterConfigEntry
from .api import SchluterError
from .const import (
    ATTR_ACTIVE,
    ATTR_BACKLIGHT,
    ATTR_DISPLAY_2,
    ATTR_EARLY_START,
    ATTR_FLOOR_MODE,
    ATTR_KEYPAD,
    ATTR_ROOM_SETPOINT_MAX,
    ATTR_ROOM_SETPOINT_MIN,
    ATTR_STATUS,
    ATTR_TEMP,
    ATTR_TIME,
    ATTR_VALUE,
    DOMAIN,
    SERVICE_SET_ACTIVATION,
    SERVICE_SET_AIR_FLOOR_MODE,
    SERVICE_SET_AUX_CYCLE_LENGTH,
    SERVICE_SET_BACKLIGHT,
    SERVICE_SET_CLIMATE_KEYPAD_LOCK,
    SERVICE_SET_CYCLE_LENGTH,
    SERVICE_SET_EARLY_START,
    SERVICE_SET_ECO_STATUS,
    SERVICE_SET_EM_HEAT,
    SERVICE_SET_SECOND_DISPLAY,
    SERVICE_SET_SETPOINT_MAX,
    SERVICE_SET_SETPOINT_MIN,
    SERVICE_SET_TEMPERATURE_FORMAT,
    SERVICE_SET_TIME_FORMAT,
)
from .coordinator import SchluterCoordinator

PERIOD_VALUES = (
    "15 sec",
    "5 min",
    "10 min",
    "15 min",
    "20 min",
    "25 min",
    "30 min",
)

HA_TO_SCHLUTER_PERIOD = {
    "15 sec": "short",
    "5 min": "long5min",
    "10 min": "long10min",
    "15 min": "long15min",
    "20 min": "long20min",
    "25 min": "long25min",
    "30 min": "long30min",
}

SERVICE_SCHEMAS: dict[str, dict[vol.Marker, Any]] = {
    SERVICE_SET_ACTIVATION: {
        vol.Required(ATTR_ACTIVE): vol.In([True, False]),
    },
    SERVICE_SET_SECOND_DISPLAY: {
        vol.Required(ATTR_DISPLAY_2): vol.In(["outsideTemperature", "default"]),
    },
    SERVICE_SET_BACKLIGHT: {
        vol.Required(ATTR_BACKLIGHT): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=100)
        ),
    },
    SERVICE_SET_CLIMATE_KEYPAD_LOCK: {
        vol.Required(ATTR_KEYPAD): vol.In(["locked", "unlocked"]),
    },
    SERVICE_SET_EARLY_START: {
        vol.Required(ATTR_EARLY_START): vol.In(["on", "off"]),
    },
    SERVICE_SET_TIME_FORMAT: {
        vol.Required(ATTR_TIME): vol.In([12, 24]),
    },
    SERVICE_SET_TEMPERATURE_FORMAT: {
        vol.Required(ATTR_TEMP): vol.In(["celsius", "fahrenheit"]),
    },
    SERVICE_SET_SETPOINT_MAX: {
        vol.Required(ATTR_ROOM_SETPOINT_MAX): vol.All(
            vol.Coerce(float), vol.Range(min=10, max=30)
        ),
    },
    SERVICE_SET_SETPOINT_MIN: {
        vol.Required(ATTR_ROOM_SETPOINT_MIN): vol.All(
            vol.Coerce(float), vol.Range(min=5, max=24)
        ),
    },
    SERVICE_SET_AIR_FLOOR_MODE: {
        vol.Required(ATTR_FLOOR_MODE): vol.In(["airByFloor", "floor"]),
    },
    SERVICE_SET_CYCLE_LENGTH: {
        vol.Required(ATTR_VALUE): vol.All(cv.ensure_list, [vol.In(PERIOD_VALUES)]),
    },
    SERVICE_SET_AUX_CYCLE_LENGTH: {
        vol.Required(ATTR_VALUE): vol.All(cv.ensure_list, [vol.In(PERIOD_VALUES)]),
    },
    SERVICE_SET_ECO_STATUS: {
        vol.Required(ATTR_STATUS): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=1)
        ),
    },
    SERVICE_SET_EM_HEAT: {
        vol.Required(ATTR_VALUE): vol.In(["on", "off"]),
    },
}


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register actions independently of config-entry setup."""
    for service_name, schema in SERVICE_SCHEMAS.items():
        hass.services.async_register(
            DOMAIN,
            service_name,
            partial(_async_handle_service, hass, service_name),
            schema=cv.make_entity_service_schema(schema),
        )


async def _async_handle_service(
    hass: HomeAssistant, service_name: str, call: ServiceCall
) -> None:
    """Resolve targeted climate entities and execute the requested action."""
    selected = target.async_extract_referenced_entity_ids(
        hass, target.TargetSelection(call.data)
    )
    entity_ids = selected.referenced | selected.indirectly_referenced
    if not entity_ids:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="target_required"
        )

    entity_registry = er.async_get(hass)
    for entity_id in entity_ids:
        entity_entry = entity_registry.async_get(entity_id)
        if (
            entity_entry is None
            or entity_entry.domain != "climate"
            or entity_entry.platform != DOMAIN
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_target"
            )

        config_entry: SchluterConfigEntry = service.async_get_config_entry(
            hass, DOMAIN, entity_entry.config_entry_id
        )
        device_id = entity_entry.unique_id
        if service_name == SERVICE_SET_EARLY_START and any(
            str(device["id"]) == device_id and device["sku"] == "OTH3600-GA-GT"
            for device in config_entry.runtime_data.api_client.gateway_data
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_command"
            )
        await _async_execute_action(
            config_entry.runtime_data.api_client,
            config_entry.runtime_data.coordinator,
            service_name,
            device_id,
            call.data,
        )


async def _async_execute_action(
    client: SchluterApiClient,
    coordinator: SchluterCoordinator,
    service_name: str,
    device_id: str,
    data: Mapping[str, Any],
) -> None:
    """Run a thermostat action."""
    try:
        if service_name == SERVICE_SET_ACTIVATION:
            coordinator.set_device_active(device_id, data[ATTR_ACTIVE])
        elif service_name == SERVICE_SET_SECOND_DISPLAY:
            await client.async_set_second_display(device_id, data[ATTR_DISPLAY_2])
        elif service_name == SERVICE_SET_BACKLIGHT:
            await client.async_set_backlight(device_id, data[ATTR_BACKLIGHT])
        elif service_name == SERVICE_SET_CLIMATE_KEYPAD_LOCK:
            await client.async_set_keypad_lock(device_id, data[ATTR_KEYPAD])
        elif service_name == SERVICE_SET_EARLY_START:
            await client.async_set_early_start(device_id, data[ATTR_EARLY_START])
        elif service_name == SERVICE_SET_TIME_FORMAT:
            time_format = "12h" if data[ATTR_TIME] == 12 else "24h"
            await client.async_set_time_format(device_id, time_format)
        elif service_name == SERVICE_SET_TEMPERATURE_FORMAT:
            await client.async_set_temperature_format(device_id, data[ATTR_TEMP])
        elif service_name == SERVICE_SET_SETPOINT_MAX:
            await client.async_set_setpoint_max(
                device_id, data[ATTR_ROOM_SETPOINT_MAX]
            )
        elif service_name == SERVICE_SET_SETPOINT_MIN:
            await client.async_set_setpoint_min(
                device_id, data[ATTR_ROOM_SETPOINT_MIN]
            )
        elif service_name == SERVICE_SET_AIR_FLOOR_MODE:
            await client.async_set_air_floor_mode(device_id, data[ATTR_FLOOR_MODE])
        elif service_name == SERVICE_SET_CYCLE_LENGTH:
            length = HA_TO_SCHLUTER_PERIOD[data[ATTR_VALUE][0]]
            await client.async_set_cycle_length(device_id, length)
        elif service_name == SERVICE_SET_AUX_CYCLE_LENGTH:
            length = HA_TO_SCHLUTER_PERIOD[data[ATTR_VALUE][0]]
            output = "shortCycle" if length == "short" else "longCycle"
            await client.async_set_aux_cycle_length(device_id, output, length)
        elif service_name == SERVICE_SET_ECO_STATUS:
            await client.async_set_eco_status(device_id, data[ATTR_STATUS])
        elif service_name == SERVICE_SET_EM_HEAT:
            heat = "slave" if data[ATTR_VALUE] == "on" else "off"
            await client.async_set_em_heat(device_id, heat, None, True)
    except SchluterError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="command_failed"
        ) from err
