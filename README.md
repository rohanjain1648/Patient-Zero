# Patient Zero - Core

**Claim provenance and propagation forensics engine, powered by SerpApi.**

Patient Zero is a robust, modular system designed to dissect raw text inputs (such as news articles, internet forwards, or headlines), extract factual assertions, trace their origins across the internet using temporal search bisection, and classify the stances of various search results. It aims to understand how a claim propagated and whether it is supported or refuted by independent sources.

---

## 🧩 System Architecture

The core engine orchestrates a multi-stage pipeline (`src/patientzero/pipeline.py`), invoking specialized modules to process text while maintaining strict adherence to performance and API credit budgets.

```mermaid
flowchart TD
    Input([Raw Text Input]) --> Atomizer

    subgraph "1. Atomization"
    Atomizer(Atomizer) --> Claims([List of Claims])
    end

    Claims --> Pipeline Orchestration

    subgraph "2. Pipeline Orchestration (Per Claim)"
        Pipeline Orchestration --> Bisection(Temporal Bisection)
        Pipeline Orchestration --> Serp(SerpApi Query per Locale)
        
        Serp --> Results([Search Results])
        
        Results --> Stance(Stance Classification)
        Results --> Independence(Independence Scoring)
    end

    Bisection --> Origin([Origin Date / URLs])
    Stance --> Stances([Support / Refute Labels])
    Independence --> Score([Independence Score])

    Origin --> Aggregation(Report Generation)
    Stances --> Aggregation
    Score --> Aggregation

    Aggregation --> Output([List of ClaimReports])
```

### Core Components

#### 1. Atomizer (`atomizer.py`)
Splits raw user input into individually checkable factual assertions. It uses an LLM to extract these claims.
*   **Behavior**: If the input contains no verifiable claims (e.g., pure opinion), it gracefully returns an empty list, allowing the pipeline to exit early without error.

#### 2. Temporal Bisection (`bisection.py`)
Finds the earliest indexed-date window in which a claim's corroborated evidence first appears. This is a critical feature for tracing the "patient zero" of a viral claim.
*   **Bracket Probes**: Initiates exponential bracket probes (1 year, 3 years, and 8 years ago) to find a window with corroborated evidence.
*   **Convergence**: Bisects the dates repeatedly until the window narrows down to approximately 1 month (or reaches maximum tolerance).
*   **Validation**: Every probe strictly checks for **relevance** (deterministic token-overlap) and **corroboration** (at least 2 matching results). 

```mermaid
flowchart LR
    Start([Current Date]) --> Bracket{Bracket Search<br>-1y, -3y, -8y}
    Bracket -->|Evidence Found| Bisect[Bisect Range]
    Bracket -->|No Evidence| Epoch[Search from Epoch]
    Epoch --> Bisect
    Bisect --> |Narrow to 1 month| Converge([Earliest Valid Window])
```

#### 3. Stance Classification (`stance.py`)
Performs batched LLM stance classification for the search results retrieved for a claim.
*   **Nuanced Labels**: Strictly avoids boolean `true`/`false` labels. Instead, it categorizes results as `support`, `refute`, `unrelated`, or `unclear`.
*   **Evidence Collection**: Extracts and provides a justifying quote directly from the search result's snippet.

#### 4. Independence Scoring (`independence.py`)
Groups search results into clusters to evaluate the independence of the sources. It ensures that a claim isn't just being superficially echoed by a single network or domain, providing an independence score that reflects genuine multi-source corroboration.

#### 5. SerpApi Gateway (`serp_client.py`)
The unified network access layer for all search queries.
*   **Caching (`cache.py`)**: Every network call is routed through a local cache to prevent redundant requests and conserve SerpApi credits.
*   **Mocking**: Provides a `SERPAPI_MOCK=1` mode to run entirely off local JSON fixtures during testing and development.

---

## 🤖 LLM Strategy & Resilience

To maintain high availability and manage costs, Patient Zero utilizes a primary-fallback LLM architecture (`llm_client.py`).

```mermaid
flowchart TD
    Req([Prompt Request]) --> Primary{Primary LLM<br>Groq}
    Primary -->|Success| Resp([LLM Response])
    Primary -->|Timeout/Error| Fallback{Fallback LLM<br>OpenAI}
    Fallback -->|Success| Resp
    Fallback -->|Timeout/Error| Err([LLMClientError])
```

