# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Home Assistant custom integration (`generic_conversation`) that provides a conversation agent and AI task entity using any OpenAI-compatible API endpoint. Works with local endpoints (Ollama, LM Studio, vLLM) and cloud providers via the OpenAI Python SDK's Chat Completions API.

- **Domain:** `generic_conversation`
- **HA minimum:** 2025.7.0
- **Runtime dependency:** `openai>=1.0.0`
- **Installation:** HACS custom repository

## Development Commands

Tests require a Home Assistant development environment (pytest with HA fixtures). No standalone test runner works outside that environment.

```bash
# Lint
ruff check custom_components/generic_conversation
ruff format --check custom_components/generic_conversation

# Type check
mypy custom_components/generic_conversation

# Tests (requires HA dev env)
pytest tests/
pytest tests/test_config_flow.py          # single file
pytest tests/test_conversation.py -k "test_name"  # single test
```

## Architecture

All integration code lives in `custom_components/generic_conversation/`.

### Entry & Lifecycle (`__init__.py`)

- `async_setup_entry()` creates an `openai.AsyncOpenAI` client using the user's `base_url` and optional API key, validates connectivity via `models.list()`, and stores the client as `entry.runtime_data`.
- The config entry type alias `GenericConversationConfigEntry = ConfigEntry[openai.AsyncOpenAI]` carries the typed client.
- Two platforms are forwarded: `Platform.CONVERSATION` and `Platform.AI_TASK`.

### Subentry-Based Multi-Entity Pattern

The integration uses HA's **subentry** system. A single config entry (holding connection details) spawns two default subentries:
- `"conversation"` subentry -> `GenericConversationEntity` (conversation agent)
- `"ai_task_data"` subentry -> `GenericTaskEntity` (AI task entity)

Each subentry is independently configurable with its own model, temperature, max_tokens, system prompt, and LLM API selection.

### Base Entity (`entity.py`)

`GenericBaseLLMEntity` is the shared base class. Its `_async_handle_chat_log()` method implements the full Chat Completions interaction:
1. Converts HA `ChatLog` content to OpenAI message format
2. Attaches tools (from HA's LLM API) and structured output (JSON Schema via `response_format`) when available
3. Base64-encodes image attachments as data URLs
4. Runs a streaming tool-call loop (up to `MAX_TOOL_ITERATIONS=10`)
5. Handles auth errors (triggers reauth flow), rate limits, and connection errors

`_transform_stream()` is an async generator that converts OpenAI streaming chunks into HA's delta content format, accumulating streamed tool calls and emitting usage stats.

### Platform Wrappers

- **`conversation.py`** — `GenericConversationEntity` adds LLM context (user prompt, HA tools) and delegates to the base entity.
- **`ai_task.py`** — `GenericTaskEntity` adds structured output support (voluptuous schema -> JSON Schema) and parses JSON responses.

### Config Flow (`config_flow.py`)

Two-level flow: main entry (base_url + API key) and subentry flow (model parameters). Subentry flow has a "recommended" toggle that hides advanced options (model, tokens, temperature, top_p) behind defaults.

### Graceful Degradation

The integration silently degrades when the endpoint doesn't support certain features:
- `models.list()` fails -> falls back to text input for model selection
- Tools not supported -> skips tool calling
- Structured output not supported -> returns plain text
- `stream_options` not supported -> skips token tracking
