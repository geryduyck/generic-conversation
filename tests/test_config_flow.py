"""Test the Generic Conversation config flow."""

from unittest.mock import AsyncMock, patch

import openai
import pytest

from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.generic_conversation.const import (
    CONF_BASE_URL,
    DOMAIN,
)


async def test_full_flow(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test the full config flow with API key and base URL."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(
        "custom_components.generic_conversation.config_flow.openai.AsyncOpenAI"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.list = AsyncMock(return_value=AsyncMock(data=[]))

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_KEY: "test-key",
                CONF_BASE_URL: "http://localhost:11434/v1",
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Generic Conversation"
    assert result["data"] == {
        CONF_API_KEY: "test-key",
        CONF_BASE_URL: "http://localhost:11434/v1",
    }
    assert len(result["subentries"]) == 2


async def test_flow_no_api_key(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test config flow with no API key (local server)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "custom_components.generic_conversation.config_flow.openai.AsyncOpenAI"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        # Simulate endpoint not supporting GET /models
        mock_client.models.list = AsyncMock(
            side_effect=openai.OpenAIError("Not supported")
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_BASE_URL: "http://localhost:8080/v1"},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_flow_invalid_auth(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test config flow with invalid API key."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "custom_components.generic_conversation.config_flow.openai.AsyncOpenAI"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.list = AsyncMock(
            side_effect=openai.AuthenticationError(
                message="Invalid API key",
                response=AsyncMock(status_code=401),
                body=None,
            )
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_KEY: "bad-key",
                CONF_BASE_URL: "https://api.example.com/v1",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_flow_cannot_connect(
    hass: HomeAssistant,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test config flow with connection error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    with patch(
        "custom_components.generic_conversation.config_flow.openai.AsyncOpenAI"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.list = AsyncMock(
            side_effect=openai.APIConnectionError(request=AsyncMock())
        )

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_API_KEY: "test-key",
                CONF_BASE_URL: "http://unreachable:1234/v1",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_reauth_flow(
    hass: HomeAssistant,
    mock_config_entry,
    mock_setup_entry: AsyncMock,
) -> None:
    """Test the reauth flow."""
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.generic_conversation.config_flow.openai.AsyncOpenAI"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.models.list = AsyncMock(return_value=AsyncMock(data=[]))

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_API_KEY: "new-key"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
