# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Home Assistant custom integration (`generic_conversation`) that provides a **generic AI conversation agent** using any **OpenAI-compatible API endpoint**. Unlike the official `openai_conversation` or `anthropic` integrations which are vendor-locked, this integration allows users to point at any compatible endpoint (e.g., local LLM servers like Ollama, LM Studio, vLLM, text-generation-webui, or third-party providers).

The integration is modeled after two reference implementations:
- **ha-openai** (`openai_conversation`): The OpenAI integration from HA core — our primary structural reference since we target OpenAI-compatible APIs.
- **ha-anthropic** (`anthropic`): The Anthropic integration from HA core — used as a secondary reference for patterns and architecture.

Both reference repos are available as sibling directories (`../ha-openai`, `../ha-anthropic`) for consultation.

## Architecture

This integration follows the standard Home Assistant custom component pattern with a **subentry-based multi-entity architecture**:

### Core Files

| File | Purpose |
|---|---|
| `manifest.json` | Integration metadata: domain, dependencies, requirements |
| `const.py` | Configuration keys, default values, model constants |
| `__init__.py` | Entry setup, client initialization, platform forwarding, migrations |
| `config_flow.py` | Multi-step configuration UI (API key + base URL, then subentry options) |
| `entity.py` | **Core logic** — base LLM entity with message conversion, streaming, tool loop |
| `conversation.py` | Conversation agent platform (thin wrapper around entity.py) |
| `ai_task.py` | AI task platform for structured data generation |
| `strings.json` | All UI-facing text and localization |

### Key Architectural Patterns

**Subentry Pattern**: A single config entry holds the API key + base URL. Users create multiple subentries (conversation agents, AI task entities) each with their own model/temperature/prompt settings. This mirrors how both reference integrations work in HA 2025.x+.

**Entity Hierarchy**: `entity.py` contains the base class (e.g., `GenericBaseLLMEntity`) that handles:
- Converting HA `ChatLog` content to OpenAI API message format (`_convert_content_to_param`)
- Streaming response transformation (`_transform_stream`) — async generator converting API stream events to HA `ChatLogDelta` events
- Tool call iteration loop (max 10 rounds to prevent infinite loops)
- File attachment encoding (images, PDFs as base64)

`conversation.py` and `ai_task.py` are thin platform wrappers that inherit from the base entity.

**Config Flow**: Multi-step with dynamic options:
1. User step: API key + **base URL** (the key differentiator from vendor-specific integrations)
2. Init step: Name, recommended settings toggle, LLM API selection
3. Advanced step: Model selection, temperature, top_p
4. Model step: Max tokens, and any model-specific options supported by the endpoint

**Client Initialization**: Uses the `openai` Python SDK's `AsyncOpenAI` with a custom `base_url` parameter to point at any compatible endpoint. The HA httpx client is used for proxy support.

**Streaming**: All inference calls use streaming (`client.responses.create` or `client.chat.completions.create` with `stream=True`). The `_transform_stream` async generator in `entity.py` is the most complex piece of code — it maps API-specific stream events into HA's internal format.

### Differences from Reference Integrations

