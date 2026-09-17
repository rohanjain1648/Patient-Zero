# Patient Zero — Design Spec

**Hackathon:** SerpApi India Hackathon 2026
**Track:** Knowledge & Public Interest
**Deadline:** October 5, 2026, 23:59 IST
**Author:** solo, full-time
**Status:** approved for implementation

## 1. Problem & Positioning

Existing fact-check tools answer "is this true?" — a saturated, low-technical-complexity
space that's easy for a judge to pattern-match and dismiss. Patient Zero answers a
different, harder question: **where did this claim come from, when did it first appear,
who amplified it, and does the answer change depending on what language you search in?**

The product never issues a TRUE/FALSE verdict. It produces a forensic report:
origin date (with confidence), a recycling timeline, independent-corroboration count
(collapsing syndicated copies), a stance breakdown with justifying quotes, and a
cross-lingual asymmetry panel. This framing must be maintained everywhere — README,
UI copy, demo script — as "forensics/provenance," never "fact-check," or the project
risks being judged against a crowded category it isn't competing in.

## 2. Judging Criteria Mapping

- **Idea strength:** provenance/propagation gap, not verdict — a genuine insight into
  how Indian misinformation spreads (recycled forwards, language asymmetry).
- **Originality:** temporal bisection for origin-finding + echo/independence scoring +
  cross-lingual stance asymmetry. Not seen combined elsewhere.
- **Technical complexity:** bisection algorithm with self-verification, simhash
  clustering, batched LLM stance classification, confidence calibration.
- **Usefulness:** journalists, researchers, and anyone who receives a forward.
- **Meaningful SerpApi usage:** the engine *is* multi-locale, date-restricted,
  multi-engine SerpApi search. Remove SerpApi, remove the product.

## 3. Architecture

Single FastAPI service + SQLite + Next.js frontend. No microservices, no queue,
no Postgres — solo/18-day constraint means minimizing moving parts.

```
Next.js (Vercel)
   │  SSE — live progress stream
   ▼
FastAPI ────────────────────────────────┐
   │                                    │
   ├─ Atomizer          (LLM)           │
   ├─ Query Planner     (LLM + locales) │
   ├─ Search Gateway ──► CachedSerp ────┼──► SerpApi
   ├─ Provenance Bisector               │
   ├─ Echo Detector     (simhash)       │
   ├─ Stance Classifier (LLM, batched)  │
   ├─ Independence Scorer               │
   └─ Report Assembler                  │
   ▼                                    │
SQLite: response cache + saved reports ─┘
```

Two deliberate structural decisions:

1. **The pipeline ships as a standalone pip package (`patientzero-core`)**; the FastAPI
   app is a thin HTTP wrapper over it. A judge can `pip install` and call the engine
   directly from their own code — engineering credit without leaving the track.
2. **Every SerpApi call goes through a content-addressed cache with a replay mode**
   (normalized params → SHA256 → SQLite blob). This is foundational, not an
   optimization: free dev loop, deterministic offline tests, and a repo that runs
   end-to-end from shipped fixtures with **no API key required**.

SSE streaming exists specifically for the demo video — watching queries fan out and
the timeline assemble live is more persuasive than a spinner-then-result.

## 4. Provenance Algorithm

### 4.1 Temporal bisection (origin-finding)

Uses SerpApi Google engine `tbs=cdr:1,cd_min:…,cd_max:…` date restriction.

1. **Exponential bracket probe:** query at `[…, today−1y]`, `[…, today−3y]`,
   `[…, today−8y]` → 3 calls establish the bracket containing first appearance.
2. **Bisection:** 4–5 further calls narrow the bracket to within a month.
3. **Per-probe verification:** every probe's top results are checked for relevance
   to the claim before being counted — a window returning *results* is not a window
   returning *this claim*. This check is mandatory; skipping it produces confident
   but wrong origin dates.
4. **Corroboration requirement:** a candidate origin date only counts with ≥2
   independent results in that window.

**Honesty constraint:** Google's date filter reflects indexed date, not true
publication date, and CMS migrations corrupt this regularly. The system must report
a confidence level and label the result a *candidate origin*, never an unqualified
fact. If no corroborated origin is found, the report states this explicitly rather
than guessing.

Cost: ~8 SerpApi calls per claim.

### 4.2 Echo / independence detection

- Normalize title+snippet per result, shingle, simhash, cluster at a tuned threshold.
- Clusters spanning distinct domains = syndication/copy-paste, not independent
  corroboration.
- Independence score = f(distinct clusters, distinct domains, temporal spread).
- This is what turns "142 sources agree" into "3 independent origins" — the report's
  key differentiator.

### 4.3 Cross-lingual asymmetry

