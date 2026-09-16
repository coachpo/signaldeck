"""Bounded evidence composition preserving collection gaps and stable identities."""

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Literal

from plugin_runtime.common import CamelModel, ensure_timezone
from plugin_runtime.formatting import normalize_symbol
from pydantic import ConfigDict, Field, field_validator

from .research_context import CompactEvidence, make_analysis_context
from .research_evidence import ResearchEvidence
from .research_monitor_contracts import Coverage
from .research_report_validation import day_end
from .research_valuation import calculate_valuation


class ResearchScope(CamelModel):
    model_config = ConfigDict(extra="forbid")
    symbol: str = Field(min_length=1, max_length=30)
    as_of_date: date
    cutoff_at: datetime | None = None

    @field_validator("symbol")
    @classmethod
    def symbol_value(cls, value):
        result = normalize_symbol(value)
        if not result:
            raise ValueError("symbol is required")
        return result

    @field_validator("cutoff_at")
    @classmethod
    def cutoff_value(cls, value):
        return ensure_timezone(value) if value else None


class ResearchCollectionOutput(CamelModel):
    evidence: list[ResearchEvidence] = Field(max_length=300)
    gaps: list[str] = Field(max_length=300)
    analysis_evidence: list[CompactEvidence] = Field(default_factory=list, max_length=64)
    analysis_context_truncated: bool = False
    cutoff_at: datetime
    coverage: list[Coverage] = Field(default_factory=list, max_length=30)


