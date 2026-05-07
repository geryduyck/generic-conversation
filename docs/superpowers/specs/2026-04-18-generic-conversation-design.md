# Generic Conversation Integration — Design Spec

**Date:** 2026-04-18
**Status:** Approved
**Scope:** Initial release (v1.0.0) — Conversation + AI Task platforms

## Overview

A Home Assistant custom integration (`generic_conversation`) that provides a generic AI conversation agent and AI task entity using any OpenAI-compatible API endpoint. Unlike vendor-locked integrations (`openai_conversation`, `anthropic`), this integration allows users to point at any compatible endpoint (Ollama, LM Studio, vLLM, text-generation-webui, third-party providers) by specifying a custom `base_url`.

The integration uses the **Chat Completions API** (`client.chat.completions.create`) rather than the newer Responses API, because Chat Completions is the most widely supported interface across OpenAI-compatible endpoints.

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| API surface | Chat Completions API | Most widely supported across OpenAI-compatible endpoints |
| SDK | `openai` Python SDK with custom `base_url` | Handles auth, retries, streaming, type safety |
| Authentication | Optional API key + required base_url | Supports both local (no auth) and cloud providers |
| Architecture | Simplified generic (Approach 2) | No vendor-specific logic; focus on common API surface |
| Tool calling | Full HA LLM API support with streaming tool loop | Maximum Home Assistant control capability |
| Structured output | `response_format` with `json_schema` | Standard Chat Completions feature |
| File attachments | Images only (base64 encoded) | Most widely supported; PDFs deferred |
| Model selection | Text input with optional fetch from endpoint | Graceful fallback when `GET /models` unsupported |
| Config pattern | Subentry-based multi-entity | Matches reference implementations; future-proof |
| Vendor features | Omitted | No web search, code interpreter, reasoning, image gen, prompt caching |

## File Structure

```
custom_components/generic_conversation/
├── __init__.py          # Entry setup, client init, platform forwarding
├── manifest.json        # Integration metadata
├── const.py             # Config keys, defaults
├── config_flow.py       # User step + subentry flows
├── entity.py            # Base LLM entity: streaming, tool loop, message conversion
├── conversation.py      # Conversation agent platform (thin wrapper)
├── ai_task.py           # AI task platform (thin wrapper)
├── strings.json         # All UI text
└── icons.json           # Entity icons
```

## Module Specifications

### `const.py` — Constants & Defaults

```python
DOMAIN = "generic_conversation"

# Config keys — parent entry
CONF_BASE_URL = "base_url"

# Config keys — subentry
CONF_CHAT_MODEL = "chat_model"
CONF_MAX_TOKENS = "max_tokens"
CONF_TEMPERATURE = "temperature"
CONF_TOP_P = "top_p"
CONF_PROMPT = "prompt"
CONF_RECOMMENDED = "recommended"

# Defaults
DEFAULT_CHAT_MODEL = "gpt-4o-mini"
DEFAULT_MAX_TOKENS = 3000
DEFAULT_TEMPERATURE = 1.0
DEFAULT_TOP_P = 1.0

# Tool iteration limit
MAX_TOOL_ITERATIONS = 10

# Platforms
PLATFORMS = [Platform.CONVERSATION, Platform.AI_TASK]

# Recommended options (used when "recommended" toggle is checked)
RECOMMENDED_CONVERSATION_OPTIONS = {
    CONF_CHAT_MODEL: DEFAULT_CHAT_MODEL,
    CONF_MAX_TOKENS: DEFAULT_MAX_TOKENS,
    CONF_TEMPERATURE: DEFAULT_TEMPERATURE,
    CONF_TOP_P: DEFAULT_TOP_P,
    CONF_RECOMMENDED: True,
}
RECOMMENDED_AI_TASK_OPTIONS = {
    CONF_CHAT_MODEL: DEFAULT_CHAT_MODEL,
    CONF_MAX_TOKENS: DEFAULT_MAX_TOKENS,
    CONF_TEMPERATURE: DEFAULT_TEMPERATURE,
    CONF_TOP_P: DEFAULT_TOP_P,
    CONF_RECOMMENDED: True,
}
```

CONF_API_KEY and CONF_LLM_HASS_API come from `homeassistant.const`.

### `__init__.py` — Entry Setup

