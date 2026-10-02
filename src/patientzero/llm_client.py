"""LLM client abstraction. Stance classification and atomization depend only
on the `complete(prompt) -> str` method, never on a specific provider SDK, so
tests can inject FakeLLMClient with zero network or API-key requirements.

Real usage is Groq as the primary provider (fast, cheap) with OpenAI as an
automatic fallback when Groq fails: FallbackLLMClient wraps both behind the
same LLMClient protocol so every caller (atomizer, stance classifier,
pipeline) stays completely unaware of which provider actually answered.
"""
import os
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


# Sampling temperature for every real provider. Non-zero temperature made the
# atomizer reword the same input differently on each run ("...visible from
# space." vs "...visible from space with the naked eye."), which changed the
# claim text, which changed the SerpApi query, which changed the cache key —
# so an identical input was billed as a fresh set of searches every time.
# Deterministic decoding is what makes the content-addressed cache in spec
# sec 5 actually pay off, and it keeps stance labels stable between runs.
DEFAULT_TEMPERATURE = 0.0

# Hosted model names get decommissioned without notice — llama-3.3-70b-versatile
# stopped resolving mid-project and every LLM call began failing with a 404,
# which the pipeline correctly degraded into "no claims extracted". Both
# defaults are overridable by environment variable so the next retirement is a
# config change rather than a code change.
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


class GroqLLMClient:
    """Primary real implementation, backed by Groq. Requires the `groq`
    package (install with `pip install patientzero-core[llm]`).
    """

    def __init__(
        self,
        api_key: str,
        model: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
    ):
        import groq  # deferred import: only required when actually used

        self._client = groq.Groq(api_key=api_key)
        self._model = model or os.environ.get("GROQ_MODEL") or DEFAULT_GROQ_MODEL
        self._temperature = temperature

    def complete(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=1024,
                temperature=self._temperature,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise LLMClientError(f"Groq API call failed: {exc}") from exc
        return response.choices[0].message.content or ""


class OpenAILLMClient:
    """Fallback real implementation, backed by OpenAI. Requires the `openai`
    package (install with `pip install patientzero-core[llm]`).
    """

    def __init__(
        self,
        api_key: str,
        model: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
    ):
        import openai  # deferred import: only required when actually used

        self._client = openai.OpenAI(api_key=api_key)
        self._model = model or os.environ.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
        self._temperature = temperature

    def complete(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=1024,
                temperature=self._temperature,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise LLMClientError(f"OpenAI API call failed: {exc}") from exc
        return response.choices[0].message.content or ""


class FallbackLLMClient:
    """Tries `primary.complete()` first; if it raises LLMClientError, tries
    `fallback.complete()` instead. If the fallback ALSO raises, that error
    propagates uncaught — this is intentional, not a bug: the pipeline
    (spec sec 6) already degrades a claim to "skipped" on an uncaught
    LLMClientError, so letting a double failure propagate is the correct
    degrade-to-partial-results path, not a silent swallow.
    """

    def __init__(self, primary: LLMClient, fallback: LLMClient):
        self._primary = primary
        self._fallback = fallback

    def complete(self, prompt: str) -> str:
        try:
            return self._primary.complete(prompt)
        except LLMClientError:
            return self._fallback.complete(prompt)
