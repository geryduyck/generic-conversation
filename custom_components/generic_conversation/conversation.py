"""Conversation support for Generic Conversation."""

from __future__ import annotations

from typing import Any, Literal

from homeassistant.components import conversation
from homeassistant.const import CONF_LLM_HASS_API, MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GenericConversationConfigEntry
from .const import CONF_AGENTS, CONF_SYSTEM_PROMPT, CONF_TYPE, DOMAIN
from .entity import GenericBaseLLMEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: GenericConversationConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up conversation entities."""
    entities = [
        GenericConversationEntity(config_entry, agent_config)
        for agent_config in config_entry.data[CONF_AGENTS]
        if agent_config[CONF_TYPE] == "conversation"
    ]
    if entities:
        async_add_entities(entities)


class GenericConversationEntity(
    conversation.ConversationEntity,
    conversation.AbstractConversationAgent,
    GenericBaseLLMEntity,
):
    """Generic conversation agent."""

    _attr_supports_streaming = True

    def __init__(
        self,
        entry: GenericConversationConfigEntry,
        agent_config: dict[str, Any],
    ) -> None:
        """Initialize the agent."""
        super().__init__(entry, agent_config)
        if self._config.get(CONF_LLM_HASS_API):
            self._attr_supported_features = (
                conversation.ConversationEntityFeature.CONTROL
            )

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return a list of supported languages."""
        return MATCH_ALL

    async def async_added_to_hass(self) -> None:
        """When entity is added to Home Assistant."""
        await super().async_added_to_hass()
        conversation.async_set_agent(self.hass, self.entry, self)

    async def async_will_remove_from_hass(self) -> None:
        """When entity will be removed from Home Assistant."""
        conversation.async_unset_agent(self.hass, self.entry)
        await super().async_will_remove_from_hass()

    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
    ) -> conversation.ConversationResult:
        """Process the user input and call the API."""
        try:
            await chat_log.async_provide_llm_data(
                user_input.as_llm_context(DOMAIN),
                self._config.get(CONF_LLM_HASS_API),
                self._config.get(CONF_SYSTEM_PROMPT, llm.DEFAULT_INSTRUCTIONS_PROMPT),
                user_input.extra_system_prompt,
            )
        except conversation.ConverseError as err:
            return err.as_conversation_result()

        await self._async_handle_chat_log(chat_log)

        return conversation.async_get_result_from_chat_log(user_input, chat_log)
