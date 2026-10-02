export interface Stance { claim_index: number; result_index: number; label: string; quote: string }
export interface TrendPoint { date: string; timestamp: number; value: number }
export interface MediaMention { medium: string; title: string; link: string; source: string; date: string | null }
export interface Propagation { trend: TrendPoint[]; mentions: MediaMention[]; peak_date: string | null }
export interface ClaimReport {
  claim: { text: string; index: number };
  origin: { date: string | null; confidence: string; evidence_urls: string[] };
  independence: { distinct_clusters: number; distinct_domains: number; temporal_spread_days: number; score: number };
  stances: Stance[];
  locale_asymmetry: Record<string, Stance[]>;
  propagation?: Propagation;
}
export interface ProgressEvent { stage: string; [k: string]: unknown }
/** Live SerpApi calls billed for a run, vs calls the cache served for free. */
export interface Usage { live_calls: number; cache_hits: number }
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Engines the pipeline queries, for the UI's SerpApi attribution strip. */
export const ENGINES = ["google", "google_news", "google_trends"] as const;

export function yearOf(iso: string | null): number | null {
  if (!iso) return null;
  const y = Number(iso.slice(0, 4));
  return Number.isFinite(y) ? y : null;
}
