"""Bounded explicit original-document retrieval; no discovery or historical archive."""

from __future__ import annotations

import hashlib
import ipaddress
import os
import re
from datetime import UTC, date, datetime, time, timedelta
from time import monotonic
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
from plugin_runtime.common import CamelModel
from pydantic import Field, field_validator

from .research_documents_evidence import ResearchEvidence
from .research_documents_extract import DocumentPassage, OriginalHTML, select_passages


class DocumentQuery(CamelModel):
    urls: list[str] = Field(default_factory=list, max_length=5)
    symbol: str | None = Field(default=None, min_length=1, max_length=30)
    cik: str | None = Field(default=None, min_length=1, max_length=13)
    include_insider: bool = False
    as_of_date: date | None = None
    cutoff_at: datetime | None = None

    @field_validator("cutoff_at")
    @classmethod
    def aware(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("cutoffAt requires timezone")
        return value


class Document(CamelModel):
    source_id: str
    url: str
    retrieved_at: datetime
    status: Literal["read", "unavailable", "after_cutoff", "publication_unknown"]
    document_digest: str | None = None
    published_at: datetime | None = None
    locator: str | None = None
    excerpt: str | None = None
    text: str | None = None
    passages: list[DocumentPassage] = Field(default_factory=list, max_length=5)
    gaps: list[str] = Field(default_factory=list)


class SourceCoverage(CamelModel):
    source_id: str
    complete: bool
    observed_at: datetime
    evidence_ids: list[str] = Field(default_factory=list, max_length=300)
    warning: str | None = None


class DocumentsResult(CamelModel):
    schema_version: Literal["research-sources/v1"] = "research-sources/v1"
    cutoff_at: datetime
    documents: list[Document]
    coverage: list[SourceCoverage] = Field(default_factory=list, max_length=30)
    evidence: list[ResearchEvidence] = Field(default_factory=list, max_length=300)
    gaps: list[str] = Field(default_factory=list)


def source_identity(url: str) -> str:
    if (urlsplit(url).hostname or "") in ("www.sec.gov", "sec.gov", "data.sec.gov"):
        match = re.search(r"/data/[0-9]+/([0-9]{10})([0-9]{2})([0-9]{6})/", url)
        if match:
            return "sec:" + "-".join(match.groups())
    return digest(url.encode())


def digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def cutoff(query, now: datetime) -> datetime:
    bounds = [now]
    if query.cutoff_at:
        bounds.append(query.cutoff_at)
    if query.as_of_date:
        bounds.append(
            datetime.combine(
                query.as_of_date + timedelta(days=1), time(), ZoneInfo("America/New_York")
            ).astimezone(UTC)
        )
    return min(bounds)


def timestamp(value) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else None
    except (ValueError, TypeError):
        return None


def public_url(url: str) -> bool:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443):
        return False
    if "." not in host or host.endswith((".localhost", ".local", ".internal")):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return True


def fetch(client: httpx.Client, url: str, *, headers=None) -> tuple[bytes, str]:
    if not public_url(url):
        raise ValueError("public_https_url_required")
    started = monotonic()
    # No implicit redirects: the exact supplied source must be reviewable.
    with client.stream("GET", url, headers=headers, follow_redirects=False) as response:
        response.raise_for_status()
        content = bytearray()
        for chunk in response.iter_bytes():
            if monotonic() - started > 15:
                raise ValueError("document_timeout")
            content.extend(chunk)
            if len(content) > 8_000_000:
                raise ValueError("document_size_limit")
        return bytes(content), response.headers.get("content-type", "").lower()


