"""Config flow for Schluter."""

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers import selector

from .const import DOMAIN, NAME

CONFIG_SCHEMA = vol.Schema(
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
    _reauth_entry: ConfigEntry | None = None

    async def async_step_user(self, user_input=None):
        """Set up Schluter from the UI."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(title=NAME, data=user_input)

        return self.async_show_form(step_id="user", data_schema=CONFIG_SCHEMA)

    async def async_step_reauth(self, user_input=None):
        """Start reauthentication for an existing config entry."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        if self._reauth_entry is None:
            return self.async_abort(reason="reauth_failed")
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Update the stored account credentials."""
        if self._reauth_entry is None:
            return self.async_abort(reason="reauth_failed")

        if user_input is not None:
            return self.async_update_reload_and_abort(
                self._reauth_entry,
                data_updates=user_input,
            )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=CONFIG_SCHEMA,
        )
