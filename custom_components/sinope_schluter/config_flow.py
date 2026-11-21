"""Config flow for Schluter."""

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import SchluterApiClient
from .api import SchluterError, SchluterInvalidAuth
from .const import DOMAIN, NAME

CONFIG_SCHEMA: Any = vol.Schema(
    {
        vol.Required(CONF_USERNAME): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
        ),
        vol.Required(CONF_PASSWORD): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    }
)


class SchluterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle Schluter config flow."""

    VERSION = 1
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set up Schluter from the UI."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            errors = await self._async_validate_input(user_input)
            if errors:
                return self.async_show_form(
                    step_id="user", data_schema=CONFIG_SCHEMA, errors=errors
                )
            return self.async_create_entry(title=NAME, data=user_input)

        return self.async_show_form(step_id="user", data_schema=CONFIG_SCHEMA)

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start reauthentication for an existing config entry."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update the stored account credentials."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="reauth_failed")

        if user_input is not None:
            errors = await self._async_validate_input(user_input)
            if errors:
                return self.async_show_form(
                    step_id="reauth_confirm",
                    data_schema=CONFIG_SCHEMA,
                    errors=errors,
                )
            return self.async_update_reload_and_abort(
                entry,
                data_updates=user_input,
            )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=CONFIG_SCHEMA,
        )

    async def _async_validate_input(
        self, user_input: dict[str, Any]
    ) -> dict[str, str]:
        """Validate account credentials and supported devices."""
        client = SchluterApiClient(
            self.hass,
            async_get_clientsession(self.hass),
            str(user_input[CONF_USERNAME]),
            str(user_input[CONF_PASSWORD]),
        )
        try:
            await client.async_connect()
        except SchluterInvalidAuth:
            return {"base": "invalid_auth"}
        except SchluterError:
            return {"base": "cannot_connect"}
        return {}