def lookup_documents(arguments: dict) -> DocumentsResult:
    query = DocumentQuery.model_validate(arguments)
    now = datetime.now(UTC)
    bound = cutoff(query, now)
    documents = []
    urls = list(query.urls)
    published = {}
    discovery_gaps = []
    if not urls and (query.symbol or query.cik):
        from .research_documents_discovery import filing_sources

        discovery = filing_sources(query.symbol, query.cik, query.as_of_date)
        discovery_gaps = [
            str(w.get("code", "sec_source_warning")) for w in discovery.get("warnings", [])
        ]
        for filing in discovery.get("filings", []):
            if filing.get("url"):
                urls.append(filing["url"])
                published[filing["url"]] = timestamp(filing.get("acceptedAt"))
    with httpx.Client(
        timeout=httpx.Timeout(10), headers={"User-Agent": "SignalDeck research"}
    ) as client:
        for url in dict.fromkeys(urls[:5]):
            item = Document(
                source_id=source_identity(url), url=url, retrieved_at=now, status="unavailable"
            )
            try:
                headers = {}
                if (urlsplit(url).hostname or "") in ("www.sec.gov", "sec.gov", "data.sec.gov"):
                    contact = os.environ.get("EDGAR_CONTACT_EMAIL")
                    if not contact:
                        raise ValueError("edgar_contact_not_configured")
                    headers["User-Agent"] = f"SignalDeck research {contact}"
                raw, kind = fetch(client, url, headers=headers)
                item.retrieved_at = datetime.now(UTC)
                item.document_digest = digest(raw)
                if "html" in kind:
                    parser = OriginalHTML()
                    parser.feed(raw.decode("utf-8", errors="replace"))
                    body = parser.body()
                    item.published_at = published.get(url) or parser.published
                elif kind.startswith("text/plain"):
                    body = raw.decode("utf-8", errors="replace").strip()
                else:
                    raise ValueError("unsupported_document_format")
                if not body:
                    raise ValueError("empty_document")
                item.status = "read"
                if item.published_at is None:
                    item.status = "publication_unknown"
                    item.gaps.append("publication_time_unknown; historical_availability_unverified")
                elif item.published_at >= bound:
                    item.status = "after_cutoff"
                    item.gaps.append("document_published_after_cutoff")
                    documents.append(item)
                    continue
                item.passages = select_passages(body)
                item.text = "\n\n".join(
                    f"[{p.title}; {p.locator}]\n{p.text}" for p in item.passages
                )
                item.excerpt = item.passages[0].text[:1600]
                item.locator = "; ".join(p.locator for p in item.passages)
                if sum(len(p.text) for p in item.passages) < len(body):
                    item.gaps.append("selected_passages_only; remainder_not_returned")
                if not item.source_id.startswith("sec:"):
                    item.gaps.append("source_authority_not_independently_confirmed")
            except httpx.HTTPError:
                # Do not echo upstream exceptions containing deployment headers/credentials.
                item.gaps.append("document_unavailable")
            except ValueError as exc:
                safe_codes = {
                    "public_https_url_required",
                    "document_size_limit",
                    "document_timeout",
                    "unsupported_document_format",
                    "empty_document",
                    "edgar_contact_not_configured",
                }
                item.gaps.append(str(exc) if str(exc) in safe_codes else "document_unavailable")
            documents.append(item)
    evidence = [
        ResearchEvidence(
            evidence_id=digest((d.source_id + (d.document_digest or "") + p.locator).encode()),
            source_id=d.source_id,
            kind="excerpt",
            title=p.title,
            url=d.url,
            published_at=d.published_at,
            retrieved_at=d.retrieved_at,
            text=p.text,
            locator=p.locator,
            verified=d.status == "read" and d.source_id.startswith("sec:"),
            source_type=(
                "sec"
                if (urlsplit(d.url).hostname or "") in ("www.sec.gov", "sec.gov", "data.sec.gov")
                else None
            ),
            uncertainty_reason="; ".join(d.gaps) or None,
        )
        for d in documents
        for p in d.passages
    ]
    document_evidence_ids = [e.evidence_id for e in evidence]
    insider_coverage = []
    if query.include_insider:
        from .research_documents_insider import insider_evidence

        insider, insider_status = insider_evidence(query, now, bound)
        evidence.extend(insider)
        insider_coverage.append(insider_status)
    document_gaps = [
        f"{d.url.split('?')[0].split('#')[0][:240]}: {gap}" for d in documents for gap in d.gaps
    ]
    if not documents:
        document_gaps.append("no_documents_selected_or_available")
    all_gaps = (
        discovery_gaps
        + document_gaps
        + ["insider: " + c.warning for c in insider_coverage if c.warning]
    )
    if len(evidence) > 30:
        all_gaps.append("evidence_truncated_to_30")
        evidence = evidence[:30]
        kept = {e.evidence_id for e in evidence}
        for coverage in insider_coverage:
            if not set(coverage.evidence_ids) <= kept:
                coverage.complete = False
                coverage.evidence_ids = [
                    identity for identity in coverage.evidence_ids if identity in kept
                ]
                coverage.warning = (coverage.warning or "") + "; evidence_truncated_to_30"
    return DocumentsResult(
        cutoff_at=bound,
        documents=documents,
        evidence=evidence,
        gaps=all_gaps[:100],
        coverage=insider_coverage
        + [
            SourceCoverage(
                source_id="documents",
                complete=bool(documents)
                and not discovery_gaps
                and all(d.status == "read" and not d.gaps for d in documents),
                observed_at=datetime.now(UTC),
                evidence_ids=document_evidence_ids,
                warning="; ".join(discovery_gaps + document_gaps)
                or ("no_documents_selected" if not documents else None),
            )
        ],
    )
