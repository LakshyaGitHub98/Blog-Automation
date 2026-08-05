from config import settings
from libs.llm.provider import LLMError, LLMProvider

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


def get_llm():
    s = settings
    if s.llm_provider == "nvidia":
        if not s.nvidia_api_key:
            raise LLMError("NVIDIA_API_KEY not set (get one at https://build.nvidia.com)")
        return LLMProvider(s.nvidia_api_key, NVIDIA_BASE_URL, s.llm_model)
    if s.llm_provider == "openai":
        if not s.openai_api_key:
            raise LLMError("OPENAI_API_KEY not set")
        return LLMProvider(s.openai_api_key, "https://api.openai.com/v1", s.llm_model)
    if s.llm_provider == "local":
        return LLMProvider("sk-local", s.local_base_url, s.local_model)
    raise LLMError(f"unknown LLM_PROVIDER: {s.llm_provider}")


__all__ = ["LLMProvider", "LLMError", "get_llm"]