**Type alias:**
```python
type GenericConversationConfigEntry = ConfigEntry[AsyncOpenAI]
```

Runtime data is the `AsyncOpenAI` client instance directly (no wrapper dataclass needed).

**`async_setup_entry()`:**
1. Create `AsyncOpenAI` client:
   ```python
   client = AsyncOpenAI(
       api_key=entry.data.get(CONF_API_KEY) or None,
       base_url=entry.data[CONF_BASE_URL],
       http_client=get_async_client(hass),
   )
   ```
2. Store: `entry.runtime_data = client`
3. Forward platforms: `await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)`

**`async_unload_entry()`:**
1. Unload platforms: `return await hass.config_entries.async_unload_entry_platforms(entry, PLATFORMS)`

**Subentry lifecycle:**
- `async_setup_entry` handles initial subentries
- Listen for subentry add/remove events to dynamically add/remove entities

### `config_flow.py` — Configuration Flow

**`GenericConversationConfigFlow(ConfigFlow)`:**

VERSION = 1, MINOR_VERSION = 1

#### User Step (parent entry)

Form fields:
- `api_key`: Optional text input (password field)
- `base_url`: Required text input, default `"http://localhost:11434/v1"`

Validation:
1. Create temporary client with provided credentials
2. Try `await client.models.list()` with 10s timeout
3. If `AuthenticationError` → show `invalid_auth` error
4. If `APIConnectionError` → show `cannot_connect` error
5. If other error or success → proceed (graceful — some endpoints don't support model listing)

On success, create entry with two default subentries:
```python
self.async_create_entry(
    title="Generic Conversation",
    data={"api_key": api_key, "base_url": base_url},
    subentries=[
        {
            "subentry_type": "conversation",
            "data": RECOMMENDED_CONVERSATION_OPTIONS,
            "title": "Generic Conversation",
            "unique_id": None,
        },
        {
            "subentry_type": "ai_task_data",
            "data": RECOMMENDED_AI_TASK_OPTIONS,
            "title": "Generic AI Task",
            "unique_id": None,
        },
    ],
)
```

#### Reauth Flow

Triggered when API returns `AuthenticationError` during operation.
- `async_step_reauth()` → `async_step_reauth_confirm()`: Show form to re-enter API key
- Validate new key, update entry data

#### Subentry Flow Handler

`GenericConversationSubentryFlowHandler(ConfigSubentryFlow)` — handles both `"conversation"` and `"ai_task_data"` subentry types.

Registered via:
```python
@classmethod
@callback
def async_get_supported_subentry_types(cls, config_entry):
    return {
        "conversation": GenericConversationSubentryFlowHandler,
        "ai_task_data": GenericConversationSubentryFlowHandler,
    }
```

**Init step:**
- `name`: Text input (only shown for new subentries)
- `prompt`: Template selector (conversation subentries only)
- `llm_hass_api`: Multi-select for LLM API selection (conversation subentries only)
- `recommended`: Boolean toggle — if checked, create/update with recommended defaults and skip advanced step

**Advanced step** (if recommended unchecked):
- `chat_model`: Text input with suggestions (attempt to fetch model list from endpoint; if fails, show empty suggestions)
- `max_tokens`: Integer input (default 3000)
- `temperature`: Float input, range 0-2, step 0.05 (default 1.0)
- `top_p`: Float input, range 0-1, step 0.05 (default 1.0)

Model suggestion fetching:
```python
try:
    models = await client.models.list()
    suggestions = [m.id for m in models.data]
except Exception:
    suggestions = []
```

### `entity.py` — Base LLM Entity

#### Class: `GenericBaseLLMEntity(Entity)`

```python
class GenericBaseLLMEntity(Entity):
    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, entry: GenericConversationConfigEntry, subentry: ConfigSubentry):
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
```

#### Method: `_async_handle_chat_log()`

```python
async def _async_handle_chat_log(
    self,
    chat_log: conversation.ChatLog,
    structure_name: str | None = None,
    structure: vol.Schema | None = None,
    max_iterations: int = MAX_TOOL_ITERATIONS,
) -> None:
```

Processing steps:

1. **Extract system message** from `chat_log.content[0]` (must be `SystemContent`)

2. **Convert chat history** via `_convert_content_to_param(chat_log.content[1:])`

3. **Build model arguments:**
   ```python
   model_args = {
       "model": options.get(CONF_CHAT_MODEL, DEFAULT_CHAT_MODEL),
       "messages": messages,
       "max_tokens": options.get(CONF_MAX_TOKENS, DEFAULT_MAX_TOKENS),
       "temperature": options.get(CONF_TEMPERATURE, DEFAULT_TEMPERATURE),
       "top_p": options.get(CONF_TOP_P, DEFAULT_TOP_P),
       "stream": True,
       "user": chat_log.conversation_id,
   }
   ```

4. **Add tools** from `chat_log.llm_api` if available:
   ```python
   if chat_log.llm_api and chat_log.llm_api.tools:
       model_args["tools"] = [
           _format_tool(tool, chat_log.llm_api.custom_serializer)
           for tool in chat_log.llm_api.tools
       ]
   ```

5. **Add structured output** if `structure` provided:
   ```python
   if structure and structure_name:
       model_args["response_format"] = {
           "type": "json_schema",
           "json_schema": {
               "name": slugify(structure_name),
               "schema": _format_structured_output(structure, chat_log.llm_api),
           },
       }
   ```

6. **Handle image attachments** on last user message:
   ```python
   if last_content.role == "user" and last_content.attachments:
       files = await async_prepare_files_for_prompt(
           self.hass,
           [(a.path, a.mime_type) for a in last_content.attachments],
       )
       last_message["content"] = [
           {"type": "text", "text": last_message["content"]},
           *files,
       ]
   ```

7. **Add stream_options** (best-effort token tracking):
   ```python
   model_args["stream_options"] = {"include_usage": True}
   ```
   If the endpoint doesn't support this, it will either ignore it or the final chunk won't include usage — both are fine.

8. **Streaming tool loop:**
   ```python
   for _iteration in range(max_iterations):
       response = await client.chat.completions.create(**model_args)
       messages.extend(
           _convert_content_to_param([
               content
               async for content in chat_log.async_add_delta_content_stream(
                   self.entity_id,
                   _transform_stream(chat_log, response),
               )
           ])
       )
       if not chat_log.unresponded_tool_results:
           break
   ```

9. **Error handling:**
   - `openai.AuthenticationError` → trigger reauth, raise `HomeAssistantError`
   - `openai.RateLimitError` → raise `HomeAssistantError` with rate limit message
   - `openai.APIConnectionError` → raise `HomeAssistantError` indicating unreachable
   - `openai.APIError` → log and raise `HomeAssistantError`

#### Function: `_transform_stream()`

```python
async def _transform_stream(
    chat_log: conversation.ChatLog,
    stream: AsyncStream[ChatCompletionChunk],
) -> AsyncGenerator[
    conversation.AssistantContentDeltaDict | conversation.ToolResultContentDeltaDict
]:
```

Processes Chat Completions streaming chunks:

1. **Track state:** `current_tool_calls: dict[int, dict]` keyed by tool call index
2. **For each chunk:**
   - If `delta.role == "assistant"` → yield `{"role": "assistant"}`
   - If `delta.content` is not None → yield `{"content": delta.content}`
   - If `delta.tool_calls` present:
     - For each tool call delta, accumulate `id`, `function.name`, `function.arguments` by index
   - If `chunk.usage` present (when endpoint supports `stream_options`):
     - Trace token stats to `chat_log.async_trace()`
3. **On stream end:** yield any accumulated complete tool calls:
   ```python
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
   ```

**Tool call accumulation detail:** Chat Completions streams tool calls incrementally:
- First chunk for a tool call: `index=0, id="call_xyz", function={"name": "HassTurnOn", "arguments": ""}`
- Subsequent chunks: `index=0, function={"arguments": "{\"entity"}`
- More chunks: `index=0, function={"arguments": "_id\": \"lig"}`
- Each chunk appends to `current_tool_calls[index]["function"]["arguments"]`

When `finish_reason == "tool_calls"`, all accumulated tool calls are yielded.

#### Function: `_convert_content_to_param()`

```python
def _convert_content_to_param(
    chat_content: Iterable[conversation.Content],
) -> list[ChatCompletionMessageParam]:
```

Conversion mapping:

| HA Content | Chat Completions Message |
|---|---|
| `SystemContent` | `{"role": "system", "content": text}` |
| `UserContent` (text only) | `{"role": "user", "content": text}` |
| `UserContent` (with images) | `{"role": "user", "content": [{"type": "text", ...}, {"type": "image_url", ...}]}` |
| `AssistantContent` (text) | `{"role": "assistant", "content": text}` |
| `AssistantContent` (tool calls) | `{"role": "assistant", "content": text, "tool_calls": [...]}` |
| `ToolResultContent` | `{"role": "tool", "tool_call_id": id, "content": json_dumps(result)}` |

For assistant messages with tool calls, format each tool call as:
```python
{
    "id": tool_call.id,
    "type": "function",
    "function": {
        "name": tool_call.tool_name,
        "arguments": json.dumps(tool_call.tool_args),
    },
}
```

#### Function: `_format_tool()`

```python
def _format_tool(
    tool: llm.Tool,
    custom_serializer: Callable | None = None,
) -> ChatCompletionToolParam:
    return ChatCompletionToolParam(
        type="function",
        function=FunctionDefinition(
            name=tool.name,
            description=tool.description or "",
            parameters=convert(tool.parameters, custom_serializer=custom_serializer),
        ),
    )
```

Uses the `convert` function from `homeassistant.helpers.llm` to convert `vol.Schema` to OpenAI-compatible JSON Schema. This is the same converter used by the official openai_conversation integration.

#### Function: `async_prepare_files_for_prompt()`

```python
async def async_prepare_files_for_prompt(
    hass: HomeAssistant,
    files: list[tuple[Path, str | None]],
) -> list[dict]:
```

For each file:
1. Validate file exists
2. Auto-detect MIME type if not provided
3. Only accept `image/*` types
4. Base64 encode file bytes
5. Return as:
   ```python
   {
       "type": "image_url",
       "image_url": {
           "url": f"data:{mime_type};base64,{base64_data}",
           "detail": "auto",
       },
   }
   ```

#### Function: `_format_structured_output()`

```python
def _format_structured_output(
    structure: vol.Schema,
    llm_api: llm.APIInstance | None,
) -> dict:
```

Converts a `vol.Schema` (HA's selector-based schema) to a JSON Schema object suitable for Chat Completions `response_format.json_schema.schema`. Uses `convert` from HA's OpenAI schema converter.

### `conversation.py` — Conversation Platform

```python
class GenericConversationEntity(
    conversation.ConversationEntity,
    conversation.AbstractConversationAgent,
    GenericBaseLLMEntity,
):
    _attr_supports_streaming = True
    _attr_translation_key = "conversation"

    def __init__(self, entry, subentry):
        super().__init__(entry, subentry)
        if self.subentry.data.get(CONF_LLM_HASS_API):
            self._attr_supported_features = (
                conversation.ConversationEntityFeature.CONTROL
            )

    @property
    def supported_languages(self) -> Literal["*"]:
        return MATCH_ALL

    async def async_added_to_hass(self):
        conversation.async_set_agent(self.hass, self)
        await super().async_added_to_hass()

    async def async_will_remove_from_hass(self):
        conversation.async_unset_agent(self.hass, self)
        await super().async_will_remove_from_hass()

    async def _async_handle_message(self, user_input, chat_log):
        await chat_log.async_provide_llm_data(
            user_input.as_llm_context(DOMAIN),
            self.subentry.data.get(CONF_LLM_HASS_API),
            self.subentry.data.get(CONF_PROMPT),
            user_input.extra_system_prompt,
        )
        await self._async_handle_chat_log(chat_log)
        return conversation.async_get_result_from_chat_log(user_input, chat_log)
```

**Platform setup function:**
```python
async def async_setup_entry(hass, config_entry, async_add_entities):
    entities = []
    for subentry in config_entry.subentries.values():
        if subentry.subentry_type == "conversation":
            entities.append(GenericConversationEntity(config_entry, subentry))
    async_add_entities(entities)
```

### `ai_task.py` — AI Task Platform

```python
class GenericTaskEntity(
    ai_task.AITaskEntity,
    GenericBaseLLMEntity,
):
    _attr_supported_features = (
        ai_task.AITaskEntityFeature.GENERATE_DATA
        | ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS
    )
    _attr_translation_key = "ai_task_data"

    async def _async_generate_data(self, task, chat_log):
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
            LOGGER.error("Failed to parse JSON response: %s. Response: %s", err, text)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="json_parse_error",
            ) from err

        return ai_task.GenDataTaskResult(
            conversation_id=chat_log.conversation_id,
            data=data,
        )
```

**Platform setup function:**
```python
async def async_setup_entry(hass, config_entry, async_add_entities):
    entities = []
    for subentry in config_entry.subentries.values():
        if subentry.subentry_type == "ai_task_data":
            entities.append(GenericTaskEntity(config_entry, subentry))
    async_add_entities(entities)
```

## Packaging

### `manifest.json`

```json
{
  "domain": "generic_conversation",
  "name": "Generic Conversation",
  "codeowners": [],
  "dependencies": ["conversation"],
  "documentation": "https://github.com/geryduyck/generic-conversation",
  "integration_type": "service",
  "iot_class": "cloud_polling",
  "requirements": ["openai>=1.0.0"],
  "version": "1.0.0"
}
```

### `hacs.json` (repository root)

```json
{
  "name": "Generic Conversation",
  "content_in_root": false,
  "homeassistant": "2025.7.0",
  "hacs": "1.34.0"
}
```

### `strings.json` — UI Text

Covers:
- **Config flow:** step titles/descriptions for `user`, `reauth_confirm`
- **Subentry flow:** step titles/descriptions for `init`, `advanced`
- **Field labels:** `api_key`, `base_url`, `chat_model`, `max_tokens`, `temperature`, `top_p`, `prompt`, `llm_hass_api`, `recommended`
- **Errors:** `cannot_connect`, `invalid_auth`, `unknown`
- **Entity translations:** `conversation`, `ai_task_data`
- **Exception messages:** `response_not_found`, `json_parse_error`

### `icons.json`

```json
{
  "services": {
    "conversation": { "service": "mdi:chat-processing" },
    "ai_task_data": { "service": "mdi:creation" }
  }
}
```

## Graceful Degradation

Since this targets any OpenAI-compatible endpoint, several features may not be available:

| Feature | Graceful Behavior |
|---|---|
| `GET /models` not supported | Config flow skips model suggestions; text input still works |
| Tools not supported by endpoint | `_async_handle_chat_log` sends request without tools; tool loop completes in 1 iteration |
| `response_format` not supported | AI task falls back gracefully — endpoint returns unstructured text, JSON parsing may fail with helpful error |
| `stream: true` not supported | This is a hard requirement; endpoints that don't support streaming will fail. Streaming is essential for the HA chat_log delta pattern. |
| Image input not supported | Endpoint returns an error; surfaced as `HomeAssistantError` |
| `stream_options` not supported | Token usage tracking silently skipped |

## What Is NOT In Scope (v1)

- No vendor-specific tools (web search, code interpreter, image generation)
- No reasoning/thinking model support (o-series, extended thinking)
- No prompt caching configuration
- No service tier selection
- No coordinator or model list polling
- No diagnostics module
- No repair flows
- No migration system (v1 has nothing to migrate from)
- No STT/TTS platforms
- No PDF attachment support
- No `generate_image` AI task support

## Testing Strategy

All tests mock the `AsyncOpenAI` client. No real API calls.

### Config Flow Tests
- Happy path: API key + base_url → entry created with 2 default subentries
- No API key (local server): base_url only → entry created
- Auth error: invalid API key → `invalid_auth` error shown
- Connection error: unreachable endpoint → `cannot_connect` error shown
- Model list failure: endpoint doesn't support `GET /models` → proceeds anyway
- Subentry creation: both conversation and ai_task_data types
- Subentry editing: change model, temperature, prompt
- Reauth flow: re-enter API key

### Entity Setup Tests
- Entities created from subentries
- Client initialized correctly
- Device info populated
- Entity unique_id matches subentry_id

### Conversation Tests
- Simple text response (no tools)
- Streaming text response
- Tool calling: single tool call → tool result → final response
- Tool calling: multiple iterations
- Tool calling: max iterations reached
- Image attachment in user message
- Error: authentication failure triggers reauth
- Error: connection error surfaces user-friendly message
- Error: content filter / max tokens

### AI Task Tests
- Plain text generation (no structure)
- Structured data generation with JSON schema
- JSON parse error handling
- Attachment support
- High iteration count (1000 max)
