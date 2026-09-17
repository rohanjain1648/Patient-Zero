# Patient Zero LLM Provider Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `patientzero-core`'s `AnthropicLLMClient` with a Groq-primary, OpenAI-fallback pair behind a new `FallbackLLMClient`, so every LLM call tries Groq first and automatically retries on OpenAI if Groq fails — with zero change to any module that consumes `LLMClient` (atomizer, stance classifier, pipeline).

**Architecture:** `GroqLLMClient` and `OpenAILLMClient` are two new real implementations of the existing `LLMClient` protocol (`complete(prompt: str) -> str`), each a thin wrapper around its provider's SDK with deferred imports, mirroring the shape `AnthropicLLMClient` already had. `FallbackLLMClient` composes any two `LLMClient`s: it calls the first, and on `LLMClientError` calls the second. Nothing downstream of `LLMClient` (atomizer.py, stance.py, pipeline.py) changes at all — they already depend only on the protocol, never on a concrete provider.

**Tech Stack:** Python ≥3.10 (unchanged). New dependencies `groq` and `openai`, both optional (installed via a `[llm]` extra), both imported lazily inside their client's `__init__` so the base `patientzero-core` install never requires either SDK.

**Spec:** [docs/superpowers/specs/2026-09-17-patient-zero-design.md](../specs/2026-09-17-patient-zero-design.md) — the spec names "LLM" generically wherever it discusses the Atomizer, Query Planner's stance batches, and Stance Classifier (spec §3, §4.4); it does not mandate a specific provider. This plan is a provider substitution requested directly, not a spec-driven requirement — the binding constraint carried forward is spec §6's "degrade to partial results rather than raising," which `FallbackLLMClient` must preserve exactly (raise `LLMClientError`, never swallow, when both providers fail).

## Global Constraints

- No verdict language ("true"/"false") anywhere in code, comments, or output field names (spec §1) — not touched by this change, but still binding on anything this task adds.
- Every real-provider client must raise `LLMClientError` on any underlying SDK failure, never let a provider-specific exception type escape — this is what lets `run_pipeline`'s existing `except (SerpApiError, LLMClientError)` guard keep working unchanged (spec §6).
- Real provider SDKs (`groq`, `openai`) must be imported lazily inside `__init__`, never at module level — the base package must remain installable and importable with neither SDK present, matching the precedent already set by the `AnthropicLLMClient` this plan removes.
- `FallbackLLMClient` must not swallow a failure when BOTH providers fail — it must let the second provider's `LLMClientError` propagate, so the pipeline's existing degrade-to-partial-results behavior (skip that claim, continue) still applies. Silently returning an empty string or a fabricated response on double failure would violate spec §6 by hiding a real failure as if it were a normal answer.

---

## File Structure

```
src/patientzero/
└── llm_client.py       # MODIFY: remove AnthropicLLMClient; add GroqLLMClient,
                         #         OpenAILLMClient, FallbackLLMClient
tests/
└── test_llm_client.py  # MODIFY: add FallbackLLMClient tests (pure logic,
                         #         no SDK/network needed — same treatment
                         #         AnthropicLLMClient.complete already got:
                         #         zero coverage on the real network path,
                         #         since that needs a live key)
pyproject.toml           # MODIFY: replace the `anthropic` extra with an
                          #         `llm` extra bundling groq + openai
```

---

### Task 1: Replace `AnthropicLLMClient` with Groq-primary/OpenAI-fallback

**Files:**
- Modify: `src/patientzero/llm_client.py`
- Modify: `tests/test_llm_client.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: nothing new — same `LLMClientError`/`LLMClient` protocol already defined in this file.
- Produces: `GroqLLMClient(api_key: str, model: str = "llama-3.3-70b-versatile")`, `OpenAILLMClient(api_key: str, model: str = "gpt-4o-mini")`, `FallbackLLMClient(primary: LLMClient, fallback: LLMClient)` — all implementing `complete(prompt: str) -> str`. `AnthropicLLMClient` is removed entirely (no other file in this codebase imports it — `pipeline.py`, `stance.py`, `atomizer.py` only import `LLMClient`/`LLMClientError`, verified by grep before writing this plan). A later plan (the API wrapper) will construct `FallbackLLMClient(primary=GroqLLMClient(...), fallback=OpenAILLMClient(...))` from environment variables.

- [ ] **Step 1: Write the failing tests**

Add these tests to the end of `tests/test_llm_client.py` (the file's existing imports — `pytest`, `FakeLLMClient`, `LLMClientError` — already cover everything needed):

```python
def test_fallback_llm_client_uses_primary_when_it_succeeds():
    primary = FakeLLMClient(responses=["from primary"])
    fallback = FakeLLMClient(responses=["from fallback"])
    client = FallbackLLMClient(primary=primary, fallback=fallback)

    result = client.complete("prompt")

    assert result == "from primary"
    assert fallback.received_prompts == []


