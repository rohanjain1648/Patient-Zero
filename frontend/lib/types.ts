export interface Stance { claim_index: number; result_index: number; label: string; quote: string }
export interface ClaimReport {
  claim: { text: string; index: number };
  origin: { date: string | null; confidence: string; evidence_urls: string[] };
  independence: { distinct_clusters: number; distinct_domains: number; temporal_spread_days: number; score: number };
  stances: Stance[];
  locale_asymmetry: Record<string, Stance[]>;
}
export interface ProgressEvent { stage: string; [k: string]: unknown }
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
