"""Test the Generic Conversation conversation entity."""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.components import conversation
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent

from custom_components.generic_conversation.const import DOMAIN


def _make_chunk(
    content: str | None = None,
    role: str | None = None,
    finish_reason: str | None = None,
    tool_calls: list | None = None,
) -> MagicMock:
    """Create a mock ChatCompletionChunk."""
    chunk = MagicMock()
    choice = MagicMock()
    delta = MagicMock()
    delta.role = role
    delta.content = content
    delta.tool_calls = tool_calls
    choice.delta = delta
    choice.finish_reason = finish_reason
    chunk.choices = [choice]
    chunk.usage = None
    return chunk


async def _mock_stream(
    chunks: list[MagicMock],
) -> AsyncGenerator[MagicMock]:
    """Create a mock async stream from chunks."""
    for chunk in chunks:
        yield chunk


async def test_simple_text_response(
    hass: HomeAssistant,
    mock_config_entry,
    mock_openai_client: AsyncMock,
) -> None:
    """Test a simple text response without tools."""
    chunks = [
        _make_chunk(role="assistant"),
        _make_chunk(content="Hello! "),
        _make_chunk(content="How can I help?"),
        _make_chunk(finish_reason="stop"),
    ]

    mock_openai_client.chat.completions.create = AsyncMock(
        return_value=_mock_stream(chunks)
    )

    with patch(
        f"custom_components.{DOMAIN}.openai.AsyncOpenAI",
        return_value=mock_openai_client,
    ):
        mock_config_entry.runtime_data = mock_openai_client
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    result = await conversation.async_converse(
        hass,
        "Hello",
        None,
        None,
    )

    assert result.response.response_type == intent.IntentResponseType.ACTION_DONE
    assert "Hello! How can I help?" in result.response.speech["plain"]["speech"]
