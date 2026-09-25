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
class MediaMention:
    """One appearance of a claim in a non-web-search medium (news, video).
    `medium` is "news" | "video"; `date` is an ISO string when the engine
    gave us a parseable one, else None.
    """
    medium: str
    title: str
    link: str
    source: str
    date: str | None


@dataclass(frozen=True)
class TrendPoint:
    date: str                  # human label as Google Trends returns it, e.g. "Jun 2016"
    timestamp: int             # unix seconds, for plotting
    value: int                 # 0-100 relative interest


@dataclass(frozen=True)
class Propagation:
    """How a claim spread beyond plain web search: public attention over time
    (Google Trends) plus dated appearances in other media (News, video).
    Every field degrades to empty rather than failing the claim (spec sec 6).
    """
    trend: list[TrendPoint] = field(default_factory=list)
    mentions: list[MediaMention] = field(default_factory=list)
    peak_date: str | None = None          # ISO date of maximum public interest


@dataclass(frozen=True)
class ClaimReport:
    claim: Claim
    origin: OriginCandidate
    independence: IndependenceScore
    stances: list[StanceResult]
    locale_asymmetry: dict[str, list[StanceResult]]  # locale code -> stances for that locale
    propagation: Propagation = field(default_factory=lambda: Propagation())
