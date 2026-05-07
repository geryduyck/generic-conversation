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
