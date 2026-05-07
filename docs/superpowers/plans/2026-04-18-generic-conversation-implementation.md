# Generic Conversation Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Home Assistant custom integration (`generic_conversation`) that provides conversation agent and AI task entities using any OpenAI-compatible API endpoint.

**Architecture:** Subentry-based multi-entity integration using the `openai` Python SDK with a custom `base_url`. A base entity class in `entity.py` handles streaming, tool calls, and message conversion. Thin platform wrappers in `conversation.py` and `ai_task.py` inherit from it. Config flow supports optional API key + required base URL, with subentry flows for creating multiple agents.

**Tech Stack:** Python 3.13+, `openai` SDK (Chat Completions API), Home Assistant Core (2025.7.0+), voluptuous, voluptuous-openapi

---

## File Structure

```
custom_components/generic_conversation/
├── __init__.py          # Entry setup, client init, platform forwarding (~60 lines)
├── manifest.json        # Integration metadata (~12 lines)
├── const.py             # Config keys, defaults, constants (~50 lines)
├── config_flow.py       # User step + subentry flows (~200 lines)
├── entity.py            # Base LLM entity: streaming, tool loop, message conversion (~300 lines)
├── conversation.py      # Conversation agent platform wrapper (~60 lines)
├── ai_task.py           # AI task platform wrapper (~70 lines)
├── strings.json         # All UI text (~100 lines)
└── icons.json           # Entity icons (~6 lines)
```

Repository root files:
```
├── hacs.json            # HACS metadata
└── .gitignore           # Python + HA ignores
```

---

### Task 1: Repository Initialization & Project Scaffolding

**Files:**
- Create: `.gitignore`
- Create: `hacs.json`
- Create: `custom_components/generic_conversation/manifest.json`
- Create: `custom_components/generic_conversation/icons.json`

- [ ] **Step 1: Initialize git repository**

```bash
cd /Users/geryduyck/Documents/Code/generic_conversation
git init
```

- [ ] **Step 2: Create .gitignore**

```gitignore
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
.eggs/
*.egg
.venv/
venv/
.env
*.log
.DS_Store
.idea/
.vscode/
*.swp
*.swo
```

- [ ] **Step 3: Create hacs.json**

```json
{
  "name": "Generic Conversation",
  "content_in_root": false,
  "homeassistant": "2025.7.0",
  "hacs": "1.34.0"
}
```

- [ ] **Step 4: Create the custom_components directory and manifest.json**

```bash
mkdir -p custom_components/generic_conversation
```

```json
{
  "domain": "generic_conversation",
  "name": "Generic Conversation",
  "codeowners": [],
  "config_flow": true,
  "dependencies": ["conversation"],
  "documentation": "https://github.com/geryduyck/generic-conversation",
  "integration_type": "service",
  "iot_class": "cloud_polling",
  "requirements": ["openai>=1.0.0"],
  "version": "1.0.0"
}
```

- [ ] **Step 5: Create icons.json**

```json
{
  "services": {
    "conversation": { "service": "mdi:chat-processing" },
    "ai_task_data": { "service": "mdi:creation" }
  }
}
```

- [ ] **Step 6: Commit**

```bash
git add .gitignore hacs.json custom_components/generic_conversation/manifest.json custom_components/generic_conversation/icons.json
git commit -m "chore: initialize repository with project scaffolding"
```

---

### Task 2: Constants Module

**Files:**
- Create: `custom_components/generic_conversation/const.py`

- [ ] **Step 1: Create const.py with all configuration keys, defaults, and constants**

