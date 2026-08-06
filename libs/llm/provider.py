import logging
import time

from openai import OpenAI

from config import settings

logger = logging.getLogger("blog_gen.llm")


class LLMError(RuntimeError):
    pass


class LLMProvider:
    """OpenAI-compatible client. Works with OpenAI, NVIDIA NIM, Ollama/vLLM."""

    def __init__(self, api_key, base_url, model):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.client = OpenAI(
            api_key=api_key or "sk-none",
            base_url=base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )

    def complete(self, system, user, temperature=0.85, max_tokens=4096):
        start = time.perf_counter()
        logger.info(
            "llm call start model=%s base=%s max_tokens=%s temperature=%s",
            self.model,
            self.base_url,
            max_tokens,
            temperature,
        )
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:
            elapsed = round(time.perf_counter() - start, 1)
            logger.error("llm call FAILED after %.1fs: %s: %s", elapsed, type(e).__name__, e)
            raise LLMError(f"LLM call failed after {elapsed}s ({type(e).__name__}): {e}") from e

        elapsed = round(time.perf_counter() - start, 1)
        content = resp.choices[0].message.content
        usage = resp.usage
        logger.info(
            "llm call done in %.1fs model=%s finish=%s prompt_tokens=%s completion_tokens=%s",
            elapsed,
            self.model,
            resp.choices[0].finish_reason,
            getattr(usage, "prompt_tokens", None),
            getattr(usage, "completion_tokens", None),
        )
        if not content:
            raise LLMError("LLM returned empty response")
        return content.strip()


def complete_with_failover(system, user, temperature=0.85, max_tokens=2000):
    """Try each provider in the priority chain until one succeeds.

    Each provider gets `LLM_TIMEOUT_SECONDS` before it is abandoned and the
    next one is tried. Raises LLMError if all providers fail.
    """
    from libs.llm import get_llm_chain

    chain = get_llm_chain()
    errors = []
    for name, provider in chain:
        try:
            return provider.complete(system, user, temperature=temperature, max_tokens=max_tokens)
        except LLMError as e:
            errors.append(f"{name}: {e}")
            logger.warning("provider %s failed, trying next: %s", name, e)
    raise LLMError("all LLM providers failed: " + " | ".join(errors))