*   **Groq (Primary)**: Favored for speed and low cost on standard tasks.
*   **OpenAI (Fallback)**: Steps in automatically if the primary provider fails.
*   **Graceful Degradation**: If both providers fail (raising an `LLMClientError`), the pipeline catches the error and degrades the specific task to a partial result (e.g., marking stances as "unclear" or skipping a single claim) rather than crashing the entire batch process.

---

## 🛠 Tech Stack & Dependencies

- **Language**: Python `>= 3.10`
- **Core Dependencies**: `requests>=2.31`
- **Optional Dependencies**: 
    - `[llm]`: Installs `groq>=0.11` and `openai>=1.40` for LLM capabilities.
    - `[dev]`: Installs `pytest>=8.0` and `pytest-cov>=5.0` for development and testing.

---

## 🚀 Installation & Setup

1. **Clone the repository and install core:**
   ```bash
   pip install .
   ```

2. **Install with LLM Provider support:**
   ```bash
   pip install .[llm]
   ```

3. **Install for Development:**
   ```bash
   pip install .[dev]
   ```

---

## ▶️ Quick start

### Run it with no API keys at all

The repo ships a session recorded from a real analysis, so it runs end to end
without a SerpApi, Groq or OpenAI key — and without spending anyone's credits:

```bash
python -m venv .venv && .venv/Scripts/activate    # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev,llm,api]"
uvicorn patientzero_api.main:app --port 8000      # starts in DEMO MODE when keys are absent

cd frontend && npm install && npm run dev         # http://localhost:3000
```

The UI labels the stream as a replay, and `GET /api/health` reports
`{"mode": "demo"}`. Nothing recorded is ever presented as a live result.

### Run a live analysis

```bash
cp .env.example .env     # fill in SERPAPI_API_KEY, GROQ_API_KEY, OPENAI_API_KEY
uvicorn patientzero_api.main:app --port 8000
```

A full analysis costs roughly 12–15 SerpApi calls, capped per run and
content-address cached, so a repeated claim costs nothing. The UI shows live
calls vs cache hits while the analysis streams.

To re-record the demo session from a live run:

```bash
python scripts/record_demo.py "Some claim to analyse"
```

---

## 🔍 SerpApi engines used

| Engine | Role in the pipeline |
|---|---|
| `google` | Date-restricted probes for temporal bisection, plus per-locale corroboration queries (`hl=en`, `hl=hi`) |
| `google_news` | Dated, source-attributed propagation trail — where the claim travelled after it first appeared |
| `google_trends` | Public search interest over time (`TIMESERIES`, full history), overlaid with the bisected origin date |

The gap between the two markers on the Trends curve is the analytical payload:
a claim indexed years before anyone searched for it spread slowly, while a peak
sitting on top of the origin date arrived fully formed.

---

## ⚙️ Configuration & Environment

The application relies on API keys injected into the core clients. Set these in your environment or pass them directly during client instantiation:

| Variable | Purpose |
|---|---|
| `SERPAPI_API_KEY` | SerpApi access for `SerpClient`. Absent → the API starts in demo mode. |
| `GROQ_API_KEY` | Primary LLM provider. Absent → demo mode. |
| `OPENAI_API_KEY` | Fallback LLM provider. Absent → demo mode. |
| `SERPAPI_MOCK` | `1` reads SerpApi responses from fixtures in `SERPAPI_MOCK_DIR` instead of the network. |
| `PATIENTZERO_DATA_DIR` | Where the response cache and saved reports live (default `data/`). |
| `CORS_ORIGINS` | Comma-separated origins allowed to call the API (default `http://localhost:3000`). |

---

## 🧪 Testing and Mocking

Patient Zero is designed with robust testing capabilities that do not require spending API credits.

Enable the SerpApi mock mode to use local JSON fixtures instead of making live network calls:

```bash
export SERPAPI_MOCK=1
python -m pytest tests/ -v
```

**Note:** The codebase mandates that tests never make actual network calls to LLM providers. `FakeLLMClient` is used extensively in unit tests to simulate predictable LLM outputs.

---

## 📜 Core Design Constraints (Spec)

Patient Zero adheres strictly to several core behavioral constraints:

1. **No Verdicts**: The engine will never output a definitive "True" or "False" verdict for a claim. It surfaces context, origins, and independent stances, leaving the final judgment to the human user.
2. **Graceful Degradation**: Failure in one component (like an LLM timeout while classifying stances for one claim) must not abort the pipeline. The system must degrade to partial results (e.g., returning the claims that *did* succeed, or returning "unclear" stances).
3. **Credit Discipline**: Bisection's relevance checks deliberately use deterministic token-overlap rather than LLM calls to prevent exponential LLM costs during rapid search iteration.
