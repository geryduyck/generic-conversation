"""The Generic Conversation integration."""

from __future__ import annotations

from typing import Any

import openai
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.const import CONF_API_KEY, CONF_LLM_HASS_API, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.reload import async_integration_yaml_config
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify

from .const import (
    CONF_AGENTS,
    CONF_BASE_URL,
    CONF_CHAT_MODEL,
    CONF_MAX_TOKENS,
    CONF_NAME,
    CONF_SERVICES,
    CONF_SYSTEM_PROMPT,
    CONF_TEMPERATURE,
    CONF_TOP_P,
    CONF_TYPE,
    DEFAULT_MAX_TOKENS,
    DOMAIN,
    LOGGER,
)

PLATFORMS = (Platform.AI_TASK, Platform.CONVERSATION)

type GenericConversationConfigEntry = ConfigEntry[openai.AsyncOpenAI]


def _unique_names(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate that all names (and their slugified forms) are unique."""
    names = [v[CONF_NAME] for v in values]
    if len(names) != len(set(names)):
        raise vol.Invalid("Names must be unique")
    slugs = [slugify(n) for n in names]
    if len(slugs) != len(set(slugs)):
        raise vol.Invalid("Names must be unique after normalization")
    return values


AGENT_CONVERSATION_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TYPE): "conversation",
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_CHAT_MODEL): cv.string,
        vol.Optional(CONF_MAX_TOKENS, default=DEFAULT_MAX_TOKENS): vol.All(
            vol.Coerce(int), vol.Range(min=1)
        ),
        vol.Optional(CONF_TEMPERATURE): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=2)
        ),
        vol.Optional(CONF_TOP_P): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=1)
        ),
        vol.Optional(CONF_SYSTEM_PROMPT): cv.string,
        vol.Optional(CONF_LLM_HASS_API, default=["assist"]): vol.All(
            cv.ensure_list, [cv.string]
        ),
    }
)

AGENT_AI_TASK_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TYPE): "ai_task",
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_CHAT_MODEL): cv.string,
        vol.Optional(CONF_MAX_TOKENS, default=DEFAULT_MAX_TOKENS): vol.All(
            vol.Coerce(int), vol.Range(min=1)
        ),
        vol.Optional(CONF_TEMPERATURE): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=2)
        ),
        vol.Optional(CONF_TOP_P): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=1)
        ),
    }
)


def _validate_agent(agent: dict[str, Any]) -> dict[str, Any]:
    """Validate an agent config based on its type."""
    agent_type = agent.get(CONF_TYPE)
    if agent_type == "conversation":
        return AGENT_CONVERSATION_SCHEMA(agent)
    if agent_type == "ai_task":
        return AGENT_AI_TASK_SCHEMA(agent)
    raise vol.Invalid(f"Invalid agent type: {agent_type}")


SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_BASE_URL): cv.url,
        vol.Optional(CONF_API_KEY): cv.string,
        vol.Required(CONF_AGENTS): vol.All(
            [_validate_agent], vol.Length(min=1), _unique_names
        ),
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_SERVICES): vol.All(
                    [SERVICE_SCHEMA], vol.Length(min=1), _unique_names
                ),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def _reconcile_entries(
    hass: HomeAssistant, yaml_services: dict[str, dict[str, Any]]
) -> None:
    """Reconcile config entries with YAML service definitions (awaited, for reload)."""
    existing_entries = {
        entry.unique_id: entry for entry in hass.config_entries.async_entries(DOMAIN)
    }

    for unique_id, service_conf in yaml_services.items():
        import_data = _build_import_data(unique_id, service_conf)

        if unique_id in existing_entries:
            entry = existing_entries[unique_id]
            if entry.data != import_data:
                hass.config_entries.async_update_entry(entry, data=import_data)
                await hass.config_entries.async_reload(entry.entry_id)
        else:
            await hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data=import_data,
            )

    for unique_id, entry in existing_entries.items():
        if unique_id not in yaml_services:
            await hass.config_entries.async_remove(entry.entry_id)


def _build_import_data(unique_id: str, service_conf: dict[str, Any]) -> dict[str, Any]:
    """Build the import data dict for a service config entry."""
    import_data = {
        "unique_id": unique_id,
        CONF_NAME: service_conf[CONF_NAME],
        CONF_BASE_URL: service_conf[CONF_BASE_URL],
        CONF_AGENTS: service_conf[CONF_AGENTS],
    }
    if CONF_API_KEY in service_conf:
        import_data[CONF_API_KEY] = service_conf[CONF_API_KEY]
    return import_data


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Generic Conversation from YAML configuration."""
    if DOMAIN not in config:
        return True

    conf = config[DOMAIN]
    yaml_services = {slugify(s[CONF_NAME]): s for s in conf[CONF_SERVICES]}

    existing_entries = {
        entry.unique_id: entry for entry in hass.config_entries.async_entries(DOMAIN)
    }

    for unique_id, service_conf in yaml_services.items():
        import_data = _build_import_data(unique_id, service_conf)

        if unique_id in existing_entries:
            entry = existing_entries[unique_id]
            if entry.data != import_data:
                hass.config_entries.async_update_entry(entry, data=import_data)
                hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))
        else:
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": SOURCE_IMPORT},
                    data=import_data,
                )
            )

    for unique_id, entry in existing_entries.items():
        if unique_id not in yaml_services:
            hass.async_create_task(hass.config_entries.async_remove(entry.entry_id))

    async def handle_reload(_call: ServiceCall) -> None:
        """Handle reload service call."""
        await _async_reload(hass)

    async_register_admin_service(hass, DOMAIN, "reload", handle_reload)

    return True


async def _async_reload(hass: HomeAssistant) -> None:
    """Reload YAML configuration and reconcile config entries."""
    conf = await async_integration_yaml_config(hass, DOMAIN)
    if conf is None:
        LOGGER.error("Failed to reload YAML configuration")
        return

    if DOMAIN not in conf:
        for entry in hass.config_entries.async_entries(DOMAIN):
            await hass.config_entries.async_remove(entry.entry_id)
        return

    yaml_services = {slugify(s[CONF_NAME]): s for s in conf[DOMAIN][CONF_SERVICES]}
    await _reconcile_entries(hass, yaml_services)


async def async_setup_entry(
    hass: HomeAssistant, entry: GenericConversationConfigEntry
) -> bool:
    """Set up Generic Conversation from a config entry."""
    client = openai.AsyncOpenAI(
        api_key=entry.data.get(CONF_API_KEY) or None,
        base_url=entry.data[CONF_BASE_URL],
        http_client=get_async_client(hass),
    )

    try:
        await client.models.list(timeout=10.0)
    except openai.AuthenticationError as err:
        LOGGER.error(
            "Authentication failed for %s — check api_key in YAML: %s",
            entry.data[CONF_NAME],
            err,
        )
    except openai.OpenAIError as err:
        LOGGER.debug("Could not validate endpoint: %s", err)

    entry.runtime_data = client

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: GenericConversationConfigEntry
) -> bool:
    """Unload Generic Conversation."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
