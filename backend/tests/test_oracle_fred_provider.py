"""FRED observations retain their time window, vintage and native measurement units."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"
for directory in ("runtime", "digital_oracle"):
    sys.path.insert(0, str(PLUGINS / directory))

from oracle_plugin.config import reset_digital_oracle_settings_cache  # noqa: E402
from oracle_plugin.contracts import RuntimeToolContext  # noqa: E402
from oracle_plugin.runtime_macro_rates import (  # noqa: E402
    execute_macro_rates_lookup,
    parse_macro_rates_lookup_arguments,
)

_TEST_KEY = "fred-test-credential"
_SERIES = {
    "CPIAUCSL": ("Consumer Price Index for All Urban Consumers", "Index 1982-1984=100"),
    "GDP": ("Gross Domestic Product", "Billions of Dollars"),
    "UNRATE": ("Unemployment Rate", "Percent"),
}


@pytest.fixture
def mock_fred(monkeypatch: pytest.MonkeyPatch):
    client_class = httpx.Client

    def install(handler: Callable[[httpx.Request], httpx.Response]) -> None:
        monkeypatch.setattr(
            "oracle_plugin.runtime_macro_rates_client.httpx.Client",
            lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs),
        )

    reset_digital_oracle_settings_cache()
    yield install
    reset_digital_oracle_settings_cache()


def _lookup(**arguments: object) -> dict[str, object]:
    return execute_macro_rates_lookup(
        RuntimeToolContext(secrets={"fred_api_key": _TEST_KEY}),
        parse_macro_rates_lookup_arguments(json.dumps({"sources": ["fred"], **arguments})),
    )


def _metadata(series_id: str) -> dict[str, object]:
    title, unit = _SERIES[series_id]
    return {"seriess": [{"id": series_id, "title": title, "units": unit}]}


def test_fred_returns_recent_window_and_each_requested_series_with_native_units(mock_fred) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        params = request.url.params
        series_id = params["series_id"]
        assert params["api_key"] == _TEST_KEY
        if request.url.path == "/fred/series":
            return httpx.Response(200, json=_metadata(series_id))
        # Model the upstream default (ascending dates) so a missing sort/window regresses.
        observations = [
            {"date": "1950-01-01", "value": "10"},
            {"date": "2026-01-01", "value": "100"},
            {"date": "2026-02-01", "value": "101"},
            {"date": "2026-03-01", "value": "102"},
            {"date": "2026-04-01", "value": "103"},
        ]
        observations = [
            row
            for row in observations
            if params.get("observation_start", "0001-01-01")
            <= row["date"]
            <= params.get("observation_end", "9999-12-31")
        ]
        observations.sort(key=lambda row: row["date"], reverse=params.get("sort_order") == "desc")
        return httpx.Response(200, json={"observations": observations[: int(params["limit"])]})

    mock_fred(respond)
    payload = _lookup(
        seriesIds=list(_SERIES), startDate="2026-01-01", endDate="2026-03-31", itemLimit=5
    )
    series = payload["series"]
    assert len(series) == 5
    assert {row["seriesId"] for row in series} == set(_SERIES)
    assert {row["date"] for row in series} == {"2026-02-01", "2026-03-01"}
    for row in series:
        assert (row["label"], row["unit"]) == _SERIES[row["seriesId"]]
        assert row["currency"] is None
        assert row["sourceUrl"] == f"https://fred.stlouisfed.org/series/{row['seriesId']}"
    observations = [request for request in requests if request.url.path.endswith("observations")]
    assert [request.url.params["limit"] for request in observations] == ["2", "2", "1"]
    assert all(request.url.params["units"] == "lin" for request in observations)
    assert payload["warnings"] == []
    assert _TEST_KEY not in json.dumps(payload)


def test_fred_as_of_excludes_unpublished_observations_and_later_revisions(mock_fred) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        params = request.url.params
        cutoff = params.get("realtime_end", "9999-12-31")
        if request.url.path == "/fred/series":
            return httpx.Response(200, json=_metadata("GDP"))
        return httpx.Response(
            200,
            json={
                "observations": (
                    [
                        {"date": "2026-04-01", "value": "32000"},
                        {"date": "2026-01-01", "value": "31000"},
                    ]
                    if cutoff >= "2026-07-30"
                    else [{"date": "2026-01-01", "value": "30000"}]
                )
            },
        )

    mock_fred(respond)
    payload = _lookup(
        seriesIds=["GDP"],
        startDate="2026-01-01",
        endDate="2026-12-31",
        asOfDate="2026-06-15",
        itemLimit=2,
    )
    assert [(row["date"], row["value"]) for row in payload["series"]] == [("2026-01-01", "30000")]
    assert all(
        request.url.params["realtime_start"] == request.url.params["realtime_end"] == "2026-06-15"
        for request in requests
    )
    assert requests[-1].url.params["observation_end"] == "2026-06-15"
    assert payload["warnings"] == []


def test_fred_without_dates_returns_latest_observations(mock_fred) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/fred/series":
            return httpx.Response(200, json=_metadata("UNRATE"))
        assert request.url.params["sort_order"] == "desc"
        assert request.url.params["limit"] == "1"
        assert "observation_end" not in request.url.params
        assert "realtime_start" not in request.url.params
        return httpx.Response(200, json={"observations": [{"date": "2026-08-01", "value": "4.1"}]})

    mock_fred(respond)
    payload = _lookup(seriesIds=["UNRATE"], itemLimit=1)
    assert payload["series"][0]["date"] == "2026-08-01"
    assert payload["warnings"] == []


def test_fred_window_after_as_of_returns_empty_without_invalid_upstream_query(mock_fred) -> None:
    def unexpected_request(request: httpx.Request) -> httpx.Response:
        pytest.fail("The window is empty before any FRED request is necessary.")

    mock_fred(unexpected_request)
    payload = _lookup(seriesIds=["GDP"], startDate="2026-07-01", asOfDate="2026-06-15", itemLimit=1)
    assert payload["series"] == []
    assert "macro_rates_empty" in {warning["code"] for warning in payload["warnings"]}


@pytest.mark.parametrize("failure_path", ["/fred/series", "/fred/series/observations"])
def test_fred_errors_do_not_expose_key_or_response_body(mock_fred, failure_path: str) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == failure_path:
            return httpx.Response(429, text=f"Provider rejected {request.url} {_TEST_KEY}")
        return httpx.Response(200, json=_metadata("GDP"))

    mock_fred(respond)
    payload = _lookup(seriesIds=["GDP"], itemLimit=1)
    assert payload["series"] == []
    assert "macro_rates_provider_rate_limited" in {
        warning["code"] for warning in payload["warnings"]
    }
    assert _TEST_KEY not in json.dumps(payload)
    assert "Provider rejected" not in json.dumps(payload)


def test_fred_missing_unit_is_reported_instead_of_inventing_percent(mock_fred) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/fred/series"
        return httpx.Response(200, json={"seriess": [{"id": "GDP", "title": "GDP"}]})

    mock_fred(respond)
    payload = _lookup(seriesIds=["GDP"], itemLimit=1)
    assert payload["series"] == []
    assert payload["warnings"][0]["message"] == "fred returned malformed series metadata"
