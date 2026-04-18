"""Base entity for Generic Conversation."""

from __future__ import annotations

import base64
from collections.abc import AsyncGenerator, Callable, Iterable
import json
from mimetypes import guess_file_type
from pathlib import Path
from typing import TYPE_CHECKING, Any

import openai
from openai._streaming import AsyncStream
from openai.types.chat import (
    ChatCompletionChunk,
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
)
from openai.types.shared_params import FunctionDefinition
import voluptuous as vol
from voluptuous_openapi import convert

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, llm
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.json import json_dumps
from homeassistant.util import slugify

from .const import (
    CONF_CHAT_MODEL,
    CONF_MAX_TOKENS,
    CONF_TEMPERATURE,
    CONF_TOP_P,
    DEFAULT_CHAT_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DOMAIN,
    LOGGER,
    MAX_TOOL_ITERATIONS,
)

if TYPE_CHECKING:
    from . import GenericConversationConfigEntry


def _adjust_schema(schema: dict[str, Any]) -> None:
    """Adjust the schema to be compatible with OpenAI structured output API."""
    if schema["type"] == "object":
        schema.setdefault("strict", True)
        schema.setdefault("additionalProperties", False)
        if "properties" not in schema:
            return

        if "required" not in schema:
            schema["required"] = []

        for prop, prop_info in schema["properties"].items():
            _adjust_schema(prop_info)
            if prop not in schema["required"]:
                prop_info["type"] = [prop_info["type"], "null"]
                schema["required"].append(prop)

    elif schema["type"] == "array":
        if "items" not in schema:
            return
        _adjust_schema(schema["items"])


def _format_structured_output(
    schema: vol.Schema, llm_api: llm.APIInstance | None
) -> dict[str, Any]:
    """Format a vol.Schema into an OpenAI-compatible JSON Schema."""
    result: dict[str, Any] = convert(
        schema,
        custom_serializer=(
            llm_api.custom_serializer if llm_api else llm.selector_serializer
        ),
    )
    _adjust_schema(result)
    return result


def _format_tool(
    tool: llm.Tool, custom_serializer: Callable[[Any], Any] | None
) -> ChatCompletionToolParam:
    """Format an HA LLM tool into Chat Completions format."""
    return ChatCompletionToolParam(
        type="function",
        function=FunctionDefinition(
            name=tool.name,
            description=tool.description or "",
            parameters=convert(tool.parameters, custom_serializer=custom_serializer),
        ),
    )


def _convert_content_to_param(
    chat_content: Iterable[conversation.Content],
) -> list[ChatCompletionMessageParam]:
    """Convert HA chat content to Chat Completions message format."""
    messages: list[ChatCompletionMessageParam] = []

    for content in chat_content:
        if isinstance(content, conversation.ToolResultContent):
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": content.tool_call_id,
                    "content": json_dumps(content.tool_result),
                }
            )
            continue

        if isinstance(content, conversation.SystemContent):
            messages.append({"role": "system", "content": content.content or ""})
            continue

        if isinstance(content, conversation.UserContent):
            messages.append({"role": "user", "content": content.content or ""})
            continue

        if isinstance(content, conversation.AssistantContent):
            msg: dict[str, Any] = {
                "role": "assistant",
                "content": content.content or "",
            }
            if content.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.tool_name,
                            "arguments": json.dumps(tc.tool_args),
                        },
                    }
                    for tc in content.tool_calls
                ]
            messages.append(msg)

    return messages


async def async_prepare_files_for_prompt(
    hass: HomeAssistant, files: list[tuple[Path, str | None]]
) -> list[dict]:
    """Encode image files as base64 data URLs for the prompt."""

    def _prepare() -> list[dict]:
        content: list[dict] = []
        for file_path, mime_type in files:
            if not file_path.exists():
                raise HomeAssistantError(f"`{file_path}` does not exist")

            if mime_type is None:
                mime_type = guess_file_type(file_path)[0]

            if not mime_type or not mime_type.startswith("image/"):
                raise HomeAssistantError(
                    f"Only images are supported, `{file_path}` is not an image"
                )

            base64_data = base64.b64encode(file_path.read_bytes()).decode("utf-8")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{base64_data}",
                        "detail": "auto",
                    },
                }
            )
        return content

    return await hass.async_add_executor_job(_prepare)
