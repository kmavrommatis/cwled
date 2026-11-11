"""
LLM providers offered by CWLed and the environment variable each one reads its API key from.

The variable name is fixed by the provider, so the user does not need to know it:
the AI Assistant tab fills it in when a provider is chosen, and the value is
written to the `api_key_env` entry of the `llm` configuration.
"""

from typing import Optional

# provider name (as passed to LangChain's init_chat_model) -> API key variable, None if no key is needed
PROVIDER_API_KEY_ENV = {
    'google_genai': 'GOOGLE_API_KEY',
    'openai': 'OPENAI_API_KEY',
    'anthropic': 'ANTHROPIC_API_KEY',
    'openrouter': 'OPENROUTER_API_KEY',
    'ollama': None,
}


def defaultApiKeyEnv(provider: str) -> Optional[str]:
    """Return the API key variable name expected by the provider, or None if the provider needs no key."""
    return PROVIDER_API_KEY_ENV.get(provider)