```python
"""Constants for the Generic Conversation integration."""

import logging

from homeassistant.const import CONF_LLM_HASS_API
from homeassistant.helpers import llm

DOMAIN = "generic_conversation"
LOGGER = logging.getLogger(__package__)

CONF_BASE_URL = "base_url"
CONF_CHAT_MODEL = "chat_model"
CONF_MAX_TOKENS = "max_tokens"
CONF_TEMPERATURE = "temperature"
CONF_TOP_P = "top_p"
CONF_PROMPT = "prompt"
CONF_RECOMMENDED = "recommended"

DEFAULT_CHAT_MODEL = "gpt-4o-mini"
DEFAULT_MAX_TOKENS = 3000
DEFAULT_TEMPERATURE = 1.0
DEFAULT_TOP_P = 1.0

DEFAULT_CONVERSATION_NAME = "Generic Conversation"
DEFAULT_AI_TASK_NAME = "Generic AI Task"

MAX_TOOL_ITERATIONS = 10

RECOMMENDED_CONVERSATION_OPTIONS = {
    CONF_RECOMMENDED: True,
    CONF_LLM_HASS_API: [llm.LLM_API_ASSIST],
    CONF_PROMPT: llm.DEFAULT_INSTRUCTIONS_PROMPT,
}

RECOMMENDED_AI_TASK_OPTIONS: dict = {
    CONF_RECOMMENDED: True,
}
```

- [ ] **Step 2: Commit**

```bash
git add custom_components/generic_conversation/const.py
git commit -m "feat: add constants module with config keys and defaults"
```

---

### Task 3: Entry Setup Module

**Files:**
- Create: `custom_components/generic_conversation/__init__.py`

- [ ] **Step 1: Create __init__.py with entry setup, unload, and options update**

```python
"""The Generic Conversation integration."""

from __future__ import annotations

import openai

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.httpx_client import get_async_client

from .const import CONF_BASE_URL

PLATFORMS = (Platform.AI_TASK, Platform.CONVERSATION)

type GenericConversationConfigEntry = ConfigEntry[openai.AsyncOpenAI]


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
        raise ConfigEntryAuthFailed(err) from err
    except openai.OpenAIError:
        pass  # Many endpoints don't support GET /models — proceed anyway

    entry.runtime_data = client

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: GenericConversationConfigEntry
) -> bool:
    """Unload Generic Conversation."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_options(
    hass: HomeAssistant, entry: GenericConversationConfigEntry
) -> None:
    """Update options."""
    await hass.config_entries.async_reload(entry.entry_id)
```

- [ ] **Step 2: Commit**

```bash
git add custom_components/generic_conversation/__init__.py
git commit -m "feat: add entry setup with client initialization and platform forwarding"
```

---

### Task 4: Base Entity Module — Helper Functions

**Files:**
- Create: `custom_components/generic_conversation/entity.py`

This is the most complex module. We build it in stages. This task covers the helper functions: `_format_tool`, `_convert_content_to_param`, `async_prepare_files_for_prompt`, `_format_structured_output`, and `_adjust_schema`.

