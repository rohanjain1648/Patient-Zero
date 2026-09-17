"""LLM client abstraction. Stance classification (Task 9) and atomization
(Task 10) depend only on the `complete(prompt) -> str` method, never on a
specific provider SDK, so tests can inject FakeLLMClient with zero network
or API-key requirements.
"""
from typing import Protocol


class LLMClientError(Exception):
    pass


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str: ...


class FakeLLMClient:
    """Test double: returns pre-scripted responses in order."""

    def __init__(self, responses: list[str]):
        self._responses = list(responses)
        self.received_prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.received_prompts.append(prompt)
        if not self._responses:
            raise LLMClientError("FakeLLMClient exhausted: no more queued responses")
        return self._responses.pop(0)


class AnthropicLLMClient:
    """Real implementation backed by the Anthropic API. Requires the
    `anthropic` package (install with `pip install patientzero-core[anthropic]`).
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-5"):
        import anthropic  # deferred import: only required when actually used

        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def complete(self, prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            block.text for block in response.content if hasattr(block, "text")
        )
