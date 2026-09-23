"use client";
import { useState } from "react";
import { API_URL, ClaimReport, ProgressEvent } from "@/lib/types";

function describe(e: ProgressEvent): string {
  const { stage, ...rest } = e;
  const extra = Object.keys(rest).length ? " " + JSON.stringify(rest) : "";
  return stage.replace(/_/g, " ") + extra;
}

function Stances({ items }: { items: ClaimReport["stances"] }) {
  if (!items.length) return <div className="sub">No stance data.</div>;
  return (
    <>
      {items.map((s, i) => (
        <div key={i}>
          <span className={`tag ${s.label}`}>{s.label}</span>
          <blockquote>{s.quote || "—"}</blockquote>
        </div>
      ))}
    </>
  );
}

function Report({ r }: { r: ClaimReport }) {
  const o = r.origin;
  return (
    <section>
      <div className="claim">{r.claim.text}</div>
      <div className="panel">
        <h3>Origin</h3>
        {o.date ? <div>Earliest corroborated appearance: <b>{o.date}</b> <span className="tag">{o.confidence} confidence</span></div>
          : <div>No clear origin identified in the indexed window.</div>}
        {o.evidence_urls.map((u) => <div key={u}><a href={u} target="_blank" rel="noreferrer">{u}</a></div>)}
      </div>
      <div className="panel">
        <h3>Independent corroboration</h3>
        <div className="bar"><i style={{ width: `${Math.round(r.independence.score * 100)}%` }} /></div>
        <div className="sub">
          score {r.independence.score.toFixed(2)} · {r.independence.distinct_clusters} distinct clusters ·{" "}
          {r.independence.distinct_domains} domains · {r.independence.temporal_spread_days} days spread
        </div>
      </div>
      <div className="panel"><h3>Stance</h3><Stances items={r.stances} /></div>
      {Object.entries(r.locale_asymmetry).map(([loc, s]) => (
        <div className="panel" key={loc}><h3>Locale: {loc}</h3><Stances items={s} /></div>
      ))}
    </section>
  );
}

export default function Home() {
  const [text, setText] = useState("");
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const [reports, setReports] = useState<ClaimReport[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  function analyze() {
    setRunning(true); setLog([]); setReports(null); setError(null);
    const es = new EventSource(`${API_URL}/api/analyze?text=${encodeURIComponent(text)}`);
    const finish = () => { es.close(); setRunning(false); };
    es.addEventListener("progress", (m) => setLog((l) => [...l, describe(JSON.parse((m as MessageEvent).data))]));
    es.addEventListener("report", (m) => { setReports(JSON.parse((m as MessageEvent).data).claims); finish(); });
    es.addEventListener("error", (m) => {
      const d = (m as MessageEvent).data;
      setError(d ? JSON.parse(d).message : "Connection to the API was lost.");
      finish();
    });
  }

  return (
    <main>
      <h1>Patient Zero</h1>
      <p className="sub">Paste a claim or forward. We trace where it started and who independently backs it up.</p>
      <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste a headline, forward, or article…" />
      <button onClick={analyze} disabled={running || !text.trim()}>{running ? "Analyzing…" : "Trace claim"}</button>
      {log.length > 0 && <div className="panel log"><h3>Live progress</h3>{log.map((l, i) => <div key={i}>{l}</div>)}</div>}
      {error && <div className="panel err">{error}</div>}
      {reports && (reports.length ? reports.map((r) => <Report key={r.claim.index} r={r} />)
        : <div className="panel">No verifiable factual claims detected.</div>)}
    </main>
  );
}
