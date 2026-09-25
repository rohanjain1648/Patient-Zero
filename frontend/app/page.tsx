"use client";
import { useState, useRef, useEffect } from "react";
import { API_URL, ClaimReport, ProgressEvent } from "@/lib/types";

function describe(e: ProgressEvent): string {
  const { stage, ...rest } = e;
  const extra = Object.keys(rest).length ? " " + JSON.stringify(rest) : "";
  return stage.replace(/_/g, " ") + extra;
}

function StanceBadge({ label }: { label: string }) {
  return <span className={`stance-badge ${label}`}>{label}</span>;
}

function StancesPanel({ items }: { items: ClaimReport["stances"] }) {
  if (!items.length)
    return <div style={{ color: "var(--mute-light)", fontSize: 13 }}>No stance data available.</div>;
  return (
    <div className="stances-list">
      {items.map((s, i) => (
        <div key={i} className="stance-item">
          <StanceBadge label={s.label} />
          <div className="stance-quote">{s.quote || "—"}</div>
        </div>
      ))}
    </div>
  );
}

function ReportCard({ r, index }: { r: ClaimReport; index: number }) {
  const o = r.origin;
  const scorePercent = Math.round(r.independence.score * 100);

  return (
    <div className="report-card">
      {/* Claim Header */}
      <div className="report-claim-header">
        <div className="report-claim-index">#{String(index + 1).padStart(2, "0")}</div>
        <div className="report-claim-text">{r.claim.text}</div>
      </div>

      {/* Panels Grid */}
      <div className="report-panels">
        {/* Origin */}
        <div className="report-panel">
          <div className="report-panel-label">
            <span className="report-panel-label-dot" style={{ background: "var(--lime-dark)" }} />
            Origin
          </div>
          {o.date ? (
            <>
              <div className="origin-date">{o.date}</div>
              <div className="origin-confidence">
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    background:
                      o.confidence === "high"
                        ? "var(--ok)"
                        : o.confidence === "medium"
                        ? "var(--warn)"
                        : "var(--bad)",
                    display: "inline-block",
                  }}
                />
                {o.confidence} confidence
              </div>
            </>
          ) : (
            <div style={{ color: "var(--mute)", fontSize: 13 }}>
              No clear origin identified in indexed window.
            </div>
          )}
          {o.evidence_urls.length > 0 && (
            <div className="origin-urls">
              {o.evidence_urls.map((u) => (
                <a key={u} href={u} target="_blank" rel="noreferrer" className="origin-url-link">
                  ↗ {u.replace(/^https?:\/\//, "").split("/")[0]}
                </a>
              ))}
            </div>
          )}
        </div>

        {/* Independence */}
        <div className="report-panel">
          <div className="report-panel-label">
            <span className="report-panel-label-dot" style={{ background: "var(--lavender)" }} />
            Independent Corroboration
          </div>
          <div className="independence-score-display">
            {scorePercent}
            <span style={{ fontSize: 16, fontWeight: 500, color: "var(--mute)", marginLeft: 2 }}>
              %
            </span>
          </div>
          <div className="score-bar-track">
            <div className="score-bar-fill" style={{ width: `${scorePercent}%` }} />
          </div>
          <div className="independence-meta">
            <span className="independence-chip">⬡ {r.independence.distinct_clusters} clusters</span>
            <span className="independence-chip">◎ {r.independence.distinct_domains} domains</span>
            <span className="independence-chip">⌛ {r.independence.temporal_spread_days}d spread</span>
          </div>
        </div>

        {/* Stances */}
        <div className="report-panel full-width">
          <div className="report-panel-label">
            <span className="report-panel-label-dot" />
            Stance Analysis
          </div>
          <StancesPanel items={r.stances} />
        </div>

        {/* Locale Asymmetry */}
        {Object.entries(r.locale_asymmetry).length > 0 && (
          <div className="report-panel full-width">
            <div className="report-panel-label">
              <span className="report-panel-label-dot" style={{ background: "var(--warn)" }} />
              Locale Asymmetry
            </div>
            {Object.entries(r.locale_asymmetry).map(([loc, stances]) => (
              <div key={loc} style={{ marginBottom: 16 }}>
                <div className="locale-header">🌐 {loc}</div>
                <StancesPanel items={stances} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

const BENTO_FEATURES = [
  {
    icon: "⧖",
    title: "Temporal Bisection",
    desc: "Binary-searches time to find the earliest indexed date a claim first appeared with corroboration.",
    tag: "bisection.py",
    style: "bento-card-lime",
  },
  {
    icon: "◎",
    title: "Independence Scoring",
    desc: "Clusters sources by domain network to ensure corroboration isn't just echo-chamber amplification.",
    tag: "independence.py",
    style: "bento-card-lavender",
  },
  {
    icon: "⬡",
    title: "Stance Classification",
    desc: "LLM classifies each result as support, refute, unclear, or unrelated — never a binary verdict.",
    tag: "stance.py",
    style: "bento-card-cream",
  },
  {
    icon: "🌐",
    title: "Locale Asymmetry",
    desc: "Cross-regional search reveals when a claim is reported differently across geographies.",
    tag: "multi-locale",
    style: "bento-card-dark bento-card-span2",
  },
  {
    icon: "⚡",
    title: "LLM Resilience",
    desc: "Groq primary + OpenAI fallback — automatic failover with graceful partial degradation.",
    tag: "llm_client.py",
    style: "bento-card-cream",
  },
];

const HOW_STEPS = [
  { num: "01", icon: "✦", title: "Atomize", desc: "LLM splits your text into distinct, individually checkable factual claims." },
  { num: "02", icon: "⧖", title: "Bisect", desc: "Exponential date probes narrow the earliest appearance window to ~1 month." },
  { num: "03", icon: "⬡", title: "Classify", desc: "Search results are labelled as supporting, refuting, or unclear — no verdicts." },
  { num: "04", icon: "◎", title: "Report", desc: "Origin, corroboration score, and locale asymmetry rendered as structured reports." },
];

export default function Home() {
  const [text, setText] = useState("");
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const [reports, setReports] = useState<ClaimReport[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [log]);

  function analyze() {
    setRunning(true);
    setLog([]);
    setReports(null);
    setError(null);

    const es = new EventSource(`${API_URL}/api/analyze?text=${encodeURIComponent(text)}`);
    const finish = () => {
      es.close();
      setRunning(false);
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 200);
    };

    es.addEventListener("progress", (m) =>
      setLog((l) => [...l, describe(JSON.parse((m as MessageEvent).data))])
    );
    es.addEventListener("report", (m) => {
      setReports(JSON.parse((m as MessageEvent).data).claims);
      finish();
    });
    es.addEventListener("error", (m) => {
      const d = (m as MessageEvent).data;
      setError(d ? JSON.parse(d).message : "Connection to the API was lost.");
      finish();
    });
  }

  return (
    <>
      {/* Announcement Banner */}
      <div className="announcement-banner">
        <span>⬡ Patient Zero v1.0</span> — Claim provenance &amp; propagation forensics, powered by SerpApi
      </div>

      {/* Sticky Pill Nav */}
      <nav className="nav-wrapper">
        <div className="nav-pill">
          <a href="#" className="nav-brand">
            <div className="nav-logo">PZ</div>
            <span className="nav-brand-text">Patient Zero</span>
          </a>
          <div className="nav-links">
            <a href="#how" className="nav-link">How it works</a>
            <a href="#features" className="nav-link">Features</a>
            <a
              href="https://github.com"
              target="_blank"
              rel="noreferrer"
              className="nav-link"
            >
              GitHub ↗
            </a>
          </div>
          <div className="nav-actions">
            <a
              href="https://serpapi.com"
              target="_blank"
              rel="noreferrer"
              className="btn-lime"
            >
              SerpApi ↗
            </a>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <div className="hero-wrapper">
        <div className="hero-card">
          <div className="hero-eyebrow">
            <span className="hero-eyebrow-dot" />
            Forensics Engine
          </div>

          <h1 className="hero-headline">
            Where did this<br />
            claim <span className="hero-highlight">originate?</span>
          </h1>

          <p className="hero-sub">
            Paste any headline, forward, or article. Patient Zero traces its earliest indexed appearance,
            scores independent corroboration, and surfaces regional stance asymmetry — without ever
            issuing a verdict.
          </p>

          <div className="hero-input-group">
            <div className="hero-textarea-wrapper">
              <label className="hero-textarea-label" htmlFor="claim-input">
                Input — Claim / Headline / Forward
              </label>
              <textarea
                id="claim-input"
                className="hero-textarea"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="e.g. Scientists confirm that drinking coffee prevents cancer in 90% of cases…"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && !running && text.trim()) {
                    analyze();
                  }
                }}
              />
            </div>
            <div className="hero-submit-row">
              <span className="hero-hint">⌘ + Enter to analyze</span>
              <button
                id="trace-btn"
                className={`btn-trace ${running ? "analyzing" : ""}`}
                onClick={analyze}
                disabled={running || !text.trim()}
              >
                {running ? (
                  <>
                    <div className="progress-spinner" style={{ width: 14, height: 14 }} />
                    Tracing claim…
                  </>
                ) : (
                  <>
                    Trace claim
                    <div className="btn-trace-arrow">→</div>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="stats-bar">
        <div className="stats-grid">
          <div className="stat-item">
            <div className="stat-value">~1<span className="lime">mo</span></div>
            <div className="stat-label">Origin precision window</div>
          </div>
          <div className="stat-item">
            <div className="stat-value">4<span className="lime">+</span></div>
            <div className="stat-label">Stance classification labels</div>
          </div>
          <div className="stat-item">
            <div className="stat-value">0<span className="lime">x</span></div>
            <div className="stat-label">Verdicts ever issued</div>
          </div>
        </div>
      </div>

      {/* Live Progress + Results */}
      {(log.length > 0 || error || reports !== null) && (
        <div className="content-area" ref={resultRef}>
          {/* Progress Log */}
          {log.length > 0 && (
            <div className="progress-panel">
              <div className="progress-panel-header">
                {running && <div className="progress-spinner" />}
                <span className="progress-panel-title">
                  {running ? "Live progress" : "Completed"}
                </span>
                {!running && (
                  <span
                    style={{
                      marginLeft: "auto",
                      fontFamily: "var(--font-mono)",
                      fontSize: 10,
                      color: "var(--lime)",
                      letterSpacing: "0.06em",
                    }}
                  >
                    ✓ DONE
                  </span>
                )}
              </div>
              <div className="progress-log">
                {log.map((entry, i) => (
                  <div key={i} className="progress-log-entry">
                    {entry}
                  </div>
                ))}
                <div ref={logEndRef} />
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="error-panel">
              <div className="error-icon">⚠</div>
              <div>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>Analysis failed</div>
                <div style={{ fontSize: 13 }}>{error}</div>
              </div>
            </div>
          )}

          {/* Reports */}
          {reports !== null && (
            <>
              <div className="reports-header">
                <div className="reports-title">
                  {reports.length > 0 ? "Claim Reports" : "Analysis Complete"}
                </div>
                {reports.length > 0 && (
                  <div className="reports-count-badge">{reports.length} claim{reports.length !== 1 ? "s" : ""}</div>
                )}
              </div>

              {reports.length === 0 ? (
                <div className="no-claims-panel">
                  <span className="empty-state-icon">◎</span>
                  No verifiable factual claims detected in this input.
                </div>
              ) : (
                reports.map((r, i) => <ReportCard key={r.claim.index} r={r} index={i} />)
              )}
            </>
          )}
        </div>
      )}

      {/* Features Bento */}
      <div className="bento-section" id="features">
        <div className="bento-label">Core pipeline modules</div>
        <div className="bento-grid">
          {BENTO_FEATURES.map((f, i) => (
            <div key={i} className={`bento-card ${f.style}`}>
              <div className="bento-icon">{f.icon}</div>
              <div className="bento-title">{f.title}</div>
              <div className="bento-desc">{f.desc}</div>
              <div className="bento-tag">{f.tag}</div>
            </div>
          ))}
        </div>
      </div>

      {/* How It Works — Dark Section */}
      <div className="how-section" id="how">
        <div className="how-inner">
          <div className="how-title">How it works</div>
          <div className="how-sub">A four-stage forensics pipeline, zero verdicts issued.</div>
          <div className="how-steps">
            {HOW_STEPS.map((s) => (
              <div key={s.num} className="how-step">
                <div className="how-step-num">{s.num}</div>
                <div className="how-step-icon">{s.icon}</div>
                <div className="how-step-title">{s.title}</div>
                <div className="how-step-desc">{s.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer>
        <div className="footer">
          <div className="footer-brand">
            <div className="footer-logo">PZ</div>
            Patient Zero
          </div>
          <div className="footer-copy">
            Claim forensics, powered by SerpApi &amp; Groq
          </div>
          <div className="footer-badges">
            <span className="footer-badge">SerpApi</span>
            <span className="footer-badge">Groq</span>
            <span className="footer-badge">Next.js</span>
          </div>
        </div>
      </footer>
    </>
  );
}
