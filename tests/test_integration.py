"""Tests for integration setup and unload handling."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sinope_schluter import (
    SchluterApiClient,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.sinope_schluter.api import (
    SchluterApiError,
    SchluterError,
    SchluterInvalidAuth,
)
from custom_components.sinope_schluter.const import DOMAIN

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        data={"username": "user@example.com", "password": "secret"},
    )


@pytest.mark.parametrize(
    ("error", "expected_error"),
    [
        (SchluterInvalidAuth("AUTH", "invalid"), ConfigEntryAuthFailed),
        (SchluterError("offline"), ConfigEntryNotReady),
    ],
)
async def test_setup_translates_connection_errors(hass, error, expected_error):
    entry = _entry()
    entry.add_to_hass(hass)
    with patch.object(
        SchluterApiClient, "async_connect", new=AsyncMock(side_effect=error)
    ), pytest.raises(expected_error):
        await async_setup_entry(hass, entry)


async def test_setup_delays_retry_after_session_limit(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    sleep = AsyncMock()
    error = SchluterApiError("ACCSESSEXC", "too many sessions")

    with (
        patch.object(
            SchluterApiClient, "async_connect", new=AsyncMock(side_effect=error)
        ),
        patch("custom_components.sinope_schluter.asyncio.sleep", new=sleep),
        pytest.raises(ConfigEntryNotReady),
    ):
        await async_setup_entry(hass, entry)

    sleep.assert_awaited_once_with(300)


async def test_successful_setup_can_unload(hass):
    entry = _entry()
    entry.add_to_hass(hass)
    await async_setup(hass, {})

    with patch.object(SchluterApiClient, "async_connect", new=AsyncMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)

    assert await async_unload_entry(hass, entry)
