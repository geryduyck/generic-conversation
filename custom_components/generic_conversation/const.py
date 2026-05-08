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

MAX_TOOL_ITERATIONS = 10
