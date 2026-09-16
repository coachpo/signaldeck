"""Bounded model context; the complete evidence ledger remains authoritative."""

import json
from collections import defaultdict, deque
from datetime import date, datetime

from plugin_runtime.common import CamelModel
from pydantic import ConfigDict, Field

from .research_evidence import ResearchEvidence


class CompactEvidence(CamelModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    source_id: str
    kind: str
    title: str
    symbol: str | None = None
    source_type: str | None = None
    metric: str | None = None
    value: str | None = None
    unit: str | None = None
    currency: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    published_at: datetime | None = None
    publication_date: date | None = None
    available_by_date: date | None = None
    verified: bool
    url: str | None = None
    locator: str | None = None
    text: str = Field(default="", max_length=800)
    excerpt_truncated: bool = False


def _project(item: ResearchEvidence) -> CompactEvidence:
    fields = CompactEvidence.model_fields.keys() - {"text", "excerpt_truncated"}
    values = {key: getattr(item, key) for key in fields}
    text = item.text or ""
    return CompactEvidence(**values, text=text[:800], excerpt_truncated=len(text) > 800)


def _chronology(item: ResearchEvidence):
    # ISO dates and aware UTC instants are ordered only within the same date first.
    public_day = (
        item.published_at.date()
        if item.published_at
        else item.publication_date or item.available_by_date or date.min
    )
    return (public_day, item.period_end or date.min, item.evidence_id)


def context_size(items: list[CompactEvidence]) -> int:
    return len(
        json.dumps(
            [item.model_dump(mode="json", by_alias=True) for item in items], ensure_ascii=False
        )
    )


def make_analysis_context(evidence: list[ResearchEvidence]) -> list[CompactEvidence]:
    superseded = {item.supersedes_evidence_id for item in evidence if item.supersedes_evidence_id}
    eligible = [item for item in evidence if item.evidence_id not in superseded]
    # Numeric metrics receive one fresh sample before historical repeats. Outer source
    # rotation protects original documents and macro series from a large SEC metric set.
    queues = {}
    for verified in (True, False):
        groups = defaultdict(lambda: defaultdict(list))
        for item in eligible:
            if item.verified == verified:
                groups[item.source_type or "unknown"][item.metric or "text"].append(item)
        for source, metrics in sorted(groups.items()):
            buckets = [
                deque(
                    sorted(items, key=_chronology, reverse=True)[:6]
                    if metric == "text"
                    else sorted(items, key=_chronology, reverse=True)
                )
                for metric, items in sorted(metrics.items())
            ]
            ordered = []
            while any(buckets):
                for bucket in buckets:
                    if bucket:
                        ordered.append(bucket.popleft())
            queues[(verified, source)] = deque(ordered)
    result = []
    for verified in (True, False):
        sources = [queue for (trusted, _), queue in queues.items() if trusted == verified]
        while any(sources) and len(result) < 64:
            for source in sources:
                if not source or len(result) >= 64:
                    continue
                candidate = _project(source.popleft())
                if context_size(result + [candidate]) <= 24000:
                    result.append(candidate)
    return result
