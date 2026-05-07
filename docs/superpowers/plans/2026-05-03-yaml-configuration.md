# YAML Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace GUI config flow with YAML-based configuration, using programmatic config entries (import flow) for automatic lifecycle management.

**Architecture:** YAML is the user-facing config. `async_setup` reads it and creates one config entry per service via `SOURCE_IMPORT`. `async_setup_entry` / `async_unload_entry` provide automatic entity and device cleanup. No user-facing config flow; the `config_flow.py` becomes an import-only handler.

**Tech Stack:** Python, Home Assistant Core APIs, voluptuous, openai SDK

**Spec:** `docs/superpowers/specs/2026-05-03-yaml-configuration-design.md`

**Testing Note:** Tests require a Home Assistant dev environment (`pytest` with HA fixtures). This repo has no `tests/` directory. Each task includes manual verification steps. If a HA dev env is available, add unit tests after each task.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `custom_components/generic_conversation/const.py` | Modify | Add YAML config keys, remove GUI-only constants |
| `custom_components/generic_conversation/config_flow.py` | Rewrite | Import-only flow handler (~15 lines) |
| `custom_components/generic_conversation/entity.py` | Modify | Accept `agent_config` dict instead of `ConfigSubentry` |
| `custom_components/generic_conversation/__init__.py` | Rewrite | Add `CONFIG_SCHEMA`, `async_setup`, reconciliation, reload service |
| `custom_components/generic_conversation/conversation.py` | Modify | Iterate agents from `entry.data` instead of subentries |
| `custom_components/generic_conversation/ai_task.py` | Modify | Iterate agents from `entry.data` instead of subentries |
| `custom_components/generic_conversation/strings.json` | Simplify | Keep only `exceptions` section |
| `README.md` | Create | Full user-facing documentation |

---

### Task 1: Update Constants

**Files:**
- Modify: `custom_components/generic_conversation/const.py`

- [ ] **Step 1: Rewrite const.py**

Replace the entire file contents with:

```python
"""Constants for the Generic Conversation integration."""

import logging

DOMAIN = "generic_conversation"
LOGGER = logging.getLogger(__package__)

CONF_SERVICES = "services"
CONF_AGENTS = "agents"
CONF_TYPE = "type"
CONF_NAME = "name"
CONF_BASE_URL = "base_url"
CONF_CHAT_MODEL = "model"
CONF_SYSTEM_PROMPT = "system_prompt"
CONF_MAX_TOKENS = "max_tokens"
CONF_TEMPERATURE = "temperature"
CONF_TOP_P = "top_p"

DEFAULT_MAX_TOKENS = 3000
DEFAULT_TEMPERATURE = 1.0
DEFAULT_TOP_P = 1.0

MAX_TOOL_ITERATIONS = 10
```

Key changes from old file:
- `CONF_CHAT_MODEL` value changes from `"chat_model"` to `"model"` (matches YAML key in spec)
- Removed: `CONF_RECOMMENDED`, `CONF_PROMPT`, `DEFAULT_CHAT_MODEL`, `DEFAULT_CONVERSATION_NAME`, `DEFAULT_AI_TASK_NAME`, `RECOMMENDED_CONVERSATION_OPTIONS`, `RECOMMENDED_AI_TASK_OPTIONS`
- Removed: `from homeassistant.const import CONF_LLM_HASS_API` and `from homeassistant.helpers import llm` (no longer needed here)
- Added: `CONF_SERVICES`, `CONF_AGENTS`, `CONF_TYPE`, `CONF_NAME`, `CONF_SYSTEM_PROMPT`

- [ ] **Step 2: Verify no syntax errors**

Run: `python -c "import ast; ast.parse(open('custom_components/generic_conversation/const.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/generic_conversation/const.py
git commit -m "refactor: update constants for YAML configuration

Remove GUI-only constants (CONF_RECOMMENDED, RECOMMENDED_*_OPTIONS).
Add YAML config keys (CONF_SERVICES, CONF_AGENTS, CONF_TYPE, etc.).
Rename CONF_CHAT_MODEL value to 'model' to match YAML schema."
```

---

### Task 2: Rewrite Config Flow (Import-Only)

**Files:**
- Rewrite: `custom_components/generic_conversation/config_flow.py`

- [ ] **Step 1: Replace config_flow.py with import-only handler**

