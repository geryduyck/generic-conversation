"""Test the Generic Conversation AI task entity."""

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.components import ai_task
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from custom_components.generic_conversation.const import DOMAIN


def _make_chunk(
    content: str | None = None,
    role: str | None = None,
    finish_reason: str | None = None,
) -> MagicMock:
    """Create a mock ChatCompletionChunk."""
    chunk = MagicMock()
    choice = MagicMock()
    delta = MagicMock()
    delta.role = role
    delta.content = content
    delta.tool_calls = None
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


async def test_plain_text_generation(
    hass: HomeAssistant,
    mock_config_entry,
    mock_openai_client: AsyncMock,
) -> None:
    """Test plain text generation without structure."""
    chunks = [
        _make_chunk(role="assistant"),
        _make_chunk(content="The summary of the text is: test."),
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

    result = await ai_task.async_generate_data(
        hass,
        task_name="test_summary",
        entity_id="ai_task.generic_ai_task",
        instructions="Summarize this text",
    )

    assert result.data == "The summary of the text is: test."


async def test_structured_json_generation(
    hass: HomeAssistant,
    mock_config_entry,
    mock_openai_client: AsyncMock,
) -> None:
    """Test structured JSON data generation."""
    json_response = '{"name": "John", "age": 30}'
    chunks = [
        _make_chunk(role="assistant"),
        _make_chunk(content=json_response),
        _make_chunk(finish_reason="stop"),
    ]

    mock_openai_client.chat.completions.create = AsyncMock(
        return_value=_mock_stream(chunks)
    )

    import voluptuous as vol

    with patch(
        f"custom_components.{DOMAIN}.openai.AsyncOpenAI",
        return_value=mock_openai_client,
    ):
        mock_config_entry.runtime_data = mock_openai_client
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    result = await ai_task.async_generate_data(
        hass,
        task_name="test_structured",
        entity_id="ai_task.generic_ai_task",
        instructions="Extract person data",
        structure=vol.Schema(
            {vol.Required("name"): str, vol.Required("age"): int}
        ),
    )

    assert result.data == {"name": "John", "age": 30}
