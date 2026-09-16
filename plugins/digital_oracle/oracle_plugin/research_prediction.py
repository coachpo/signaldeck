"""Explicit prediction identities and rule-bound current observations."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal
from urllib.parse import quote

import httpx
from plugin_runtime.common import CamelModel
from pydantic import Field, field_validator, model_validator

from .research_documents import SourceCoverage, cutoff, digest, fetch, timestamp
from .research_documents_evidence import ResearchEvidence
from .research_prediction_evidence import prediction_evidence


class SelectedEvent(CamelModel):
    venue: Literal["polymarket", "kalshi"]
    event_id: str | None = Field(default=None, min_length=1, max_length=160)
    contract_id: str | None = Field(default=None, min_length=1, max_length=160)
    hypothesis: str = Field(min_length=1, max_length=1000)
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def identity(self):
        if not self.event_id and not self.contract_id:
            raise ValueError("Explicit eventId or contractId required")
        return self


class PredictionQuery(CamelModel):
    as_of_date: date | None = None
    cutoff_at: datetime | None = None

    @field_validator("cutoff_at")
    @classmethod
    def aware(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("cutoffAt requires timezone")
        return value

    events: list[SelectedEvent] = Field(default_factory=list, max_length=3)


class PredictionSnapshot(CamelModel):
    venue: str
    event_id: str
    contract_id: str
    outcome: str
    token_id: str | None = None
    hypothesis: str
    reason: str
    source_id: str
    url: str
    retrieved_at: datetime
    document_digest: str
    rule_version: str | None = None
    rules: str | None = None
    resolution_source: str | None = None
    deadline: datetime | None = None
    status: str
    quoted_at: datetime | None = None
    quote_type: Literal["bid_ask"] = "bid_ask"
    bid: str | None = None
    ask: str | None = None
    volume: str | None = None
    liquidity: str | None = None
    gaps: list[str] = Field(default_factory=list)


class PredictionResult(CamelModel):
    schema_version: Literal["research-sources/v1"] = "research-sources/v1"
    cutoff_at: datetime
    snapshots: list[PredictionSnapshot]
    coverage: list[SourceCoverage] = Field(default_factory=list, max_length=30)
    evidence: list[ResearchEvidence] = Field(default_factory=list, max_length=300)
    gaps: list[str] = Field(default_factory=list)


def number(value) -> str | None:
    try:
        n = Decimal(str(value))
        return format(n, "f") if n.is_finite() and n >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def read_json(client, url):
    raw, _ = fetch(client, url)
    return json.loads(raw)


def array(value):
    return json.loads(value) if isinstance(value, str) else value or []


def _markets(client, selected):
    identity = quote(selected.contract_id or selected.event_id, safe="")
    if selected.venue == "polymarket":
        base = "https://gamma-api.polymarket.com"
        if selected.contract_id:
            url = f"{base}/markets/{identity}"
            market = read_json(client, url)
            if str(market.get("id")) != selected.contract_id:
                raise ValueError("contract_identity_mismatch")
            if selected.event_id and not any(
                str(e.get("id")) == selected.event_id for e in market.get("events", [])
            ):
                raise ValueError("event_identity_mismatch")
            return [market], url
        url = f"{base}/events/{identity}"
        event = read_json(client, url)
        if str(event.get("id")) != selected.event_id:
            raise ValueError("event_identity_mismatch")
        return event.get("markets", []), url
    base = "https://api.elections.kalshi.com/trade-api/v2"
    if selected.contract_id:
        url = f"{base}/markets/{identity}"
        market = read_json(client, url)["market"]
        if market.get("ticker") != selected.contract_id or (
            selected.event_id and market.get("event_ticker") != selected.event_id
        ):
            raise ValueError("contract_identity_mismatch")
        return [market], url
    url = f"{base}/events/{identity}?with_nested_markets=true"
    data = read_json(client, url)
    event = data["event"]
    if event.get("event_ticker") != selected.event_id:
        raise ValueError("event_identity_mismatch")
    return event.get("markets", data.get("markets", [])), url


def _snapshots(client, selected, market, url, now):
    poly = selected.venue == "polymarket"
    contract = str(market["id"] if poly else market["ticker"])
    event = selected.event_id or (
        str((market.get("events") or [{}])[0].get("id", ""))
        if poly
        else market.get("event_ticker", "")
    )
    rules = str(
        market.get("description", "")
        if poly
        else "\n".join(filter(None, [market.get("rules_primary"), market.get("rules_secondary")]))
    )
    resolution = market.get("resolutionSource") if poly else url
    rule_version = (
        digest(json.dumps([rules, resolution], ensure_ascii=False).encode()) if rules else None
    )
    outcomes = array(market.get("outcomes")) if poly else ["Yes", "No"]
    tokens = array(market.get("clobTokenIds")) if poly else []
    for i, outcome in enumerate(outcomes[:2]):
        snapshot = PredictionSnapshot(
            venue=selected.venue,
            event_id=event,
            contract_id=contract,
            outcome=str(outcome),
            hypothesis=selected.hypothesis,
            reason=selected.reason,
            source_id=f"{selected.venue}:{contract}",
            url=url,
            retrieved_at=now,
            document_digest=digest(json.dumps(market, sort_keys=True).encode()),
            rules=rules[:12000] or None,
            rule_version=rule_version,
            resolution_source=resolution,
            deadline=timestamp(market.get("endDate") if poly else market.get("close_time")),
            status=(
                ("closed" if market.get("closed") else "active")
                if poly
                else str(market.get("status", "unknown"))
            ),
            volume=number(market.get("volume") if poly else market.get("volume_fp")),
            liquidity=number(market.get("liquidity")) if poly else None,
        )
        if not rules:
            snapshot.gaps.append("settlement_rules_missing")
        if not resolution:
            snapshot.gaps.append("resolution_source_missing")
        if poly and i < len(tokens):
            snapshot.token_id = str(tokens[i])
            try:
                book = read_json(
                    client,
                    "https://clob.polymarket.com/book?token_id="
                    + quote(snapshot.token_id, safe=""),
                )
                if str(book.get("asset_id")) != snapshot.token_id:
                    raise ValueError("token_identity_mismatch")
                snapshot.quoted_at = datetime.fromtimestamp(
                    float(Decimal(str(book["timestamp"])) / 1000), UTC
                )
                bids = [
                    Decimal(n)
                    for p in book.get("bids", [])
                    if (n := number(p.get("price"))) is not None and Decimal(n) <= 1
                ]
                asks = [
                    Decimal(n)
                    for p in book.get("asks", [])
                    if (n := number(p.get("price"))) is not None and Decimal(n) <= 1
                ]
                snapshot.bid = str(max(bids)) if bids else None
                snapshot.ask = str(min(asks)) if asks else None
            except (
                httpx.HTTPError,
                ValueError,
                KeyError,
                TypeError,
                InvalidOperation,
                OverflowError,
            ):
                snapshot.gaps.append("orderbook_unavailable")
        else:
            # Kalshi updated_time is metadata time, not an exchange quote timestamp.
            side = "yes" if i == 0 else "no"
            snapshot.bid = number(market.get(side + "_bid_dollars"))
            snapshot.ask = number(market.get(side + "_ask_dollars"))
        if snapshot.bid is not None and Decimal(snapshot.bid) > 1:
            snapshot.bid = None
        if snapshot.ask is not None and Decimal(snapshot.ask) > 1:
            snapshot.ask = None
        if snapshot.bid is None or snapshot.ask is None:
            snapshot.gaps.append("bid_ask_incomplete")
        if snapshot.deadline is None:
            snapshot.gaps.append("deadline_unknown")
        if snapshot.quoted_at is None:
            snapshot.gaps.append("quote_time_unknown; no_historical_comparison")
        snapshot.retrieved_at = datetime.now(UTC)
        yield snapshot


def lookup_prediction(arguments: dict) -> PredictionResult:
    query = PredictionQuery.model_validate(arguments)
    now = datetime.now(UTC)
    bound = cutoff(query, now)
    result = PredictionResult(cutoff_at=bound, snapshots=[])
    if not query.events:
        result.gaps.append("prediction_selection_empty")
    with httpx.Client(timeout=httpx.Timeout(10)) as client:
        for selected in query.events:
            try:
                markets, url = _markets(client, selected)
                if len(markets) > 3:
                    result.gaps.append(
                        f"{selected.venue}:event_contracts_truncated_to_3; select_explicit_contract"
                    )
                for market in markets[:3]:
                    for snapshot in _snapshots(client, selected, market, url, now):
                        historical_date = query.as_of_date is not None and bound.date() < now.date()
                        if (
                            historical_date
                            or (snapshot.quoted_at and snapshot.quoted_at >= bound)
                            or (bound < now and snapshot.quoted_at is None)
                        ):
                            snapshot.bid = snapshot.ask = snapshot.volume = snapshot.liquidity = (
                                None
                            )
                            snapshot.gaps.append("historical_quote_unavailable_at_cutoff")
                        if bound < now:
                            # Current market aggregate fields have no historical timestamp.
                            snapshot.volume = snapshot.liquidity = None
                        result.snapshots.append(snapshot)
            except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError):
                result.gaps.append(f"{selected.venue}:selected_event_unavailable")
    result.evidence = [prediction_evidence(snap) for snap in result.snapshots]
    result.coverage = [
        SourceCoverage(
            source_id="prediction",
            complete=bool(result.snapshots)
            and not result.gaps
            and all(not s.gaps for s in result.snapshots),
            observed_at=datetime.now(UTC),
            evidence_ids=[e.evidence_id for e in result.evidence],
            warning="; ".join(result.gaps + [g for s in result.snapshots for g in s.gaps]) or None,
        )
    ]
    return result
