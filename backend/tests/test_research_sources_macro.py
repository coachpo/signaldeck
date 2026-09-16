"""FRED vintage evidence separates observed periods from date-precision availability."""

import sys
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"
for directory in ("runtime", "digital_oracle"):
    sys.path.insert(0, str(PLUGINS / directory))

from oracle_plugin import research_macro  # noqa: E402
from oracle_plugin.research_macro import DEFAULT_SERIES, lookup_macro_evidence  # noqa: E402


@pytest.fixture
def fred_http(monkeypatch):
    original = httpx.Client
    monkeypatch.setenv("FRED_API_KEY", "private-test-key")

    def install(handler):
        monkeypatch.setattr(
            httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw)
        )

    return install


def responder(request):
    series = request.url.params["series_id"]
    if request.url.path == "/fred/series":
        return httpx.Response(
            200,
            json={
                "seriess": [
                    {"id": series, "title": "Consumer price index", "units": "Index 1982-1984=100"}
                ]
            },
        )
    return httpx.Response(200, json={"observations": [{"date": "2026-01-01", "value": "320.125"}]})


def test_fred_vintage_is_available_date_not_observation_or_publication(fred_http):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.params["realtime_start"] == "2026-03-08"
        assert request.url.params["realtime_end"] == "2026-03-08"
        return responder(request)

    fred_http(handler)
    result = lookup_macro_evidence({"asOfDate": "2026-03-08"})
    assert len(calls) == 10
    assert {e.metric for e in result.evidence} == set(DEFAULT_SERIES)
    assert result.coverage[0].complete
    for item in result.evidence:
        assert item.available_by_date == date(2026, 3, 8)
        assert item.period_end == date(2026, 1, 1)
        assert item.published_at is None and item.publication_date is None
        assert item.unit == "Index 1982-1984=100"
        assert item.verified
    assert "private-test-key" not in result.model_dump_json()


def test_intraday_and_future_cutoff_use_latest_complete_ny_date(fred_http, monkeypatch):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 3, 9, 15, tzinfo=UTC)

    monkeypatch.setattr(research_macro, "datetime", FrozenDateTime)
    fred_http(responder)
    current = lookup_macro_evidence({"seriesIds": ["CPIAUCSL"], "asOfDate": "2028-01-01"})
    assert current.available_by_date == date(2026, 3, 8)
    assert current.cutoff_at == datetime(2026, 3, 9, 15, tzinfo=UTC)
    intraday = lookup_macro_evidence(
        {"seriesIds": ["CPIAUCSL"], "cutoffAt": "2026-03-08T16:00:00Z"}
    )
    assert intraday.available_by_date == date(2026, 3, 7)


def test_optional_fred_failure_preserves_other_series(fred_http):
    def handler(request):
        return (
            httpx.Response(429)
            if request.url.params["series_id"] == "UNRATE"
            else responder(request)
        )

    fred_http(handler)
    result = lookup_macro_evidence({"seriesIds": ["CPIAUCSL", "UNRATE"], "asOfDate": "2026-03-08"})
    assert len(result.evidence) == 1
    assert result.gaps == ["UNRATE:fred_vintage_unavailable"]
    assert not result.coverage[0].complete


def test_macro_budget_stops_before_issuing_more_requests(fred_http, monkeypatch):
    calls = []
    times = iter([0, 0, 20, 20, 20, 20, 20])
    monkeypatch.setattr(research_macro, "monotonic", lambda: next(times))
    fred_http(lambda request: calls.append(request) or responder(request))
    result = lookup_macro_evidence({"asOfDate": "2026-03-08"})
    assert len(calls) == 1
    assert not result.evidence
    assert len(result.gaps) == 5


def test_macro_missing_config_never_fetches(fred_http, monkeypatch):
    monkeypatch.delenv("FRED_API_KEY")
    fred_http(lambda request: pytest.fail("must not issue request"))
    assert lookup_macro_evidence({}).gaps == ["fred_api_key_not_configured"]
