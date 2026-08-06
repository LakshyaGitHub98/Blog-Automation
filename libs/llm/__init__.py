from config import settings
from libs.llm.provider import LLMError, LLMProvider

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"

_BUILDERS = {
    "groq": lambda: LLMProvider(
        settings.groq_api_key, GROQ_BASE_URL, settings.groq_model
    ),
    "nvidia": lambda: LLMProvider(
        settings.nvidia_api_key,
        NVIDIA_BASE_URL,
        settings.nvidia_model,
        timeout=settings.nvidia_timeout_seconds,
    ),
    "openai": lambda: LLMProvider(
        settings.openai_api_key, OPENAI_BASE_URL, settings.llm_model
    ),
    "local": lambda: LLMProvider(
        "sk-local", settings.local_base_url, settings.local_model
    ),
}


def _build(name):
    if name not in _BUILDERS:
        raise LLMError(f"unknown LLM_PROVIDER: {name}")
    provider = _BUILDERS[name]()
    if not provider.api_key:
        raise LLMError(f"{name}: API key not set")
    return provider


def get_llm():
    """Single provider, for backward compatibility (first in priority chain)."""
    return get_llm_chain()[0]


def get_llm_chain():
    """Build the ordered list of provider instances from LLM_PROVIDER_PRIORITY,
    skipping any that aren't configured (missing key)."""
    chain = []
    for name in settings.llm_provider_priority:
        try:
            chain.append((name, _build(name)))
        except LLMError as e:
            continue
    if not chain:
        raise LLMError(
            "no LLM provider configured. Set GROQ_API_KEY, NVIDIA_API_KEY, "
            "OPENAI_API_KEY, or configure a local provider."
        )
    return chain


__all__ = ["LLMProvider", "LLMError", "get_llm", "get_llm_chain"]