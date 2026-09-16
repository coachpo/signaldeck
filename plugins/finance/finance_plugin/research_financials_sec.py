"""Bounded SEC companyfacts ingestion with accession-based publication cutoffs."""

import hashlib
import os
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import httpx

from .research_financials_models import METRIC_TAGS, FinancialFact, FinancialGap

NY = ZoneInfo("America/New_York")


def identifier(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()[:32]


def research_cutoff(as_of_date: date | None, now: datetime) -> datetime:
    if as_of_date is None:
        return now.astimezone(UTC)
    end = datetime.combine(as_of_date + timedelta(days=1), time.min, NY).astimezone(UTC)
    return min(now.astimezone(UTC), end)


def period_type(start: date | None, end: date) -> str:
    if start is None:
        return "instant"
    days = (end - start).days + 1
    if 77 <= days <= 105:
        return "quarterly"
    if 350 <= days <= 378:
        return "annual"
    if 150 <= days <= 294:
        return "year_to_date"
    return "other"


def filing_index(submissions: dict) -> dict[str, dict]:
    recent = submissions.get("filings", {}).get("recent", submissions)
    return {
        accession: {
            key: values[index]
            for key, values in recent.items()
            if isinstance(values, list) and index < len(values)
        }
        for index, accession in enumerate(recent.get("accessionNumber", []))
    }


def parse_facts(
    company: dict, filings: dict, cutoff: datetime
) -> tuple[list[FinancialFact], list[FinancialGap]]:
    facts: list[FinancialFact] = []
    gaps: list[FinancialGap] = []
    taxonomy = company.get("facts", {}).get("us-gaap", {})
    for metric, tags in METRIC_TAGS.items():
        for tag in tags:
            for unit, observations in taxonomy.get(tag, {}).get("units", {}).items():
                expected_unit = "shares" if "shares" in metric else "USD"
                if unit != expected_unit:
                    gaps.append(
                        FinancialGap(
                            code="unsupported_unit",
                            metric=metric,
                            message=(
                                f"Unsupported unit {unit} for {tag}; no currency conversion or "
                                f"unit mixing."
                            ),
                        )
                    )
                    continue
                for row in observations:
                    fact = _parse_fact(metric, tag, unit, row, filings, cutoff, company["cik"])
                    if fact is not None:
                        facts.append(fact)
        if not any(f.metric == metric for f in facts):
            gaps.append(
                FinancialGap(
                    code="metric_missing",
                    metric=metric,
                    message="No supported standard-taxonomy fact visible by cutoff.",
                )
            )
    for row in (
        company.get("facts", {})
        .get("dei", {})
        .get("EntityCommonStockSharesOutstanding", {})
        .get("units", {})
        .get("shares", [])
    ):
        fact = _parse_fact(
            "shares_outstanding",
            "EntityCommonStockSharesOutstanding",
            "shares",
            row,
            filings,
            cutoff,
            company["cik"],
        )
        if fact is not None:
            fact.taxonomy = "dei"
            fact.locator = fact.locator.replace("us-gaap:", "dei:")
            facts.append(fact)
    # Identical same-filing revenue aliases are one fact, with every tag retained.
    aliases = {}
    for fact in facts:
        key = (
            fact.metric,
            fact.unit,
            fact.period_start,
            fact.period_end,
            fact.accession,
            fact.value,
        )
        if key in aliases:
            aliases[key].alias_tags.append(fact.tag)
        else:
            aliases[key] = fact
    facts = list(aliases.values())
    # fy/fp describe the filing focus, not necessarily the fact's actual period.
    unique = {f.evidence_id: f for f in facts}
    groups: dict[tuple, list[FinancialFact]] = {}
    for fact in unique.values():
        groups.setdefault(
            (fact.metric, fact.tag, fact.unit, fact.period_start, fact.period_end), []
        ).append(fact)
    for versions in groups.values():
        versions.sort(
            key=lambda f: (f.accepted_at or datetime.combine(f.filed_at, time.max, NY), f.accession)
        )
        for fact in versions[:-1]:
            fact.selected = False
        for index, fact in enumerate(versions):
            fact.supersedes_evidence_ids = [f.evidence_id for f in versions[:index]]
    for metric in METRIC_TAGS:
        chosen = [f for f in unique.values() if f.selected and f.metric == metric]
        periods = {(f.period_start, f.period_end) for f in chosen}
        for period in periods:
            if sum((f.period_start, f.period_end) == period for f in chosen) > 1:
                gaps.append(
                    FinancialGap(
                        code="ambiguous_concept",
                        metric=metric,
                        period_end=period[1],
                        message=(
                            "Conflicting standard concepts for the same period; "
                            "no preferred alias."
                        ),
                    )
                )
    return sorted(unique.values(), key=lambda f: (f.period_end, f.metric, f.accession)), gaps


def _parse_fact(metric, tag, unit, row, filings, cutoff, cik):
    if row.get("form") not in {"10-K", "10-K/A", "10-Q", "10-Q/A"}:
        return None
    try:
        filed = date.fromisoformat(row["filed"])
        start = date.fromisoformat(row["start"]) if row.get("start") else None
        end = date.fromisoformat(row["end"])
        value = Decimal(str(row["val"]))
        if not value.is_finite() or (start and start > end):
            return None
        accession = row["accn"]
        filing = filings.get(accession, {})
        accepted = (
            datetime.fromisoformat(filing["acceptanceDateTime"].replace("Z", "+00:00"))
            if filing.get("acceptanceDateTime")
            else None
        )
        if accepted and accepted.tzinfo is None:
            accepted = accepted.replace(tzinfo=NY)
        # Date-only availability is conservative, never an invented intraday timestamp.
        public_bound = accepted or datetime.combine(filed + timedelta(days=1), time.min, NY)
        if (accepted and public_bound >= cutoff) or (not accepted and public_bound > cutoff):
            return None
        expected = "shares" if "shares" in metric else "USD"
        if unit != expected:
            return None
        source_id = f"sec:{accession}"
        return FinancialFact(
            evidence_id=identifier(source_id, tag, unit, start, end, value),
            source_id=source_id,
            metric=metric,
            taxonomy="us-gaap",
            tag=tag,
            value=format(value, "f"),
            unit=unit,
            currency="USD" if unit == "USD" else None,
            period_start=start,
            period_end=end,
            period_type=period_type(start, end),
            fiscal_year=row.get("fy"),
            fiscal_period=row.get("fp"),
            accession=accession,
            form=row["form"],
            filed_at=filed,
            accepted_at=accepted,
            locator=f"us-gaap:{tag}; unit={unit}; start={start}; end={end}; accession={accession}",
            excerpt=f"{tag}: {format(value, 'f')} {unit}; {start or 'instant'} to {end}",
        )
    except (KeyError, ValueError, TypeError, InvalidOperation):
        return None


class SecFinancialsProvider:
    def __init__(self, *, timeout: float = 15, transport=None):
        self.timeout = timeout
        self.transport = transport

    def fetch(
        self,
        symbol: str,
        as_of_date: date | None = None,
        *,
        now: datetime | None = None,
        cutoff_at: datetime | None = None,
    ):
        observed = now or datetime.now(UTC)
        cutoff = (
            min(research_cutoff(as_of_date, observed), cutoff_at)
            if cutoff_at
            else research_cutoff(as_of_date, observed)
        )
        contact = os.environ.get("EDGAR_CONTACT_EMAIL", "").strip()
        if not contact:
            raise ValueError(
                "SEC financials require EDGAR_CONTACT_EMAIL in the Finance deployment environment"
            )
        with httpx.Client(
            timeout=self.timeout,
            transport=self.transport,
            headers={"User-Agent": f"SignalDeck research {contact}", "Accept": "application/json"},
        ) as client:

            def get(url):
                response = client.get(url)
                response.raise_for_status()
                return response.json()

            tickers = get("https://www.sec.gov/files/company_tickers.json")
            match = next(
                (r for r in tickers.values() if r["ticker"].upper() == symbol.upper()), None
            )
            if not match:
                raise ValueError("Symbol is not present in SEC's company ticker directory")
            cik = str(match["cik_str"]).zfill(10)
            submissions = get(f"https://data.sec.gov/submissions/CIK{cik}.json")
            company = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
        filings = filing_index(submissions)
        facts, gaps = parse_facts(company, filings, cutoff)
        gaps.append(
            FinancialGap(
                code="coverage_limit",
                metric="all",
                message=(
                    "Standard entity-wide US GAAP only; recent submissions only. "
                    "Historical availability without acceptance metadata is date "
                    "precision; companyfacts is a current aggregate."
                ),
            )
        )
        return cik, observed, cutoff, facts, filings, gaps
