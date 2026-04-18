"""Fixtures for Generic Conversation tests."""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.const import CONF_API_KEY, CONF_LLM_HASS_API
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.setup import async_setup_component

from custom_components.generic_conversation.const import (
    CONF_BASE_URL,
    CONF_CHAT_MODEL,
    CONF_MAX_TOKENS,
    CONF_RECOMMENDED,
    CONF_TEMPERATURE,
    CONF_TOP_P,
    DEFAULT_CHAT_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DOMAIN,
    RECOMMENDED_AI_TASK_OPTIONS,
    RECOMMENDED_CONVERSATION_OPTIONS,
)


@pytest.fixture
def mock_config_entry(hass: HomeAssistant) -> ConfigEntry:
    """Create a mock config entry."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Generic Conversation",
        data={
            CONF_API_KEY: "test-api-key",
            CONF_BASE_URL: "http://localhost:11434/v1",
        },
        source="user",
        unique_id=None,
    )
    entry.add_to_hass(hass)

    conversation_subentry = ConfigSubentry(
        data=RECOMMENDED_CONVERSATION_OPTIONS,
        subentry_type="conversation",
        title="Generic Conversation",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(entry, conversation_subentry)

    ai_task_subentry = ConfigSubentry(
        data=RECOMMENDED_AI_TASK_OPTIONS,
        subentry_type="ai_task_data",
        title="Generic AI Task",
        unique_id=None,
    )
    hass.config_entries.async_add_subentry(entry, ai_task_subentry)

    return entry


@pytest.fixture
def mock_openai_client() -> AsyncMock:
    """Create a mock AsyncOpenAI client."""
    client = AsyncMock()
    client.models.list = AsyncMock(return_value=MagicMock(data=[]))
    client.chat.completions.create = AsyncMock()
    return client


@pytest.fixture
def mock_setup_entry() -> AsyncGenerator[AsyncMock]:
    """Override async_setup_entry."""
    with patch(
        f"custom_components.{DOMAIN}.async_setup_entry",
        return_value=True,
    ) as mock:
        yield mock