def test_fallback_llm_client_falls_back_when_primary_raises():
    primary = FakeLLMClient(responses=[])  # exhausted immediately -> raises LLMClientError
    fallback = FakeLLMClient(responses=["from fallback"])
    client = FallbackLLMClient(primary=primary, fallback=fallback)

    result = client.complete("prompt")

    assert result == "from fallback"
    assert fallback.received_prompts == ["prompt"]


def test_fallback_llm_client_propagates_error_when_both_providers_fail():
    primary = FakeLLMClient(responses=[])
    fallback = FakeLLMClient(responses=[])
    client = FallbackLLMClient(primary=primary, fallback=fallback)

    with pytest.raises(LLMClientError):
        client.complete("prompt")
```

You also need to add `FallbackLLMClient` to the import line at the top of the test file — change:
```python
from patientzero.llm_client import FakeLLMClient, LLMClientError
```
to:
```python
from patientzero.llm_client import FakeLLMClient, FallbackLLMClient, LLMClientError
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_llm_client.py -v`
Expected: FAIL with `ImportError: cannot import name 'FallbackLLMClient' from 'patientzero.llm_client'`

- [ ] **Step 3: Rewrite `llm_client.py`**

Replace the full contents of `src/patientzero/llm_client.py` with:

```python
"""LLM client abstraction. Stance classification and atomization depend only
on the `complete(prompt) -> str` method, never on a specific provider SDK, so
tests can inject FakeLLMClient with zero network or API-key requirements.

Real usage is Groq as the primary provider (fast, cheap) with OpenAI as an
automatic fallback when Groq fails: FallbackLLMClient wraps both behind the
same LLMClient protocol so every caller (atomizer, stance classifier,
pipeline) stays completely unaware of which provider actually answered.
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


class GroqLLMClient:
    """Primary real implementation, backed by Groq. Requires the `groq`
    package (install with `pip install patientzero-core[llm]`).
    """

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        import groq  # deferred import: only required when actually used

        self._client = groq.Groq(api_key=api_key)
        self._model = model

    def complete(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise LLMClientError(f"Groq API call failed: {exc}") from exc
        return response.choices[0].message.content or ""


class OpenAILLMClient:
    """Fallback real implementation, backed by OpenAI. Requires the `openai`
    package (install with `pip install patientzero-core[llm]`).
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        import openai  # deferred import: only required when actually used

        self._client = openai.OpenAI(api_key=api_key)
        self._model = model

    def complete(self, prompt: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=1024,
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_llm_client.py -v`
Expected: PASS (6 passed — 3 pre-existing `FakeLLMClient` tests + 3 new `FallbackLLMClient` tests)

- [ ] **Step 5: Update `pyproject.toml`**

Replace the `[project.optional-dependencies]` block:

```toml
[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov>=5.0"]
llm = ["groq>=0.11", "openai>=1.40"]
```

(This removes the `anthropic` extra — nothing in the shipped test suite or any other module references `anthropic` or `AnthropicLLMClient` after Step 3, so no other file needs updating. Confirm with a grep before committing: `grep -ri anthropic src/ tests/` should return nothing.)

- [ ] **Step 6: Run the full suite to confirm nothing regressed**

Run: `python -m pytest -q`
Expected: all 46 tests pass (43 pre-existing + 3 new), output pristine.

- [ ] **Step 7: Commit**

```bash
git add src/patientzero/llm_client.py tests/test_llm_client.py pyproject.toml
git commit -m "feat: replace AnthropicLLMClient with Groq-primary/OpenAI-fallback

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## After This Plan

This plan only touches `patientzero-core`'s LLM client layer. It does **not** cover:

- Wiring `FallbackLLMClient(GroqLLMClient(...), OpenAILLMClient(...))` into the FastAPI wrapper's `clients.py` (that module doesn't exist yet — it's Task 5 of the separate, in-progress `docs/superpowers/plans/2026-09-18-patientzero-api.md` plan, which this change must be reflected into before that plan's Task 5 is dispatched).
- Any test against the real Groq/OpenAI network APIs — both clients' `complete()` methods have zero test coverage on their actual SDK call path, matching the exact precedent already accepted for `AnthropicLLMClient` (tracked debt, not a gap introduced by this plan).