- [ ] **Step 1: Create entity.py with imports and helper functions**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add custom_components/generic_conversation/entity.py
git commit -m "feat: add entity module with helper functions for tool formatting and message conversion"
```

---

### Task 5: Base Entity Module — Stream Transform & Chat Log Handler

**Files:**
- Modify: `custom_components/generic_conversation/entity.py`

Adds the `_transform_stream` async generator, the `GenericBaseLLMEntity` class, and its `_async_handle_chat_log` method.

- [ ] **Step 1: Add _transform_stream function to entity.py**

Append after `async_prepare_files_for_prompt`:

```python
async def _transform_stream(
    chat_log: conversation.ChatLog,
    stream: AsyncStream[ChatCompletionChunk],
) -> AsyncGenerator[
    conversation.AssistantContentDeltaDict | conversation.ToolResultContentDeltaDict
]:
    """Transform a Chat Completions stream into HA delta format."""
    current_tool_calls: dict[int, dict[str, Any]] = {}

    async for chunk in stream:
        if not chunk.choices:
            if chunk.usage is not None:
                chat_log.async_trace(
                    {
                        "stats": {
                            "input_tokens": chunk.usage.prompt_tokens,
                            "output_tokens": chunk.usage.completion_tokens,
                        }
                    }
                )
            continue

        choice = chunk.choices[0]
        delta = choice.delta

        if delta.role == "assistant":
            yield {"role": "assistant"}

        if delta.content is not None:
            yield {"content": delta.content}

        if delta.tool_calls:
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index
                if idx not in current_tool_calls:
                    current_tool_calls[idx] = {
                        "id": "",
                        "function": {"name": "", "arguments": ""},
                    }
                tc = current_tool_calls[idx]
                if tc_delta.id:
                    tc["id"] = tc_delta.id
                if tc_delta.function:
                    if tc_delta.function.name:
                        tc["function"]["name"] = tc_delta.function.name
                    if tc_delta.function.arguments:
                        tc["function"]["arguments"] += tc_delta.function.arguments

        if choice.finish_reason == "tool_calls" and current_tool_calls:
            yield {
                "tool_calls": [
                    llm.ToolInput(
                        id=tc["id"],
                        tool_name=tc["function"]["name"],
                        tool_args=json.loads(tc["function"]["arguments"]),
                    )
                    for tc in current_tool_calls.values()
                ]
            }
            current_tool_calls = {}

        if choice.finish_reason == "length":
            raise HomeAssistantError("Response incomplete: max output tokens reached")

        if choice.finish_reason == "content_filter":
            raise HomeAssistantError("Response incomplete: content filter triggered")
```

- [ ] **Step 2: Add GenericBaseLLMEntity class with _async_handle_chat_log**

Append after `_transform_stream`:

```python
class GenericBaseLLMEntity(Entity):
    """Base entity for Generic Conversation LLM entities."""

    _attr_has_entity_name = True
    _attr_name: str | None = None

    def __init__(
        self, entry: GenericConversationConfigEntry, subentry: ConfigSubentry
    ) -> None:
        """Initialize the entity."""
        self.entry = entry
        self.subentry = subentry
        self._attr_unique_id = subentry.subentry_id
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            manufacturer="Generic",
            model=subentry.data.get(CONF_CHAT_MODEL, DEFAULT_CHAT_MODEL),
            entry_type=dr.DeviceEntryType.SERVICE,
        )

    async def _async_handle_chat_log(
        self,
        chat_log: conversation.ChatLog,
        structure_name: str | None = None,
        structure: vol.Schema | None = None,
        max_iterations: int = MAX_TOOL_ITERATIONS,
    ) -> None:
        """Generate an answer for the chat log."""
        options = self.subentry.data

        messages = _convert_content_to_param(chat_log.content)

        model_args: dict[str, Any] = {
            "model": options.get(CONF_CHAT_MODEL, DEFAULT_CHAT_MODEL),
            "messages": messages,
            "max_tokens": options.get(CONF_MAX_TOKENS, DEFAULT_MAX_TOKENS),
            "top_p": options.get(CONF_TOP_P, DEFAULT_TOP_P),
            "temperature": options.get(CONF_TEMPERATURE, DEFAULT_TEMPERATURE),
            "stream": True,
            "user": chat_log.conversation_id,
        }

        if chat_log.llm_api and chat_log.llm_api.tools:
            model_args["tools"] = [
                _format_tool(tool, chat_log.llm_api.custom_serializer)
                for tool in chat_log.llm_api.tools
            ]

        if structure and structure_name:
            model_args["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": slugify(structure_name),
                    "schema": _format_structured_output(structure, chat_log.llm_api),
                },
            }

        last_content = chat_log.content[-1]
        if last_content.role == "user" and last_content.attachments:
            files = await async_prepare_files_for_prompt(
                self.hass,
                [(a.path, a.mime_type) for a in last_content.attachments],
            )
            last_message = messages[-1]
            assert isinstance(last_message.get("content"), str)
            last_message["content"] = [
                {"type": "text", "text": last_message["content"]},
                *files,
            ]

        model_args["stream_options"] = {"include_usage": True}

        client = self.entry.runtime_data

        for _iteration in range(max_iterations):
            try:
                response = await client.chat.completions.create(**model_args)

                messages.extend(
                    _convert_content_to_param(
                        [
                            content
                            async for content in (
                                chat_log.async_add_delta_content_stream(
                                    self.entity_id,
                                    _transform_stream(chat_log, response),
                                )
                            )
                        ]
                    )
                )
            except openai.AuthenticationError as err:
                self.entry.async_start_reauth(self.hass)
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="authentication_error",
                ) from err
            except openai.RateLimitError as err:
                raise HomeAssistantError(
                    "Rate limited or insufficient funds"
                ) from err
            except openai.APIConnectionError as err:
                raise HomeAssistantError(
                    "Could not connect to API endpoint"
                ) from err
            except openai.APIError as err:
                LOGGER.error("Error talking to API endpoint: %s", err)
                raise HomeAssistantError(
                    "Error talking to API endpoint"
                ) from err

            if not chat_log.unresponded_tool_results:
                break