- Run the query set at `gl=in` across `hl=en`, `hl=hi`, and one regional language
  (default: `ta` or `bn`, configurable).
- Compare stance distributions across locales; divergence is the reportable signal
  (e.g., debunked in English, unchallenged in Hindi).
- **Descope path if schedule slips:** drop to `en`+`hi` only. This is the cheapest
  cut that doesn't hollow out the pitch — do this before cutting anything else.

### 4.4 Stance classification

- Batches (claim, title, snippet) tuples through one LLM call per batch.
- Returns label (support/refute/unrelated/unclear) + the specific justifying quote.
- Batching keeps end-to-end latency within demo-video tolerance.

## 5. Credit Budget

Free tier: 250/month + 1,000 on submission ≈ 1,250 total searches.

| Stage | Calls |
|---|---|
| Bracket probes | 3 |
| Bisection refinement | 4–5 |
| Corroboration query (`en`) | 1 |
| Corroboration query (`hi`) | 1 |
| Corroboration query (regional) | 1 |
| News engine pass | 1 |
| **Total per analysis** | **~11–12** |

~100 full analyses across the whole budget if cache is honored (repeat claim = 0
calls) and demo fixtures are pre-captured (demo day = 0 calls).

Allocation: ~40 calls for bisection dev/debug, ~30 for stance/echo tuning, remainder
reserved for final demo recording + judge testing.

**Mandatory guardrails:**
- Hard per-run call cap.
- `SERPAPI_MOCK=1` env flag forcing fixture-only mode — lets a judge run the repo
  with zero cost to either party's credits.

## 6. Error Handling & Honesty

Failure modes are part of the design, each with a fixture-backed test:

- No corroborated origin → "no clear origin identified in the indexed window;
  showing all located matches."
- SerpApi call fails/rate-limited → exponential backoff (max 3 retries), then
  degrade to a partial report rather than hard failure.
- Zero checkable claims extracted (pure opinion input) → "no verifiable factual
  claims detected," not a silent empty report.
- Low-confidence stance → labeled "unclear," never forced into support/refute.
- Cache miss/corruption on replay → transparent fallback to live call, logged,
  never crashes the run.

## 7. Testing Strategy

- **Unit tests:** bisection math, simhash clustering, independence scoring — pure
  functions, no network.
- **Integration tests:** full pipeline against recorded fixtures (`SERPAPI_MOCK=1`),
  covering all error paths in §6, runs in CI with no API key.
- **Manual real-API smoke test:** run before each fixture recapture to confirm
  fixtures still match real API response shape.
- **Golden-claim regression set:** 5–6 hand-verified real claims (old recycled
  forward, recently debunked, regional-language-only, no-clear-origin case) with
  expected report shapes, re-run against fixtures on every pipeline change.

This directly satisfies the submission's testing requirement: `git clone &&
pip install -e . && pytest` proves the engine works with no key and no network.

## 8. Schedule (Sep 17 → Oct 5)

| Days | Focus |
|---|---|
| 1–2 (17–18) | Package skeleton: SerpApi client + cache, atomizer, one claim traced manually end-to-end. First fixtures captured. |
| 3–5 (19–21) | Bisection algorithm + verification/corroboration, tuned against 5–6 real claims. |
| 6–7 (22–23) | Echo detection (simhash) + independence scoring. |
| 8–9 (24–25) | Stance classification + cross-lingual asymmetry. |
| 10 (26) | Freeze `patientzero-core` API; publish to PyPI (minimal is fine) for OSS-integration credit. |
| 11–13 (27–29) | FastAPI wrapper + SSE + Next.js frontend (5-panel report UI). |
| 14 (30) | Golden-claim regression set finalized; error-path tests; README + one-command setup. |
| 15 (Oct 1) | Full dry run with real key; capture final demo fixtures; polish pass. |
| 16 (Oct 2) | Record demo video; private-window test of repo + demo links (submission requirement). |
| 17 (Oct 3) | Buffer; write submission text (SerpApi usage explanation is judged — be precise). |
| 18 (Oct 4–5) | Submit on the 4th, not 23:59 on the 5th — leaves margin to fix a broken link. |

**Primary schedule risk:** days 3–5 (bisection tuning) sliding — the one stage with
real algorithmic uncertainty. Mitigation: cross-lingual descope path in §4.3.

## 9. Explicit Non-Goals (YAGNI)

- No user accounts/auth for the hackathon build.
- No Postgres/queue/microservices — SQLite + single FastAPI process is sufficient
  at this scale and avoids infra debugging time.
- No support for arbitrary languages beyond en/hi/+1 regional — breadth here doesn't
  move any judging criterion as much as depth on the core algorithm does.
- No mobile app — web demo only.
