"""Shared data structures for the Patient Zero pipeline.

No stage constructs its own ad-hoc dicts for cross-stage data — everything
that crosses a stage boundary is one of these frozen dataclasses.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SearchResult:
    title: str
    link: str
    snippet: str
    domain: str
    date: str | None  # ISO date string if known, else None


@dataclass(frozen=True)
class Claim:
    text: str
    index: int


@dataclass(frozen=True)
class OriginCandidate:
    date: str | None          # ISO date of earliest corroborated appearance, or None if unresolved
    confidence: str           # "high" | "medium" | "low" | "unresolved"
    evidence_urls: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EchoCluster:
    result_indices: tuple[int, ...]
    domain_count: int


@dataclass(frozen=True)
class IndependenceScore:
    distinct_clusters: int
    distinct_domains: int
    temporal_spread_days: int
    score: float               # 0.0-1.0, higher = more independent corroboration


@dataclass(frozen=True)
class StanceResult:
    claim_index: int
    result_index: int
    label: str                 # "support" | "refute" | "unrelated" | "unclear"
    quote: str


@dataclass(frozen=True)
class ClaimReport:
    claim: Claim
    origin: OriginCandidate
    independence: IndependenceScore
    stances: list[StanceResult]
    locale_asymmetry: dict[str, list[StanceResult]]  # locale code -> stances for that locale