```

- [ ] **Step 3: Verify the complete entity.py is well-formed**

```bash
python3 -c "import ast; ast.parse(open('custom_components/generic_conversation/entity.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add custom_components/generic_conversation/entity.py
git commit -m "feat: add stream transform and base LLM entity with chat log handler"
```

---

### Task 6: Conversation Platform

**Files:**
- Create: `custom_components/generic_conversation/conversation.py`

- [ ] **Step 1: Create conversation.py**

```python
"""Conversation support for Generic Conversation."""

from typing import Literal

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import CONF_LLM_HASS_API, MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GenericConversationConfigEntry
from .const import CONF_PROMPT, DOMAIN
from .entity import GenericBaseLLMEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: GenericConversationConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up conversation entities."""
    for subentry in config_entry.subentries.values():
        if subentry.subentry_type != "conversation":
            continue
        async_add_entities(
            [GenericConversationEntity(config_entry, subentry)],
            config_subentry_id=subentry.subentry_id,
        )


class GenericConversationEntity(
    conversation.ConversationEntity,
    conversation.AbstractConversationAgent,
    GenericBaseLLMEntity,
):
    """Generic conversation agent."""

    _attr_supports_streaming = True

    def __init__(
        self, entry: GenericConversationConfigEntry, subentry: ConfigSubentry
    ) -> None:
        """Initialize the agent."""
        super().__init__(entry, subentry)
        if self.subentry.data.get(CONF_LLM_HASS_API):
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
        options = self.subentry.data

        try:
            await chat_log.async_provide_llm_data(
                user_input.as_llm_context(DOMAIN),
                options.get(CONF_LLM_HASS_API),
                options.get(CONF_PROMPT),
                user_input.extra_system_prompt,
            )
        except conversation.ConverseError as err:
            return err.as_conversation_result()

        await self._async_handle_chat_log(chat_log)

        return conversation.async_get_result_from_chat_log(user_input, chat_log)
```

- [ ] **Step 2: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('custom_components/generic_conversation/conversation.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/generic_conversation/conversation.py
git commit -m "feat: add conversation platform entity"
```

---

### Task 7: AI Task Platform

**Files:**
- Create: `custom_components/generic_conversation/ai_task.py`

- [ ] **Step 1: Create ai_task.py**

```python
"""AI Task integration for Generic Conversation."""

from __future__ import annotations

from json import JSONDecodeError
from typing import TYPE_CHECKING

from homeassistant.components import ai_task, conversation
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.json import json_loads

from .const import DOMAIN
from .entity import GenericBaseLLMEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigSubentry

    from . import GenericConversationConfigEntry

LOGGER = __import__("logging").getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: GenericConversationConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AI Task entities."""
    for subentry in config_entry.subentries.values():
        if subentry.subentry_type != "ai_task_data":
            continue
        async_add_entities(
            [GenericTaskEntity(config_entry, subentry)],
            config_subentry_id=subentry.subentry_id,
        )


