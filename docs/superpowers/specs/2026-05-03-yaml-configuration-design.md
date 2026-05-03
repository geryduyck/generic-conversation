# YAML Configuration Design

Replace the GUI config flow with pure YAML-based configuration for the `generic_conversation` integration.

## Motivation

The current config flow (GUI) with subentries is buggy and fragile. YAML configuration is more stable, version-controllable, and directly editable. Since this is a custom integration (not HA core), we are free to diverge from ADR-0010's preference for config-flow-only.

## YAML Structure

Configuration lives under `generic_conversation:` in `configuration.yaml`:

```yaml
generic_conversation:
  services:
    - name: "Local Ollama"
      base_url: "http://localhost:11434/v1"
      # api_key: optional, omitted for local endpoints
      agents:
        - type: conversation
          name: "Ollama Chat"
          model: "llama3"
          max_tokens: 3000        # optional, default: 3000
          temperature: 1.0        # optional, default: 1.0, range: 0-2
          top_p: 1.0              # optional, default: 1.0, range: 0-1
          system_prompt: "You are a helpful assistant."  # optional
          llm_hass_api:           # optional, conversation-only
            - assist

        - type: ai_task
          name: "Ollama Tasks"
          model: "llama3"
          max_tokens: 3000

    - name: "OpenAI Cloud"
      base_url: "https://api.openai.com/v1"
      api_key: !secret openai_api_key
      agents:
        - type: conversation
          name: "GPT-4o Chat"
          model: "gpt-4o"
          temperature: 0.7
```

### Schema Rules