class SupportingMaterial(CamelModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["宏观数据", "公司财报", "新闻", "美国政策", "其他"]
    title: str = Field(min_length=1, max_length=160)
    published_date: date
    source: str = Field(min_length=1, max_length=1000)
    content: str = Field(min_length=1, max_length=6000)


class ResearchMergeInput(ResearchScope):
    include_prediction: bool = False
    include_valuation: bool = False
    groups: list[list[ResearchEvidence]] = Field(max_length=20)
    supporting_materials: list[SupportingMaterial] = Field(default_factory=list, max_length=8)
    upstream_gaps: list[str] = Field(default_factory=list, max_length=300)
    gap_groups: list[list[str]] = Field(default_factory=list, max_length=20)
    coverage_groups: list[list[Coverage]] = Field(default_factory=list, max_length=20)


def collection_cutoff(payload: ResearchScope, now: datetime) -> datetime:
    bound = day_end(payload.as_of_date)
    if payload.cutoff_at is not None and payload.cutoff_at > bound:
        raise ValueError("cutoffAt exceeds asOfDate day boundary")
    return min(bound, payload.cutoff_at or now, now)


def bounded_gaps(gaps: list[str]) -> list[str]:
    unique = list(dict.fromkeys(gaps))
    if len(unique) <= 300:
        return unique
    return unique[:299] + ["Additional collection gaps omitted: gap limit of 300 exceeded"]


def stable_id(prefix: str, value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    return prefix + hashlib.sha256(encoded).hexdigest()[:40]


def evidence_identity(item: ResearchEvidence) -> dict:
    return item.model_dump(mode="json", exclude={"retrieved_at", "evidence_id"})


def make_evidence(**values) -> ResearchEvidence:
    item = ResearchEvidence(evidence_id="pending", **values)
    return item.model_copy(update={"evidence_id": stable_id("ev-", evidence_identity(item))})


def within_cutoff(item: ResearchEvidence, cutoff: datetime) -> bool:
    if item.published_at is not None:
        return item.published_at < cutoff and item.published_at <= item.retrieved_at
    if item.publication_date is not None:
        return day_end(item.publication_date) <= cutoff
    return item.available_by_date is not None and day_end(item.available_by_date) <= cutoff


def merge_evidence(payload: ResearchMergeInput, *, now: datetime | None = None):
    now = now or datetime.now(UTC)
    cutoff = collection_cutoff(payload, now)
    candidates = [item for group in payload.groups for item in group]
    for material in payload.supporting_materials:
        candidates.append(
            make_evidence(
                source_id=stable_id("user-", material.source),
                kind="user",
                source_type="user",
                title=material.title,
                url=material.source if material.source.startswith("https://") else None,
                publication_date=material.published_date,
                retrieved_at=now,
                text=material.content,
                locator=material.source,
                symbol=payload.symbol,
                verified=False,
                uncertainty_reason=(
                    "User supplied material; " "source authenticity has not been verified."
                ),
            )
        )
    gaps = list(payload.upstream_gaps)
    gaps.extend(gap for group in payload.gap_groups for gap in group)
    unique: dict[str, ResearchEvidence] = {}
    fingerprints: set[str] = set()
    conflicts: set[str] = set()
    for item in candidates:
        if item.symbol and normalize_symbol(item.symbol) != payload.symbol:
            gaps.append(f"{item.evidence_id}: symbol mismatch")
            continue
        if not within_cutoff(item, cutoff):
            gaps.append(f"{item.evidence_id}: publication unknown or outside cutoff")
            continue
        if item.evidence_id in conflicts:
            continue
        fingerprint = stable_id("", evidence_identity(item))
        previous = unique.get(item.evidence_id)
        if previous is not None and evidence_identity(previous) != evidence_identity(item):
            unique.pop(item.evidence_id)
            conflicts.add(item.evidence_id)
            gaps.append(f"{item.evidence_id}: conflicting evidence identity excluded")
        elif fingerprint not in fingerprints:
            unique[item.evidence_id] = item
            fingerprints.add(fingerprint)
    combined = list(unique.values())
    coverage_groups = list(payload.coverage_groups)
    if payload.include_valuation:
        estimates, valuation_gaps = calculate_valuation(combined)
        combined.extend(estimates)
        if not estimates and not valuation_gaps:
            valuation_gaps.append("Valuation unavailable: no eligible numeric source evidence")
        gaps.extend(valuation_gaps)
        coverage_groups.append(
            [
                Coverage(
                    source_id="valuation",
                    complete=False,
                    observed_at=now,
                    evidence_ids=[item.evidence_id for item in estimates],
                    warning="Valuation estimates are unverified; share changes are not reconciled.",
                )
            ]
        )
    evidence = combined[:300]
    if len(combined) > 300:
        gaps.append("Evidence truncated to 300 items; coverage is incomplete")
    retained = {item.evidence_id for item in evidence}
    coverage: dict[str, Coverage] = {}
    for group in coverage_groups:
        for record in group:
            ids = [key for key in record.evidence_ids if key in retained]
            complete = record.complete and len(ids) == len(record.evidence_ids)
            current = record.model_copy(update={"evidence_ids": ids, "complete": complete})
            previous = coverage.get(record.source_id)
            if previous:
                current = current.model_copy(
                    update={
                        "evidence_ids": list(dict.fromkeys(previous.evidence_ids + ids)),
                        "complete": previous.complete and complete,
                        "observed_at": min(previous.observed_at, current.observed_at),
                        "warning": "; ".join(filter(None, [previous.warning, current.warning]))
                        or None,
                    }
                )
            coverage[record.source_id] = current
    if len(coverage) > 30:
        raise ValueError("At most 30 distinct coverage sources are allowed")
    if payload.include_prediction and "prediction" not in coverage:
        gaps.append("Selected prediction collection failed; no coverage result was received")
    analysis_evidence = make_analysis_context(evidence)
    return ResearchCollectionOutput(
        evidence=evidence,
        analysis_evidence=analysis_evidence,
        analysis_context_truncated=(
            len(analysis_evidence) != len(evidence)
            or any(item.excerpt_truncated for item in analysis_evidence)
        ),
        gaps=bounded_gaps(gaps),
        cutoff_at=cutoff,
        coverage=list(coverage.values()),
    )
