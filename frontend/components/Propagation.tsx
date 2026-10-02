"use client";
import { MediaMention, Propagation, TrendPoint } from "@/lib/types";

const VIEW_W = 1000;
const VIEW_H = 200;

/**
 * Trends returns 0-100 relative interest, and a claim's all-time curve is
 * typically one viral spike at 100 with near-zero everywhere else. On a linear
 * axis that renders as a flat line plus a hairline, hiding whether the claim
 * had any traction at all before it broke — which is the question this panel
 * exists to answer. A square-root axis lifts the low end into view while
 * keeping the peak at the top, and the axis is labelled as such.
 */
function scaleY(value: number): number {
  return VIEW_H - Math.sqrt(Math.max(0, value) / 100) * VIEW_H;
}

function toX(ts: number, min: number, max: number): number {
  if (max <= min) return 0;
  return ((ts - min) / (max - min)) * VIEW_W;
}

function isoToTs(iso: string | null): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isFinite(t) ? t / 1000 : null;
}

function label(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-IN", { month: "short", year: "numeric" });
}

/**
 * Public-attention curve (Google Trends) with the bisected origin date and the
 * interest peak marked on it. The distance between those two markers is the
 * point of the whole panel: a claim indexed years before anyone searched for it
 * spread slowly, while a peak sitting on the origin arrived fully formed.
 */
function TrendChart({ trend, originDate, peakDate }: {
  trend: TrendPoint[];
  originDate: string | null;
  peakDate: string | null;
}) {
  if (trend.length < 2) return null;

  const stamps = trend.map((p) => p.timestamp);
  const min = Math.min(...stamps);
  const max = Math.max(...stamps);

  const points = trend
    .map((p) => `${toX(p.timestamp, min, max).toFixed(1)},${scaleY(p.value).toFixed(1)}`)
    .join(" ");

  const originTs = isoToTs(originDate);
  const peakTs = isoToTs(peakDate);
  // Only draw a marker that actually falls inside the charted window.
  const originX = originTs !== null && originTs >= min && originTs <= max ? toX(originTs, min, max) : null;
  const peakX = peakTs !== null && peakTs >= min && peakTs <= max ? toX(peakTs, min, max) : null;

  return (
    <div className="trend-chart">
      <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} preserveAspectRatio="none" role="img"
           aria-label="Search interest over time, with claim origin and interest peak marked">
        <defs>
          <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--lavender-deep)" stopOpacity="0.5" />
            <stop offset="100%" stopColor="var(--lavender-deep)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon points={`0,${VIEW_H} ${points} ${VIEW_W},${VIEW_H}`} fill="url(#trendFill)" />
        <polyline points={points} fill="none" stroke="var(--lavender-deep)" strokeWidth="2.5"
                  vectorEffect="non-scaling-stroke" />
        {peakX !== null && (
          <>
            <line x1={peakX} y1="0" x2={peakX} y2={VIEW_H} stroke="var(--warn)" strokeWidth="1.5"
                  strokeDasharray="6 5" vectorEffect="non-scaling-stroke" />
            <circle cx={peakX} cy="0" r="4" fill="var(--warn)" />
          </>
        )}
        {originX !== null && (
          <>
            <line x1={originX} y1="0" x2={originX} y2={VIEW_H} stroke="var(--lime-dark)"
                  strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
            <circle cx={originX} cy="0" r="4" fill="var(--lime-dark)" />
          </>
        )}
      </svg>
      <div className="trend-axis">
        <span>{new Date(min * 1000).getFullYear()}</span>
        <span className="trend-axis-note">relative search interest · √ scale</span>
        <span>{new Date(max * 1000).getFullYear()}</span>
      </div>
      <div className="trend-legend">
        <span className="trend-legend-item">
          <i style={{ background: "var(--lime-dark)" }} /> Claim origin · {label(originDate)}
        </span>
        <span className="trend-legend-item">
          <i style={{ background: "var(--warn)" }} /> Interest peak · {label(peakDate)}
        </span>
      </div>
    </div>
  );
}

/** "Indexed in 2014, but nobody searched for it until 2017" — stated plainly. */
function LagCallout({ originDate, peakDate }: { originDate: string | null; peakDate: string | null }) {
  const o = isoToTs(originDate);
  const p = isoToTs(peakDate);
  if (o === null || p === null) return null;

  const months = Math.round((p - o) / (60 * 60 * 24 * 30.44));
  if (Math.abs(months) < 2) {
    return (
      <div className="lag-callout">
        Public interest peaked <strong>as the claim appeared</strong> — no slow build.
      </div>
    );
  }
  const years = Math.abs(months) / 12;
  const span = years >= 1 ? `${years.toFixed(1)} years` : `${Math.abs(months)} months`;
  return (
    <div className="lag-callout">
      Public interest peaked <strong>{span} {months > 0 ? "after" : "before"}</strong> the earliest
      indexed appearance.
    </div>
  );
}

function MentionRow({ m }: { m: MediaMention }) {
  return (
    <a className="mention-row" href={m.link} target="_blank" rel="noreferrer">
      <span className="mention-date">{m.date ? label(m.date) : "undated"}</span>
      <span className="mention-body">
        <span className="mention-title">{m.title || m.link}</span>
        {m.source && <span className="mention-source">{m.source}</span>}
      </span>
    </a>
  );
}

export default function PropagationPanel({ propagation, originDate }: {
  propagation: Propagation | undefined;
  originDate: string | null;
}) {
  if (!propagation) return null;
  const { trend, mentions, peak_date } = propagation;
  if (!trend.length && !mentions.length) return null;

  // Oldest first reads as a propagation trail rather than a news feed.
  const ordered = [...mentions].sort((a, b) => (a.date ?? "9999").localeCompare(b.date ?? "9999"));

  return (
    <div className="report-panel full-width">
      <div className="report-panel-label">
        <span className="report-panel-label-dot" style={{ background: "var(--lavender-deep)" }} />
        Propagation
        <span className="engine-chip">google_trends</span>
        <span className="engine-chip">google_news</span>
      </div>

      {trend.length > 1 ? (
        <>
          <TrendChart trend={trend} originDate={originDate} peakDate={peak_date} />
          <LagCallout originDate={originDate} peakDate={peak_date} />
        </>
      ) : (
        <div className="trend-absent">
          Not enough search-interest data for this claim to plot an attention curve.
        </div>
      )}

      {ordered.length > 0 && (
        <div className="mentions-list">
          <div className="mentions-heading">Media trail · {ordered.length} dated appearances</div>
          {ordered.map((m, i) => <MentionRow key={`${m.link}-${i}`} m={m} />)}
        </div>
      )}
    </div>
  );
}
