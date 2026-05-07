"""Config flow for Generic Conversation integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import CONF_NAME, DOMAIN


class GenericConversationConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle import-only config flow for Generic Conversation."""

    VERSION = 1

    async def async_step_import(
        self, import_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle import from YAML configuration."""
        await self.async_set_unique_id(import_data["unique_id"])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=import_data[CONF_NAME],
            data=import_data,
        )