- `services` is a required list with at least one entry.
- Each service requires `name` (unique across services) and `base_url`.
- `api_key` is optional (local endpoints like Ollama don't need it).
- `agents` is a required list with at least one entry per service.
- Each agent requires `type` (`conversation` or `ai_task`), `name` (unique within the service), and `model`.
- `system_prompt` and `llm_hass_api` are only valid on `conversation` type agents; rejected on `ai_task`. When `system_prompt` is omitted, defaults to `llm.DEFAULT_INSTRUCTIONS_PROMPT` (HA's built-in assistant prompt). When `llm_hass_api` is omitted, defaults to `["assist"]`.
- `max_tokens`, `temperature`, `top_p` are optional with defaults from `const.py`.
- Duplicate service names or duplicate agent names within a service are rejected at validation.

## Architecture

### Approach: Pure `async_setup` with `CONFIG_SCHEMA`

No config entries, no subentries, no config flow. The integration uses `async_setup(hass, config)` as its sole entry point. Entities are created directly from parsed YAML.

### Data Flow

```
configuration.yaml
    ↓ (HA parses YAML)
CONFIG_SCHEMA validates (voluptuous)
    ↓
async_setup(hass, config)
    ↓ for each service:
    Create AsyncOpenAI client, validate via models.list()
    Store in hass.data[DOMAIN][service_slug]
        ↓ for each agent:
        Call platform setup (conversation or ai_task)
        Create entity with (client, agent_config, device_info)
```

### Reload Flow

A `generic_conversation.reload` service is registered at setup time.

```
User calls generic_conversation.reload
    ↓
Re-read & validate YAML via async_integration_yaml_config()
    ↓
Tear down all existing entities (async_remove_entity for each)
Close existing OpenAI clients
Clear hass.data[DOMAIN]
    ↓
Re-run setup logic with new config
```

### Entity Identity

- Entity unique IDs: `slugify(service_name) + "_" + slugify(agent_name)`
- Stable across reloads as long as names don't change.
- Renaming an agent in YAML creates a new entity; the old one becomes unavailable.

### Device Registry

Devices are registered manually (no config entries to do it automatically):
- One device per service, identified by `(DOMAIN, slugify(service_name))`
- Device name matches service name
- Manufacturer: "Generic", model: service base_url, entry_type: SERVICE

## Module Changes

### `__init__.py` — Rewrite

- Remove `async_setup_entry()`, `async_unload_entry()`, `async_update_options()`
- Remove `GenericConversationConfigEntry` type alias
- Add `CONFIG_SCHEMA` (voluptuous schema matching the YAML structure above)
- Add `async_setup(hass, config)`:
  - Iterate services, create `openai.AsyncOpenAI` client per service
  - Validate connectivity via `models.list()` (log warning on failure, continue)
  - Store clients, config, and entity lists in `hass.data[DOMAIN]`
  - Register devices in device registry
  - For each agent, directly instantiate entities and add via platform helpers (`async_add_entities` callbacks stored during platform setup)
  - Register `generic_conversation.reload` service
- Add `async_reload(hass)`:
  - Re-read YAML via `async_integration_yaml_config(hass, DOMAIN)`
  - Remove all tracked entities via `entity_registry.async_remove()` using entity IDs stored in `hass.data[DOMAIN]`
  - Clear `hass.data[DOMAIN]`
  - Re-run setup logic with new config

### `entity.py` — Modify

- `GenericBaseLLMEntity.__init__()` takes `(hass, client, agent_config, device_info)` instead of `(entry, subentry)`
- `self.entry.runtime_data` becomes `self._client` (direct attribute)
- `self.subentry.data` becomes `self._config` (plain dict)
- All helper functions unchanged
- `_async_handle_chat_log()` unchanged except client access path

### `conversation.py` — Modify

- Replace `async_setup_entry()` with a setup function called from `__init__.py`
- Receives list of `(client, agent_config, device_info)` tuples for conversation agents
- Creates `GenericConversationEntity` instances and adds them via `async_add_entities`
- Entity constructor adapted to match new base entity signature
- `system_prompt` read from `agent_config` instead of subentry data

### `ai_task.py` — Modify

- Same pattern as conversation.py
- Receives list of `(client, agent_config, device_info)` tuples for ai_task agents
- No `system_prompt` or `llm_hass_api` handling

### `config_flow.py` — Delete

Entire file removed. No GUI configuration.

### `const.py` — Modify

- Remove `CONF_RECOMMENDED` (no recommended toggle in YAML)
- Add `CONF_SERVICES = "services"`, `CONF_AGENTS = "agents"`, `CONF_TYPE = "type"`, `CONF_NAME = "name"`, `CONF_SYSTEM_PROMPT = "system_prompt"`
- Keep all defaults unchanged

### `strings.json` — Simplify

Remove all `config` and `config_subentries` sections. Keep only `exceptions` section for runtime error translations.

### `manifest.json` — Modify

Remove `"config_flow": true` line.

## Error Handling

### Startup
- **Invalid YAML** — `CONFIG_SCHEMA` validation fails, integration doesn't load, HA logs validation error. Standard HA behavior.
- **API connection failure** — logged as warning, service still created. Entities created but will error on first use. Matches existing graceful degradation.
- **Auth failure on startup** — logged as error with message pointing to YAML config. User fixes YAML and calls reload service.

### Runtime
- **Auth error during chat** — raises `HomeAssistantError` with translation key. No reauth flow (was GUI-only). User fixes YAML and reloads.
- **Rate limit / connection errors** — same behavior as current implementation.

### Reload
- **YAML removed entirely** — all entities torn down, `hass.data[DOMAIN]` cleared.
- **Service removed** — its entities removed, others untouched.
- **Agent added/removed** — only affected service's entities rebuilt.
- **Validation failure on reload** — reload aborted, existing config preserved, error logged.

## What Stays Unchanged

- `_async_handle_chat_log()` core logic (streaming, tool-call loop, error handling)
- `_transform_stream()` async generator
- All helper functions: `_adjust_schema`, `_format_structured_output`, `_format_tool`, `_convert_content_to_param`, `async_prepare_files_for_prompt`
- Graceful degradation behaviors (tools, structured output, stream_options, models.list)
- `MAX_TOOL_ITERATIONS = 10`
- All default values for model parameters
