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
