"""Tests for the Schluter config flow."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sinope_schluter.api import (
    SchluterInvalidAuth,
    SchluterRequestError,
)
from custom_components.sinope_schluter.const import DOMAIN

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

USER_INPUT = {"username": "user@example.com", "password": "secret"}


async def test_user_flow_creates_entry(hass):
    with patch(
        "custom_components.sinope_schluter.config_flow.SchluterApiClient.async_connect",
        new_callable=AsyncMock,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == DOMAIN
    assert result["data"] == USER_INPUT


@pytest.mark.parametrize(
    ("error", "expected_error"),
    [
        (SchluterInvalidAuth("AUTH", "invalid"), "invalid_auth"),
        (SchluterRequestError("offline"), "cannot_connect"),
    ],
)
async def test_user_flow_recovers_from_connection_errors(
    hass, error, expected_error
):
    with patch(
        "custom_components.sinope_schluter.config_flow.SchluterApiClient.async_connect",
        new_callable=AsyncMock,
    ) as mock_connect:
        mock_connect.side_effect = error
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": expected_error}

        mock_connect.side_effect = None
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == DOMAIN


async def test_user_flow_rejects_duplicate_entry(hass):
    MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow_updates_credentials(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={"username": "old@example.com", "password": "old"},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.sinope_schluter.config_flow.SchluterApiClient.async_connect",
        new_callable=AsyncMock,
    ) as mock_connect:
        result = await entry.start_reauth_flow(hass)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"

        mock_connect.side_effect = SchluterInvalidAuth("AUTH", "invalid")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}

        mock_connect.side_effect = None
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data == USER_INPUT


async def test_reauth_flow_aborts_if_entry_is_missing(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": "missing"},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_failed"