class GenericTaskEntity(
    ai_task.AITaskEntity,
    GenericBaseLLMEntity,
):
    """Generic AI Task entity."""

    _attr_supported_features = (
        ai_task.AITaskEntityFeature.GENERATE_DATA
        | ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS
    )
    _attr_translation_key = "ai_task_data"

    async def _async_generate_data(
        self,
        task: ai_task.GenDataTask,
        chat_log: conversation.ChatLog,
    ) -> ai_task.GenDataTaskResult:
        """Handle a generate data task."""
        await self._async_handle_chat_log(
            chat_log,
            structure_name=task.name,
            structure=task.structure,
            max_iterations=1000,
        )

        if not isinstance(chat_log.content[-1], conversation.AssistantContent):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="response_not_found",
            )

        text = chat_log.content[-1].content or ""

        if not task.structure:
            return ai_task.GenDataTaskResult(
                conversation_id=chat_log.conversation_id,
                data=text,
            )

        try:
            data = json_loads(text)
        except JSONDecodeError as err:
            LOGGER.error(
                "Failed to parse JSON response: %s. Response: %s", err, text
            )
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="json_parse_error",
            ) from err

        return ai_task.GenDataTaskResult(
            conversation_id=chat_log.conversation_id,
            data=data,
        )
```

- [ ] **Step 2: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('custom_components/generic_conversation/ai_task.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/generic_conversation/ai_task.py
git commit -m "feat: add AI task platform entity with structured data generation"
```

---

### Task 8: UI Strings

**Files:**
- Create: `custom_components/generic_conversation/strings.json`

- [ ] **Step 1: Create strings.json with all UI text**

```json
{
  "config": {
    "abort": {
      "already_configured": "[%key:common::config_flow::abort::already_configured_service%]",
      "reauth_successful": "[%key:common::config_flow::abort::reauth_successful%]"
    },
    "error": {
      "cannot_connect": "[%key:common::config_flow::error::cannot_connect%]",
      "invalid_auth": "[%key:common::config_flow::error::invalid_auth%]",
      "unknown": "[%key:common::config_flow::error::unknown%]"
    },
    "step": {
      "user": {
        "data": {
          "api_key": "[%key:common::config_flow::data::api_key%]",
          "base_url": "API Base URL"
        },
        "data_description": {
          "api_key": "Your API key (leave empty for local servers that don't require authentication).",
          "base_url": "The base URL of the OpenAI-compatible API endpoint."
        },
        "description": "Configure a connection to an OpenAI-compatible API endpoint."
      },
      "reauth_confirm": {
        "data": {
          "api_key": "[%key:common::config_flow::data::api_key%]"
        },
        "data_description": {
          "api_key": "Your updated API key."
        },
        "description": "Reauthentication required. Please enter your updated API key."
      }
    }
  },
  "config_subentries": {
    "conversation": {
      "abort": {
        "entry_not_loaded": "Cannot add things while the configuration is disabled.",
        "reconfigure_successful": "[%key:common::config_flow::abort::reconfigure_successful%]"
      },
      "entry_type": "Conversation agent",
      "initiate_flow": {
        "reconfigure": "Reconfigure conversation agent",
        "user": "Add conversation agent"
      },
      "step": {
        "init": {
          "data": {
            "llm_hass_api": "[%key:common::config_flow::data::llm_hass_api%]",
            "name": "[%key:common::config_flow::data::name%]",
            "prompt": "[%key:common::config_flow::data::prompt%]",
            "recommended": "Recommended model settings"
          },
          "data_description": {
            "prompt": "Instruct how the LLM should respond. This can be a template."
          }
        },
        "advanced": {
          "data": {
            "chat_model": "[%key:common::generic::model%]",
            "max_tokens": "Maximum tokens to return in response",
            "temperature": "Temperature",
            "top_p": "Top P"
          },
          "title": "Advanced settings"
        }
      }
    },
    "ai_task_data": {
      "abort": {
        "entry_not_loaded": "[%key:component::generic_conversation::config_subentries::conversation::abort::entry_not_loaded%]",
        "reconfigure_successful": "[%key:common::config_flow::abort::reconfigure_successful%]"
      },
      "entry_type": "AI task",
      "initiate_flow": {
        "reconfigure": "Reconfigure AI task",
        "user": "Add AI task"
      },
      "step": {
        "init": {
          "data": {
            "name": "[%key:common::config_flow::data::name%]",
            "recommended": "[%key:component::generic_conversation::config_subentries::conversation::step::init::data::recommended%]"
          }
        },
        "advanced": {
          "data": {
            "chat_model": "[%key:common::generic::model%]",
            "max_tokens": "[%key:component::generic_conversation::config_subentries::conversation::step::advanced::data::max_tokens%]",
            "temperature": "[%key:component::generic_conversation::config_subentries::conversation::step::advanced::data::temperature%]",
            "top_p": "[%key:component::generic_conversation::config_subentries::conversation::step::advanced::data::top_p%]"
          },
          "title": "[%key:component::generic_conversation::config_subentries::conversation::step::advanced::title%]"
        }
      }
    }
  },
  "exceptions": {
    "authentication_error": {
      "message": "Authentication failed. Please check your API key."
    },
    "response_not_found": {
      "message": "No response was generated by the AI model."
    },
    "json_parse_error": {
      "message": "Failed to parse the structured response from the AI model."
    }
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add custom_components/generic_conversation/strings.json
git commit -m "feat: add UI strings for config flow and error messages"
```