- **base_url** is a first-class config option (not present in vendor integrations)
- Vendor-specific features (Anthropic's extended thinking, prompt caching; OpenAI's DALL-E, code interpreter) should be **omitted or made optional** — focus on the common OpenAI-compatible subset
- Model list may not be fetchable via API (many local servers don't support `GET /models`) — config flow should allow manual model name entry
- No coordinator for model list polling unless the endpoint supports it

## HA Platform Patterns

These are the canonical patterns from HA core that this integration must follow.

### Conversation Entity

Ref: [HA Conversation Entity Docs](https://developers.home-assistant.io/docs/core/entity/conversation)

```python
class MyConversationEntity(conversation.ConversationEntity):
    """Conversation agent entity."""

    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
    ) -> None:
        """Handle a message."""
        await chat_log.async_provide_llm_data(
            user_input.as_llm_context(DOMAIN),
            self.entry.options.get(CONF_LLM_HASS_API),
            self.entry.options.get(CONF_PROMPT),
            user_input.extra_system_prompt,
        )
        tools = [_format_tool(tool) for tool in chat_log.llm_api.tools] if chat_log.llm_api else []

        # Tool call loop — max 10 iterations to prevent infinite loops
        for _iteration in range(10):
            response = ...  # Send to LLM with streaming
            messages.extend([
                ...async for content in chat_log.async_add_delta_content_stream(
                    user_input.agent_id, _transform_stream(response)
                )
            ])
            if not chat_log.unresponded_tool_results:
                break
```

### AI Task Entity

Ref: [HA AI Task Entity Docs](https://developers.home-assistant.io/docs/core/entity/ai-task)

```python
class MyAITaskEntity(AITaskEntity):
    """AI task entity for structured data generation."""

    async def _async_generate_data(
        self, task: GenDataTask, chat_log: ChatLog
    ) -> GenDataTaskResult:
        """Generate data from a task."""
        # Process task, call LLM, return structured result
        return GenDataTaskResult(
            conversation_id=chat_log.conversation_id,
            data=data,
        )
```

### LLM API & Tool Integration

Ref: [HA LLM API Docs](https://developers.home-assistant.io/docs/core/llm)

Custom LLM APIs can be registered to expose tools to the conversation agent:

```python
class MyAPI(llm.API):
    """Custom LLM API."""

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        return llm.APIInstance(
            api=self,
            api_prompt="Instructions for the LLM on how to use these tools",
            llm_context=llm_context,
            tools=[...],
        )

# Register during entry setup, unregister on unload
unreg = llm.async_register_api(hass, MyAPI(hass, f"key-{entry.entry_id}", entry.title))
entry.async_on_unload(unreg)
```

Tool schemas from HA are `vol.Schema` based. Convert to OpenAI function-calling format:
```python
def _format_tool(tool: llm.Tool) -> dict:
    """Format an HA LLM tool into OpenAI function-calling format."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": convert_to_openai_schema(tool.parameters),
        },
    }
```

### Runtime Data Pattern

Ref: [HA Integration Setup Docs](https://developers.home-assistant.io/docs/config_entries_index)

```python
type MyConfigEntry = ConfigEntry[MyData]

@dataclass
class MyData:
    client: AsyncOpenAI
    # ... other runtime state

async def async_setup_entry(hass: HomeAssistant, entry: MyConfigEntry) -> bool:
    """Set up integration from a config entry."""
    client = AsyncOpenAI(api_key=entry.data[CONF_API_KEY], base_url=entry.data[CONF_BASE_URL])
    entry.runtime_data = MyData(client=client)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True
```

### Config Flow Best Practices

Ref: [HA Config Flow Docs](https://developers.home-assistant.io/docs/config_entries_config_flow_handler)

- Use `async_set_unique_id` + `_abort_if_unique_id_configured` to prevent duplicate entries
- Validate credentials during the user step (test the API connection before creating the entry)
- Use `self.async_show_progress` / `self.async_show_progress_done` for long-running operations
- Strings go in `strings.json`, not hardcoded — HA auto-generates translations
- Options flow handler for post-setup configuration changes
- Subentry flows for creating multiple agents under a single config entry

### Manifest Best Practices

Ref: [HA Manifest Docs](https://developers.home-assistant.io/docs/creating_integration_manifest)

```json
{
  "domain": "generic_conversation",
  "name": "Generic Conversation",
  "codeowners": ["@username"],
  "dependencies": [],
  "documentation": "https://github.com/user/generic-conversation",
  "integration_type": "service",
  "iot_class": "cloud_polling",
  "requirements": ["openai>=1.0.0"],
  "version": "1.0.0"
}
```

Required fields: `domain`, `name`, `codeowners`, `documentation`, `integration_type`, `iot_class`, `requirements`. The `version` field is required for custom integrations (HACS).

### Diagnostics

Ref: [HA Diagnostics Docs](https://developers.home-assistant.io/docs/core/integration-diagnostics)

```python
TO_REDACT = {CONF_API_KEY}

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return {
        "entry_data": async_redact_data(entry.data, TO_REDACT),
        "options": async_redact_data(entry.options, TO_REDACT),
    }
```

Always redact sensitive data (API keys, tokens) using `async_redact_data`.

## Quality Scale

Ref: [HA Integration Quality Scale](https://developers.home-assistant.io/docs/integration_quality_scale_index)

HA core integrations are rated Bronze/Silver/Gold/Platinum. While custom integrations aren't formally rated, following these tiers provides a roadmap for quality:

- **Bronze** (minimum): config flow, unique IDs, `async_unload_entry`, basic test coverage
- **Silver**: diagnostics, entity descriptions, reconfigure flow, stale data handling
- **Gold**: repair issues, dynamic device/entity removal, entity translations
- **Platinum**: full test coverage, strict typing, quality_scale.yaml in manifest

Track progress with a `quality_scale.yaml`:
```yaml
rules:
  config_flow: done
  unique_config_entry: done
  test_before_configure: done
  diagnostics:
    status: todo
    comment: "Needs implementation"
```

## Development

### Prerequisites

- Home Assistant development environment (Python 3.13+)
- The `openai` Python SDK is the primary dependency

### Testing

Ref: [HA Testing Docs](https://developers.home-assistant.io/docs/development_testing)

This integration should be testable using Home Assistant's standard testing approach:
```bash
# Run tests from HA core dev environment
pytest tests/components/generic_conversation/ -xvs

# Run a single test
pytest tests/components/generic_conversation/test_conversation.py::test_default_prompt -xvs
```

**HA Testing Patterns:**
- Use `pytest` with HA fixtures (`hass`, `mock_config_entry`, `aioclient_mock`)
- Snapshot assertions with `syrupy` for config flow tests:
  ```python
  async def test_full_flow(hass, mock_setup_entry, snapshot: SnapshotAssertion):
      result = await hass.config_entries.flow.async_init(
          DOMAIN, context={"source": SOURCE_USER}
      )
      assert result["type"] is FlowResultType.FORM
      # ... step through flow ...
      assert result == snapshot
  ```
- Update snapshots: `pytest tests/components/generic_conversation/ --snapshot-update`
- Config flow tests should cover: happy path, error handling (auth failures, connection errors), and options flow
- Mock external API calls — never hit real endpoints in tests

### Linting & Type Checking

```bash
# Ruff for linting/formatting (HA standard)
ruff check .
ruff format .

# MyPy for type checking
mypy .
```

### Installation for Manual Testing

Copy/symlink the integration directory into `custom_components/generic_conversation/` within a Home Assistant config directory, then restart HA.

## HACS Deployment

Ref: [HACS Publishing Docs](https://hacs.xyz/docs/publish/integration)

### Repository Structure

HACS expects this layout:
```
repository_root/
├── custom_components/
│   └── generic_conversation/
│       ├── __init__.py
│       ├── manifest.json
│       ├── config_flow.py
│       ├── entity.py
│       ├── conversation.py
│       ├── ai_task.py
│       ├── const.py
│       ├── strings.json
│       └── ...
├── hacs.json
├── README.md
└── .github/
    └── workflows/
        └── validate.yml
```

### hacs.json

```json
{
  "name": "Generic Conversation",
  "content_in_root": false,
  "homeassistant": "2025.1.0",
  "hacs": "1.34.0"
}
```

- `content_in_root`: `false` because integration files live in `custom_components/generic_conversation/`
- `homeassistant`: minimum HA version required
- `hacs`: minimum HACS version required

### GitHub Actions Validation

Add `.github/workflows/validate.yml` to run HACS and hassfest validation on every push/PR:

```yaml
name: Validate
on:
  push:
  pull_request:

jobs:
  validate-hacs:
    runs-on: "ubuntu-latest"
    steps:
      - uses: "actions/checkout@v4"
      - name: HACS validation
        uses: "hacs/action@main"
        with:
          category: "integration"

  validate-hassfest:
    runs-on: "ubuntu-latest"
    steps:
      - uses: "actions/checkout@v4"
      - uses: "home-assistant/actions/hassfest@master"
```

### HACS Publishing Requirements

1. **GitHub repository** must be public
2. **`manifest.json`** must include `version` field
3. **`hacs.json`** at repository root
4. **GitHub releases** with semantic versioning tags (e.g., `v1.0.0`) — HACS uses these for updates
5. **Brand assets** (optional but recommended): submit `icon.png` (256x256) and `logo.png` (256x128) to the [brands repository](https://github.com/home-assistant/brands)
6. **Default repository**: submit a PR to the [HACS default repository](https://github.com/hacs/default) to be listed in the HACS store
7. **My Home Assistant** deep links for easy installation — add a badge to README:
   ```markdown
   [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=OWNER&repository=REPO&category=integration)
   ```

## Key Design Decisions

- **Use the `openai` SDK, not raw HTTP**: The SDK handles auth, retries, streaming, and type safety. Set `base_url` to point at any compatible endpoint.
- **OpenAI Responses API vs Chat Completions API**: The ha-openai reference uses the newer Responses API (`client.responses.create`). For maximum compatibility with third-party endpoints, prefer the **Chat Completions API** (`client.chat.completions.create`) as it is more widely supported.
- **Graceful degradation**: Not all endpoints support tools/function calling, streaming, or file attachments. The integration should handle missing capabilities without crashing.
- **Minimal vendor-specific features**: Keep the integration focused on the common OpenAI-compatible subset. Features like web search, code interpreter, or image generation should only be added if they use standardized API patterns.

## Reference Documentation

- [HA Developer Docs — Creating an Integration](https://developers.home-assistant.io/docs/creating_component_index)
- [HA Developer Docs — Config Flow](https://developers.home-assistant.io/docs/config_entries_config_flow_handler)
- [HA Developer Docs — Conversation Entity](https://developers.home-assistant.io/docs/core/entity/conversation)
- [HA Developer Docs — AI Task Entity](https://developers.home-assistant.io/docs/core/entity/ai-task)
- [HA Developer Docs — LLM API](https://developers.home-assistant.io/docs/core/llm)
- [HA Developer Docs — Integration Manifest](https://developers.home-assistant.io/docs/creating_integration_manifest)
- [HA Developer Docs — Diagnostics](https://developers.home-assistant.io/docs/core/integration-diagnostics)
- [HA Developer Docs — Quality Scale](https://developers.home-assistant.io/docs/integration_quality_scale_index)
- [HA Developer Docs — Testing](https://developers.home-assistant.io/docs/development_testing)
- [HACS — Publishing an Integration](https://hacs.xyz/docs/publish/integration)
- [HACS — hacs.json Manifest](https://hacs.xyz/docs/publish/configuration)
- [HACS — GitHub Action Validation](https://hacs.xyz/docs/publish/action)
- [Home Assistant Brands Repository](https://github.com/home-assistant/brands)
- [HACS Default Repository](https://github.com/hacs/default)
