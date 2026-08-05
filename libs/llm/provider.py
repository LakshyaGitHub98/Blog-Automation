from openai import OpenAI


class LLMError(RuntimeError):
    pass


class LLMProvider:
    """OpenAI-compatible client. Works with OpenAI, NVIDIA NIM, Ollama/vLLM."""

    def __init__(self, api_key, base_url, model):
        self.model = model
        self.client = OpenAI(api_key=api_key or "sk-none", base_url=base_url)

    def complete(self, system, user, temperature=0.85, max_tokens=4096):
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = resp.choices[0].message.content
        if not content:
            raise LLMError("LLM returned empty response")
        return content.strip()