---

### Task 9: Configuration Flow

**Files:**
- Create: `custom_components/generic_conversation/config_flow.py`

- [ ] **Step 1: Create config_flow.py with main flow, reauth, and subentry handler**

```python
"""Config flow for Generic Conversation integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import openai
import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_API_KEY, CONF_LLM_HASS_API, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import llm
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TemplateSelector,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.typing import VolDictType

from .const import (
    CONF_BASE_URL,
    CONF_CHAT_MODEL,
    CONF_MAX_TOKENS,
    CONF_PROMPT,
    CONF_RECOMMENDED,
    CONF_TEMPERATURE,
    CONF_TOP_P,
    DEFAULT_AI_TASK_NAME,
    DEFAULT_CHAT_MODEL,
    DEFAULT_CONVERSATION_NAME,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DOMAIN,
    RECOMMENDED_AI_TASK_OPTIONS,
    RECOMMENDED_CONVERSATION_OPTIONS,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_API_KEY): str,
        vol.Required(
            CONF_BASE_URL, default="http://localhost:11434/v1"
        ): str,
    }
)


class GenericConversationConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Generic Conversation."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._async_abort_entries_match(
                {CONF_BASE_URL: user_input[CONF_BASE_URL]}
            )

            client = openai.AsyncOpenAI(
                api_key=user_input.get(CONF_API_KEY) or None,
                base_url=user_input[CONF_BASE_URL],
                http_client=get_async_client(self.hass),
            )

            try:
                await client.models.list(timeout=10.0)
            except openai.AuthenticationError:
                errors["base"] = "invalid_auth"
            except openai.APIConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                pass  # Endpoint may not support GET /models — proceed

            if not errors:
                if self.source == SOURCE_REAUTH:
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(), data_updates=user_input
                    )
                return self.async_create_entry(
                    title="Generic Conversation",
                    data=user_input,
                    subentries=[
                        {
                            "subentry_type": "conversation",
                            "data": RECOMMENDED_CONVERSATION_OPTIONS,
                            "title": DEFAULT_CONVERSATION_NAME,
                            "unique_id": None,
                        },
                        {
                            "subentry_type": "ai_task_data",
                            "data": RECOMMENDED_AI_TASK_OPTIONS,
                            "title": DEFAULT_AI_TASK_NAME,
                            "unique_id": None,
                        },
                    ],
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        if not user_input:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=vol.Schema(
                    {vol.Required(CONF_API_KEY): str}
                ),
            )
        reauth_entry = self._get_reauth_entry()
        return await self.async_step_user(
            {**reauth_entry.data, **user_input}
        )

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {
            "conversation": GenericSubentryFlowHandler,
            "ai_task_data": GenericSubentryFlowHandler,
        }


class GenericSubentryFlowHandler(ConfigSubentryFlow):
    """Flow for managing Generic Conversation subentries."""

    options: dict[str, Any]

    @property
    def _is_new(self) -> bool:
        """Return if this is a new subentry."""
        return self.source == "user"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Add a subentry."""
        if self._subentry_type == "ai_task_data":
            self.options = RECOMMENDED_AI_TASK_OPTIONS.copy()
        else:
            self.options = RECOMMENDED_CONVERSATION_OPTIONS.copy()
        return await self.async_step_init()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle reconfiguration of a subentry."""
        self.options = self._get_reconfigure_subentry().data.copy()
        return await self.async_step_init()

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Manage initial options."""
        if self._get_entry().state != ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        options = self.options

        step_schema: VolDictType = {}

        if self._is_new:
            if self._subentry_type == "ai_task_data":
                default_name = DEFAULT_AI_TASK_NAME
            else:
                default_name = DEFAULT_CONVERSATION_NAME
            step_schema[vol.Required(CONF_NAME, default=default_name)] = str

        if self._subentry_type == "conversation":
            hass_apis: list[SelectOptionDict] = [
                SelectOptionDict(label=api.name, value=api.id)
                for api in llm.async_get_apis(self.hass)
            ]
            if suggested_llm_apis := options.get(CONF_LLM_HASS_API):
                if isinstance(suggested_llm_apis, str):
                    suggested_llm_apis = [suggested_llm_apis]
                valid_apis = {api.id for api in llm.async_get_apis(self.hass)}
                options[CONF_LLM_HASS_API] = [
                    api for api in suggested_llm_apis if api in valid_apis
                ]

            step_schema.update(
                {
                    vol.Optional(
                        CONF_PROMPT,
                        description={
                            "suggested_value": options.get(
                                CONF_PROMPT, llm.DEFAULT_INSTRUCTIONS_PROMPT
                            )
                        },
                    ): TemplateSelector(),
                    vol.Optional(CONF_LLM_HASS_API): SelectSelector(
                        SelectSelectorConfig(options=hass_apis, multiple=True)
                    ),
                }
            )

        step_schema[
            vol.Required(
                CONF_RECOMMENDED, default=options.get(CONF_RECOMMENDED, False)
            )
        ] = bool

        if user_input is not None:
            if not user_input.get(CONF_LLM_HASS_API):
                user_input.pop(CONF_LLM_HASS_API, None)

            if user_input[CONF_RECOMMENDED]:
                if self._is_new:
                    return self.async_create_entry(
                        title=user_input.pop(CONF_NAME),
                        data=user_input,
                    )
                return self.async_update_and_abort(
                    self._get_entry(),
                    self._get_reconfigure_subentry(),
                    data=user_input,
                )

            options.update(user_input)
            if CONF_LLM_HASS_API in options and CONF_LLM_HASS_API not in user_input:
                options.pop(CONF_LLM_HASS_API)
            return await self.async_step_advanced()

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(step_schema), options
            ),
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Manage advanced options."""
        options = self.options

        step_schema: VolDictType = {
            vol.Optional(
                CONF_CHAT_MODEL,
                default=DEFAULT_CHAT_MODEL,
            ): TextSelector(
                TextSelectorConfig(type=TextSelectorType.TEXT)
            ),
            vol.Optional(
                CONF_MAX_TOKENS,
                default=DEFAULT_MAX_TOKENS,
            ): int,
            vol.Optional(
                CONF_TOP_P,
                default=DEFAULT_TOP_P,
            ): NumberSelector(NumberSelectorConfig(min=0, max=1, step=0.05)),
            vol.Optional(
                CONF_TEMPERATURE,
                default=DEFAULT_TEMPERATURE,
            ): NumberSelector(NumberSelectorConfig(min=0, max=2, step=0.05)),
        }

        if user_input is not None:
            options.update(user_input)
            if self._is_new:
                return self.async_create_entry(
                    title=options.pop(CONF_NAME),
                    data=options,
                )
            return self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                data=options,
            )

        return self.async_show_form(
            step_id="advanced",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(step_schema), options
            ),
        )
```