Replace the entire file contents with:

```python
"""Config flow for Generic Conversation integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


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
```

Wait — `CONF_NAME` is imported from `.const` but the import is missing. Fix:

```python
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
```

- [ ] **Step 2: Verify no syntax errors**

Run: `python -c "import ast; ast.parse(open('custom_components/generic_conversation/config_flow.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/generic_conversation/config_flow.py
git commit -m "refactor: replace GUI config flow with import-only handler

Remove all GUI steps (user, reauth, subentry flows).
Single async_step_import creates config entries from YAML data.
No user-facing config flow - all configuration via YAML."
```

---

### Task 3: Update Base Entity

**Files:**
- Modify: `custom_components/generic_conversation/entity.py`

This task changes the entity constructor to accept a plain dict `agent_config` instead of `ConfigSubentry`, and updates `_async_handle_chat_log` to read from `self._config`.

- [ ] **Step 1: Replace entity.py**

Replace the entire file contents with:

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
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, llm
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.json import json_dumps
from homeassistant.util import slugify

from .const import (
    CONF_BASE_URL,
    CONF_CHAT_MODEL,
    CONF_MAX_TOKENS,
    CONF_NAME,
    CONF_TEMPERATURE,
    CONF_TOP_P,
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


class GenericBaseLLMEntity(Entity):
    """Base entity for Generic Conversation LLM entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: GenericConversationConfigEntry,
        agent_config: dict[str, Any],
    ) -> None:
        """Initialize the entity."""
        self.entry = entry
        self._config = agent_config
        service_slug = slugify(entry.data[CONF_NAME])
        agent_slug = slugify(agent_config[CONF_NAME])
        self._attr_unique_id = f"{service_slug}_{agent_slug}"
        self._attr_name = agent_config[CONF_NAME]
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, service_slug)},
            name=entry.data[CONF_NAME],
            manufacturer="Generic",
            model=entry.data[CONF_BASE_URL],
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
        options = self._config

        messages = _convert_content_to_param(chat_log.content)

        model_args: dict[str, Any] = {
            "model": options[CONF_CHAT_MODEL],
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
            if not isinstance(last_message.get("content"), str):
                raise HomeAssistantError("Expected string content in last message")
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

Key changes from old file:
- `__init__` takes `agent_config: dict[str, Any]` instead of `subentry: ConfigSubentry`
- `self._config` replaces `self.subentry.data`
- `self._attr_unique_id` is `slugify(service_name) + "_" + slugify(agent_name)` instead of `subentry.subentry_id`
- `self._attr_name` is set to the agent name (was `None` before — entities had no name, relying on subentry title)
- `self._attr_device_info` uses service-level identifiers `(DOMAIN, service_slug)` — one device per service, not per agent
- `model` is now a required key (`options[CONF_CHAT_MODEL]` not `.get(...)`) since YAML schema enforces it
- Removed `self.entry.async_start_reauth(self.hass)` from auth error handler (no reauth flow in YAML mode)
- Removed `from homeassistant.config_entries import ConfigSubentry` import
- Added imports for `CONF_BASE_URL`, `CONF_NAME`

- [ ] **Step 2: Verify no syntax errors**

Run: `python -c "import ast; ast.parse(open('custom_components/generic_conversation/entity.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/generic_conversation/entity.py
git commit -m "refactor: update base entity for YAML agent config

Accept agent_config dict instead of ConfigSubentry.
Use slugified service+agent names for unique ID.
One device per service (not per agent).
Remove reauth trigger (no GUI reauth in YAML mode)."
```

---

### Task 4: Update Conversation Platform

**Files:**
- Modify: `custom_components/generic_conversation/conversation.py`

- [ ] **Step 1: Replace conversation.py**

Replace the entire file contents with:

```python
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
                self._config.get(
                    CONF_SYSTEM_PROMPT, llm.DEFAULT_INSTRUCTIONS_PROMPT
                ),
                user_input.extra_system_prompt,
            )
        except conversation.ConverseError as err:
            return err.as_conversation_result()

        await self._async_handle_chat_log(chat_log)

        return conversation.async_get_result_from_chat_log(user_input, chat_log)
```

Key changes from old file:
- `async_setup_entry` iterates `entry.data[CONF_AGENTS]` filtering by `type == "conversation"` instead of iterating `config_entry.subentries`
- No `config_subentry_id` parameter on `async_add_entities`
- Entity `__init__` calls `super().__init__(entry, agent_config)` instead of `(entry, subentry)`
- `self.subentry.data` replaced with `self._config` throughout
- `CONF_PROMPT` replaced with `CONF_SYSTEM_PROMPT` (matches YAML key)
- Default system prompt applied explicitly: `self._config.get(CONF_SYSTEM_PROMPT, llm.DEFAULT_INSTRUCTIONS_PROMPT)`
- Removed `from homeassistant.config_entries import ConfigSubentry` import

- [ ] **Step 2: Verify no syntax errors**

Run: `python -c "import ast; ast.parse(open('custom_components/generic_conversation/conversation.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/generic_conversation/conversation.py
git commit -m "refactor: update conversation platform for YAML agents

Iterate entry.data agents instead of subentries.
Read system_prompt and llm_hass_api from agent config dict."
```

---

### Task 5: Update AI Task Platform

**Files:**
- Modify: `custom_components/generic_conversation/ai_task.py`

- [ ] **Step 1: Replace ai_task.py**

Replace the entire file contents with:

```python
"""AI Task integration for Generic Conversation."""

from __future__ import annotations

from json import JSONDecodeError
from typing import TYPE_CHECKING, Any

from homeassistant.components import ai_task, conversation
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.json import json_loads

from .const import CONF_AGENTS, CONF_TYPE, DOMAIN, LOGGER
from .entity import GenericBaseLLMEntity

if TYPE_CHECKING:
    from . import GenericConversationConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: GenericConversationConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AI Task entities."""
    entities = [
        GenericTaskEntity(config_entry, agent_config)
        for agent_config in config_entry.data[CONF_AGENTS]
        if agent_config[CONF_TYPE] == "ai_task"
    ]
    if entities:
        async_add_entities(entities)


class GenericTaskEntity(
    ai_task.AITaskEntity,
    GenericBaseLLMEntity,
):
    """Generic AI Task entity."""

    _attr_supported_features = (
        ai_task.AITaskEntityFeature.GENERATE_DATA
        | ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS
    )

    def __init__(
        self,
        entry: GenericConversationConfigEntry,
        agent_config: dict[str, Any],
    ) -> None:
        """Initialize the entity."""
        super().__init__(entry, agent_config)

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

Key changes from old file:
- `async_setup_entry` iterates `entry.data[CONF_AGENTS]` filtering by `type == "ai_task"` instead of iterating subentries
- No `config_subentry_id` parameter on `async_add_entities`
- Entity `__init__` calls `super().__init__(entry, agent_config)` instead of `(entry, subentry)`
- Removed `_attr_translation_key = "ai_task_data"` (entity name now comes from YAML config)
- Uses `LOGGER` from const instead of manual `_LOGGER` creation
- Removed `from homeassistant.config_entries import ConfigSubentry` import

- [ ] **Step 2: Verify no syntax errors**

Run: `python -c "import ast; ast.parse(open('custom_components/generic_conversation/ai_task.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/generic_conversation/ai_task.py
git commit -m "refactor: update AI task platform for YAML agents

Iterate entry.data agents instead of subentries.
Use LOGGER from const, remove translation_key."
```

---

### Task 6: Rewrite `__init__.py` (CONFIG_SCHEMA + async_setup + Reload)

**Files:**
- Rewrite: `custom_components/generic_conversation/__init__.py`

This is the largest task — the core of the YAML integration.

- [ ] **Step 1: Replace __init__.py**

Replace the entire file contents with:

```python
"""The Generic Conversation integration."""

from __future__ import annotations

from typing import Any

import openai
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.httpx_client import get_async_client
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
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    DOMAIN,
    LOGGER,
)

PLATFORMS = (Platform.AI_TASK, Platform.CONVERSATION)

type GenericConversationConfigEntry = ConfigEntry[openai.AsyncOpenAI]


def _unique_names(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate that all names in a list are unique."""
    names = [v[CONF_NAME] for v in values]
    if len(names) != len(set(names)):
        raise vol.Invalid("Names must be unique")
    return values


AGENT_CONVERSATION_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TYPE): "conversation",
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_CHAT_MODEL): cv.string,
        vol.Optional(CONF_MAX_TOKENS, default=DEFAULT_MAX_TOKENS): vol.All(
            vol.Coerce(int), vol.Range(min=1)
        ),
        vol.Optional(CONF_TEMPERATURE, default=DEFAULT_TEMPERATURE): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=2)
        ),
        vol.Optional(CONF_TOP_P, default=DEFAULT_TOP_P): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=1)
        ),
        vol.Optional(CONF_SYSTEM_PROMPT): cv.string,
        vol.Optional("llm_hass_api"): vol.All(cv.ensure_list, [cv.string]),
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
        vol.Optional(CONF_TEMPERATURE, default=DEFAULT_TEMPERATURE): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=2)
        ),
        vol.Optional(CONF_TOP_P, default=DEFAULT_TOP_P): vol.All(
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


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Generic Conversation from YAML configuration."""
    if DOMAIN not in config:
        return True

    conf = config[DOMAIN]
    yaml_services = {slugify(s[CONF_NAME]): s for s in conf[CONF_SERVICES]}

    existing_entries = {
        entry.unique_id: entry
        for entry in hass.config_entries.async_entries(DOMAIN)
    }

    for unique_id, service_conf in yaml_services.items():
        import_data = {
            "unique_id": unique_id,
            CONF_NAME: service_conf[CONF_NAME],
            CONF_BASE_URL: service_conf[CONF_BASE_URL],
            CONF_AGENTS: service_conf[CONF_AGENTS],
        }
        if CONF_API_KEY in service_conf:
            import_data[CONF_API_KEY] = service_conf[CONF_API_KEY]

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

    async def handle_reload(call: ServiceCall) -> None:
        """Handle reload service call."""
        await _async_reload(hass)

    hass.services.async_register(DOMAIN, "reload", handle_reload)

    return True


async def _async_reload(hass: HomeAssistant) -> None:
    """Reload YAML configuration and reconcile config entries."""
    conf = await hass.helpers.integration_yaml_config(DOMAIN)
    if conf is None:
        LOGGER.error("Failed to reload YAML configuration")
        return

    if DOMAIN not in conf:
        for entry in hass.config_entries.async_entries(DOMAIN):
            await hass.config_entries.async_remove(entry.entry_id)
        return

    yaml_services = {
        slugify(s[CONF_NAME]): s for s in conf[DOMAIN][CONF_SERVICES]
    }

    existing_entries = {
        entry.unique_id: entry
        for entry in hass.config_entries.async_entries(DOMAIN)
    }

    for unique_id, service_conf in yaml_services.items():
        import_data = {
            "unique_id": unique_id,
            CONF_NAME: service_conf[CONF_NAME],
            CONF_BASE_URL: service_conf[CONF_BASE_URL],
            CONF_AGENTS: service_conf[CONF_AGENTS],
        }
        if CONF_API_KEY in service_conf:
            import_data[CONF_API_KEY] = service_conf[CONF_API_KEY]

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
```

Key changes from old file:
- Added `CONFIG_SCHEMA` with full voluptuous validation of the YAML structure
- Added `async_setup()` that reads YAML, reconciles config entries (create/update/remove), and registers reload service
- Added `_async_reload()` that re-reads YAML and reconciles again
- `async_setup_entry` no longer raises `ConfigEntryAuthFailed` (no reauth flow) — logs error instead
- Removed `async_update_options()` listener (no options flow)
- Two separate agent schemas (`AGENT_CONVERSATION_SCHEMA`, `AGENT_AI_TASK_SCHEMA`) ensure `system_prompt` and `llm_hass_api` are only valid on conversation agents
- `_unique_names` validator rejects duplicate service/agent names
- `_validate_agent` dispatches to the correct schema based on `type`

- [ ] **Step 2: Verify no syntax errors**

Run: `python -c "import ast; ast.parse(open('custom_components/generic_conversation/__init__.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/generic_conversation/__init__.py
git commit -m "feat: add YAML configuration with import-flow lifecycle

Add CONFIG_SCHEMA for YAML validation.
async_setup reads YAML, creates config entries via SOURCE_IMPORT.
async_reload reconciles entries on service call.
Auth errors logged instead of triggering reauth flow."
```

---

### Task 7: Simplify strings.json

**Files:**
- Modify: `custom_components/generic_conversation/strings.json`

- [ ] **Step 1: Replace strings.json with exceptions-only content**

Replace the entire file contents with:

```json
{
  "exceptions": {
    "authentication_error": {
      "message": "Authentication failed. Please check your API key in configuration.yaml."
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

Changes: removed `config` and `config_subentries` sections entirely. Updated auth error message to reference YAML config.

- [ ] **Step 2: Verify valid JSON**

Run: `python -c "import json; json.load(open('custom_components/generic_conversation/strings.json')); print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add custom_components/generic_conversation/strings.json
git commit -m "chore: remove GUI flow strings, keep only exceptions

All config/subentry translation strings removed.
Auth error message now references configuration.yaml."
```

---

### Task 8: Lint and Verify All Files Together

**Files:**
- All modified files

- [ ] **Step 1: Run ruff check**

Run: `ruff check custom_components/generic_conversation`

Expected: no errors (or only pre-existing warnings)

- [ ] **Step 2: Run ruff format check**

Run: `ruff format --check custom_components/generic_conversation`

Expected: all files already formatted, or format and re-commit

- [ ] **Step 3: Fix any lint issues and commit if needed**

If ruff reports issues:

```bash
ruff check --fix custom_components/generic_conversation
ruff format custom_components/generic_conversation
git add custom_components/generic_conversation/
git commit -m "style: fix lint issues"
```

---

### Task 9: Create README.md

**Files:**
- Create: `README.md` (repository root)

- [ ] **Step 1: Create README.md**

Create the file at `/README.md` (repo root) with this content:

```markdown
# Generic Conversation

A Home Assistant custom integration that provides conversation agents and AI task entities using any OpenAI-compatible API endpoint.

Works with local inference servers (Ollama, LM Studio, vLLM) and cloud providers (OpenAI, OpenRouter) — anything that implements the OpenAI Chat Completions API.

## Features

- **Conversation agents** for voice assistants and chat interfaces
- **AI task entities** for automations with structured data output
- **Multiple services** — connect to several API endpoints simultaneously
- **Multiple agents per service** — run different models or configurations side by side
- **Streaming responses** with tool calling support
- **Graceful degradation** — features like tool calling and structured output degrade silently when the endpoint doesn't support them

## Requirements

- Home Assistant **2025.7.0** or later
- [HACS](https://hacs.xyz/) installed
- At least one OpenAI-compatible API endpoint accessible from your Home Assistant instance

## Installation

1. Open HACS in your Home Assistant instance
2. Click the three dots in the top right corner, then **Custom repositories**
3. Add this repository URL and select **Integration** as the category
4. Search for **Generic Conversation** and click **Install**
5. Restart Home Assistant
6. Add the YAML configuration (see below)
7. Restart Home Assistant again, or call the `generic_conversation.reload` service

## Configuration

All configuration is done in `configuration.yaml`. There is no GUI setup.

### Minimal Example (Ollama)

```yaml
generic_conversation:
  services:
    - name: "Ollama"
      base_url: "http://localhost:11434/v1"
      agents:
        - type: conversation
          name: "Chat"
          model: "llama3"
```

### Cloud Provider Example (OpenAI)

```yaml
generic_conversation:
  services:
    - name: "OpenAI"
      base_url: "https://api.openai.com/v1"
      api_key: !secret openai_api_key
      agents:
        - type: conversation
          name: "GPT-4o Chat"
          model: "gpt-4o"
          temperature: 0.7
          system_prompt: "You are a helpful home assistant."
        - type: ai_task
          name: "GPT-4o Tasks"
          model: "gpt-4o"
```

### Multi-Service Example

```yaml
generic_conversation:
  services:
    - name: "Local Ollama"
      base_url: "http://192.168.1.100:11434/v1"
      agents:
        - type: conversation
          name: "Local Chat"
          model: "llama3"
          max_tokens: 2000
          temperature: 0.8
          llm_hass_api:
            - assist

    - name: "OpenAI Cloud"
      base_url: "https://api.openai.com/v1"
      api_key: !secret openai_api_key
      agents:
        - type: conversation
          name: "GPT-4o Chat"
          model: "gpt-4o"
          temperature: 0.7
          system_prompt: "You are a helpful smart home assistant."
          llm_hass_api:
            - assist
        - type: ai_task
          name: "GPT-4o Tasks"
          model: "gpt-4o"
```

### Full Configuration Reference

```yaml
generic_conversation:
  services:
    - name: "Service Name"          # Required. Unique across all services.
      base_url: "http://host/v1"    # Required. OpenAI-compatible API endpoint.
      api_key: "your-key"           # Optional. Omit for local endpoints.
      agents:
        - type: conversation        # Required. "conversation" or "ai_task".
          name: "Agent Name"        # Required. Unique within the service.
          model: "model-id"         # Required. Model identifier for the endpoint.
          max_tokens: 3000          # Optional. Default: 3000.
          temperature: 1.0          # Optional. Default: 1.0. Range: 0-2.
          top_p: 1.0                # Optional. Default: 1.0. Range: 0-1.
          system_prompt: "..."      # Optional. Conversation agents only.
          llm_hass_api:             # Optional. Conversation agents only.
            - assist                # Default: ["assist"].
```

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `services` | list | Yes | — | List of API service connections |
| `name` (service) | string | Yes | — | Unique display name for the service |
| `base_url` | string | Yes | — | OpenAI-compatible API endpoint URL |
| `api_key` | string | No | — | API key for authentication |
| `agents` | list | Yes | — | List of agents to create for this service |
| `type` | string | Yes | — | Agent type: `conversation` or `ai_task` |
| `name` (agent) | string | Yes | — | Display name for the agent entity |
| `model` | string | Yes | — | Model identifier (e.g., `llama3`, `gpt-4o`) |
| `max_tokens` | integer | No | `3000` | Maximum tokens in the response |
| `temperature` | float | No | `1.0` | Sampling temperature (0 = deterministic, 2 = creative) |
| `top_p` | float | No | `1.0` | Nucleus sampling threshold |
| `system_prompt` | string | No | HA default | Custom system prompt (conversation agents only) |
| `llm_hass_api` | list | No | `["assist"]` | HA LLM APIs to expose (conversation agents only) |

### Using Secrets

Store API keys securely using Home Assistant's secrets management:

```yaml
# configuration.yaml
generic_conversation:
  services:
    - name: "OpenAI"
      base_url: "https://api.openai.com/v1"
      api_key: !secret openai_api_key
      agents:
        - type: conversation
          name: "Chat"
          model: "gpt-4o"
```

```yaml
# secrets.yaml
openai_api_key: "sk-your-api-key-here"
```

## Setting Up as a Voice Assistant

After adding the YAML configuration and restarting:

1. Go to **Settings** > **Voice assistants**
2. Click **Add assistant** (or edit an existing one)
3. Under **Conversation agent**, select the conversation agent created by this integration (it will appear with the name you configured)
4. Optionally configure language, wake word, STT, and TTS
5. Click **Create** / **Update**

Your voice assistant now uses the configured LLM for conversation.

## Using AI Task in Automations

AI task entities let you use LLMs in automations to generate data from natural language instructions.

### Simple Text Generation

```yaml
automation:
  - alias: "Morning Briefing"
    trigger:
      - trigger: time
        at: "07:00:00"
    action:
      - action: ai_task.generate_data
        data:
          task_name: "Morning briefing"
          instructions: "Generate a brief morning greeting with today's date."
          entity_id: ai_task.gpt_4o_tasks
        response_variable: result
      - action: notify.mobile_app
        data:
          message: "{{ result.data }}"
```

### Structured Data Output

```yaml
automation:
  - alias: "Categorize Notification"
    trigger:
      - trigger: event
        event_type: notification_received
    action:
      - action: ai_task.generate_data
        data:
          task_name: "Categorize"
          instructions: "Categorize this notification: {{ trigger.event.data.message }}"
          entity_id: ai_task.gpt_4o_tasks
          structure:
            - category:
                selector:
                  select:
                    options:
                      - urgent
                      - info
                      - spam
            - summary:
                selector:
                  text:
        response_variable: result
```

## Reloading Configuration

After editing `configuration.yaml`, reload without restarting:

1. Go to **Developer Tools** > **Actions**
2. Search for `generic_conversation.reload`
3. Click **Perform action**

Or call it from an automation:

```yaml
action:
  - action: generic_conversation.reload
```

What happens on reload:
- **New services** in YAML are created automatically
- **Removed services** are cleaned up (entities and devices removed)
- **Changed services** are reloaded with the updated configuration
- **Validation errors** abort the reload — existing configuration is preserved

## Troubleshooting

### Integration not loading

Check the Home Assistant logs for validation errors:

```
Settings > System > Logs
```

Common causes: invalid YAML syntax, missing required fields, duplicate names.

### Cannot connect to endpoint

- Verify the `base_url` is reachable from your Home Assistant instance
- For local servers, ensure the service is running and the port is correct
- For Docker-based HA, use the host IP (not `localhost`)

### Authentication failed

- Check that your `api_key` is correct in `secrets.yaml`
- Verify the key has not expired or been revoked
- For local endpoints that don't need auth, omit `api_key` entirely

### Model not found

- Verify the model name matches exactly what the endpoint provides
- For Ollama: run `ollama list` to see available models
- For OpenAI: check their [models documentation](https://platform.openai.com/docs/models)

### Enable Debug Logging

Add this to your `configuration.yaml` for detailed logs:

```yaml
logger:
  logs:
    custom_components.generic_conversation: debug
```

## Supported Endpoints

Any endpoint implementing the OpenAI Chat Completions API should work. Tested with:

| Endpoint | Base URL | API Key |
|----------|----------|---------|
| [Ollama](https://ollama.ai) | `http://host:11434/v1` | Not required |
| [LM Studio](https://lmstudio.ai) | `http://host:1234/v1` | Not required |
| [vLLM](https://docs.vllm.ai) | `http://host:8000/v1` | Not required |
| [OpenAI](https://openai.com) | `https://api.openai.com/v1` | Required |
| [OpenRouter](https://openrouter.ai) | `https://openrouter.ai/api/v1` | Required |

## Limitations

- **No GUI configuration** — all settings are managed through YAML
- **Renaming** a service or agent in YAML creates a new entity; the old one becomes unavailable and must be manually removed from the entity registry
- **Graceful degradation** — tool calling, structured output, streaming token stats, and model listing all degrade silently when the endpoint doesn't support them
- **No reauth flow** — if an API key becomes invalid, update it in YAML and reload

## License

This project is licensed under the MIT License.
```

- [ ] **Step 2: Verify the file renders correctly**

Run: `wc -l README.md` — should be around 250-280 lines.

Run: `head -5 README.md` — should show the title and description.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add comprehensive README with setup and usage guide

Covers installation, YAML configuration examples, voice assistant
setup, AI task automations, reload, troubleshooting, and supported
endpoints."
```

---

### Task 10: Final Verification

- [ ] **Step 1: Verify all files parse correctly**

Run each check:

```bash
python -c "import ast; ast.parse(open('custom_components/generic_conversation/const.py').read()); print('const.py OK')"
python -c "import ast; ast.parse(open('custom_components/generic_conversation/config_flow.py').read()); print('config_flow.py OK')"
python -c "import ast; ast.parse(open('custom_components/generic_conversation/entity.py').read()); print('entity.py OK')"
python -c "import ast; ast.parse(open('custom_components/generic_conversation/__init__.py').read()); print('__init__.py OK')"
python -c "import ast; ast.parse(open('custom_components/generic_conversation/conversation.py').read()); print('conversation.py OK')"
python -c "import ast; ast.parse(open('custom_components/generic_conversation/ai_task.py').read()); print('ai_task.py OK')"
python -c "import json; json.load(open('custom_components/generic_conversation/strings.json')); print('strings.json OK')"
python -c "import json; json.load(open('custom_components/generic_conversation/manifest.json')); print('manifest.json OK')"
```

Expected: all print `OK`

- [ ] **Step 2: Run ruff**

```bash
ruff check custom_components/generic_conversation
ruff format --check custom_components/generic_conversation
```

Expected: clean output

- [ ] **Step 3: Check git status**

```bash
git status
git log --oneline -10
```

Expected: clean working tree, ~7-8 commits for this feature

- [ ] **Step 4: Verify file list is complete**

```bash
ls custom_components/generic_conversation/
```

Expected files: `__init__.py`, `ai_task.py`, `config_flow.py`, `const.py`, `conversation.py`, `entity.py`, `icons.json`, `manifest.json`, `strings.json`

Plus `README.md` at repo root.

No files should be deleted. `icons.json` and `manifest.json` are unchanged.
