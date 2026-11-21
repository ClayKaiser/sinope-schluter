"""Tests for Schluter diagnostics redaction."""

from types import SimpleNamespace

from custom_components.sinope_schluter.diagnostics import (
    async_get_config_entry_diagnostics,
)


async def test_diagnostics_redact_account_credentials(hass):
    username = "private@example.com"
    password = "private-password"
    entry = SimpleNamespace(
        data={"username": username, "password": password},
        runtime_data=SimpleNamespace(
            coordinator=SimpleNamespace(data={"device-1": {"attributes": {}}}),
            api_client=SimpleNamespace(
                gateway_data=[
                    {
                        "id": "device-1",
                        "name": "Thermostat",
                        "sku": "740",
                        "signature": {"model": 740},
                    }
                ]
            ),
        ),
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry_data"]["username"] != username
    assert diagnostics["entry_data"]["password"] != password
    assert diagnostics["coordinator_data"] == {"device-1": {"attributes": {}}}
    assert diagnostics["devices"][0]["id"] == "device-1"