- [ ] **Step 2: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('custom_components/generic_conversation/config_flow.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/generic_conversation/config_flow.py
git commit -m "feat: add config flow with user step, reauth, and subentry handler"
```

---

### Task 10: Integration Smoke Test

**Files:** None modified — verification only

This task verifies the complete integration is syntactically valid and all imports resolve correctly (to the extent possible without the HA runtime).

- [ ] **Step 1: Verify all Python files parse correctly**

```bash
for f in custom_components/generic_conversation/*.py; do
  python3 -c "import ast; ast.parse(open('$f').read())" && echo "OK: $f" || echo "FAIL: $f"
done
```

Expected: All files show `OK`

- [ ] **Step 2: Verify JSON files are valid**

```bash
python3 -c "import json; json.load(open('custom_components/generic_conversation/strings.json')); print('strings.json OK')"
python3 -c "import json; json.load(open('custom_components/generic_conversation/icons.json')); print('icons.json OK')"
python3 -c "import json; json.load(open('custom_components/generic_conversation/manifest.json')); print('manifest.json OK')"
python3 -c "import json; json.load(open('hacs.json')); print('hacs.json OK')"
```

Expected: All files show `OK`

- [ ] **Step 3: Verify file structure matches spec**

```bash
ls -la custom_components/generic_conversation/
```

Expected files: `__init__.py`, `ai_task.py`, `config_flow.py`, `const.py`, `conversation.py`, `entity.py`, `icons.json`, `manifest.json`, `strings.json`

- [ ] **Step 4: Create final integration commit if any fixes were needed**

If any issues were found and fixed in steps 1-3, commit them:

```bash
git add -A
git commit -m "fix: resolve any issues found during smoke testing"
```

---

### Task 11: Test Infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

This task sets up the test infrastructure. Note: these tests require a Home Assistant development environment to run. They will not run standalone.

- [ ] **Step 1: Create tests directory and empty __init__.py**

```bash
mkdir -p tests
```

```python
# tests/__init__.py
```

- [ ] **Step 2: Create conftest.py with shared fixtures**

```python
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
```

- [ ] **Step 3: Commit**

```bash
git add tests/
git commit -m "test: add test infrastructure with shared fixtures"
```

---

### Task 12: Config Flow Tests

**Files:**
- Create: `tests/test_config_flow.py`

- [ ] **Step 1: Create config flow test file**

```python
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
        mock_client.models.list = AsyncMock(side_effect=Exception("Not supported"))

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
```

- [ ] **Step 2: Commit**

```bash
git add tests/test_config_flow.py
git commit -m "test: add config flow tests for happy path, errors, and reauth"
```

---

### Task 13: Conversation Entity Tests

**Files:**
- Create: `tests/test_conversation.py`

- [ ] **Step 1: Create conversation test file**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add tests/test_conversation.py
git commit -m "test: add conversation entity test for simple text response"
```

---

### Task 14: AI Task Entity Tests

**Files:**
- Create: `tests/test_ai_task.py`

- [ ] **Step 1: Create AI task test file**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add tests/test_ai_task.py
git commit -m "test: add AI task tests for plain text and structured JSON generation"
```
