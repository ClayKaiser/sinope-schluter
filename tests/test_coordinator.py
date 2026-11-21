"""Tests for Schluter coordinator device inventory updates."""

import time
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sinope_schluter.api import (
    SchluterDeviceError,
    SchluterError,
    SchluterInvalidAuth,
    SchluterRequestError,
    SchluterSessionExpired,
)
from custom_components.sinope_schluter.const import DOMAIN
from custom_components.sinope_schluter.coordinator import (
    DEVICE_DISCOVERY_INTERVAL,
    SchluterCoordinator,
)


async def test_device_refresh_adds_new_and_removes_stale_devices(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "stale")},
        name="Removed thermostat",
    )
    current_device = {
        "id": "current",
        "name": "Thermostat",
        "sku": "740",
        "signature": {"model": 740},
    }

    async def refresh_devices():
        client.gateway_data = [current_device]

    client = AsyncMock()
    client.gateway_data = []
    client.async_refresh_devices.side_effect = refresh_devices
    client.async_get_device_attributes.return_value = {}
    client.async_get_device_hourly_stats.return_value = None

    coordinator = SchluterCoordinator(hass, entry, client)
    coordinator._devices_updated_at = (
        time.monotonic() - DEVICE_DISCOVERY_INTERVAL.total_seconds()
    )

    data = await coordinator._async_fetch_data_once()

    assert set(data) == {"current"}
    assert (
        registry.async_get_device_by_identifier((DOMAIN, "stale"), entry.entry_id)
        is None
    )


async def test_inactive_device_keeps_cached_data_without_polling(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.gateway_data = [
        {
            "id": "current",
            "name": "Thermostat",
            "sku": "740",
            "signature": {"model": 740},
        }
    ]
    client.async_get_device_attributes.return_value = {}
    client.async_get_device_hourly_stats.return_value = None
    coordinator = SchluterCoordinator(hass, entry, client)
    await coordinator.async_refresh()
    assert client.async_get_device_attributes.await_count == 1

    coordinator.set_device_active("current", False)
    await hass.async_block_till_done()

    assert client.async_get_device_attributes.await_count == 1
    assert "current" in coordinator.data

    with patch.object(hass, "add_job") as add_job:
        coordinator.set_device_active("current", True)

    assert "current" not in coordinator._inactive_devices
    add_job.assert_called_once_with(coordinator.async_request_refresh)
    await coordinator.async_shutdown()


@pytest.mark.parametrize(
    ("error", "expected_error"),
    [
        (SchluterInvalidAuth("AUTH", "invalid"), ConfigEntryAuthFailed),
        (SchluterRequestError("offline"), UpdateFailed),
        (SchluterError("failed"), UpdateFailed),
    ],
)
async def test_update_data_translates_api_errors(hass, error, expected_error):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    coordinator = SchluterCoordinator(hass, entry, AsyncMock())
    coordinator._async_fetch_data = AsyncMock(side_effect=error)

    with pytest.raises(expected_error):
        await coordinator._async_update_data()


async def test_fetch_data_reconnects_once_after_session_expiry(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    client = AsyncMock()
    coordinator = SchluterCoordinator(hass, entry, client)
    coordinator._async_fetch_data_once = AsyncMock(
        side_effect=[
            SchluterSessionExpired("SESSION_EXPIRED", "expired"),
            {"current": {}},
        ]
    )

    assert await coordinator._async_fetch_data() == {"current": {}}
    client.async_reconnect.assert_awaited_once()
    assert coordinator._device_inventory_needs_reconcile


async def test_fetch_data_fails_after_second_session_expiry(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    client = AsyncMock()
    coordinator = SchluterCoordinator(hass, entry, client)
    coordinator._async_fetch_data_once = AsyncMock(
        side_effect=SchluterSessionExpired("SESSION_EXPIRED", "expired")
    )

    with pytest.raises(SchluterError, match="after reconnecting"):
        await coordinator._async_fetch_data()

    client.async_reconnect.assert_awaited_once()


async def test_device_errors_and_invalid_energy_preserve_thermostat_data(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    unavailable = {
        "id": "unavailable",
        "name": "Unavailable",
        "sku": "740",
        "signature": {"model": 740},
    }
    current = {
        "id": "current",
        "name": "Current",
        "sku": "740",
        "signature": {"model": 740},
    }
    client = AsyncMock()
    client.gateway_data = [unavailable, current]
    client.async_get_device_attributes.side_effect = [
        SchluterDeviceError("DVCUNVLB", "unavailable"),
        {},
    ]
    client.async_get_device_hourly_stats.return_value = [None]
    coordinator = SchluterCoordinator(hass, entry, client)

    data = await coordinator._async_fetch_data_once()

    assert set(data) == {"current"}
    assert data["current"] == {"attributes": {}}
    assert coordinator._unavailable_devices == {"unavailable"}
    assert coordinator._energy_updated_at == {}


async def test_device_becoming_available_is_recovered(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    device = {
        "id": "current",
        "name": "Thermostat",
        "sku": "740",
        "signature": {"model": 740},
    }
    client = AsyncMock()
    client.gateway_data = [device]
    client.async_get_device_attributes.return_value = {}
    coordinator = SchluterCoordinator(hass, entry, client)
    coordinator._unavailable_devices.add("current")

    assert "current" in await coordinator._async_fetch_data_once()
    assert coordinator._unavailable_devices == set()


async def test_all_request_failures_raise_cannot_connect(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.gateway_data = [
        {
            "id": "current",
            "name": "Thermostat",
            "sku": "740",
            "signature": {"model": 740},
        }
    ]
    client.async_get_device_attributes.side_effect = SchluterRequestError("offline")
    coordinator = SchluterCoordinator(hass, entry, client)

    with pytest.raises(UpdateFailed) as err:
        await coordinator._async_fetch_data_once()

    assert err.value.translation_key == "cannot_connect"


async def test_mixed_device_failures_raise_generic_update_error(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.gateway_data = [
        {"id": "request", "name": "Request failure", "sku": "740"},
        {"id": "device", "name": "Device failure", "sku": "740"},
    ]
    client.async_get_device_attributes.side_effect = [
        SchluterRequestError("offline"),
        SchluterDeviceError("DVCUNVLB", "unavailable"),
    ]
    coordinator = SchluterCoordinator(hass, entry, client)

    with pytest.raises(UpdateFailed, match="Unable to refresh any"):
        await coordinator._async_fetch_data_once()
