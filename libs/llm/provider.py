import logging
import time

from openai import OpenAI, RateLimitError

from config import settings

logger = logging.getLogger("blog_gen.llm")


class LLMError(RuntimeError):
    pass


def _retry_after_seconds(err, attempt):
    """Seconds to wait before retrying a rate-limited call.

    Prefers the server's Retry-After header; falls back to exponential backoff
    with a small cap so the pipeline never stalls forever.
    """
    try:
        resp = getattr(err, "response", None)
        headers = getattr(resp, "headers", None) or {}
        raw = headers.get("retry-after") or headers.get("Retry-After")
        if raw:
            try:
                return max(1.0, min(float(raw), 60.0))
            except (TypeError, ValueError):
                pass
    except Exception:  # noqa: BLE001 - best effort
        pass
    return min(2 ** attempt, 15.0)


class LLMProvider:
    """OpenAI-compatible client. Works with OpenAI, NVIDIA NIM, Ollama/vLLM."""

    def __init__(self, api_key, base_url, model, timeout=None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout or settings.llm_timeout_seconds
        self.client = OpenAI(
            api_key=api_key or "sk-none",
            base_url=base_url,
            timeout=self.timeout,
            max_retries=settings.llm_max_retries,
        )

    def complete(self, system, user, temperature=0.85, max_tokens=2000):
        start = time.perf_counter()
        logger.info(
            "llm call start model=%s base=%s max_tokens=%s temperature=%s timeout=%s",
            self.model,
            self.base_url,
            max_tokens,
            temperature,
            self.timeout,
        )
        max_attempts = max(1, settings.llm_rate_limit_retries + 1)
        resp = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=self.timeout,
                )
                break
            except RateLimitError as e:
                if attempt >= max_attempts:
                    elapsed = round(time.perf_counter() - start, 1)
                    logger.error(
                        "llm rate limited after %d attempts (%.1fs): %s",
                        max_attempts,
                        elapsed,
                        e,
                    )
                    raise LLMError(
                        "LLM provider is rate limited. Wait ~60s and try again "
                        f"({type(e).__name__}: {e})"
                    ) from e
                wait = _retry_after_seconds(e, attempt)
                logger.warning(
                    "llm rate limited (attempt %d/%d), retrying in %.1fs: %s",
                    attempt,
                    max_attempts,
                    wait,
                    e,
                )
                time.sleep(wait)
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

    Each provider gets its own timeout before it is abandoned and the next one
    is tried. Raises LLMError if all providers fail.
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
