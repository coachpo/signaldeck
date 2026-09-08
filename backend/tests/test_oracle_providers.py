"""Independent oracle provider parsing, bounded inputs and safe degradation contracts."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"
for directory in ("runtime", "digital_oracle"):
    sys.path.insert(0, str(PLUGINS / directory))


from oracle_plugin.config import (  # noqa: E402
    DIGITAL_ORACLE_PHASE1_PROVIDER_BOUNDARY,
    DIGITAL_ORACLE_PHASE1_REQUIRES_VENDORED_PACKAGE,
    DIGITAL_ORACLE_PHASE1_REQUIRES_YFINANCE,
    EDGAR_CONTACT_EMAIL_MISSING_CODE,
    EDGAR_CONTACT_EMAIL_MISSING_MESSAGE,
    EDGAR_CONTACT_EMAIL_SECRET,
    FRED_API_KEY_MISSING_CODE,
    FRED_API_KEY_MISSING_MESSAGE,
    FRED_API_KEY_SECRET,
    MARKET_SENTIMENT_SOURCE_URL,
    CryptoDerivativesVenue,
    DigitalOracleSettings,
    MacroRatesSource,
    PredictionMarketVenue,
    get_digital_oracle_provider_config,
    reset_digital_oracle_settings_cache,
)
from oracle_plugin.contracts import (  # noqa: E402
    RuntimeToolContext,
    RuntimeToolError,
    RuntimeToolWarning,
)
from oracle_plugin.factory import (  # noqa: E402
    DigitalOracleProviderFailure,
    DigitalOracleProviderSecrets,
    create_digital_oracle_phase1_provider_bundle,
    create_prediction_markets_provider_bundle,
    create_sec_filings_provider,
)
from oracle_plugin.mappers import (  # noqa: E402
    map_cftc_positioning_result,
    map_crypto_derivatives_result,
    map_macro_rates_result,
    map_market_sentiment_result,
    map_options_result,
    map_prediction_markets_result,
    map_sec_filings_result,
)
from oracle_plugin.ownership import DIGITAL_ORACLE_EXTENSION_KEY  # noqa: E402
from oracle_plugin.runtime_cftc_positioning import (  # noqa: E402
    CFTC_POSITIONING_LOOKUP_OPENAI_FUNCTION_NAME,
    CFTC_POSITIONING_LOOKUP_TOOL_SPEC,
    CftcCotPositioningProvider,
    execute_cftc_positioning_lookup,
    parse_cftc_positioning_lookup_arguments,
)
from oracle_plugin.runtime_crypto_derivatives import (  # noqa: E402
    CRYPTO_DERIVATIVES_LOOKUP_OPENAI_FUNCTION_NAME,
    CRYPTO_DERIVATIVES_LOOKUP_TOOL_SPEC,
    CoinGeckoCryptoDerivativesProvider,
    DeribitCryptoDerivativesProvider,
    execute_crypto_derivatives_lookup,
    parse_crypto_derivatives_lookup_arguments,
)
from oracle_plugin.runtime_macro_rates import (  # noqa: E402
    MACRO_RATES_LOOKUP_OPENAI_FUNCTION_NAME,
    MACRO_RATES_LOOKUP_TOOL_SPEC,
    BisMacroRatesProvider,
    FredMacroRatesProvider,
    TreasuryMacroRatesProvider,
    execute_macro_rates_lookup,
    parse_macro_rates_lookup_arguments,
)
from oracle_plugin.runtime_market_sentiment import (  # noqa: E402
    MARKET_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
    MARKET_SENTIMENT_LOOKUP_TOOL_SPEC,
    FearGreedMarketSentimentProvider,
    execute_market_sentiment_lookup,
    parse_market_sentiment_lookup_arguments,
)
from oracle_plugin.runtime_options import (  # noqa: E402
    OPTIONS_LOOKUP_OPENAI_FUNCTION_NAME,
    OPTIONS_LOOKUP_TOOL_SPEC,
    YahooOptionsProvider,
    execute_options_lookup,
    parse_options_lookup_arguments,
)
from oracle_plugin.runtime_prediction_markets import (  # noqa: E402
    PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME,
    PREDICTION_MARKETS_LOOKUP_TOOL_SPEC,
    KalshiPredictionMarketsProvider,
    PolymarketPredictionMarketsProvider,
    execute_prediction_markets_lookup,
    parse_prediction_markets_lookup_arguments,
)
from oracle_plugin.runtime_sec_filings import (  # noqa: E402
    SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME,
    SEC_FILINGS_LOOKUP_TOOL_SPEC,
    EdgarSecFilingsProvider,
    execute_sec_filings_lookup,
    parse_sec_filings_lookup_arguments,
)
from oracle_plugin.runtime_types import (  # noqa: E402
    CFTC_POSITIONING_LOOKUP_TOOL_KEY,
    CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY,
    MACRO_RATES_LOOKUP_TOOL_KEY,
    MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
    OPTIONS_LOOKUP_TOOL_KEY,
    PREDICTION_MARKETS_LOOKUP_TOOL_KEY,
    SEC_FILINGS_LOOKUP_TOOL_KEY,
    RuntimeCftcPositioningLookupResult,
    RuntimeCryptoDerivativesLookupResult,
    RuntimeDigitalOracleUnavailableLookupResult,
    RuntimeMacroRatesLookupResult,
    RuntimeMarketSentimentLookupResult,
    RuntimeOptionsLookupResult,
    RuntimePredictionMarketsLookupResult,
    RuntimeSecFilingsLookupResult,
)
from oracle_plugin.service import DigitalOraclePhase1Service  # noqa: E402
from oracle_plugin.types import (  # noqa: E402
    DigitalOracleCftcPositioningProviderQuery,
    DigitalOracleCftcPositioningProviderResult,
    DigitalOracleCftcPositioningQuery,
    DigitalOracleCftcPositioningReport,
    DigitalOracleCftcPositioningResult,
    DigitalOracleCftcPositioningRow,
    DigitalOracleCryptoDerivativesGlobalMetrics,
    DigitalOracleCryptoDerivativesOptionSummary,
    DigitalOracleCryptoDerivativesOrderBook,
    DigitalOracleCryptoDerivativesOrderBookLevel,
    DigitalOracleCryptoDerivativesProviderQuery,
    DigitalOracleCryptoDerivativesProviderResult,
    DigitalOracleCryptoDerivativesQuery,
    DigitalOracleCryptoDerivativesResult,
    DigitalOracleCryptoDerivativesSpotQuote,
    DigitalOracleCryptoDerivativesTermPoint,
    DigitalOracleMacroRatesProviderQuery,
    DigitalOracleMacroRatesProviderResult,
    DigitalOracleMacroRatesResult,
    DigitalOracleMacroRatesSeries,
    DigitalOracleMarketSentimentProviderQuery,
    DigitalOracleMarketSentimentProviderResult,
    DigitalOracleMarketSentimentQuery,
    DigitalOracleOptionContract,
    DigitalOracleOptionGreeks,
    DigitalOracleOptionsChain,
    DigitalOracleOptionsProviderQuery,
    DigitalOracleOptionsProviderResult,
    DigitalOracleOptionsQuery,
    DigitalOracleOptionsResult,
    DigitalOraclePredictionMarketContract,
    DigitalOraclePredictionMarketEvent,
    DigitalOraclePredictionMarketOrderBook,
    DigitalOraclePredictionMarketOrderBookLevel,
    DigitalOraclePredictionMarketsProviderQuery,
    DigitalOraclePredictionMarketsProviderResult,
    DigitalOraclePredictionMarketsQuery,
    DigitalOracleProviderError,
    DigitalOracleSecFiling,
    DigitalOracleSecFilingsProviderQuery,
    DigitalOracleSecFilingsProviderResult,
    DigitalOracleSecFilingsQuery,
    DigitalOracleSecFilingsResult,
    DigitalOracleSecOwnershipTransaction,
    DigitalOracleSecSearchHit,
)


class FakeDigitalOracleProvider:

    def __init__(
        self,
        provider: str | DigitalOracleMarketSentimentProviderResult = "fake",
        *,
        events: Sequence[DigitalOraclePredictionMarketEvent] = (),
        warnings: Sequence[RuntimeToolWarning] = (),
        result: object | None = None,
        series: Sequence[DigitalOracleMacroRatesSeries] = (),
        failure: DigitalOracleProviderError | None = None,
    ) -> None:
        if isinstance(provider, DigitalOracleMarketSentimentProviderResult):
            result = provider
            provider = provider.provider
        if provider == "fake" and isinstance(
            result,
            (
                DigitalOracleCftcPositioningProviderResult,
                DigitalOracleCryptoDerivativesProviderResult,
                DigitalOracleMacroRatesProviderResult,
                DigitalOracleMarketSentimentProviderResult,
                DigitalOracleOptionsProviderResult,
                DigitalOraclePredictionMarketsProviderResult,
            ),
        ):
            provider = result.provider
        if provider == "fake" and failure is not None:
            provider = cast(str, failure.details.get("provider", provider))
        self.provider_name = provider
        self.source = cast(MacroRatesSource, provider)
        self.venue = cast(PredictionMarketVenue | CryptoDerivativesVenue, provider)
        self.events = tuple(events)
        self.warnings = tuple(warnings)
        self.result = result
        self.series = tuple(series)
        self.failure = failure
        self.calls: list[object] = []

    def _record_or_fail(self, query: object) -> None:
        self.calls.append(query)
        if self.failure is not None:
            raise self.failure

    def lookup_prediction_markets(
        self, query: DigitalOraclePredictionMarketsProviderQuery
    ) -> DigitalOraclePredictionMarketsProviderResult:
        self._record_or_fail(query)
        return DigitalOraclePredictionMarketsProviderResult(
            provider=cast(PredictionMarketVenue, self.provider_name),
            events=self.events,
            warnings=self.warnings,
        )

    def lookup_market_sentiment(
        self, query: DigitalOracleMarketSentimentProviderQuery
    ) -> DigitalOracleMarketSentimentProviderResult:
        self._record_or_fail(query)
        if self.result is not None:
            return cast(DigitalOracleMarketSentimentProviderResult, self.result)
        return DigitalOracleMarketSentimentProviderResult(provider=self.provider_name)

    def lookup_macro_rates(
        self, query: DigitalOracleMacroRatesProviderQuery
    ) -> DigitalOracleMacroRatesProviderResult:
        self._record_or_fail(query)
        if self.result is not None:
            return cast(DigitalOracleMacroRatesProviderResult, self.result)
        return DigitalOracleMacroRatesProviderResult(
            provider=cast(MacroRatesSource, self.provider_name), series=self.series
        )

    def lookup_crypto_derivatives(
        self, query: DigitalOracleCryptoDerivativesProviderQuery
    ) -> DigitalOracleCryptoDerivativesProviderResult:
        self._record_or_fail(query)
        if self.result is not None:
            return cast(DigitalOracleCryptoDerivativesProviderResult, self.result)
        return DigitalOracleCryptoDerivativesProviderResult(
            provider=cast(CryptoDerivativesVenue, self.provider_name)
        )

    def lookup_cftc_positioning(
        self, query: DigitalOracleCftcPositioningProviderQuery
    ) -> DigitalOracleCftcPositioningProviderResult:
        self._record_or_fail(query)
        if self.result is not None:
            return cast(DigitalOracleCftcPositioningProviderResult, self.result)
        return DigitalOracleCftcPositioningProviderResult(provider=self.provider_name)

    def lookup_options(
        self, query: DigitalOracleOptionsProviderQuery
    ) -> DigitalOracleOptionsProviderResult:
        self._record_or_fail(query)
        if self.result is not None:
            return cast(DigitalOracleOptionsProviderResult, self.result)
        return DigitalOracleOptionsProviderResult(provider=self.provider_name)


class FakeDigitalOracleSecFilingsProvider:
    provider_name = "edgar"

    def __init__(
        self,
        filings: Sequence[DigitalOracleSecFiling],
        *,
        ownership_transactions: Sequence[DigitalOracleSecOwnershipTransaction] = (),
        search_hits: Sequence[DigitalOracleSecSearchHit] = (),
        failure: DigitalOracleProviderError | None = None,
    ) -> None:
        self.filings = tuple(filings)
        self.ownership_transactions = tuple(ownership_transactions)
        self.search_hits = tuple(search_hits)
        self.failure = failure
        self.calls: list[DigitalOracleSecFilingsProviderQuery] = []

    def lookup_sec_filings(
        self, query: DigitalOracleSecFilingsProviderQuery
    ) -> DigitalOracleSecFilingsProviderResult:
        self.calls.append(query)
        if self.failure is not None:
            raise self.failure
        return DigitalOracleSecFilingsProviderResult(
            provider=self.provider_name,
            ticker=query.ticker,
            cik="0001045810",
            entity_name="NVIDIA CORP",
            filings=self.filings,
            search_hits=self.search_hits,
            ownership_transactions=self.ownership_transactions,
        )


class FakeJsonClient:

    def __init__(
        self,
        payloads_by_url_fragment: Mapping[str, object] | None = None,
        *,
        payload: object | None = None,
        text_by_url_fragment: Mapping[str, str] | None = None,
    ) -> None:
        self.payloads_by_url_fragment = dict(payloads_by_url_fragment or {})
        self.payload = payload
        self.text_by_url_fragment = dict(text_by_url_fragment or {})
        self.calls: list[dict[str, object]] = []
        self.text_calls: list[dict[str, object]] = []

    def get_json(self, url: str, *, timeout: float, **kwargs: object) -> object:
        call: dict[str, object] = {"url": url, "timeout": timeout}
        params = kwargs.pop("params", None)
        if params is not None:
            call["params"] = dict(cast(Mapping[str, object], params))
        call.update(oracle_fake__recorded_kwargs(kwargs))
        self.calls.append(call)
        if self.payload is not None:
            if isinstance(self.payload, DigitalOracleProviderError):
                raise self.payload
            return self.payload
        for fragment, payload in sorted(
            self.payloads_by_url_fragment.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            if fragment in url:
                if isinstance(payload, DigitalOracleProviderError):
                    raise payload
                return payload
        raise AssertionError(f"No fake JSON payload configured for {url}")

    def get_text(self, url: str, *, timeout: float, contact_email: str) -> str:
        self.text_calls.append({"url": url, "timeout": timeout, "contactEmail": contact_email})
        for fragment, payload in self.text_by_url_fragment.items():
            if fragment in url:
                return payload
        raise AssertionError(f"No fake text payload configured for {url}")


def oracle_fake__recorded_kwargs(kwargs: Mapping[str, object]) -> dict[str, object]:
    mapped: dict[str, object] = {}
    for key, value in kwargs.items():
        if value is None:
            continue
        mapped[
            {
                "api_key": "apiKey",
                "contact_email": "contactEmail",
                "report_type": "reportType",
                "source_url": "sourceUrl",
            }.get(key, key)
        ] = value
    return mapped


class oracle_fake_FakeOptionsTable:

    def __init__(self, rows: Sequence[Mapping[str, object]]) -> None:
        self.rows = tuple(rows)

    def to_dict(self, orient: str) -> list[Mapping[str, object]]:
        assert orient == "records"
        return list(self.rows)


class FakeOptionsChainPayload:

    def __init__(
        self,
        *,
        calls: Sequence[Mapping[str, object]],
        puts: Sequence[Mapping[str, object]],
    ) -> None:
        self.calls = oracle_fake_FakeOptionsTable(calls)
        self.puts = oracle_fake_FakeOptionsTable(puts)


class FakeOptionsTicker:

    def __init__(
        self,
        *,
        chains_by_expiration: Mapping[str, FakeOptionsChainPayload],
        spot_price: Decimal | None = Decimal("200"),
    ) -> None:
        self._chains_by_expiration = dict(chains_by_expiration)
        self._spot_price = spot_price
        self.option_chain_calls: list[str] = []

    @property
    def options(self) -> Sequence[str]:
        return tuple(self._chains_by_expiration)

    @property
    def fast_info(self) -> Mapping[str, object]:
        if self._spot_price is None:
            return {}
        return {"last_price": str(self._spot_price)}

    @property
    def info(self) -> Mapping[str, object]:
        return {}

    def option_chain(self, date: str) -> FakeOptionsChainPayload:
        self.option_chain_calls.append(date)
        return self._chains_by_expiration[date]


class FakeOptionsTickerFactory:

    def __init__(self, ticker: FakeOptionsTicker) -> None:
        self.ticker = ticker
        self.symbols: list[str] = []

    def __call__(self, symbol: str) -> FakeOptionsTicker:
        self.symbols.append(symbol)
        return self.ticker


oracle_fake__DIGITAL_ORACLE_FIXTURE_DIR = (
    Path(__file__).resolve().parent / "fixtures" / "digital_oracle"
)


def oracle_fake__normalize_digital_oracle_fixture_params(
    params: Mapping[str, object] | None
) -> dict[str, object]:
    if params is None:
        return {}
    return {str(key): value for (key, value) in sorted(params.items()) if value is not None}


def oracle_fake__digital_oracle_fixture_request_key(
    *, kind: str, url: str, params: Mapping[str, object] | None
) -> str:
    return json.dumps(
        {
            "kind": kind,
            "url": url,
            "params": oracle_fake__normalize_digital_oracle_fixture_params(params),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


class DigitalOracleFixtureReplayJsonClient:

    def __init__(
        self,
        fixture_names: Sequence[str],
        *,
        fixture_dir: Path = oracle_fake__DIGITAL_ORACLE_FIXTURE_DIR,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self._fixtures: dict[str, dict[str, object]] = {}
        for fixture_name in fixture_names:
            path = fixture_dir / fixture_name
            if not path.exists():
                raise AssertionError(f"Missing Digital Oracle fixture file: {path}")
            try:
                raw_payload = cast(object, json.loads(path.read_text()))
            except json.JSONDecodeError as exc:
                raise AssertionError(f"Malformed Digital Oracle fixture JSON: {path}") from exc
            if not isinstance(raw_payload, dict):
                raise AssertionError(f"Digital Oracle fixture must be an object: {path}")
            fixture = cast(dict[str, object], raw_payload)
            kind = fixture.get("kind")
            request = fixture.get("request")
            if kind != "json" or not isinstance(request, dict):
                raise AssertionError(f"Digital Oracle fixture has invalid envelope: {path}")
            request_payload = cast(dict[str, object], request)
            url = request_payload.get("url")
            params = request_payload.get("params")
            if not isinstance(url, str) or not isinstance(params, dict):
                raise AssertionError(f"Digital Oracle fixture has invalid request: {path}")
            has_response = "response" in fixture
            has_error = "error" in fixture
            if has_response == has_error:
                raise AssertionError(
                    f"Digital Oracle fixture must contain exactly one response or error: {path}"
                )
            params_payload = cast(dict[str, object], params)
            key = oracle_fake__digital_oracle_fixture_request_key(
                kind="json", url=url, params=params_payload
            )
            if key in self._fixtures:
                raise AssertionError(f"Duplicate Digital Oracle fixture request: {path}")
            self._fixtures[key] = fixture

    def get_json(
        self,
        url: str,
        *,
        timeout: float,
        params: Mapping[str, object] | None = None,
        provider: PredictionMarketVenue | str | None = None,
        contact_email: str | None = None,
        source_url: str | None = None,
    ) -> object:
        normalized_params = oracle_fake__normalize_digital_oracle_fixture_params(params)
        call: dict[str, object] = {
            "url": url,
            "timeout": timeout,
            "params": normalized_params,
        }
        if provider is not None:
            call["provider"] = provider
        if contact_email is not None:
            call["contactEmail"] = contact_email
        if source_url is not None:
            call["sourceUrl"] = source_url
        self.calls.append(call)
        key = oracle_fake__digital_oracle_fixture_request_key(
            kind="json", url=url, params=normalized_params
        )
        fixture = self._fixtures.get(key)
        if fixture is None:
            raise AssertionError(
                f"Missing Digital Oracle fixture for {url} params={normalized_params}"
            )
        error = fixture.get("error")
        if isinstance(error, dict):
            error_payload = cast(dict[str, object], error)
            message = error_payload.get("message")
            code = error_payload.get("code")
            details = error_payload.get("details")
            raise DigitalOracleProviderError(
                (message if isinstance(message, str) else "Digital Oracle fixture provider error"),
                code=code if isinstance(code, str) else "provider_error",
                details=cast(Mapping[str, object], details if isinstance(details, dict) else {}),
            )
        return fixture["response"]

    def get_text(self, url: str, *, timeout: float, contact_email: str) -> str:
        del timeout, contact_email
        raise AssertionError(f"No Digital Oracle text fixture configured for {url}")


_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _assert_native_runtime_payload_is_json_safe_and_camel(payload: dict[str, object]) -> None:
    _ = json.dumps(payload)
    _assert_no_snake_case_keys(payload, path="$")


def _assert_no_snake_case_keys(value: object, *, path: str) -> None:
    if isinstance(value, dict):
        payload = cast(dict[object, object], value)
        for key, nested_value in payload.items():
            assert isinstance(key, str)
            assert "_" not in key, f"snake_case key leaked at {path}.{key}"
            _assert_no_snake_case_keys(nested_value, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        payload = cast(list[object], value)
        for index, nested_value in enumerate(payload):
            _assert_no_snake_case_keys(nested_value, path=f"{path}[{index}]")


def test_digital_oracle_config_keeps_provider_credentials_out_of_backend_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with monkeypatch.context() as patched:
        patched.setenv("DIGITAL_ORACLE_PREDICTION_MARKETS_DEFAULT_ITEM_LIMIT", "7")
        patched.setenv("DIGITAL_ORACLE_SEC_FILINGS_DEFAULT_ITEM_LIMIT", "11")
        reset_digital_oracle_settings_cache()
        try:
            config = get_digital_oracle_provider_config()
            assert config.prediction_markets_default_item_limit == 7
            assert config.sec_filings_default_item_limit == 11
            assert config.edgar_contact_email is None
            assert config.fred_api_key is None
        finally:
            reset_digital_oracle_settings_cache()


def test_digital_oracle_provider_config_reads_new_provider_controls_from_backend_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with monkeypatch.context() as patched:
        patched.setenv("DIGITAL_ORACLE_MACRO_RATES_ENABLED", "false")
        patched.setenv("DIGITAL_ORACLE_MACRO_RATES_DEFAULT_ITEM_LIMIT", "13")
        patched.setenv("DIGITAL_ORACLE_CRYPTO_DERIVATIVES_ENABLED", "false")
        patched.setenv("DIGITAL_ORACLE_CRYPTO_DERIVATIVES_DEFAULT_ITEM_LIMIT", "14")
        patched.setenv("DIGITAL_ORACLE_CFTC_POSITIONING_ENABLED", "false")
        patched.setenv("DIGITAL_ORACLE_CFTC_POSITIONING_DEFAULT_ITEM_LIMIT", "15")
        patched.setenv("DIGITAL_ORACLE_OPTIONS_ENABLED", "false")
        patched.setenv("DIGITAL_ORACLE_OPTIONS_DEFAULT_ITEM_LIMIT", "16")
        reset_digital_oracle_settings_cache()
        try:
            config = get_digital_oracle_provider_config()
        finally:
            reset_digital_oracle_settings_cache()
    assert config.macro_rates_enabled is False
    assert config.macro_rates_default_item_limit == 13
    assert config.fred_api_key is None
    assert config.crypto_derivatives_enabled is False
    assert config.crypto_derivatives_default_item_limit == 14
    assert config.cftc_positioning_enabled is False
    assert config.cftc_positioning_default_item_limit == 15
    assert config.options_enabled is False
    assert config.options_default_item_limit == 16


def test_digital_oracle_configured_provider_factory_construction_uses_defaults() -> None:
    settings = DigitalOracleSettings.model_validate(
        {
            "DIGITAL_ORACLE_PROVIDER_TIMEOUT": "2.5",
            "DIGITAL_ORACLE_PREDICTION_MARKETS_DEFAULT_ITEM_LIMIT": "6",
            "DIGITAL_ORACLE_SEC_FILINGS_DEFAULT_ITEM_LIMIT": "12",
            "DIGITAL_ORACLE_MACRO_RATES_DEFAULT_ITEM_LIMIT": "13",
            "DIGITAL_ORACLE_CRYPTO_DERIVATIVES_DEFAULT_ITEM_LIMIT": "14",
            "DIGITAL_ORACLE_CFTC_POSITIONING_DEFAULT_ITEM_LIMIT": "15",
            "DIGITAL_ORACLE_OPTIONS_DEFAULT_ITEM_LIMIT": "16",
        }
    )
    config = get_digital_oracle_provider_config(settings)
    assert config.prediction_markets_enabled is True
    assert config.sec_filings_enabled is True
    assert config.market_sentiment_enabled is True
    assert config.provider_timeout_seconds == 2.5
    assert config.requires_vendored_package is DIGITAL_ORACLE_PHASE1_REQUIRES_VENDORED_PACKAGE
    assert config.requires_yfinance is DIGITAL_ORACLE_PHASE1_REQUIRES_YFINANCE
    assert config.requires_vendored_package is False
    assert config.requires_yfinance is False
    assert config.provider_boundary == DIGITAL_ORACLE_PHASE1_PROVIDER_BOUNDARY
    bundle = create_digital_oracle_phase1_provider_bundle(
        settings,
        provider_secrets=DigitalOracleProviderSecrets(
            edgar_contact_email="sec-contact@example.test", fred_api_key="fred-key"
        ),
    )
    prediction_markets = bundle.prediction_markets
    sec_filings = bundle.sec_filings
    market_sentiment = bundle.market_sentiment
    assert not isinstance(prediction_markets, DigitalOracleProviderFailure)
    assert prediction_markets.venues == ("polymarket", "kalshi")
    assert prediction_markets.default_item_limit == 6
    assert [provider.key for provider in prediction_markets.providers] == [
        "polymarket",
        "kalshi",
    ]
    assert {provider.timeout_seconds for provider in prediction_markets.providers} == {2.5}
    assert not isinstance(sec_filings, DigitalOracleProviderFailure)
    assert sec_filings.provider.key == "edgar"
    assert sec_filings.provider.default_item_limit == 12
    assert sec_filings.edgar_contact_email == "sec-contact@example.test"
    assert not isinstance(market_sentiment, DigitalOracleProviderFailure)
    assert market_sentiment.provider.key == "fear_greed"
    assert market_sentiment.indicator == "fear_greed"
    assert not isinstance(bundle.macro_rates, DigitalOracleProviderFailure)
    assert bundle.macro_rates.default_item_limit == 13
    assert [provider.key for provider in bundle.macro_rates.providers] == [
        "treasury",
        "bis",
        "worldbank",
        "cme_fedwatch",
        "fred",
    ]
    assert bundle.macro_rates.source_failures == ()
    assert not isinstance(bundle.crypto_derivatives, DigitalOracleProviderFailure)
    assert bundle.crypto_derivatives.default_item_limit == 14
    assert [provider.key for provider in bundle.crypto_derivatives.providers] == [
        "deribit",
        "coingecko",
    ]
    assert not isinstance(bundle.cftc_positioning, DigitalOracleProviderFailure)
    assert bundle.cftc_positioning.default_item_limit == 15
    assert [provider.key for provider in bundle.cftc_positioning.providers] == ["cftc"]
    assert not isinstance(bundle.options, DigitalOracleProviderFailure)
    assert bundle.options.default_item_limit == 16
    assert {provider.key for provider in bundle.options.providers} >= {"yahoo"}
    disabled_prediction = create_prediction_markets_provider_bundle(
        DigitalOracleSettings.model_validate({"DIGITAL_ORACLE_PREDICTION_MARKETS_ENABLED": "false"})
    )
    assert isinstance(disabled_prediction, DigitalOracleProviderFailure)
    assert (
        disabled_prediction.message
        == "Digital Oracle prediction markets provider is disabled by backend configuration."
    )


def test_digital_oracle_provider_bundle_disabled_new_sources_return_structured_failures() -> None:
    bundle = create_digital_oracle_phase1_provider_bundle(
        DigitalOracleSettings.model_validate(
            {
                "DIGITAL_ORACLE_MACRO_RATES_ENABLED": "false",
                "DIGITAL_ORACLE_CRYPTO_DERIVATIVES_ENABLED": "false",
                "DIGITAL_ORACLE_CFTC_POSITIONING_ENABLED": "false",
                "DIGITAL_ORACLE_OPTIONS_ENABLED": "false",
            }
        )
    )
    assert isinstance(bundle.macro_rates, DigitalOracleProviderFailure)
    assert bundle.macro_rates.details == {"provider": "macro_rates"}
    assert isinstance(bundle.crypto_derivatives, DigitalOracleProviderFailure)
    assert bundle.crypto_derivatives.details == {"provider": "crypto_derivatives"}
    assert isinstance(bundle.cftc_positioning, DigitalOracleProviderFailure)
    assert bundle.cftc_positioning.details == {"provider": "cftc_positioning"}
    assert isinstance(bundle.options, DigitalOracleProviderFailure)
    assert bundle.options.details == {"provider": "options"}


def test_digital_oracle_provider_bundle_missing_fred_key_is_source_scoped_failure() -> None:
    bundle = create_digital_oracle_phase1_provider_bundle(DigitalOracleSettings())
    assert not isinstance(bundle.macro_rates, DigitalOracleProviderFailure)
    assert [failure.details for failure in bundle.macro_rates.source_failures] == [
        {"provider": "fred", "secret": FRED_API_KEY_SECRET}
    ]


def test_digital_oracle_optional_dependency_missing_yfinance_is_source_scoped_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "yfinance", None)
    bundle = create_digital_oracle_phase1_provider_bundle(DigitalOracleSettings())
    assert not isinstance(bundle.options, DigitalOracleProviderFailure)
    assert [failure.details for failure in bundle.options.source_failures] == [
        {"dependency": "yfinance", "provider": "yfinance"}
    ]


def test_digital_oracle_edgar_missing_config_returns_structured_failure() -> None:
    result = create_sec_filings_provider(DigitalOracleSettings())
    assert isinstance(result, DigitalOracleProviderFailure)
    assert result.code == EDGAR_CONTACT_EMAIL_MISSING_CODE
    assert result.message == EDGAR_CONTACT_EMAIL_MISSING_MESSAGE
    assert result.details == {"provider": "edgar", "secret": EDGAR_CONTACT_EMAIL_SECRET}


def test_digital_oracle_service_disabled_provider_config_returns_warnings_without_calls() -> None:
    prediction_provider = FakeDigitalOracleProvider(
        "polymarket",
        events=(
            DigitalOraclePredictionMarketEvent(
                venue="polymarket",
                event_id="pm-disabled",
                title="Disabled provider event",
                status="open",
            ),
        ),
    )
    sec_provider = FakeDigitalOracleSecFilingsProvider(
        filings=(
            DigitalOracleSecFiling(
                accession_number="0001045810-26-000010",
                form_type="10-K",
                filing_date=date(2026, 2, 20),
            ),
        )
    )
    sentiment_provider = FakeDigitalOracleProvider(
        DigitalOracleMarketSentimentProviderResult(provider="fear_greed", score=72, label="greed")
    )
    service = DigitalOraclePhase1Service(
        settings=DigitalOracleSettings.model_validate(
            {
                "DIGITAL_ORACLE_PREDICTION_MARKETS_ENABLED": "false",
                "DIGITAL_ORACLE_SEC_FILINGS_ENABLED": "false",
                "DIGITAL_ORACLE_MARKET_SENTIMENT_ENABLED": "false",
            }
        ),
        prediction_market_providers=(prediction_provider,),
        sec_filings_provider=sec_provider,
        market_sentiment_provider=sentiment_provider,
    )
    prediction_payload = map_prediction_markets_result(
        service.lookup_prediction_markets(DigitalOraclePredictionMarketsQuery(query="NVDA"))
    ).model_dump(mode="json", by_alias=True)
    sec_payload = map_sec_filings_result(
        service.lookup_sec_filings(DigitalOracleSecFilingsQuery(ticker="NVDA"))
    ).model_dump(mode="json", by_alias=True)
    sentiment_payload = map_market_sentiment_result(
        service.lookup_market_sentiment(DigitalOracleMarketSentimentQuery())
    ).model_dump(mode="json", by_alias=True)
    assert prediction_provider.calls == []
    assert sec_provider.calls == []
    assert sentiment_provider.calls == []
    assert prediction_payload["events"] == []
    assert prediction_payload["warnings"] == [
        {
            "code": "digital_oracle_provider_disabled",
            "message": (
                "Digital Oracle prediction markets provider "
                "is disabled by backend configuration."
            ),
            "details": [
                {"key": "operation", "value": "prediction_markets"},
                {"key": "provider", "value": "prediction_markets"},
            ],
        }
    ]
    assert sec_payload["filings"] == []
    assert sec_payload["warnings"] == [
        {
            "code": "digital_oracle_provider_disabled",
            "message": "SEC EDGAR provider is disabled by backend configuration.",
            "details": [
                {"key": "operation", "value": "sec_filings"},
                {"key": "provider", "value": "edgar"},
            ],
        }
    ]
    assert sentiment_payload["score"] is None
    assert sentiment_payload["warnings"] == [
        {
            "code": "digital_oracle_provider_disabled",
            "message": (
                "Digital Oracle market sentiment provider " "is disabled by backend configuration."
            ),
            "details": [
                {"key": "operation", "value": "market_sentiment"},
                {"key": "provider", "value": "market_sentiment"},
            ],
        }
    ]


def test_digital_oracle_service_returns_normalized_phase1_dtos() -> None:
    polymarket_provider = FakeDigitalOracleProvider(
        "polymarket",
        events=(
            DigitalOraclePredictionMarketEvent(
                venue="polymarket",
                event_id="pm-nvda-earnings",
                title="Will NVDA beat earnings expectations?",
                status="open",
                url="https://polymarket.example/events/nvda-earnings",
                end_date=_NOW,
                contracts=(
                    DigitalOraclePredictionMarketContract(
                        contract_id="pm-nvda-yes",
                        title="Yes",
                        probability=Decimal("0.62"),
                        yes_price=Decimal("0.64"),
                        no_price=Decimal("0.38"),
                        volume=Decimal("125000.5"),
                        open_interest=Decimal("2500"),
                        order_book=DigitalOraclePredictionMarketOrderBook(
                            bids=(
                                DigitalOraclePredictionMarketOrderBookLevel(
                                    price=Decimal("0.63"), size=Decimal("120")
                                ),
                            ),
                            asks=(
                                DigitalOraclePredictionMarketOrderBookLevel(
                                    price=Decimal("0.65"), size=Decimal("90")
                                ),
                            ),
                            spread=Decimal("0.02"),
                            depth_limit=2,
                        ),
                    ),
                ),
            ),
        ),
    )
    kalshi_provider = FakeDigitalOracleProvider(
        "kalshi",
        events=(
            DigitalOraclePredictionMarketEvent(
                venue="kalshi",
                event_id="KXNVDA-26",
                title="NVDA closes above $150 this quarter",
                status="open",
                contracts=(
                    DigitalOraclePredictionMarketContract(
                        contract_id="KXNVDA-26-Y",
                        title="Yes",
                        probability=Decimal("0.41"),
                        yes_price=Decimal("0.42"),
                        no_price=Decimal("0.59"),
                    ),
                ),
            ),
        ),
    )
    sec_provider = FakeDigitalOracleSecFilingsProvider(
        filings=(
            DigitalOracleSecFiling(
                accession_number="0001045810-26-000010",
                form_type="10-K",
                filing_date=date(2026, 2, 20),
                accepted_at=_NOW,
                primary_document="nvda-20260131.htm",
                url="https://www.sec.gov/Archives/edgar/data/1045810/fixture.htm",
                description="Annual report",
            ),
            DigitalOracleSecFiling(
                accession_number="0001045810-26-000011",
                form_type="8-K",
                filing_date=date(2026, 3, 1),
            ),
        ),
        ownership_transactions=(
            DigitalOracleSecOwnershipTransaction(
                accession_number="0001045810-26-000020",
                filing_date=date(2026, 2, 21),
                issuer_name="NVIDIA CORP",
                issuer_ticker="NVDA",
                reporting_owner_name="Ada Lovelace",
                transaction_date=date(2026, 2, 20),
                transaction_code="P",
                acquired_disposed_code="A",
                shares=Decimal("10"),
                price=Decimal("120.25"),
                ownership_nature="D",
            ),
        ),
    )
    sentiment_provider = FakeDigitalOracleProvider(
        DigitalOracleMarketSentimentProviderResult(
            provider="fear_greed",
            score=72,
            label="greed",
            as_of_date=date(2026, 1, 2),
            previous_close=70,
            week_ago=64,
            month_ago=55,
            year_ago=None,
        )
    )
    settings = DigitalOracleSettings.model_validate(
        {
            "DIGITAL_ORACLE_PROVIDER_TIMEOUT": "2.5",
            "DIGITAL_ORACLE_PREDICTION_MARKETS_DEFAULT_ITEM_LIMIT": "6",
            "DIGITAL_ORACLE_SEC_FILINGS_DEFAULT_ITEM_LIMIT": "12",
        }
    )
    service = DigitalOraclePhase1Service(
        provider_bundle=create_digital_oracle_phase1_provider_bundle(
            settings,
            provider_secrets=DigitalOracleProviderSecrets(
                edgar_contact_email="sec-contact@example.test"
            ),
        ),
        prediction_market_providers=(polymarket_provider, kalshi_provider),
        sec_filings_provider=sec_provider,
        market_sentiment_provider=sentiment_provider,
    )
    prediction_result = service.lookup_prediction_markets(
        DigitalOraclePredictionMarketsQuery(
            query="  NVDA   earnings ",
            venues=("polymarket", "kalshi"),
            item_limit=3,
            include_order_book=True,
            depth_limit=2,
        )
    )
    prediction_payload = map_prediction_markets_result(prediction_result).model_dump(
        mode="json", by_alias=True
    )
    _assert_native_runtime_payload_is_json_safe_and_camel(prediction_payload)
    assert prediction_result.query == "NVDA earnings"
    provider_item_limits = [
        provider.calls[0].item_limit for provider in (polymarket_provider, kalshi_provider)
    ]
    provider_timeouts = {
        provider.calls[0].timeout_seconds for provider in (polymarket_provider, kalshi_provider)
    }
    assert provider_item_limits == [3, 3]
    assert provider_timeouts == {2.5}
    assert polymarket_provider.calls[0].include_order_book is True
    assert kalshi_provider.calls[0].depth_limit == 2
    assert prediction_payload["toolKey"] == PREDICTION_MARKETS_LOOKUP_TOOL_KEY
    prediction_events = cast(list[dict[str, object]], prediction_payload["events"])
    assert [event["venue"] for event in prediction_events] == ["polymarket", "kalshi"]
    assert prediction_events[0]["eventId"] == "pm-nvda-earnings"
    prediction_contracts = cast(list[dict[str, object]], prediction_events[0]["contracts"])
    assert prediction_contracts[0]["yesPrice"] == "0.64"
    assert prediction_contracts[0]["orderBook"] == {
        "bids": [{"price": "0.63", "size": "120"}],
        "asks": [{"price": "0.65", "size": "90"}],
        "spread": "0.02",
        "depthLimit": 2,
    }
    assert prediction_payload["warnings"] == []
    sec_result = service.lookup_sec_filings(
        DigitalOracleSecFilingsQuery(
            ticker=" nvda ",
            query="annual report",
            form_types=("10-k",),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            item_limit=1,
            include_ownership_transactions=True,
        )
    )
    sec_payload = map_sec_filings_result(sec_result).model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(sec_payload)
    assert sec_provider.calls[0].ticker == "NVDA"
    assert sec_provider.calls[0].query == "annual report"
    assert sec_provider.calls[0].form_types == ("10-K",)
    assert sec_provider.calls[0].include_ownership_transactions is True
    assert sec_provider.calls[0].edgar_contact_email == "sec-contact@example.test"
    assert sec_provider.calls[0].timeout_seconds == 2.5
    assert sec_payload["toolKey"] == SEC_FILINGS_LOOKUP_TOOL_KEY
    assert sec_payload["ticker"] == "NVDA"
    sec_filings = cast(list[dict[str, object]], sec_payload["filings"])
    assert [filing["formType"] for filing in sec_filings] == ["10-K"]
    sec_search_hits = cast(list[dict[str, object]], sec_payload["searchHits"])
    assert sec_search_hits[0]["matchedText"] == "Annual report"
    assert sec_payload["ownershipTransactions"] == []
    assert sec_payload["warnings"] == []
    sentiment_result = service.lookup_market_sentiment(
        DigitalOracleMarketSentimentQuery(as_of_date=date(2026, 1, 2))
    )
    sentiment_payload = map_market_sentiment_result(sentiment_result).model_dump(
        mode="json", by_alias=True
    )
    _assert_native_runtime_payload_is_json_safe_and_camel(sentiment_payload)
    assert sentiment_provider.calls[0].source_url == MARKET_SENTIMENT_SOURCE_URL
    assert sentiment_provider.calls[0].timeout_seconds == 2.5
    assert sentiment_payload["toolKey"] == MARKET_SENTIMENT_LOOKUP_TOOL_KEY
    assert sentiment_payload["score"] == 72
    assert sentiment_payload["sourceUrl"] == MARKET_SENTIMENT_SOURCE_URL
    assert sentiment_payload["warnings"] == []


def test_digital_oracle_service_partial_failures_return_structured_warnings() -> None:
    polymarket_provider = FakeDigitalOracleProvider(
        "polymarket",
        events=(
            DigitalOraclePredictionMarketEvent(
                venue="polymarket",
                event_id="pm-event",
                title="Will NVDA beat earnings expectations?",
                status="open",
                contracts=(
                    DigitalOraclePredictionMarketContract(
                        contract_id="pm-event-yes",
                        title="Yes",
                        probability=Decimal("0.62"),
                    ),
                ),
            ),
        ),
    )
    kalshi_provider = FakeDigitalOracleProvider(
        "kalshi",
        failure=DigitalOracleProviderError(
            "Kalshi provider timed out with api_key=sk-provider-secret",
            code="provider_timeout",
            details={
                "venue": "kalshi",
                "api_key": "sk-provider-secret",
                "request_id": "req-123",
            },
        ),
    )
    empty_sentiment_provider = FakeDigitalOracleProvider(
        DigitalOracleMarketSentimentProviderResult(provider="fear_greed")
    )
    service = DigitalOraclePhase1Service(
        prediction_market_providers=(polymarket_provider, kalshi_provider),
        market_sentiment_provider=empty_sentiment_provider,
    )
    prediction_payload = map_prediction_markets_result(
        service.lookup_prediction_markets(
            DigitalOraclePredictionMarketsQuery(
                query="NVDA earnings", venues=("polymarket", "kalshi")
            )
        )
    ).model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(prediction_payload)
    prediction_events = cast(list[dict[str, object]], prediction_payload["events"])
    assert [event["venue"] for event in prediction_events] == ["polymarket"]
    warning_payload = cast(list[dict[str, object]], prediction_payload["warnings"])
    assert [warning["code"] for warning in warning_payload] == [
        "prediction_markets_provider_timeout",
        "prediction_markets_partial_result",
    ]
    assert warning_payload[0]["message"] == "Kalshi provider timed out with api_key=<redacted>"
    assert warning_payload[0]["details"] == [
        {"key": "operation", "value": "prediction_markets"},
        {"key": "provider", "value": "kalshi"},
        {"key": "requestId", "value": "req-123"},
        {"key": "venue", "value": "kalshi"},
    ]
    sec_payload = map_sec_filings_result(
        DigitalOraclePhase1Service().lookup_sec_filings(DigitalOracleSecFilingsQuery(ticker="NVDA"))
    ).model_dump(mode="json", by_alias=True)
    sec_warnings = cast(list[dict[str, object]], sec_payload["warnings"])
    assert sec_payload["filings"] == []
    assert sec_warnings == [
        {
            "code": EDGAR_CONTACT_EMAIL_MISSING_CODE,
            "message": EDGAR_CONTACT_EMAIL_MISSING_MESSAGE,
            "details": [
                {"key": "operation", "value": "sec_filings"},
                {"key": "provider", "value": "edgar"},
            ],
        }
    ]
    sentiment_payload = map_market_sentiment_result(
        service.lookup_market_sentiment(DigitalOracleMarketSentimentQuery())
    ).model_dump(mode="json", by_alias=True)
    sentiment_warnings = cast(list[dict[str, object]], sentiment_payload["warnings"])
    assert sentiment_payload["score"] is None
    assert sentiment_warnings == [
        {
            "code": "market_sentiment_empty",
            "message": "No market_sentiment data returned from fear_greed.",
            "details": [
                {"key": "operation", "value": "market_sentiment"},
                {"key": "provider", "value": "fear_greed"},
            ],
        }
    ]


def oracle_dto__warning_payload() -> RuntimeToolWarning:
    return RuntimeToolWarning(
        code="provider_unavailable",
        message="Fixture provider is unavailable.",
        details={"provider": "fixture", "operation": "contract_freeze"},
    )


def oracle_dto__assert_no_raw_provider_fields(payload: dict[str, object]) -> None:
    forbidden_keys = {
        "backendException",
        "headers",
        "rawPayload",
        "requestConfig",
        "secret",
        "secrets",
    }
    assert forbidden_keys.isdisjoint(payload)


def test_digital_oracle_runtime_response_aliases_and_warnings_are_stable() -> None:
    warning = oracle_dto__warning_payload()
    as_of = datetime(2026, 6, 19, 14, 30, tzinfo=UTC)
    prediction_markets = RuntimePredictionMarketsLookupResult(
        query="election markets", events=[], warnings=[warning]
    ).model_dump(mode="json", by_alias=True)
    sec_filings = RuntimeSecFilingsLookupResult(
        ticker="AAPL", filings=[], warnings=[warning]
    ).model_dump(mode="json", by_alias=True)
    market_sentiment = RuntimeMarketSentimentLookupResult(
        indicator="fear_greed",
        as_of_date=date(2026, 6, 7),
        provider="fear_greed",
        warnings=[warning],
    ).model_dump(mode="json", by_alias=True)
    unavailable = RuntimeDigitalOracleUnavailableLookupResult(
        tool_key="signaldeck/digital-oracle/macro_rates_lookup", warnings=[warning]
    ).model_dump(mode="json", by_alias=True)
    macro_rates = map_macro_rates_result(
        DigitalOracleMacroRatesResult(
            query="fed funds",
            series=(
                DigitalOracleMacroRatesSeries(
                    provider="fred",
                    family="macro_indicators",
                    series_id="FEDFUNDS",
                    label="Effective Federal Funds Rate",
                    country="US",
                    currency="USD",
                    unit="percent",
                    date=date(2026, 6, 18),
                    value=Decimal("4.33"),
                    tenor=None,
                    source_url="https://fred.stlouisfed.org/series/FEDFUNDS",
                ),
            ),
            warnings=(warning,),
        )
    ).model_dump(mode="json", by_alias=True)
    crypto_derivatives = map_crypto_derivatives_result(
        DigitalOracleCryptoDerivativesResult(
            assets=("BTC",),
            spot=(
                DigitalOracleCryptoDerivativesSpotQuote(
                    provider="CoinGeckoProvider",
                    symbol="BTC",
                    price=Decimal("64250.12"),
                    currency="USD",
                    as_of=as_of,
                ),
            ),
            global_metrics=(
                DigitalOracleCryptoDerivativesGlobalMetrics(
                    provider="CoinGeckoProvider",
                    symbol=None,
                    market_cap=Decimal("1260000000000"),
                    volume_24h=Decimal("42000000000"),
                    as_of=as_of,
                ),
            ),
            term_structure=(
                DigitalOracleCryptoDerivativesTermPoint(
                    provider="DeribitProvider",
                    symbol="BTC",
                    expiry_date=date(2026, 9, 25),
                    instrument="BTC-PERPETUAL",
                    implied_volatility=Decimal("0.54"),
                    open_interest=Decimal("15123.5"),
                ),
            ),
            options=(
                DigitalOracleCryptoDerivativesOptionSummary(
                    provider="DeribitProvider",
                    symbol="BTC",
                    expiry_date=date(2026, 9, 25),
                    strike=Decimal("70000"),
                    option_type="call",
                    implied_volatility=Decimal("0.58"),
                    open_interest=Decimal("725.1"),
                ),
            ),
            order_books=(
                DigitalOracleCryptoDerivativesOrderBook(
                    provider="DeribitProvider",
                    symbol="BTC",
                    instrument="BTC-PERPETUAL",
                    bids=(
                        DigitalOracleCryptoDerivativesOrderBookLevel(
                            price=Decimal("64249.5"), size=Decimal("12.4")
                        ),
                    ),
                    asks=(
                        DigitalOracleCryptoDerivativesOrderBookLevel(
                            price=Decimal("64250.5"), size=Decimal("10.8")
                        ),
                    ),
                    depth_limit=1,
                ),
            ),
            warnings=(warning,),
        )
    ).model_dump(mode="json", by_alias=True)
    cftc_positioning = map_cftc_positioning_result(
        DigitalOracleCftcPositioningResult(
            reports=(
                DigitalOracleCftcPositioningReport(
                    provider="CftcCotProvider",
                    report_type="legacy_futures_only",
                    report_date=date(2026, 6, 16),
                    rows=(
                        DigitalOracleCftcPositioningRow(
                            market="Bitcoin",
                            contract_market_code="133741",
                            producer_long=Decimal("1200"),
                            producer_short=Decimal("900"),
                            swap_dealer_long=Decimal("450"),
                            swap_dealer_short=Decimal("510"),
                            managed_money_long=Decimal("7200"),
                            managed_money_short=Decimal("6800"),
                            open_interest=Decimal("18300"),
                        ),
                    ),
                ),
            ),
            warnings=(warning,),
        )
    ).model_dump(mode="json", by_alias=True)
    options = map_options_result(
        DigitalOracleOptionsResult(
            symbol="AAPL",
            chains=(
                DigitalOracleOptionsChain(
                    provider="YFinanceProvider",
                    symbol="AAPL",
                    expiry_date=date(2026, 7, 17),
                    calls=(
                        DigitalOracleOptionContract(
                            contract_symbol="AAPL260717C00200000",
                            strike=Decimal("200"),
                            last_price=Decimal("6.25"),
                            bid=Decimal("6.2"),
                            ask=Decimal("6.3"),
                            volume=Decimal("1000"),
                            open_interest=Decimal("5000"),
                            greeks=DigitalOracleOptionGreeks(
                                delta=Decimal("0.61"),
                                gamma=Decimal("0.04"),
                                theta=Decimal("-0.03"),
                                vega=Decimal("0.18"),
                                rho=Decimal("0.05"),
                                implied_volatility=Decimal("0.32"),
                            ),
                        ),
                    ),
                    puts=(
                        DigitalOracleOptionContract(
                            contract_symbol="AAPL260717P00200000",
                            strike=Decimal("200"),
                            last_price=Decimal("5.75"),
                            bid=Decimal("5.7"),
                            ask=Decimal("5.8"),
                            volume=Decimal("800"),
                            open_interest=Decimal("4200"),
                            greeks=DigitalOracleOptionGreeks(
                                delta=Decimal("-0.39"),
                                gamma=Decimal("0.04"),
                                theta=Decimal("-0.02"),
                                vega=Decimal("0.17"),
                                rho=Decimal("-0.04"),
                                implied_volatility=Decimal("0.31"),
                            ),
                        ),
                    ),
                ),
            ),
            warnings=(warning,),
        )
    ).model_dump(mode="json", by_alias=True)
    assert set(prediction_markets) == {"toolKey", "query", "events", "warnings"}
    assert prediction_markets["toolKey"] == "signaldeck/digital-oracle/prediction_markets_lookup"
    assert set(sec_filings) == {
        "toolKey",
        "ticker",
        "query",
        "cik",
        "entityName",
        "filings",
        "searchHits",
        "ownershipTransactions",
        "warnings",
    }
    assert sec_filings["toolKey"] == "signaldeck/digital-oracle/sec_filings_lookup"
    assert set(market_sentiment) == {
        "toolKey",
        "indicator",
        "asOfDate",
        "provider",
        "score",
        "label",
        "previousClose",
        "weekAgo",
        "monthAgo",
        "yearAgo",
        "sourceUrl",
        "warnings",
    }
    assert market_sentiment["toolKey"] == "signaldeck/digital-oracle/market_sentiment_lookup"
    assert set(unavailable) == {"toolKey", "warnings"}
    assert unavailable["toolKey"] == "signaldeck/digital-oracle/macro_rates_lookup"
    assert set(macro_rates) == {"toolKey", "query", "series", "warnings"}
    assert macro_rates["toolKey"] == "signaldeck/digital-oracle/macro_rates_lookup"
    assert cast(list[dict[str, object]], macro_rates["series"])[0] == {
        "provider": "fred",
        "family": "macro_indicators",
        "seriesId": "FEDFUNDS",
        "label": "Effective Federal Funds Rate",
        "country": "US",
        "currency": "USD",
        "unit": "percent",
        "date": "2026-06-18",
        "value": "4.33",
        "tenor": None,
        "sourceUrl": "https://fred.stlouisfed.org/series/FEDFUNDS",
    }
    assert set(crypto_derivatives) == {
        "toolKey",
        "assets",
        "spot",
        "globalMetrics",
        "termStructure",
        "options",
        "orderBooks",
        "warnings",
    }
    assert crypto_derivatives["toolKey"] == "signaldeck/digital-oracle/crypto_derivatives_lookup"
    assert (
        cast(list[dict[str, object]], crypto_derivatives["spot"])[0]["asOf"]
        == "2026-06-19T14:30:00Z"
    )
    assert set(cftc_positioning) == {"toolKey", "reports", "warnings"}
    assert cftc_positioning["toolKey"] == "signaldeck/digital-oracle/cftc_positioning_lookup"
    cftc_report = cast(list[dict[str, object]], cftc_positioning["reports"])[0]
    assert set(cftc_report) == {"provider", "reportType", "reportDate", "rows"}
    assert cast(list[dict[str, object]], cftc_report["rows"])[0]["managedMoneyLong"] == "7200"
    assert set(options) == {"toolKey", "symbol", "chains", "warnings"}
    assert options["toolKey"] == "signaldeck/digital-oracle/options_lookup"
    options_chain = cast(list[dict[str, object]], options["chains"])[0]
    assert set(options_chain) == {"provider", "symbol", "expiryDate", "calls", "puts"}
    call_contract = cast(list[dict[str, object]], options_chain["calls"])[0]
    assert cast(dict[str, object], call_contract["greeks"])["impliedVolatility"] == "0.32"
    for payload in (
        prediction_markets,
        sec_filings,
        market_sentiment,
        unavailable,
        macro_rates,
        crypto_derivatives,
        cftc_positioning,
        options,
    ):
        oracle_dto__assert_no_raw_provider_fields(payload)
        assert payload["warnings"] == [
            {
                "code": "provider_unavailable",
                "message": "Fixture provider is unavailable.",
                "details": [
                    {"key": "operation", "value": "contract_freeze"},
                    {"key": "provider", "value": "fixture"},
                ],
            }
        ]


@pytest.mark.parametrize(
    ("schema", "payload"),
    (
        (
            RuntimeMacroRatesLookupResult,
            {
                "toolKey": "signaldeck/digital-oracle/macro_rates_lookup",
                "query": "fed funds",
                "series": [],
                "warnings": [],
            },
        ),
        (
            RuntimeCryptoDerivativesLookupResult,
            {
                "toolKey": "signaldeck/digital-oracle/crypto_derivatives_lookup",
                "symbol": "BTC",
                "spot": None,
                "globalMetrics": None,
                "termStructure": [],
                "options": [],
                "orderBook": None,
                "warnings": [],
            },
        ),
        (
            RuntimeCftcPositioningLookupResult,
            {
                "toolKey": "signaldeck/digital-oracle/cftc_positioning_lookup",
                "reports": [],
                "warnings": [],
            },
        ),
        (
            RuntimeOptionsLookupResult,
            {
                "toolKey": "signaldeck/digital-oracle/options_lookup",
                "symbol": "AAPL",
                "chains": [],
                "warnings": [],
            },
        ),
    ),
)
def test_digital_oracle_runtime_response_aliases_reject_raw_and_unknown_fields(
    schema: (
        type[RuntimeMacroRatesLookupResult]
        | type[RuntimeCryptoDerivativesLookupResult]
        | type[RuntimeCftcPositioningLookupResult]
        | type[RuntimeOptionsLookupResult]
    ),
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        _ = schema.model_validate({**payload, "rawPayload": {"provider": "secret"}})
    with pytest.raises(ValidationError):
        _ = schema.model_validate({**payload, "requestConfig": {"headers": {}}})
    with pytest.raises(ValidationError):
        _ = schema.model_validate({**payload, "unexpectedField": "denied"})


def test_prediction_markets_runtime_tool_spec_and_parser_normalize_arguments() -> None:
    schema = PREDICTION_MARKETS_LOOKUP_TOOL_SPEC.parameters_schema
    assert PREDICTION_MARKETS_LOOKUP_TOOL_SPEC.key == PREDICTION_MARKETS_LOOKUP_TOOL_KEY
    assert (
        PREDICTION_MARKETS_LOOKUP_TOOL_SPEC.openai_function_name
        == PREDICTION_MARKETS_LOOKUP_OPENAI_FUNCTION_NAME
    )
    assert PREDICTION_MARKETS_LOOKUP_TOOL_SPEC.owner_extension_key == DIGITAL_ORACLE_EXTENSION_KEY
    assert schema["required"] == ["query"]
    properties = cast(dict[str, object], schema["properties"])
    venues_schema = cast(dict[str, object], properties["venues"])
    venues_items = cast(dict[str, object], venues_schema["items"])
    assert venues_items["enum"] == ["polymarket", "kalshi"]
    parsed = parse_prediction_markets_lookup_arguments(
        json.dumps(
            {
                "query": "  Fed   rate   cuts  ",
                "venues": [" Kalshi ", "polymarket", "kalshi"],
                "itemLimit": 2,
                "includeResolved": True,
                "includeOrderBook": True,
                "depthLimit": 4,
            }
        )
    )
    assert parsed == {
        "query": "Fed rate cuts",
        "venues": ("kalshi", "polymarket"),
        "item_limit": 2,
        "include_resolved": True,
        "include_order_book": True,
        "depth_limit": 4,
    }
    strict_nullable_payload = parse_prediction_markets_lookup_arguments(
        json.dumps(
            {
                "query": "AAPL next 30 days stock price and major company events",
                "venues": ["polymarket", "kalshi"],
                "itemLimit": 10,
                "includeResolved": True,
                "includeOrderBook": False,
                "depthLimit": 5,
            }
        )
    )
    assert strict_nullable_payload == {
        "query": "AAPL next 30 days stock price and major company events",
        "venues": ("polymarket", "kalshi"),
        "item_limit": 10,
        "include_resolved": True,
        "include_order_book": False,
        "depth_limit": None,
    }
    with pytest.raises(RuntimeToolError) as invalid_venue:
        _ = parse_prediction_markets_lookup_arguments('{"query":"Fed","venues":["predictit"]}')
    assert invalid_venue.value.message == (
        "signaldeck_digital_oracle_prediction_markets_lookup venues must u"
        "se: kalshi, polymarket."
    )
    with pytest.raises(RuntimeToolError) as invalid_limit:
        _ = parse_prediction_markets_lookup_arguments('{"query":"Fed","itemLimit":21}')
    assert (
        invalid_limit.value.message
        == "signaldeck_digital_oracle_prediction_markets_lookup itemLimit must be at most 20."
    )
    with pytest.raises(RuntimeToolError) as invalid_depth:
        _ = parse_prediction_markets_lookup_arguments(
            '{"query":"Fed","includeOrderBook":true,"depthLimit":11}'
        )
    assert (
        invalid_depth.value.message
        == "signaldeck_digital_oracle_prediction_markets_lookup depthLimit must be at most 10."
    )
    inactive_depth_limit = parse_prediction_markets_lookup_arguments(
        '{"query":"Fed","depthLimit":3}'
    )
    assert inactive_depth_limit["include_order_book"] is False
    assert inactive_depth_limit["depth_limit"] is None


@pytest.mark.parametrize(
    (
        "spec",
        "tool_key",
        "function_name",
        "parser",
        "executor",
        "required",
        "property_names",
        "checks",
    ),
    [
        (
            CRYPTO_DERIVATIVES_LOOKUP_TOOL_SPEC,
            CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY,
            CRYPTO_DERIVATIVES_LOOKUP_OPENAI_FUNCTION_NAME,
            parse_crypto_derivatives_lookup_arguments,
            execute_crypto_derivatives_lookup,
            [],
            {
                "assets",
                "venues",
                "dataTypes",
                "expirations",
                "includeOrderBook",
                "depthLimit",
                "itemLimit",
            },
            {
                ("dataTypes", "items", "enum"): [
                    "spot",
                    "global_market",
                    "term_structure",
                    "option_chain",
                    "order_book",
                ],
                ("depthLimit", "maximum"): 10,
                ("itemLimit", "maximum"): 50,
            },
        ),
        (
            CFTC_POSITIONING_LOOKUP_TOOL_SPEC,
            CFTC_POSITIONING_LOOKUP_TOOL_KEY,
            CFTC_POSITIONING_LOOKUP_OPENAI_FUNCTION_NAME,
            parse_cftc_positioning_lookup_arguments,
            execute_cftc_positioning_lookup,
            [],
            {"markets", "reportTypes", "startDate", "endDate", "itemLimit"},
            {("markets", "maxItems"): 10, ("itemLimit", "maximum"): 50},
        ),
        (
            OPTIONS_LOOKUP_TOOL_SPEC,
            OPTIONS_LOOKUP_TOOL_KEY,
            OPTIONS_LOOKUP_OPENAI_FUNCTION_NAME,
            parse_options_lookup_arguments,
            execute_options_lookup,
            ["symbols"],
            {"symbols", "expirations", "includeGreeks", "moneyness", "itemLimit"},
            {("symbols", "maxItems"): 10, ("itemLimit", "maximum"): 50},
        ),
        (
            SEC_FILINGS_LOOKUP_TOOL_SPEC,
            SEC_FILINGS_LOOKUP_TOOL_KEY,
            SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME,
            parse_sec_filings_lookup_arguments,
            execute_sec_filings_lookup,
            [],
            {
                "ticker",
                "query",
                "cik",
                "formTypes",
                "startDate",
                "endDate",
                "itemLimit",
                "includeOwnershipTransactions",
            },
            {("query", "maxLength"): 200, ("itemLimit", "maximum"): 50},
        ),
        (
            MACRO_RATES_LOOKUP_TOOL_SPEC,
            MACRO_RATES_LOOKUP_TOOL_KEY,
            MACRO_RATES_LOOKUP_OPENAI_FUNCTION_NAME,
            parse_macro_rates_lookup_arguments,
            execute_macro_rates_lookup,
            [],
            {
                "query",
                "sources",
                "families",
                "seriesIds",
                "countries",
                "startDate",
                "endDate",
                "asOfDate",
                "itemLimit",
            },
            {
                ("sources", "items", "enum"): [
                    "treasury",
                    "bis",
                    "worldbank",
                    "cme_fedwatch",
                    "fred",
                ],
                ("families", "items", "enum"): [
                    "macro_indicators",
                    "yield_curve",
                    "fx_rates",
                    "policy_rates",
                    "credit_gaps",
                    "fedwatch",
                ],
                ("itemLimit", "maximum"): 50,
            },
        ),
        (
            MARKET_SENTIMENT_LOOKUP_TOOL_SPEC,
            MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
            MARKET_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
            parse_market_sentiment_lookup_arguments,
            execute_market_sentiment_lookup,
            ["indicator"],
            {"indicator", "asOfDate"},
            {("indicator", "enum"): ["fear_greed"]},
        ),
    ],
)
def test_digital_oracle_runtime_tool_specs_preserve_business_schemas(
    spec: object,
    tool_key: str,
    function_name: str,
    parser: object,
    executor: object,
    required: list[str],
    property_names: set[str],
    checks: dict[tuple[str, ...], object],
) -> None:
    assert spec.key == tool_key
    assert spec.openai_function_name == function_name
    assert spec.owner_extension_key == DIGITAL_ORACLE_EXTENSION_KEY
    assert spec.parser is parser
    assert spec.executor is executor
    schema = spec.parameters_schema
    properties = cast(dict[str, object], schema["properties"])
    assert schema["required"] == required
    assert set(properties) == property_names
    for path, expected_value in checks.items():
        value = cast(object, properties[path[0]])
        for key in path[1:]:
            value = cast(dict[str, object], value)[key]
        assert value == expected_value


def test_prediction_markets_providers_fetch_direct_order_book_depth() -> None:
    client = FakeJsonClient(
        {
            "gamma-api.polymarket.com/events": [
                {
                    "id": "pm-fed-event",
                    "slug": "fed-cut",
                    "title": "Fed cut odds",
                    "active": True,
                    "markets": json.dumps(
                        [
                            {
                                "id": "pm-fed-yes",
                                "question": "Will the Fed cut rates?",
                                "outcomes": json.dumps(["Yes", "No"]),
                                "outcomePrices": json.dumps(["0.61", "0.40"]),
                                "clobTokenIds": json.dumps(["pm-yes-token", "pm-no-token"]),
                            }
                        ]
                    ),
                }
            ],
            "clob.polymarket.com/book?token_id=pm-yes-token": {
                "bids": [
                    {"price": "0.60", "size": "100"},
                    {"price": "0.59", "size": "50"},
                ],
                "asks": [
                    {"price": "0.62", "size": "70"},
                    {"price": "0.63", "size": "25"},
                ],
            },
            "api.elections.kalshi.com": {
                "markets": [
                    {
                        "ticker": "KXFEDCUT-26",
                        "event_ticker": "KXFEDCUT",
                        "title": "Fed cut odds",
                        "status": "open",
                        "yes_bid": 55,
                        "yes_ask": 57,
                    }
                ]
            },
            "markets/KXFEDCUT-26/orderbook": {
                "orderbook": {"yes": [[55, 100], [54, 50]], "no": [[43, 75], [42, 25]]}
            },
        }
    )
    query = DigitalOraclePredictionMarketsProviderQuery(
        query="Fed cut",
        venue="polymarket",
        item_limit=5,
        include_resolved=False,
        timeout_seconds=1.5,
        include_order_book=True,
        depth_limit=1,
    )
    polymarket_result = PolymarketPredictionMarketsProvider(client).lookup_prediction_markets(query)
    kalshi_result = KalshiPredictionMarketsProvider(client).lookup_prediction_markets(
        replace(query, venue="kalshi")
    )
    polymarket_payload = map_prediction_markets_result(
        DigitalOraclePhase1Service(
            prediction_market_providers=(
                FakeDigitalOracleProvider("polymarket", events=polymarket_result.events),
            )
        ).lookup_prediction_markets(
            DigitalOraclePredictionMarketsQuery(
                query="Fed cut",
                venues=("polymarket",),
                include_order_book=True,
                depth_limit=1,
            )
        )
    ).model_dump(mode="json", by_alias=True)
    polymarket_contracts = cast(
        list[dict[str, object]],
        cast(list[dict[str, object]], polymarket_payload["events"])[0]["contracts"],
    )
    kalshi_order_book = kalshi_result.events[0].contracts[0].order_book
    assert polymarket_contracts == [
        {
            "contractId": "pm-fed-yes",
            "title": "Will the Fed cut rates?",
            "probability": "0.61",
            "yesPrice": "0.61",
            "noPrice": "0.40",
            "volume": None,
            "openInterest": None,
            "orderBook": {
                "bids": [{"price": "0.60", "size": "100"}],
                "asks": [{"price": "0.62", "size": "70"}],
                "spread": "0.02",
                "depthLimit": 1,
            },
        }
    ]
    assert polymarket_result.warnings == ()
    assert kalshi_order_book is not None
    assert kalshi_order_book.spread == Decimal("0.02")
    assert [level.price for level in kalshi_order_book.bids] == [Decimal("0.55")]
    assert [level.size for level in kalshi_order_book.bids] == [Decimal("100")]
    assert [level.price for level in kalshi_order_book.asks] == [Decimal("0.57")]
    assert [level.size for level in kalshi_order_book.asks] == [Decimal("75")]
    assert [call["url"] for call in client.calls] == [
        "https://gamma-api.polymarket.com/events",
        "https://clob.polymarket.com/book?token_id=pm-yes-token",
        "https://api.elections.kalshi.com/trade-api/v2/markets",
        "https://api.elections.kalshi.com/trade-api/v2/markets/KXFEDCUT-26/orderbook",
    ]


def test_prediction_markets_providers_preserve_events_when_order_book_degrades() -> None:
    client = FakeJsonClient(
        {
            "gamma-api.polymarket.com/events": [
                {
                    "id": "pm-fed-event",
                    "slug": "fed-cut",
                    "title": "Fed cut odds",
                    "active": True,
                    "markets": json.dumps(
                        [
                            {
                                "id": "pm-fed-empty-book",
                                "question": "Will the Fed cut rates?",
                                "outcomes": json.dumps(["Yes", "No"]),
                                "outcomePrices": json.dumps(["0.61", "0.40"]),
                                "clobTokenIds": json.dumps(["empty-book-token", "no-token"]),
                                "orderBook": {
                                    "bids": [{"price": "0.60", "size": "22"}],
                                    "asks": [{"price": "0.63", "size": "18"}],
                                },
                            },
                            {
                                "id": "pm-fed-one-sided-book",
                                "question": "Will the Fed cut in March?",
                                "outcomes": json.dumps(["Yes", "No"]),
                                "outcomePrices": json.dumps(["0.41", "0.59"]),
                                "outcomeTokenIds": json.dumps(["one-sided-token", "no-token"]),
                            },
                            {
                                "id": "pm-fed-no-token-embedded-book",
                                "question": "Will the Fed cut in June?",
                                "outcomes": json.dumps(["Yes", "No"]),
                                "outcomePrices": json.dumps(["0.31", "0.69"]),
                                "orderBook": {
                                    "bids": [{"price": "0.30", "size": "15"}],
                                    "asks": [{"price": "0.32", "size": "20"}],
                                },
                            },
                        ]
                    ),
                }
            ],
            "clob.polymarket.com/book?token_id=empty-book-token": {
                "bids": [],
                "asks": [],
            },
            "clob.polymarket.com/book?token_id=one-sided-token": {
                "bids": [{"price": "0.40", "size": "10"}],
                "asks": [],
            },
            "api.elections.kalshi.com": {
                "markets": [
                    {
                        "ticker": "KXFEDCUT-26",
                        "event_ticker": "KXFEDCUT",
                        "title": "Fed cut odds",
                        "status": "open",
                        "yes_bid": 55,
                        "yes_ask": 57,
                    }
                ]
            },
            "markets/KXFEDCUT-26/orderbook": DigitalOracleProviderError(
                "Kalshi timed out while fetching orderbook",
                code="provider_timeout",
                details={"provider": "kalshi"},
            ),
        }
    )
    query = DigitalOraclePredictionMarketsProviderQuery(
        query="Fed cut",
        venue="polymarket",
        item_limit=5,
        include_resolved=False,
        timeout_seconds=1.5,
        include_order_book=True,
        depth_limit=2,
    )
    polymarket_result = PolymarketPredictionMarketsProvider(client).lookup_prediction_markets(query)
    kalshi_result = KalshiPredictionMarketsProvider(client).lookup_prediction_markets(
        replace(query, venue="kalshi")
    )
    payload = map_prediction_markets_result(
        DigitalOraclePhase1Service(
            prediction_market_providers=(
                FakeDigitalOracleProvider(
                    "polymarket",
                    events=polymarket_result.events,
                    warnings=polymarket_result.warnings,
                ),
                FakeDigitalOracleProvider(
                    "kalshi",
                    events=kalshi_result.events,
                    warnings=kalshi_result.warnings,
                ),
            )
        ).lookup_prediction_markets(
            DigitalOraclePredictionMarketsQuery(
                query="Fed cut", include_order_book=True, depth_limit=2
            )
        )
    ).model_dump(mode="json", by_alias=True)
    events = cast(list[dict[str, object]], payload["events"])
    polymarket_contracts = cast(list[dict[str, object]], events[0]["contracts"])
    kalshi_contracts = cast(list[dict[str, object]], events[1]["contracts"])
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert polymarket_contracts[0]["orderBook"] == {
        "bids": [{"price": "0.60", "size": "22"}],
        "asks": [{"price": "0.63", "size": "18"}],
        "spread": "0.03",
        "depthLimit": 2,
    }
    assert polymarket_contracts[1]["orderBook"] == {
        "bids": [{"price": "0.40", "size": "10"}],
        "asks": [],
        "spread": None,
        "depthLimit": 2,
    }
    assert polymarket_contracts[2]["orderBook"] == {
        "bids": [{"price": "0.30", "size": "15"}],
        "asks": [{"price": "0.32", "size": "20"}],
        "spread": "0.02",
        "depthLimit": 2,
    }
    assert kalshi_contracts[0]["orderBook"] == {
        "bids": [{"price": "0.55", "size": None}],
        "asks": [{"price": "0.57", "size": None}],
        "spread": "0.02",
        "depthLimit": 2,
    }
    assert [warning["code"] for warning in warnings] == [
        "prediction_markets_order_book_malformed",
        "prediction_markets_order_book_partial",
        "prediction_markets_order_book_unavailable",
        "prediction_markets_order_book_provider_timeout",
    ]
    warning_details = [
        {entry["key"]: entry["value"] for entry in warning["details"]} for warning in warnings
    ]
    assert [details["provider"] for details in warning_details] == [
        "polymarket",
        "polymarket",
        "polymarket",
        "kalshi",
    ]
    assert [details["scope"] for details in warning_details] == [
        "orderbook",
        "orderbook",
        "orderbook",
        "orderbook",
    ]


def test_digital_oracle_fixture_replay_maps_success_payloads_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    def blocked_httpx_client(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("Digital Oracle fixture tests must not construct live HTTP clients")

    monkeypatch.setattr(
        "oracle_plugin.runtime_prediction_markets.httpx.Client", blocked_httpx_client
    )
    monkeypatch.setattr("oracle_plugin.runtime_sec_filings.httpx.Client", blocked_httpx_client)
    monkeypatch.setattr("oracle_plugin.runtime_market_sentiment.httpx.Client", blocked_httpx_client)
    fixture_client = DigitalOracleFixtureReplayJsonClient(
        (
            "prediction_polymarket_success.json",
            "prediction_kalshi_success.json",
            "sec_company_tickers_success.json",
            "sec_submissions_success.json",
            "market_sentiment_success.json",
        )
    )
    polymarket_result = PolymarketPredictionMarketsProvider(
        fixture_client
    ).lookup_prediction_markets(
        DigitalOraclePredictionMarketsProviderQuery(
            query="Fed cut",
            venue="polymarket",
            item_limit=5,
            include_resolved=False,
            timeout_seconds=1.5,
        )
    )
    kalshi_result = KalshiPredictionMarketsProvider(fixture_client).lookup_prediction_markets(
        DigitalOraclePredictionMarketsProviderQuery(
            query="Fed cut",
            venue="kalshi",
            item_limit=5,
            include_resolved=False,
            timeout_seconds=1.5,
        )
    )
    sec_result = EdgarSecFilingsProvider(http_client=fixture_client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="NVDA",
            form_types=(),
            start_date=None,
            end_date=None,
            item_limit=10,
            edgar_contact_email="sec-contact@example.test",
            timeout_seconds=2.5,
        )
    )
    sentiment_result = FearGreedMarketSentimentProvider(
        http_client=fixture_client
    ).lookup_market_sentiment(
        DigitalOracleMarketSentimentProviderQuery(
            indicator="fear_greed",
            as_of_date=None,
            source_url=MARKET_SENTIMENT_SOURCE_URL,
            timeout_seconds=2.5,
        )
    )
    assert polymarket_result.events[0].contracts[0].yes_price == Decimal("0.63")
    assert kalshi_result.events[0].contracts[0].probability == Decimal("0.63")
    assert sec_result.filings[0].form_type == "10-K"
    assert sec_result.filings[0].accepted_at == datetime(2026, 2, 20, 16, 30, 1, tzinfo=UTC)
    assert sentiment_result.score == 72
    assert sentiment_result.label == "greed"
    assert len(fixture_client.calls) == 5


def test_digital_oracle_fixture_replay_malformed_empty_and_error_payloads() -> None:
    fixture_client = DigitalOracleFixtureReplayJsonClient(
        (
            "prediction_polymarket_malformed.json",
            "prediction_kalshi_empty.json",
            "sec_company_tickers_success.json",
            "sec_submissions_malformed.json",
        )
    )
    empty_sentiment_client = DigitalOracleFixtureReplayJsonClient(("market_sentiment_empty.json",))
    malformed_sentiment_client = DigitalOracleFixtureReplayJsonClient(
        ("market_sentiment_malformed.json",)
    )
    prediction_service = DigitalOraclePhase1Service(
        prediction_market_providers=(
            PolymarketPredictionMarketsProvider(fixture_client),
            KalshiPredictionMarketsProvider(fixture_client),
        )
    )
    prediction_payload = map_prediction_markets_result(
        prediction_service.lookup_prediction_markets(
            DigitalOraclePredictionMarketsQuery(
                query="Malformed", venues=("polymarket", "kalshi"), item_limit=5
            )
        )
    ).model_dump(mode="json", by_alias=True)
    sec_result = EdgarSecFilingsProvider(http_client=fixture_client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="MALF",
            form_types=(),
            start_date=None,
            end_date=None,
            item_limit=10,
            edgar_contact_email="sec-contact@example.test",
            timeout_seconds=2.5,
        )
    )
    empty_sentiment_result = FearGreedMarketSentimentProvider(
        http_client=empty_sentiment_client
    ).lookup_market_sentiment(
        DigitalOracleMarketSentimentProviderQuery(
            indicator="fear_greed",
            as_of_date=None,
            source_url=MARKET_SENTIMENT_SOURCE_URL,
            timeout_seconds=2.5,
        )
    )
    malformed_sentiment_payload = map_market_sentiment_result(
        DigitalOraclePhase1Service(
            market_sentiment_provider=FearGreedMarketSentimentProvider(
                http_client=malformed_sentiment_client
            )
        ).lookup_market_sentiment(DigitalOracleMarketSentimentQuery())
    ).model_dump(mode="json", by_alias=True)
    assert prediction_payload["events"] == []
    assert [
        warning["code"] for warning in cast(list[dict[str, object]], prediction_payload["warnings"])
    ] == [
        "prediction_markets_malformed_payload",
        "prediction_markets_malformed_payload",
        "prediction_markets_malformed_payload",
        "prediction_markets_empty",
        "prediction_markets_empty",
        "prediction_markets_unavailable",
    ]
    assert sec_result.filings == ()
    assert [warning.code for warning in sec_result.warnings] == ["sec_filings_malformed_payload"]
    assert empty_sentiment_result.score is None
    assert [warning.code for warning in empty_sentiment_result.warnings] == [
        "market_sentiment_sparse_history"
    ]
    assert malformed_sentiment_payload["warnings"] == [
        {
            "code": "market_sentiment_provider_error",
            "message": "Fear & Greed provider returned malformed market sentiment data",
            "details": [
                {"key": "operation", "value": "market_sentiment"},
                {"key": "provider", "value": "fear_greed"},
            ],
        }
    ]


def test_digital_oracle_fixture_replay_provider_errors_degrade_without_network() -> None:
    prediction_client = DigitalOracleFixtureReplayJsonClient(
        ("prediction_polymarket_timeout.json", "prediction_kalshi_empty.json")
    )
    prediction_payload = map_prediction_markets_result(
        DigitalOraclePhase1Service(
            prediction_market_providers=(
                PolymarketPredictionMarketsProvider(prediction_client),
                KalshiPredictionMarketsProvider(prediction_client),
            )
        ).lookup_prediction_markets(
            DigitalOraclePredictionMarketsQuery(
                query="Timeout", venues=("polymarket", "kalshi"), item_limit=5
            )
        )
    ).model_dump(mode="json", by_alias=True)
    sec_client = DigitalOracleFixtureReplayJsonClient(("sec_company_tickers_timeout.json",))
    sentiment_client = DigitalOracleFixtureReplayJsonClient(("market_sentiment_unavailable.json",))
    sec_payload = map_sec_filings_result(
        DigitalOraclePhase1Service(
            provider_bundle=create_digital_oracle_phase1_provider_bundle(
                provider_secrets=DigitalOracleProviderSecrets(
                    edgar_contact_email="sec-contact@example.test"
                )
            ),
            sec_filings_provider=EdgarSecFilingsProvider(http_client=sec_client),
        ).lookup_sec_filings(DigitalOracleSecFilingsQuery(ticker="NVDA"))
    ).model_dump(mode="json", by_alias=True)
    sentiment_payload = map_market_sentiment_result(
        DigitalOraclePhase1Service(
            market_sentiment_provider=FearGreedMarketSentimentProvider(http_client=sentiment_client)
        ).lookup_market_sentiment(DigitalOracleMarketSentimentQuery())
    ).model_dump(mode="json", by_alias=True)
    assert [
        warning["code"] for warning in cast(list[dict[str, object]], prediction_payload["warnings"])
    ] == [
        "prediction_markets_provider_timeout",
        "prediction_markets_empty",
        "prediction_markets_unavailable",
    ]
    assert [
        warning["code"] for warning in cast(list[dict[str, object]], sec_payload["warnings"])
    ] == ["sec_filings_provider_timeout", "sec_filings_unavailable"]
    assert sentiment_payload["warnings"] == [
        {
            "code": "market_sentiment_provider_unavailable",
            "message": "Fear & Greed fixture is unavailable for market sentiment",
            "details": [
                {"key": "operation", "value": "market_sentiment"},
                {"key": "provider", "value": "fear_greed"},
            ],
        }
    ]


def test_edgar_sec_filings_search_maps_hits_and_preserves_submissions_fallback() -> None:
    company_payload = {"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}}
    submissions_payload = {
        "name": "NVIDIA CORP",
        "filings": {
            "recent": {
                "accessionNumber": ["0001045810-26-000010"],
                "form": ["10-K"],
                "filingDate": ["2026-02-20"],
                "acceptanceDateTime": ["20260220163001"],
                "primaryDocument": ["nvda-20260131.htm"],
                "primaryDocDescription": ["Annual report"],
            }
        },
    }
    search_payload = {
        "hits": {
            "hits": [
                {
                    "_source": {
                        "adsh": "0001045810-26-000010",
                        "form": "10-K",
                        "filedAt": "2026-02-20",
                        "ciks": ["0001045810"],
                        "tickers": ["NVDA"],
                        "companyName": "NVIDIA CORP",
                        "linkToFilingDetails": "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000010/nvda-20260131.htm",
                        "fileName": "nvda-20260131.htm",
                        "description": "Annual report mentions accelerated computing.",
                    }
                }
            ]
        }
    }
    client = FakeJsonClient(
        {
            "company_tickers.json": company_payload,
            "submissions/CIK0001045810.json": submissions_payload,
            "search-index": search_payload,
        }
    )
    provider_result = EdgarSecFilingsProvider(http_client=client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="NVDA",
            query="accelerated computing",
            form_types=(),
            start_date=None,
            end_date=None,
            item_limit=5,
            edgar_contact_email="test@example.invalid",
            timeout_seconds=2.5,
        )
    )
    payload = map_sec_filings_result(
        DigitalOraclePhase1Service(
            provider_bundle=create_digital_oracle_phase1_provider_bundle(
                provider_secrets=DigitalOracleProviderSecrets(
                    edgar_contact_email="test@example.invalid"
                )
            ),
            sec_filings_provider=FakeDigitalOracleSecFilingsProvider(
                filings=provider_result.filings, search_hits=provider_result.search_hits
            ),
        ).lookup_sec_filings(DigitalOracleSecFilingsQuery(ticker="NVDA", query="accelerated"))
    ).model_dump(mode="json", by_alias=True)
    search_hits = cast(list[dict[str, object]], payload["searchHits"])
    assert provider_result.cik == "0001045810"
    assert provider_result.filings[0].form_type == "10-K"
    assert search_hits == [
        {
            "accessionNumber": "0001045810-26-000010",
            "formType": "10-K",
            "filingDate": "2026-02-20",
            "cik": "0001045810",
            "ticker": "NVDA",
            "entityName": "NVIDIA CORP",
            "primaryDocument": "nvda-20260131.htm",
            "url": "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000010/nvda-20260131.htm",
            "description": "Annual report mentions accelerated computing.",
            "matchedText": "Annual report mentions accelerated computing.",
        }
    ]
    assert "test@example" not in json.dumps(payload)


def test_edgar_sec_filings_cik_lookup_empty_search_warns_and_falls_back_to_metadata() -> None:
    client = FakeJsonClient(
        {
            "company_tickers.json": {
                "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}
            },
            "submissions/CIK0001045810.json": {
                "name": "NVIDIA CORP",
                "filings": {
                    "recent": {
                        "accessionNumber": ["0001045810-26-000011"],
                        "form": ["8-K"],
                        "filingDate": ["2026-03-01"],
                        "primaryDocument": ["nvda-8k.htm"],
                        "primaryDocDescription": ["Current report for AI data center demand"],
                    }
                },
            },
            "search-index": {"hits": {"hits": []}},
        }
    )
    result = EdgarSecFilingsProvider(http_client=client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker=None,
            cik="0001045810",
            query="data center",
            form_types=(),
            start_date=None,
            end_date=None,
            item_limit=5,
            edgar_contact_email="test@example.invalid",
            timeout_seconds=2.5,
        )
    )
    service_payload = map_sec_filings_result(
        DigitalOraclePhase1Service(
            provider_bundle=create_digital_oracle_phase1_provider_bundle(
                provider_secrets=DigitalOracleProviderSecrets(
                    edgar_contact_email="test@example.invalid"
                )
            ),
            sec_filings_provider=FakeDigitalOracleSecFilingsProvider(
                filings=result.filings, search_hits=result.search_hits
            ),
        ).lookup_sec_filings(DigitalOracleSecFilingsQuery(cik="1045810", query="data center"))
    ).model_dump(mode="json", by_alias=True)
    assert result.ticker == "NVDA"
    assert [warning.code for warning in result.warnings] == ["sec_filings_search_empty"]
    search_hits = cast(list[dict[str, object]], service_payload["searchHits"])
    assert search_hits[0]["matchedText"] == "Current report for AI data center demand"
    assert "test@example" not in json.dumps(service_payload)


def test_edgar_sec_filings_ownership_transactions_are_bounded_and_malformed_xml_warns() -> None:
    client = FakeJsonClient(
        {
            "company_tickers.json": {
                "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}
            },
            "submissions/CIK0001045810.json": {
                "name": "NVIDIA CORP",
                "filings": {
                    "recent": {
                        "accessionNumber": [
                            "0001045810-26-000020",
                            "0001045810-26-000021",
                        ],
                        "form": ["4", "4/A"],
                        "filingDate": ["2026-02-22", "2026-02-21"],
                        "primaryDocument": ["form4.xml", "broken.xml"],
                        "primaryDocDescription": [
                            "Statement of ownership",
                            "Broken ownership",
                        ],
                    }
                },
            },
        },
        text_by_url_fragment={
            "form4.xml": (
                "<ownershipDocument><issuer><issuerName>NVIDIA CORP</issuerName><i"
                "ssuerTradingSymbol>NVDA</issuerTradingSymbol></issuer><reportingO"
                "wner><reportingOwnerId><rptOwnerName>Ada Lovelace</rptOwnerName><"
                "/reportingOwnerId></reportingOwner><nonDerivativeTable><nonDeriva"
                "tiveTransaction><transactionDate><value>2026-02-20</value></trans"
                "actionDate><transactionCoding><transactionCode>P</transactionCode"
                "></transactionCoding><transactionAmounts><transactionShares><valu"
                "e>10</value></transactionShares><transactionPricePerShare><value>"
                "120.25</value></transactionPricePerShare><transactionAcquiredDisp"
                "osedCode><value>A</value></transactionAcquiredDisposedCode></tran"
                "sactionAmounts></nonDerivativeTransaction><nonDerivativeTransacti"
                "on><transactionDate><value>2026-02-21</value></transactionDate><t"
                "ransactionCoding><transactionCode>S</transactionCode></transactio"
                "nCoding></nonDerivativeTransaction></nonDerivativeTable></ownersh"
                "ipDocument>"
            ),
            "broken.xml": "<ownershipDocument>",
        },
    )
    result = EdgarSecFilingsProvider(http_client=client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="NVDA",
            query=None,
            form_types=("4", "4/A"),
            start_date=None,
            end_date=None,
            item_limit=1,
            edgar_contact_email="test@example.invalid",
            timeout_seconds=2.5,
            include_ownership_transactions=True,
        )
    )
    malformed_result = EdgarSecFilingsProvider(http_client=client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="NVDA",
            query=None,
            form_types=("4", "4/A"),
            start_date=None,
            end_date=None,
            item_limit=3,
            edgar_contact_email="test@example.invalid",
            timeout_seconds=2.5,
            include_ownership_transactions=True,
        )
    )
    payload = map_sec_filings_result(
        DigitalOracleSecFilingsResult(
            ticker=result.ticker,
            cik=result.cik,
            entity_name=result.entity_name,
            filings=result.filings,
            ownership_transactions=result.ownership_transactions,
            warnings=result.warnings,
        )
    ).model_dump(mode="json", by_alias=True)
    ownership = cast(list[dict[str, object]], payload["ownershipTransactions"])
    assert len(result.ownership_transactions) == 1
    assert ownership[0]["transactionCode"] == "P"
    assert ownership[0]["shares"] == "10"
    assert "sec_filings_malformed_payload" in [
        warning.code for warning in malformed_result.warnings
    ]
    assert "test@example" not in json.dumps(payload)


def test_edgar_sec_filings_search_timeout_and_malformed_ownership_degrade_safely() -> None:
    client = FakeJsonClient(
        {
            "company_tickers.json": {
                "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}
            },
            "submissions/CIK0001045810.json": {
                "name": "NVIDIA CORP",
                "filings": {
                    "recent": {
                        "accessionNumber": ["0001045810-26-000020"],
                        "form": ["4"],
                        "filingDate": ["2026-02-22"],
                        "primaryDocument": ["broken.xml"],
                        "primaryDocDescription": ["Ownership statement"],
                    }
                },
            },
            "search-index": DigitalOracleProviderError(
                "SEC EDGAR timed out while searching filings",
                code="provider_timeout",
                details={"provider": "edgar"},
            ),
        },
        text_by_url_fragment={"broken.xml": "<ownershipDocument>"},
    )
    result = EdgarSecFilingsProvider(http_client=client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="NVDA",
            query="ownership",
            form_types=("4",),
            start_date=None,
            end_date=None,
            item_limit=5,
            edgar_contact_email="test@example.invalid",
            timeout_seconds=2.5,
            include_ownership_transactions=True,
        )
    )
    payload = map_sec_filings_result(
        DigitalOraclePhase1Service(
            provider_bundle=create_digital_oracle_phase1_provider_bundle(
                provider_secrets=DigitalOracleProviderSecrets(
                    edgar_contact_email="test@example.invalid"
                )
            ),
            sec_filings_provider=FakeDigitalOracleSecFilingsProvider(
                filings=result.filings,
                search_hits=result.search_hits,
                ownership_transactions=result.ownership_transactions,
            ),
        ).lookup_sec_filings(
            DigitalOracleSecFilingsQuery(
                ticker="NVDA",
                query="ownership",
                form_types=("4",),
                include_ownership_transactions=True,
            )
        )
    ).model_dump(mode="json", by_alias=True)
    warning_codes = [warning.code for warning in result.warnings]
    assert "sec_filings_search_unavailable" in warning_codes
    assert "sec_filings_malformed_payload" in warning_codes
    assert payload["ownershipTransactions"] == []
    assert "test@example" not in json.dumps(payload)


def test_digital_oracle_fixture_replay_missing_or_malformed_fixture_fails_deterministically(
    tmp_path: Path,
) -> None:
    with pytest.raises(AssertionError, match="Missing Digital Oracle fixture file"):
        _ = DigitalOracleFixtureReplayJsonClient(("missing.json",))
    fixture_client = DigitalOracleFixtureReplayJsonClient(("prediction_kalshi_empty.json",))
    with pytest.raises(AssertionError, match="Missing Digital Oracle fixture"):
        _ = PolymarketPredictionMarketsProvider(fixture_client).lookup_prediction_markets(
            DigitalOraclePredictionMarketsProviderQuery(
                query="Fed cut",
                venue="polymarket",
                item_limit=5,
                include_resolved=False,
                timeout_seconds=1.5,
            )
        )
    malformed_fixture = tmp_path / "malformed.json"
    _ = malformed_fixture.write_text(
        json.dumps({"kind": "json", "request": {"url": "https://example.test", "params": {}}})
    )
    with pytest.raises(AssertionError, match="exactly one response or error"):
        _ = DigitalOracleFixtureReplayJsonClient(("malformed.json",), fixture_dir=tmp_path)


def test_prediction_markets_runtime_providers_normalize_venue_payloads() -> None:
    polymarket_client = FakeJsonClient(
        {
            "gamma-api.polymarket.com": [
                {
                    "id": "pm-fed-cut",
                    "slug": "fed-cut-before-june-2026",
                    "title": "Will the Fed cut rates before June 2026?",
                    "active": True,
                    "closed": False,
                    "endDate": "2026-06-01T00:00:00Z",
                    "openInterest": "2500",
                    "markets": [
                        {
                            "id": "pm-fed-cut-market",
                            "question": "Will the Fed cut rates before June 2026?",
                            "outcomes": '["Yes", "No"]',
                            "outcomePrices": '["0.63", "0.37"]',
                            "volumeNum": "125000.5",
                        }
                    ],
                }
            ]
        }
    )
    polymarket_result = PolymarketPredictionMarketsProvider(
        polymarket_client
    ).lookup_prediction_markets(
        DigitalOraclePredictionMarketsProviderQuery(
            query="Fed cut",
            venue="polymarket",
            item_limit=5,
            include_resolved=False,
            timeout_seconds=1.5,
        )
    )
    assert polymarket_client.calls[0]["timeout"] == 1.5
    assert cast(dict[str, object], polymarket_client.calls[0]["params"])["limit"] == 5
    polymarket_event = polymarket_result.events[0]
    assert polymarket_event.venue == "polymarket"
    assert polymarket_event.event_id == "pm-fed-cut"
    assert polymarket_event.status == "open"
    assert polymarket_event.end_date == datetime(2026, 6, 1, tzinfo=UTC)
    assert polymarket_event.contracts[0].yes_price == Decimal("0.63")
    assert polymarket_event.contracts[0].no_price == Decimal("0.37")
    assert polymarket_event.contracts[0].volume == Decimal("125000.5")
    assert polymarket_event.contracts[0].open_interest == Decimal("2500")
    assert polymarket_result.warnings == ()
    kalshi_client = FakeJsonClient(
        {
            "api.elections.kalshi.com": {
                "markets": [
                    {
                        "ticker": "KXFEDCUT-26JUN-T50",
                        "event_ticker": "KXFEDCUT-26JUN",
                        "title": "Fed cut before June 2026",
                        "status": "open",
                        "yes_sub_title": "Yes",
                        "yes_bid": 62,
                        "yes_ask": 64,
                        "no_ask": 38,
                        "last_price": 63,
                        "volume": "9000",
                        "open_interest": 1200,
                        "close_time": "2026-06-01T12:00:00Z",
                    }
                ]
            }
        }
    )
    kalshi_result = KalshiPredictionMarketsProvider(kalshi_client).lookup_prediction_markets(
        DigitalOraclePredictionMarketsProviderQuery(
            query="Fed cut",
            venue="kalshi",
            item_limit=5,
            include_resolved=False,
            timeout_seconds=2.0,
        )
    )
    assert kalshi_client.calls[0]["provider"] == "kalshi"
    kalshi_event = kalshi_result.events[0]
    assert kalshi_event.venue == "kalshi"
    assert kalshi_event.event_id == "KXFEDCUT-26JUN"
    assert kalshi_event.url == "https://kalshi.com/markets/KXFEDCUT-26JUN-T50"
    assert kalshi_event.contracts[0].probability == Decimal("0.63")
    assert kalshi_event.contracts[0].yes_price == Decimal("0.64")
    assert kalshi_event.contracts[0].no_price == Decimal("0.38")
    assert kalshi_event.contracts[0].open_interest == Decimal("1200")
    assert kalshi_result.warnings == ()


def test_prediction_markets_runtime_providers_accept_upstream_shaped_payloads() -> None:
    polymarket_client = FakeJsonClient(
        {
            "gamma-api.polymarket.com": [
                {
                    "slug": "resolved-fed-cut",
                    "title": "Resolved market",
                    "active": False,
                    "closed": True,
                    "tag_slug": "fed-cut",
                    "markets": json.dumps(
                        [
                            {
                                "question": "Resolved Fed cut market",
                                "outcomes": json.dumps(["Yes", "No"]),
                                "outcomePrices": json.dumps(["0.10", "0.90"]),
                                "clobTokenIds": json.dumps(["resolved-yes-token"]),
                            }
                        ]
                    ),
                },
                {
                    "slug": "live-fed-cut",
                    "title": "Live market",
                    "active": True,
                    "closed": False,
                    "tagSlug": "fed-cut",
                    "markets": json.dumps(
                        [
                            {
                                "question": "Live Fed cut market",
                                "outcomes": ["Yes", "No"],
                                "outcomePrices": ["0.61", "0.39"],
                                "outcomeTokenIds": ["live-yes-token"],
                                "volume_24hr": "4567.89",
                            }
                        ]
                    ),
                },
            ]
        }
    )
    polymarket_result = PolymarketPredictionMarketsProvider(
        polymarket_client
    ).lookup_prediction_markets(
        DigitalOraclePredictionMarketsProviderQuery(
            query="Fed cut",
            venue="polymarket",
            item_limit=5,
            include_resolved=True,
            timeout_seconds=1.5,
        )
    )
    assert [event.status for event in polymarket_result.events] == ["open", "closed"]
    live_contract = polymarket_result.events[0].contracts[0]
    assert live_contract.contract_id == "live-yes-token"
    assert live_contract.volume == Decimal("4567.89")
    assert polymarket_result.events[0].url == "https://polymarket.com/event/live-fed-cut"
    assert polymarket_result.warnings == ()
    kalshi_client = FakeJsonClient(
        {
            "api.elections.kalshi.com": {
                "markets": [
                    {
                        "ticker": "KXFEDCUT-26JUN-T50",
                        "eventTicker": "KXFEDCUT-26JUN",
                        "event_title": "Fed cut before June 2026",
                        "status": "open",
                        "subtitle": "Yes",
                        "yes_bid_dollars": "0.40",
                        "yes_ask_dollars": "0.60",
                        "no_ask_fp": "0.50",
                        "last_price_fp": "0.90",
                        "yes_bid": 1,
                        "yes_ask": 2,
                        "no_ask": 3,
                        "last_price": 4,
                        "openInterest": "345",
                        "closeDate": "2026-06-01T12:00:00Z",
                    }
                ]
            }
        }
    )
    kalshi_result = KalshiPredictionMarketsProvider(kalshi_client).lookup_prediction_markets(
        DigitalOraclePredictionMarketsProviderQuery(
            query="Fed cut",
            venue="kalshi",
            item_limit=5,
            include_resolved=False,
            timeout_seconds=2.0,
        )
    )
    assert cast(dict[str, object], kalshi_client.calls[0]["params"])["mve_filter"] == "exclude"
    kalshi_event = kalshi_result.events[0]
    assert kalshi_event.event_id == "KXFEDCUT-26JUN"
    assert kalshi_event.title == "Fed cut before June 2026"
    assert kalshi_event.end_date == datetime(2026, 6, 1, 12, tzinfo=UTC)
    assert kalshi_event.contracts[0].title == "Yes"
    assert kalshi_event.contracts[0].probability == Decimal("0.5")
    assert kalshi_event.contracts[0].yes_price == Decimal("0.6")
    assert kalshi_event.contracts[0].no_price == Decimal("0.50")
    assert kalshi_event.contracts[0].open_interest == Decimal("345")


def test_prediction_markets_runtime_executor_filters_venues_and_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polymarket_provider = FakeDigitalOracleProvider(
        "polymarket",
        events=(
            DigitalOraclePredictionMarketEvent(
                venue="polymarket",
                event_id="pm-ignored",
                title="Ignored Polymarket event",
                status="open",
            ),
        ),
    )
    kalshi_provider = FakeDigitalOracleProvider(
        "kalshi",
        events=(
            DigitalOraclePredictionMarketEvent(
                venue="kalshi",
                event_id="KXFEDCUT-26JUN",
                title="Fed cut before June 2026",
                status="open",
                contracts=(
                    DigitalOraclePredictionMarketContract(
                        contract_id="KXFEDCUT-26JUN-T50",
                        title="Yes",
                        probability=Decimal("0.63"),
                        yes_price=Decimal("0.64"),
                        no_price=Decimal("0.38"),
                    ),
                ),
            ),
            DigitalOraclePredictionMarketEvent(
                venue="kalshi",
                event_id="KXFEDCUT-26JUL",
                title="Fed cut before July 2026",
                status="open",
            ),
        ),
    )
    monkeypatch.setattr(
        "oracle_plugin.runtime_prediction_markets.create_prediction_market_providers",
        lambda: (polymarket_provider, kalshi_provider),
    )
    payload = execute_prediction_markets_lookup(
        RuntimeToolContext(),
        parse_prediction_markets_lookup_arguments(
            json.dumps(
                {
                    "query": " Fed   cut ",
                    "venues": ["kalshi"],
                    "itemLimit": 1,
                    "includeResolved": True,
                }
            )
        ),
    )
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert polymarket_provider.calls == []
    assert kalshi_provider.calls[0].query == "Fed cut"
    assert kalshi_provider.calls[0].item_limit == 1
    assert kalshi_provider.calls[0].include_resolved is True
    assert payload["toolKey"] == PREDICTION_MARKETS_LOOKUP_TOOL_KEY
    assert payload["query"] == "Fed cut"
    events = cast(list[dict[str, object]], payload["events"])
    assert [event["venue"] for event in events] == ["kalshi"]
    assert events[0]["eventId"] == "KXFEDCUT-26JUN"
    contracts = cast(list[dict[str, object]], events[0]["contracts"])
    assert contracts[0]["yesPrice"] == "0.64"
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert warnings == [
        {
            "code": "prediction_markets_truncated",
            "message": "prediction_markets results were truncated to 1 items.",
            "details": [
                {"key": "limit", "value": "1"},
                {"key": "operation", "value": "prediction_markets"},
            ],
        }
    ]


def test_prediction_markets_runtime_executor_preserves_partial_provider_warnings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polymarket_provider = FakeDigitalOracleProvider(
        "polymarket",
        events=(
            DigitalOraclePredictionMarketEvent(
                venue="polymarket",
                event_id="pm-fed-cut",
                title="Fed cut before June 2026",
                status="open",
                contracts=(
                    DigitalOraclePredictionMarketContract(
                        contract_id="pm-fed-cut-market",
                        title="Will the Fed cut rates before June 2026?",
                        probability=Decimal("0.63"),
                    ),
                ),
            ),
        ),
    )
    kalshi_provider = FakeDigitalOracleProvider(
        "kalshi",
        failure=DigitalOracleProviderError(
            "Kalshi provider timed out with token=sk-runtime-secret",
            code="provider_timeout",
            details={"venue": "kalshi", "token": "sk-runtime-secret"},
        ),
    )
    monkeypatch.setattr(
        "oracle_plugin.runtime_prediction_markets.create_prediction_market_providers",
        lambda: (polymarket_provider, kalshi_provider),
    )
    payload = execute_prediction_markets_lookup(
        RuntimeToolContext(),
        parse_prediction_markets_lookup_arguments(
            json.dumps({"query": "Fed cut", "venues": ["polymarket", "kalshi"]})
        ),
    )
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    events = cast(list[dict[str, object]], payload["events"])
    assert [event["venue"] for event in events] == ["polymarket"]
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "prediction_markets_provider_timeout",
        "prediction_markets_partial_result",
    ]
    assert warnings[0]["message"] == "Kalshi provider timed out with token=<redacted>"
    assert warnings[0]["details"] == [
        {"key": "operation", "value": "prediction_markets"},
        {"key": "provider", "value": "kalshi"},
        {"key": "venue", "value": "kalshi"},
    ]


def test_prediction_markets_runtime_executor_returns_unavailable_when_all_providers_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polymarket_provider = FakeDigitalOracleProvider("polymarket")
    kalshi_provider = FakeDigitalOracleProvider("kalshi")
    monkeypatch.setattr(
        "oracle_plugin.runtime_prediction_markets.create_prediction_market_providers",
        lambda: (polymarket_provider, kalshi_provider),
    )
    payload = execute_prediction_markets_lookup(
        RuntimeToolContext(),
        parse_prediction_markets_lookup_arguments(
            json.dumps({"query": "No matching event", "venues": ["polymarket", "kalshi"]})
        ),
    )
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert payload["events"] == []
    assert [warning["code"] for warning in cast(list[dict[str, object]], payload["warnings"])] == [
        "prediction_markets_empty",
        "prediction_markets_empty",
        "prediction_markets_unavailable",
    ]
    assert payload["warnings"] == [
        {
            "code": "prediction_markets_empty",
            "message": "No prediction_markets data returned from polymarket.",
            "details": [
                {"key": "operation", "value": "prediction_markets"},
                {"key": "provider", "value": "polymarket"},
            ],
        },
        {
            "code": "prediction_markets_empty",
            "message": "No prediction_markets data returned from kalshi.",
            "details": [
                {"key": "operation", "value": "prediction_markets"},
                {"key": "provider", "value": "kalshi"},
            ],
        },
        {
            "code": "prediction_markets_unavailable",
            "message": "No prediction_markets data available from configured providers.",
            "details": [{"key": "operation", "value": "prediction_markets"}],
        },
    ]


def test_prediction_markets_runtime_executor_returns_unavailable_when_all_providers_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polymarket_provider = FakeDigitalOracleProvider(
        "polymarket",
        failure=DigitalOracleProviderError(
            "Polymarket timed out while fetching prediction markets",
            code="provider_timeout",
            details={"provider": "polymarket"},
        ),
    )
    kalshi_provider = FakeDigitalOracleProvider(
        "kalshi",
        failure=DigitalOracleProviderError(
            "Kalshi is unavailable for prediction markets",
            code="provider_unavailable",
            details={"provider": "kalshi"},
        ),
    )
    monkeypatch.setattr(
        "oracle_plugin.runtime_prediction_markets.create_prediction_market_providers",
        lambda: (polymarket_provider, kalshi_provider),
    )
    payload = execute_prediction_markets_lookup(
        RuntimeToolContext(),
        parse_prediction_markets_lookup_arguments(
            json.dumps({"query": "Fed cut", "venues": ["polymarket", "kalshi"]})
        ),
    )
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert payload["toolKey"] == PREDICTION_MARKETS_LOOKUP_TOOL_KEY
    assert payload["query"] == "Fed cut"
    assert payload["events"] == []
    assert payload["warnings"] == [
        {
            "code": "prediction_markets_provider_timeout",
            "message": "Polymarket timed out while fetching prediction markets",
            "details": [
                {"key": "operation", "value": "prediction_markets"},
                {"key": "provider", "value": "polymarket"},
            ],
        },
        {
            "code": "prediction_markets_provider_unavailable",
            "message": "Kalshi is unavailable for prediction markets",
            "details": [
                {"key": "operation", "value": "prediction_markets"},
                {"key": "provider", "value": "kalshi"},
            ],
        },
        {
            "code": "prediction_markets_unavailable",
            "message": "No prediction_markets data available from configured providers.",
            "details": [{"key": "operation", "value": "prediction_markets"}],
        },
    ]


def test_prediction_markets_service_preserves_malformed_adapter_warnings_with_partial_result() -> (
    None
):
    polymarket_client = FakeJsonClient(
        {
            "gamma-api.polymarket.com": [
                "not-an-event-row",
                {
                    "id": "pm-fed-cut",
                    "slug": "fed-cut-before-june-2026",
                    "title": "Will the Fed cut rates before June 2026?",
                    "active": True,
                    "closed": False,
                    "markets": [
                        {
                            "id": "pm-fed-cut-market",
                            "question": "Will the Fed cut rates before June 2026?",
                            "outcomes": "not-json",
                            "outcomePrices": '["0.63", "0.37"]',
                        }
                    ],
                },
            ]
        }
    )
    polymarket_provider = PolymarketPredictionMarketsProvider(polymarket_client)
    kalshi_provider = FakeDigitalOracleProvider(
        "kalshi",
        events=(
            DigitalOraclePredictionMarketEvent(
                venue="kalshi",
                event_id="KXFEDCUT-26JUN",
                title="Fed cut before June 2026",
                status="open",
                contracts=(
                    DigitalOraclePredictionMarketContract(
                        contract_id="KXFEDCUT-26JUN-T50",
                        title="Yes",
                        probability=Decimal("0.63"),
                    ),
                ),
            ),
        ),
    )
    service = DigitalOraclePhase1Service(
        prediction_market_providers=(polymarket_provider, kalshi_provider)
    )
    payload = map_prediction_markets_result(
        service.lookup_prediction_markets(
            DigitalOraclePredictionMarketsQuery(query="Fed cut", venues=("polymarket", "kalshi"))
        )
    ).model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    events = cast(list[dict[str, object]], payload["events"])
    assert [event["venue"] for event in events] == ["kalshi"]
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "prediction_markets_malformed_payload",
        "prediction_markets_malformed_payload",
        "prediction_markets_malformed_payload",
        "prediction_markets_empty",
        "prediction_markets_partial_result",
    ]
    assert warnings[1]["details"] == [
        {"key": "eventId", "value": "pm-fed-cut"},
        {"key": "field", "value": "market outcomes"},
        {"key": "operation", "value": "prediction_markets"},
        {"key": "provider", "value": "polymarket"},
    ]
    assert warnings[-1]["details"] == [
        {"key": "operation", "value": "prediction_markets"},
        {"key": "providers", "value": "polymarket,kalshi"},
        {"key": "uncoveredProviders", "value": "polymarket"},
    ]


def test_crypto_derivatives_parser_normalizes_arrays_and_rejects_invalid_inputs() -> None:
    arguments = parse_crypto_derivatives_lookup_arguments(
        json.dumps(
            {
                "assets": [" btc ", "BTC", " eth "],
                "venues": ["DERIBIT", "coingecko", "deribit"],
                "dataTypes": ["spot", "option_chain", "order_book", "spot"],
                "expirations": ["2026-06-26", "2026-09-25"],
                "includeOrderBook": True,
                "depthLimit": 3,
                "itemLimit": 4,
            }
        )
    )
    assert arguments == {
        "assets": ("BTC", "ETH"),
        "venues": ("deribit", "coingecko"),
        "data_types": ("spot", "option_chain", "order_book"),
        "expirations": (date(2026, 6, 26), date(2026, 9, 25)),
        "include_order_book": True,
        "depth_limit": 3,
        "item_limit": 4,
    }
    assert (
        parse_crypto_derivatives_lookup_arguments(json.dumps({"depthLimit": 3}))["depth_limit"]
        is None
    )
    with pytest.raises(RuntimeToolError, match="unsupported fields"):
        _ = parse_crypto_derivatives_lookup_arguments(json.dumps({"asset": "BTC"}))
    with pytest.raises(RuntimeToolError, match="venues must use"):
        _ = parse_crypto_derivatives_lookup_arguments(json.dumps({"venues": ["finance"]}))
    with pytest.raises(RuntimeToolError, match="dataTypes must use"):
        _ = parse_crypto_derivatives_lookup_arguments(json.dumps({"dataTypes": ["funding"]}))
    with pytest.raises(RuntimeToolError, match="dataTypes must use"):
        _ = parse_crypto_derivatives_lookup_arguments(
            json.dumps({"dataTypes": ["global_metrics", "options"]})
        )
    with pytest.raises(RuntimeToolError, match="depthLimit must be at most 10"):
        _ = parse_crypto_derivatives_lookup_arguments(json.dumps({"depthLimit": 11}))
    with pytest.raises(RuntimeToolError, match="itemLimit must be at most 50"):
        _ = parse_crypto_derivatives_lookup_arguments(json.dumps({"itemLimit": 51}))


def test_cftc_positioning_parser_normalizes_filters_and_rejects_invalid_args() -> None:
    arguments = parse_cftc_positioning_lookup_arguments(
        json.dumps(
            {
                "markets": [" Bitcoin ", "BITCOIN", "Gold"],
                "reportTypes": [" legacy_futures_only ", "financial_futures"],
                "startDate": "2026-01-01",
                "endDate": "2026-06-30",
                "itemLimit": 5,
            }
        )
    )
    assert arguments == {
        "markets": ("Bitcoin", "Gold"),
        "report_types": ("legacy_futures_only", "financial_futures"),
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 6, 30),
        "item_limit": 5,
    }
    with pytest.raises(RuntimeToolError, match="unsupported fields"):
        _ = parse_cftc_positioning_lookup_arguments(json.dumps({"market": "Bitcoin"}))
    with pytest.raises(RuntimeToolError, match="reportTypes must use"):
        _ = parse_cftc_positioning_lookup_arguments(json.dumps({"reportTypes": ["legacy"]}))
    with pytest.raises(RuntimeToolError, match="markets must contain at most 10"):
        _ = parse_cftc_positioning_lookup_arguments(
            json.dumps({"markets": [f"M{index}" for index in range(11)]})
        )
    with pytest.raises(RuntimeToolError, match="startDate must be before or equal to endDate"):
        _ = parse_cftc_positioning_lookup_arguments(
            json.dumps({"startDate": "2026-06-30", "endDate": "2026-01-01"})
        )


def test_cftc_positioning_provider_maps_fake_rows_and_malformed_warning() -> None:
    client = FakeJsonClient(
        {
            "6dca-aqww": [
                {
                    "market_and_exchange_names": "BITCOIN - CHICAGO MERCANTILE EXCHANGE",
                    "cftc_contract_market_code": "133741",
                    "report_date_as_yyyy_mm_dd": "2026-06-16T00:00:00",
                    "noncomm_positions_long_all": "1200",
                    "noncomm_positions_short_all": "900",
                    "noncomm_positions_spread_all": "45",
                    "open_interest_all": "18300",
                },
                {"market_and_exchange_names": "malformed"},
            ]
        }
    )
    provider = CftcCotPositioningProvider(client)
    result = provider.lookup_cftc_positioning(
        DigitalOracleCftcPositioningProviderQuery(
            markets=("Bitcoin",),
            report_types=("legacy_futures_only",),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            item_limit=5,
            timeout_seconds=2.5,
        )
    )
    assert cast(dict[str, object], client.calls[0]["params"])["$limit"] == 5
    assert result.reports[0].report_date == date(2026, 6, 16)
    assert result.reports[0].rows[0].non_commercial_net == Decimal("300")
    assert [warning.code for warning in result.warnings] == ["cftc_positioning_malformed_payload"]


def test_cftc_positioning_service_filters_dates_report_types_and_markets() -> None:
    provider = FakeDigitalOracleProvider(
        result=DigitalOracleCftcPositioningProviderResult(
            provider="cftc",
            reports=(
                DigitalOracleCftcPositioningReport(
                    provider="cftc",
                    report_type="legacy_futures_only",
                    report_date=date(2026, 6, 16),
                    rows=(
                        DigitalOracleCftcPositioningRow(
                            market="BITCOIN - CME",
                            contract_market_code="133741",
                            producer_long=Decimal("1200"),
                            producer_short=Decimal("900"),
                            producer_net=Decimal("300"),
                            open_interest=Decimal("18300"),
                        ),
                    ),
                ),
                DigitalOracleCftcPositioningReport(
                    provider="cftc",
                    report_type="financial_futures",
                    report_date=date(2025, 12, 30),
                    rows=(DigitalOracleCftcPositioningRow(market="GOLD"),),
                ),
            ),
        )
    )
    service = DigitalOraclePhase1Service(cftc_positioning_providers=(provider,))
    payload = map_cftc_positioning_result(
        service.lookup_cftc_positioning(
            DigitalOracleCftcPositioningQuery(
                markets=("bitcoin",),
                report_types=("legacy_futures_only",),
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                item_limit=5,
            )
        )
    ).model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert provider.calls[0].markets == ("bitcoin",)
    assert provider.calls[0].report_types == ("legacy_futures_only",)
    reports = cast(list[dict[str, object]], payload["reports"])
    assert reports[0]["reportDate"] == "2026-06-16"
    row = cast(list[dict[str, object]], reports[0]["rows"])[0]
    assert row["producerNet"] == "300"
    assert row["openInterest"] == "18300"
    assert payload["warnings"] == []


def test_cftc_positioning_missing_market_and_provider_failure_return_warnings() -> None:
    empty_provider = FakeDigitalOracleProvider(
        result=DigitalOracleCftcPositioningProviderResult(
            provider="cftc",
            reports=(
                DigitalOracleCftcPositioningReport(
                    provider="cftc",
                    report_type="legacy_futures_only",
                    report_date=date(2026, 6, 16),
                    rows=(DigitalOracleCftcPositioningRow(market="GOLD"),),
                ),
            ),
        )
    )
    failed_provider = FakeDigitalOracleProvider(
        failure=DigitalOracleProviderError(
            "CFTC timed out with provider token sk-provider-secret",
            code="provider_timeout",
            details={"provider": "cftc", "api_key": "sk-provider-secret"},
        )
    )
    empty_payload = map_cftc_positioning_result(
        DigitalOraclePhase1Service(
            cftc_positioning_providers=(empty_provider,)
        ).lookup_cftc_positioning(DigitalOracleCftcPositioningQuery(markets=("Bitcoin",)))
    ).model_dump(mode="json", by_alias=True)
    failure_payload = map_cftc_positioning_result(
        DigitalOraclePhase1Service(
            cftc_positioning_providers=(failed_provider,)
        ).lookup_cftc_positioning(DigitalOracleCftcPositioningQuery(markets=("Bitcoin",)))
    ).model_dump(mode="json", by_alias=True)
    assert empty_payload["reports"] == []
    empty_warnings = cast(list[dict[str, object]], empty_payload["warnings"])
    assert [warning["code"] for warning in empty_warnings] == [
        "cftc_positioning_empty",
        "cftc_positioning_unavailable",
    ]
    failure_warnings = cast(list[dict[str, object]], failure_payload["warnings"])
    assert [warning["code"] for warning in failure_warnings] == [
        "cftc_positioning_provider_timeout",
        "cftc_positioning_unavailable",
    ]
    assert "sk-provider-secret" not in json.dumps(failure_payload)
    assert "api_key" not in json.dumps(failure_payload)


def test_crypto_derivatives_service_maps_fake_provider_results_to_camel_payload() -> None:
    coingecko_provider = FakeDigitalOracleProvider(
        "coingecko",
        result=DigitalOracleCryptoDerivativesProviderResult(
            provider="coingecko",
            spot=(
                DigitalOracleCryptoDerivativesSpotQuote(
                    provider="coingecko",
                    symbol="BTC",
                    price=Decimal("65000.5"),
                    currency="USD",
                    as_of=_NOW,
                ),
            ),
            global_metrics=(
                DigitalOracleCryptoDerivativesGlobalMetrics(
                    provider="coingecko",
                    symbol=None,
                    market_cap=Decimal("2500000000000"),
                    volume_24h=Decimal("80000000000"),
                    as_of=_NOW,
                ),
            ),
        ),
    )
    deribit_provider = FakeDigitalOracleProvider(
        "deribit",
        result=DigitalOracleCryptoDerivativesProviderResult(
            provider="deribit",
            term_structure=(
                DigitalOracleCryptoDerivativesTermPoint(
                    provider="deribit",
                    symbol="BTC",
                    expiry_date=date(2026, 6, 26),
                    instrument="BTC-26JUN26",
                    implied_volatility=Decimal("0.55"),
                    open_interest=Decimal("1200"),
                ),
            ),
            options=(
                DigitalOracleCryptoDerivativesOptionSummary(
                    provider="deribit",
                    symbol="BTC",
                    expiry_date=date(2026, 6, 26),
                    strike=Decimal("70000"),
                    option_type="call",
                    implied_volatility=Decimal("0.61"),
                    open_interest=Decimal("35"),
                ),
            ),
            order_books=(
                DigitalOracleCryptoDerivativesOrderBook(
                    provider="deribit",
                    symbol="BTC",
                    instrument="BTC-26JUN26",
                    bids=(
                        DigitalOracleCryptoDerivativesOrderBookLevel(
                            price=Decimal("64990"), size=Decimal("2.5")
                        ),
                    ),
                    asks=(
                        DigitalOracleCryptoDerivativesOrderBookLevel(
                            price=Decimal("65010"), size=Decimal("1.75")
                        ),
                    ),
                    depth_limit=2,
                ),
            ),
        ),
    )
    service = DigitalOraclePhase1Service(
        settings=DigitalOracleSettings.model_validate({"DIGITAL_ORACLE_PROVIDER_TIMEOUT": "2.5"}),
        crypto_derivatives_providers=(deribit_provider, coingecko_provider),
    )
    payload = map_crypto_derivatives_result(
        service.lookup_crypto_derivatives(
            DigitalOracleCryptoDerivativesQuery(
                assets=(" btc ", "BTC"),
                venues=("coingecko", "deribit"),
                data_types=(
                    "spot",
                    "global_market",
                    "term_structure",
                    "option_chain",
                    "order_book",
                ),
                include_order_book=True,
                depth_limit=2,
                item_limit=5,
            )
        )
    ).model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert coingecko_provider.calls[0].assets == ("BTC",)
    assert deribit_provider.calls[0].depth_limit == 2
    assert payload["toolKey"] == CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY
    assert payload["assets"] == ["BTC"]
    assert cast(list[dict[str, object]], payload["spot"])[0]["price"] == "65000.5"
    assert (
        cast(list[dict[str, object]], payload["globalMetrics"])[0]["marketCap"] == "2500000000000"
    )
    assert cast(list[dict[str, object]], payload["termStructure"])[0]["instrument"] == "BTC-26JUN26"
    assert cast(list[dict[str, object]], payload["options"])[0]["optionType"] == "call"
    assert cast(list[dict[str, object]], payload["orderBooks"])[0]["bids"] == [
        {"price": "64990", "size": "2.5"}
    ]
    assert payload["warnings"] == []


def test_crypto_derivatives_providers_normalize_coingecko_and_deribit_payloads() -> None:
    coingecko_client = FakeJsonClient(
        {
            "simple/price": {
                "bitcoin": {
                    "usd": 65000.5,
                    "usd_market_cap": 1280000000000,
                    "usd_24h_vol": 32000000000,
                    "last_updated_at": 1767225600,
                }
            },
            "/global": {
                "data": {
                    "total_market_cap": {"usd": "2500000000000"},
                    "total_volume": {"usd": "80000000000"},
                    "updated_at": 1767225600,
                }
            },
        }
    )
    coingecko_result = CoinGeckoCryptoDerivativesProvider(
        coingecko_client
    ).lookup_crypto_derivatives(
        DigitalOracleCryptoDerivativesProviderQuery(
            venue="coingecko",
            assets=("BTC",),
            data_types=("spot", "global_market"),
            expirations=None,
            include_order_book=False,
            depth_limit=5,
            item_limit=5,
            timeout_seconds=2.5,
        )
    )
    assert coingecko_result.spot[0].symbol == "BTC"
    assert coingecko_result.spot[0].price == Decimal("65000.5")
    assert coingecko_result.global_metrics[0].market_cap == Decimal("2500000000000")
    assert cast(dict[str, object], coingecko_client.calls[0]["params"])["ids"] == "bitcoin"
    deribit_client = FakeJsonClient(
        {
            "get_instruments": {
                "result": [
                    {
                        "instrument_name": "BTC-26JUN26",
                        "expiration_timestamp": 1782432000000,
                    },
                    {
                        "instrument_name": "BTC-26JUN26-70000-C",
                        "expiration_timestamp": 1782432000000,
                        "strike": "70000",
                        "option_type": "call",
                    },
                ]
            },
            "get_book_summary_by_currency": {
                "result": [
                    {
                        "instrument_name": "BTC-26JUN26",
                        "mark_iv": "55",
                        "open_interest": "1200",
                    },
                    {
                        "instrument_name": "BTC-26JUN26-70000-C",
                        "mark_iv": "61",
                        "open_interest": "35",
                    },
                ]
            },
            "get_order_book": {
                "result": {
                    "instrument_name": "BTC-26JUN26",
                    "bids": [["64990", "2.5"], ["64980", "1"]],
                    "asks": [["65010", "1.75"], ["65020", "3"]],
                }
            },
        }
    )
    deribit_result = DeribitCryptoDerivativesProvider(deribit_client).lookup_crypto_derivatives(
        DigitalOracleCryptoDerivativesProviderQuery(
            venue="deribit",
            assets=("BTC",),
            data_types=("term_structure", "option_chain", "order_book"),
            expirations=(date(2026, 6, 26),),
            include_order_book=True,
            depth_limit=1,
            item_limit=5,
            timeout_seconds=2.5,
        )
    )
    assert deribit_result.term_structure[0].instrument == "BTC-26JUN26"
    assert deribit_result.term_structure[0].implied_volatility == Decimal("55")
    assert deribit_result.options[0].strike == Decimal("70000")
    assert deribit_result.options[0].open_interest == Decimal("35")
    assert deribit_result.order_books[0].bids == (
        DigitalOracleCryptoDerivativesOrderBookLevel(price=Decimal("64990"), size=Decimal("2.5")),
    )


def test_crypto_derivatives_failure_paths_preserve_partial_results_and_scrub_payloads() -> None:
    coingecko_provider = FakeDigitalOracleProvider(
        "coingecko",
        failure=DigitalOracleProviderError(
            "CoinGecko rate limited crypto derivatives with provider token sk-provider-secret",
            code="provider_rate_limited",
            details={
                "provider": "coingecko",
                "api_key": "sk-provider-secret",
                "status": "429",
            },
        ),
    )
    deribit_provider = FakeDigitalOracleProvider(
        "deribit",
        result=DigitalOracleCryptoDerivativesProviderResult(
            provider="deribit",
            term_structure=(
                DigitalOracleCryptoDerivativesTermPoint(
                    provider="deribit",
                    symbol="BTC",
                    expiry_date=date(2026, 6, 26),
                    instrument="BTC-26JUN26",
                ),
            ),
            warnings=(
                RuntimeToolWarning(
                    code="crypto_derivatives_malformed_payload",
                    message="deribit returned malformed crypto-derivatives orderbook.",
                    details={
                        "operation": "crypto_derivatives",
                        "provider": "deribit",
                        "field": "orderbook",
                    },
                ),
            ),
        ),
    )
    service = DigitalOraclePhase1Service(
        crypto_derivatives_providers=(coingecko_provider, deribit_provider)
    )
    payload = map_crypto_derivatives_result(
        service.lookup_crypto_derivatives(
            DigitalOracleCryptoDerivativesQuery(
                assets=("BTC",),
                venues=("coingecko", "deribit"),
                data_types=("spot", "term_structure", "order_book"),
                include_order_book=True,
            )
        )
    ).model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert cast(list[dict[str, object]], payload["termStructure"])[0]["instrument"] == "BTC-26JUN26"
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [warning["code"] for warning in warnings] == [
        "crypto_derivatives_provider_rate_limited",
        "crypto_derivatives_malformed_payload",
        "crypto_derivatives_partial_result",
    ]
    assert (
        warnings[0]["message"]
        == "CoinGecko rate limited crypto derivatives with provider token <redacted>"
    )
    assert warnings[0]["details"] == [
        {"key": "operation", "value": "crypto_derivatives"},
        {"key": "provider", "value": "coingecko"},
        {"key": "status", "value": "429"},
    ]
    payload_json = json.dumps(payload, sort_keys=True)
    assert "rawPayload" not in payload_json
    assert "providerPayload" not in payload_json
    assert "api_key" not in payload_json
    assert "sk-provider-secret" not in payload_json


def test_crypto_derivatives_executor_dispatches_native_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeDigitalOracleProvider(
        "coingecko",
        result=DigitalOracleCryptoDerivativesProviderResult(
            provider="coingecko",
            spot=(
                DigitalOracleCryptoDerivativesSpotQuote(
                    provider="coingecko",
                    symbol="BTC",
                    price=Decimal("65000.5"),
                    currency="USD",
                ),
            ),
        ),
    )
    monkeypatch.setattr(
        "oracle_plugin.runtime_crypto_derivatives.create_crypto_derivatives_providers",
        lambda: (provider,),
    )
    payload = execute_crypto_derivatives_lookup(
        RuntimeToolContext(),
        parse_crypto_derivatives_lookup_arguments(
            json.dumps(
                {
                    "assets": ["btc"],
                    "venues": ["coingecko"],
                    "dataTypes": ["spot"],
                    "itemLimit": 1,
                }
            )
        ),
    )
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert provider.calls[0].assets == ("BTC",)
    assert provider.calls[0].item_limit == 1
    assert payload["toolKey"] == CRYPTO_DERIVATIVES_LOOKUP_TOOL_KEY
    assert cast(list[dict[str, object]], payload["spot"])[0]["price"] == "65000.5"


def test_options_lookup_parser_normalizes_symbols_and_rejects_invalid_args() -> None:
    arguments = parse_options_lookup_arguments(
        json.dumps(
            {
                "symbols": [" aapl ", "AAPL", "msft"],
                "expirations": ["2026-07-17"],
                "includeGreeks": True,
                "moneyness": "near_the_money",
                "itemLimit": 5,
            }
        )
    )
    assert arguments == {
        "symbols": ("AAPL", "MSFT"),
        "expirations": (date(2026, 7, 17),),
        "include_greeks": True,
        "moneyness": "near_the_money",
        "item_limit": 5,
    }
    with pytest.raises(RuntimeToolError, match="unsupported fields"):
        _ = parse_options_lookup_arguments(json.dumps({"symbol": "AAPL"}))
    with pytest.raises(RuntimeToolError, match="symbols is required"):
        _ = parse_options_lookup_arguments(json.dumps({}))
    with pytest.raises(RuntimeToolError, match="symbols must contain at most 10"):
        _ = parse_options_lookup_arguments(
            json.dumps({"symbols": [f"S{index}" for index in range(11)]})
        )
    with pytest.raises(RuntimeToolError, match="expirations must be valid ISO dates"):
        _ = parse_options_lookup_arguments(
            json.dumps({"symbols": ["AAPL"], "expirations": ["soon"]})
        )
    with pytest.raises(RuntimeToolError, match="moneyness must use"):
        _ = parse_options_lookup_arguments(json.dumps({"symbols": ["AAPL"], "moneyness": "atm"}))
    with pytest.raises(RuntimeToolError, match="includeGreeks must be a boolean"):
        _ = parse_options_lookup_arguments(
            json.dumps({"symbols": ["AAPL"], "includeGreeks": "yes"})
        )
    with pytest.raises(RuntimeToolError, match="itemLimit must be at most 50"):
        _ = parse_options_lookup_arguments(json.dumps({"symbols": ["AAPL"], "itemLimit": 51}))


def test_options_lookup_provider_maps_fake_yfinance_chain_and_filters_moneyness() -> None:
    ticker = FakeOptionsTicker(
        chains_by_expiration={
            "2026-07-17": FakeOptionsChainPayload(
                calls=(
                    {
                        "contractSymbol": "AAPL260717C00190000",
                        "strike": "190",
                        "lastPrice": "12.5",
                        "bid": "12.4",
                        "ask": "12.6",
                        "volume": "1000",
                        "openInterest": "5000",
                        "delta": "0.61",
                        "gamma": "0.04",
                        "theta": "-0.03",
                        "vega": "0.18",
                        "rho": "0.05",
                        "impliedVolatility": "0.32",
                    },
                    {"contractSymbol": "AAPL260717C00210000", "strike": "210"},
                ),
                puts=(
                    {"contractSymbol": "AAPL260717P00190000", "strike": "190"},
                    {
                        "contractSymbol": "AAPL260717P00210000",
                        "strike": "210",
                        "lastPrice": "13.1",
                        "bid": "13.0",
                        "ask": "13.2",
                        "openInterest": "4200",
                        "delta": "-0.39",
                        "impliedVolatility": "0.31",
                    },
                ),
            )
        },
        spot_price=Decimal("200"),
    )
    factory = FakeOptionsTickerFactory(ticker)
    result = YahooOptionsProvider(factory).lookup_options(
        DigitalOracleOptionsProviderQuery(
            symbol="AAPL",
            expirations=(date(2026, 7, 17),),
            include_greeks=True,
            moneyness="itm",
            item_limit=5,
            timeout_seconds=2.5,
        )
    )
    assert factory.symbols == ["AAPL"]
    assert ticker.option_chain_calls == ["2026-07-17"]
    assert result.warnings == ()
    chain = result.chains[0]
    assert chain.expiry_date == date(2026, 7, 17)
    assert chain.calls[0].contract_symbol == "AAPL260717C00190000"
    assert chain.calls[0].greeks == DigitalOracleOptionGreeks(
        delta=Decimal("0.61"),
        gamma=Decimal("0.04"),
        theta=Decimal("-0.03"),
        vega=Decimal("0.18"),
        rho=Decimal("0.05"),
        implied_volatility=Decimal("0.32"),
    )
    assert [contract.contract_symbol for contract in chain.puts] == ["AAPL260717P00210000"]


def test_options_lookup_service_and_executor_return_normalized_fake_provider_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeDigitalOracleProvider(
        result=DigitalOracleOptionsProviderResult(
            provider="yahoo",
            chains=(
                DigitalOracleOptionsChain(
                    provider="yahoo",
                    symbol="AAPL",
                    expiry_date=date(2026, 7, 17),
                    calls=(
                        DigitalOracleOptionContract(
                            contract_symbol="AAPL260717C00200000",
                            strike=Decimal("200"),
                            bid=Decimal("6.2"),
                            ask=Decimal("6.3"),
                            last_price=Decimal("6.25"),
                            volume=Decimal("1000"),
                            open_interest=Decimal("5000"),
                            greeks=DigitalOracleOptionGreeks(implied_volatility=Decimal("0.32")),
                        ),
                    ),
                    puts=(
                        DigitalOracleOptionContract(
                            contract_symbol="AAPL260717P00200000",
                            strike=Decimal("200"),
                            bid=Decimal("5.7"),
                            ask=Decimal("5.8"),
                            last_price=Decimal("5.75"),
                        ),
                    ),
                ),
            ),
        )
    )
    monkeypatch.setattr(
        "oracle_plugin.factory.importlib.util.find_spec", lambda module_name: object()
    )
    service_payload = map_options_result(
        DigitalOraclePhase1Service(options_providers=(provider,)).lookup_options(
            DigitalOracleOptionsQuery(
                symbols=(" aapl ",),
                expirations=(date(2026, 7, 17),),
                include_greeks=True,
                moneyness="near_the_money",
                item_limit=1,
            )
        )
    ).model_dump(mode="json", by_alias=True)
    monkeypatch.setattr(
        "oracle_plugin.runtime_options.create_options_providers", lambda: (provider,)
    )
    executor_payload = execute_options_lookup(
        RuntimeToolContext(),
        parse_options_lookup_arguments(
            json.dumps(
                {
                    "symbols": ["AAPL"],
                    "expirations": ["2026-07-17"],
                    "includeGreeks": True,
                    "moneyness": "near_the_money",
                    "itemLimit": 1,
                }
            )
        ),
    )
    for payload in (service_payload, executor_payload):
        _assert_native_runtime_payload_is_json_safe_and_camel(payload)
        assert payload["toolKey"] == OPTIONS_LOOKUP_TOOL_KEY
        assert payload["symbol"] == "AAPL"
        chain = cast(list[dict[str, object]], payload["chains"])[0]
        assert chain["expiryDate"] == "2026-07-17"
        call = cast(list[dict[str, object]], chain["calls"])[0]
        assert call["contractSymbol"] == "AAPL260717C00200000"
        assert call["bid"] == "6.2"
        assert cast(dict[str, object], call["greeks"])["impliedVolatility"] == "0.32"
        assert payload["warnings"] == []


def test_sec_filings_parser_normalizes_ticker_form_types_and_dates() -> None:
    arguments = parse_sec_filings_lookup_arguments(
        json.dumps(
            {
                "ticker": " nvda ",
                "query": "  Annual   report  ",
                "cik": "CIK1045810",
                "formTypes": [" 10-k ", "8-K", "10-K"],
                "startDate": "2026-01-01",
                "endDate": "2026-12-31",
                "itemLimit": 3,
                "includeOwnershipTransactions": True,
            }
        )
    )
    assert arguments == {
        "ticker": "NVDA",
        "query": "Annual report",
        "cik": "0001045810",
        "form_types": ("10-K", "8-K"),
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 12, 31),
        "item_limit": 3,
        "include_ownership_transactions": True,
    }
    assert parse_sec_filings_lookup_arguments(json.dumps({"cik": "320193"})) == {
        "ticker": None,
        "query": None,
        "cik": "0000320193",
        "form_types": None,
        "start_date": None,
        "end_date": None,
        "item_limit": None,
        "include_ownership_transactions": False,
    }
    with pytest.raises(RuntimeToolError, match="unsupported fields"):
        _ = parse_sec_filings_lookup_arguments(json.dumps({"ticker": "NVDA", "contactEmail": "x"}))
    with pytest.raises(RuntimeToolError, match="ticker or cik is required"):
        _ = parse_sec_filings_lookup_arguments(json.dumps({"query": "annual report"}))
    with pytest.raises(RuntimeToolError, match="query must not be empty"):
        _ = parse_sec_filings_lookup_arguments(json.dumps({"ticker": "NVDA", "query": "   "}))
    with pytest.raises(RuntimeToolError, match="cik must contain 1 to 10 digits"):
        _ = parse_sec_filings_lookup_arguments(json.dumps({"cik": "12-34"}))
    with pytest.raises(RuntimeToolError, match="includeOwnershipTransactions must be a boolean"):
        _ = parse_sec_filings_lookup_arguments(
            json.dumps({"ticker": "NVDA", "includeOwnershipTransactions": "yes"})
        )
    with pytest.raises(RuntimeToolError, match="startDate must be before or equal to endDate"):
        _ = parse_sec_filings_lookup_arguments(
            json.dumps({"ticker": "NVDA", "startDate": "2026-12-31", "endDate": "2026-01-01"})
        )


def test_edgar_sec_filings_provider_maps_company_submissions_to_normalized_filings() -> None:
    form4_xml = (
        "\n<ownershipDocument>\n  <issuer>\n    <issuerName>NVIDIA CORP</issu"
        "erName>\n    <issuerTradingSymbol>NVDA</issuerTradingSymbol>\n  </i"
        "ssuer>\n  <reportingOwner>\n    <reportingOwnerId><rptOwnerName>Ada"
        " Lovelace</rptOwnerName></reportingOwnerId>\n  </reportingOwner>\n "
        " <nonDerivativeTable>\n    <nonDerivativeTransaction>\n      <trans"
        "actionDate><value>2026-02-21</value></transactionDate>\n      <tra"
        "nsactionCoding><transactionCode>P</transactionCode></transactionC"
        "oding>\n      <transactionAmounts>\n        <transactionShares><val"
        "ue>10</value></transactionShares>\n        <transactionPricePerSha"
        "re><value>120.25</value></transactionPricePerShare>\n        <tran"
        "sactionAcquiredDisposedCode><value>A</value></transactionAcquired"
        "DisposedCode>\n      </transactionAmounts>\n      <ownershipNature>"
        "<directOrIndirectOwnership><value>D</value></directOrIndirectOwne"
        "rship></ownershipNature>\n    </nonDerivativeTransaction>\n  </nonD"
        "erivativeTable>\n</ownershipDocument>\n"
    )
    newer_form4_xml = (
        "\n<ownershipDocument>\n  <issuer>\n    <issuerName>NVIDIA CORP</issu"
        "erName>\n    <issuerTradingSymbol>NVDA</issuerTradingSymbol>\n  </i"
        "ssuer>\n  <reportingOwner>\n    <reportingOwnerId><rptOwnerName>Gra"
        "ce Hopper</rptOwnerName></reportingOwnerId>\n  </reportingOwner>\n "
        " <nonDerivativeTable>\n    <nonDerivativeTransaction>\n      <trans"
        "actionDate><value>2026-03-04</value></transactionDate>\n      <tra"
        "nsactionCoding><transactionCode>S</transactionCode></transactionC"
        "oding>\n      <transactionAmounts>\n        <transactionShares><val"
        "ue>5</value></transactionShares>\n        <transactionPricePerShar"
        "e><value>130.50</value></transactionPricePerShare>\n        <trans"
        "actionAcquiredDisposedCode><value>D</value></transactionAcquiredD"
        "isposedCode>\n      </transactionAmounts>\n      <ownershipNature><"
        "directOrIndirectOwnership><value>I</value></directOrIndirectOwner"
        "ship></ownershipNature>\n    </nonDerivativeTransaction>\n  </nonDe"
        "rivativeTable>\n</ownershipDocument>\n"
    )
    client = FakeJsonClient(
        {
            "company_tickers": {
                "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}
            },
            "CIK0001045810": {
                "name": "NVIDIA CORP",
                "filings": {
                    "recent": {
                        "accessionNumber": [
                            "0001045810-26-000010",
                            "0001045810-26-000011",
                            "0001045810-26-000020",
                            "0001045810-26-000021",
                        ],
                        "form": ["10-K", "8-K", "4", "4"],
                        "filingDate": [
                            "2026-02-20",
                            "2026-03-01",
                            "2026-02-22",
                            "2026-03-05",
                        ],
                        "acceptanceDateTime": [
                            "2026-02-20T16:30:01.000Z",
                            "20260301120000",
                            "2026-02-22T12:00:00Z",
                            "2026-03-05T12:00:00Z",
                        ],
                        "primaryDocument": [
                            "nvda-20260131.htm",
                            "nvda-8k.htm",
                            "form4.xml",
                            "form4-new.xml",
                        ],
                        "primaryDocDescription": [
                            "Annual report",
                            "Current report",
                            "Statement of changes in beneficial ownership",
                            "Statement of changes in beneficial ownership",
                        ],
                    }
                },
            },
        },
        text_by_url_fragment={"form4.xml": form4_xml, "form4-new.xml": newer_form4_xml},
    )
    provider = EdgarSecFilingsProvider(http_client=client)
    result = provider.lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="NVDA",
            form_types=(),
            start_date=None,
            end_date=None,
            item_limit=2,
            edgar_contact_email="sec-contact@example.test",
            timeout_seconds=2.5,
            include_ownership_transactions=True,
        )
    )
    assert [call["contactEmail"] for call in client.calls] == [
        "sec-contact@example.test",
        "sec-contact@example.test",
    ]
    assert [call["timeout"] for call in client.calls] == [2.5, 2.5]
    assert result.cik == "0001045810"
    assert result.entity_name == "NVIDIA CORP"
    assert result.warnings == ()
    assert [filing.form_type for filing in result.filings] == ["10-K", "8-K", "4", "4"]
    assert result.filings[0].accepted_at == datetime(2026, 2, 20, 16, 30, 1, tzinfo=UTC)
    assert (
        result.filings[0].url
        == "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000010/nvda-20260131.htm"
    )
    assert result.filings[0].description == "Annual report"
    assert len(client.text_calls) == 1
    assert client.text_calls[0]["contactEmail"] == "sec-contact@example.test"
    assert "form4-new.xml" in str(client.text_calls[0]["url"])
    assert result.ownership_transactions == (
        DigitalOracleSecOwnershipTransaction(
            accession_number="0001045810-26-000021",
            filing_date=date(2026, 3, 5),
            issuer_name="NVIDIA CORP",
            issuer_ticker="NVDA",
            reporting_owner_name="Grace Hopper",
            transaction_date=date(2026, 3, 4),
            transaction_code="S",
            acquired_disposed_code="D",
            shares=Decimal("5"),
            price=Decimal("130.50"),
            ownership_nature="I",
        ),
    )


def test_edgar_sec_filings_provider_uses_first_exact_ticker_when_mapping_is_ambiguous() -> None:
    client = FakeJsonClient(
        {
            "company_tickers": {
                "0": {"cik_str": 1111111, "ticker": "NVDA", "title": "FIRST NVDA CORP"},
                "1": {
                    "cik_str": 2222222,
                    "ticker": "NVDA",
                    "title": "SECOND NVDA CORP",
                },
            },
            "CIK0001111111": {
                "name": "FIRST NVDA CORP",
                "filings": {
                    "recent": {
                        "accessionNumber": ["0001111111-26-000010"],
                        "form": ["10-K"],
                        "filingDate": ["2026-02-20"],
                    }
                },
            },
        }
    )
    result = EdgarSecFilingsProvider(http_client=client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="NVDA",
            form_types=(),
            start_date=None,
            end_date=None,
            item_limit=10,
            edgar_contact_email="sec-contact@example.test",
            timeout_seconds=2.5,
        )
    )
    assert [call["url"] for call in client.calls] == [
        "https://www.sec.gov/files/company_tickers.json",
        "https://data.sec.gov/submissions/CIK0001111111.json",
    ]
    assert result.cik == "0001111111"
    assert result.entity_name == "FIRST NVDA CORP"
    assert result.filings[0].accession_number == "0001111111-26-000010"
    assert result.warnings == ()


def test_edgar_sec_filings_provider_supports_cik_lookup_without_ticker() -> None:
    client = FakeJsonClient(
        {
            "company_tickers": {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "APPLE INC"}},
            "CIK0000320193": {
                "name": "APPLE INC",
                "filings": {
                    "recent": {
                        "accessionNumber": ["0000320193-26-000010"],
                        "form": ["10-K"],
                        "filingDate": ["2026-02-20"],
                    }
                },
            },
        }
    )
    result = EdgarSecFilingsProvider(http_client=client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker=None,
            query=None,
            cik="0000320193",
            form_types=(),
            start_date=None,
            end_date=None,
            item_limit=10,
            edgar_contact_email="sec-contact@example.test",
            timeout_seconds=2.5,
        )
    )
    assert [call["url"] for call in client.calls] == [
        "https://www.sec.gov/files/company_tickers.json",
        "https://data.sec.gov/submissions/CIK0000320193.json",
    ]
    assert result.ticker == "AAPL"
    assert result.cik == "0000320193"
    assert result.entity_name == "APPLE INC"
    assert result.filings[0].accession_number == "0000320193-26-000010"


def test_edgar_sec_filings_provider_tolerates_optional_arrays_and_reuses_cik_cache() -> None:
    client = FakeJsonClient(
        {
            "company_tickers": {
                "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}
            },
            "CIK0001045810": {
                "name": "NVIDIA CORP",
                "filings": {
                    "recent": {
                        "accessionNumber": ["0001045810-26-000010"],
                        "form": ["10-K"],
                        "filingDate": ["2026-02-20"],
                    }
                },
            },
        }
    )
    provider = EdgarSecFilingsProvider(http_client=client)
    query = DigitalOracleSecFilingsProviderQuery(
        ticker="NVDA",
        form_types=(),
        start_date=None,
        end_date=None,
        item_limit=10,
        edgar_contact_email="sec-contact@example.test",
        timeout_seconds=2.5,
    )
    first_result = provider.lookup_sec_filings(query)
    second_result = provider.lookup_sec_filings(query)
    assert [call["url"] for call in client.calls].count(
        "https://www.sec.gov/files/company_tickers.json"
    ) == 1
    assert first_result.filings[0].primary_document is None
    assert first_result.filings[0].description is None
    assert (
        first_result.filings[0].url
        == "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000010"
    )
    assert second_result.filings[0].accession_number == "0001045810-26-000010"


def test_edgar_sec_filings_provider_warns_when_recent_data_is_archived_only() -> None:
    client = FakeJsonClient(
        {
            "company_tickers": {
                "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}
            },
            "CIK0001045810": {
                "name": "NVIDIA CORP",
                "filings": {
                    "recent": {"accessionNumber": []},
                    "files": [{"name": "CIK.json"}],
                },
            },
        }
    )
    result = EdgarSecFilingsProvider(http_client=client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="NVDA",
            form_types=(),
            start_date=None,
            end_date=None,
            item_limit=10,
            edgar_contact_email="sec-contact@example.test",
            timeout_seconds=2.5,
        )
    )
    assert result.filings == ()
    assert [warning.code for warning in result.warnings] == ["sec_filings_stale_archive"]
    assert result.warnings[0].details == {
        "operation": "sec_filings",
        "provider": "edgar",
        "ticker": "NVDA",
        "cik": "0001045810",
    }


def test_edgar_sec_filings_provider_warns_for_ticker_miss_and_malformed_recent_rows() -> None:
    not_found_client = FakeJsonClient(
        {"company_tickers": {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "APPLE INC"}}}
    )
    not_found_result = EdgarSecFilingsProvider(http_client=not_found_client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="NVDA",
            form_types=(),
            start_date=None,
            end_date=None,
            item_limit=10,
            edgar_contact_email="sec-contact@example.test",
            timeout_seconds=2.5,
        )
    )
    assert len(not_found_client.calls) == 1
    assert not_found_result.filings == ()
    assert [warning.code for warning in not_found_result.warnings] == [
        "sec_filings_ticker_not_found"
    ]
    assert not_found_result.warnings[0].details == {
        "operation": "sec_filings",
        "provider": "edgar",
        "ticker": "NVDA",
    }
    malformed_client = FakeJsonClient(
        {
            "company_tickers": {
                "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}
            },
            "CIK0001045810": {
                "name": "NVIDIA CORP",
                "filings": {
                    "recent": {
                        "accessionNumber": ["0001045810-26-000010"],
                        "form": ["10-K"],
                        "filingDate": ["not-a-date"],
                        "primaryDocument": ["nvda-20260131.htm"],
                    }
                },
            },
        }
    )
    malformed_result = EdgarSecFilingsProvider(http_client=malformed_client).lookup_sec_filings(
        DigitalOracleSecFilingsProviderQuery(
            ticker="NVDA",
            form_types=(),
            start_date=None,
            end_date=None,
            item_limit=10,
            edgar_contact_email="sec-contact@example.test",
            timeout_seconds=2.5,
        )
    )
    assert malformed_result.filings == ()
    assert [warning.code for warning in malformed_result.warnings] == [
        "sec_filings_malformed_payload"
    ]
    assert malformed_result.warnings[0].details == {
        "operation": "sec_filings",
        "provider": "edgar",
        "field": "filing row",
    }


def test_sec_filings_runtime_executor_filters_forms_dates_and_returns_normalized_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeDigitalOracleSecFilingsProvider(
        filings=(
            DigitalOracleSecFiling(
                accession_number="0001045810-26-000011",
                form_type="8-K",
                filing_date=date(2025, 12, 31),
                primary_document="nvda-old-8k.htm",
            ),
            DigitalOracleSecFiling(
                accession_number="0001045810-26-000010",
                form_type="10-K",
                filing_date=date(2026, 2, 20),
                accepted_at=_NOW,
                primary_document="nvda-20260131.htm",
                url="https://www.sec.gov/Archives/edgar/data/1045810/fixture.htm",
                description="Annual report",
            ),
            DigitalOracleSecFiling(
                accession_number="0001045810-26-000012",
                form_type="10-Q",
                filing_date=date(2026, 4, 1),
                primary_document="nvda-10q.htm",
            ),
        )
    )
    monkeypatch.setattr(
        "oracle_plugin.runtime_sec_filings.create_sec_filings_provider_adapter",
        lambda: provider,
    )
    reset_digital_oracle_settings_cache()
    try:
        payload = execute_sec_filings_lookup(
            RuntimeToolContext(secrets={"edgar_contact_email": "sec-contact@example.test"}),
            parse_sec_filings_lookup_arguments(
                json.dumps(
                    {
                        "ticker": " nvda ",
                        "query": "annual report",
                        "cik": "1045810",
                        "formTypes": ["10-k", "8-k"],
                        "startDate": "2026-01-01",
                        "endDate": "2026-12-31",
                        "itemLimit": 5,
                        "includeOwnershipTransactions": True,
                    }
                )
            ),
        )
    finally:
        reset_digital_oracle_settings_cache()
    assert provider.calls[0].ticker == "NVDA"
    assert provider.calls[0].query == "annual report"
    assert provider.calls[0].cik == "0001045810"
    assert provider.calls[0].form_types == ("10-K", "8-K")
    assert provider.calls[0].start_date == date(2026, 1, 1)
    assert provider.calls[0].end_date == date(2026, 12, 31)
    assert provider.calls[0].item_limit == 5
    assert provider.calls[0].edgar_contact_email == "sec-contact@example.test"
    assert provider.calls[0].include_ownership_transactions is True
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert payload["toolKey"] == SEC_FILINGS_LOOKUP_TOOL_KEY
    assert payload["ticker"] == "NVDA"
    assert payload["cik"] == "0001045810"
    assert payload["entityName"] == "NVIDIA CORP"
    filings = cast(list[dict[str, object]], payload["filings"])
    assert filings == [
        {
            "accessionNumber": "0001045810-26-000010",
            "formType": "10-K",
            "filingDate": "2026-02-20",
            "acceptedAt": "2026-01-02T03:04:05Z",
            "primaryDocument": "nvda-20260131.htm",
            "url": "https://www.sec.gov/Archives/edgar/data/1045810/fixture.htm",
            "description": "Annual report",
        }
    ]
    search_hits = cast(list[dict[str, object]], payload["searchHits"])
    assert search_hits == [
        {
            "accessionNumber": "0001045810-26-000010",
            "formType": "10-K",
            "filingDate": "2026-02-20",
            "cik": "0001045810",
            "ticker": "NVDA",
            "entityName": "NVIDIA CORP",
            "primaryDocument": "nvda-20260131.htm",
            "url": "https://www.sec.gov/Archives/edgar/data/1045810/fixture.htm",
            "description": "Annual report",
            "matchedText": "Annual report",
        }
    ]
    assert payload["ownershipTransactions"] == []
    assert payload["warnings"] == []


def test_sec_filings_runtime_executor_uses_context_edgar_contact_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeDigitalOracleSecFilingsProvider(
        filings=(
            DigitalOracleSecFiling(
                accession_number="0001045810-26-000010",
                form_type="10-K",
                filing_date=date(2026, 2, 20),
            ),
        )
    )
    monkeypatch.setattr(
        "oracle_plugin.runtime_sec_filings.create_sec_filings_provider_adapter",
        lambda: provider,
    )
    reset_digital_oracle_settings_cache()
    try:
        payload = execute_sec_filings_lookup(
            RuntimeToolContext(secrets={"edgar_contact_email": "caller-edgar@example.test"}),
            parse_sec_filings_lookup_arguments(json.dumps({"ticker": "NVDA"})),
        )
    finally:
        reset_digital_oracle_settings_cache()
    assert provider.calls[0].edgar_contact_email == "caller-edgar@example.test"
    assert payload["filings"] == [
        {
            "accessionNumber": "0001045810-26-000010",
            "formType": "10-K",
            "filingDate": "2026-02-20",
            "acceptedAt": None,
            "primaryDocument": None,
            "url": None,
            "description": None,
        }
    ]
    assert "caller-edgar@example.test" not in json.dumps(payload)


def test_sec_filings_runtime_executor_preserves_missing_edgar_email_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeDigitalOracleSecFilingsProvider(
        filings=(
            DigitalOracleSecFiling(
                accession_number="0001045810-26-000010",
                form_type="10-K",
                filing_date=date(2026, 2, 20),
            ),
        )
    )
    monkeypatch.setattr(
        "oracle_plugin.runtime_sec_filings.create_sec_filings_provider_adapter",
        lambda: provider,
    )
    reset_digital_oracle_settings_cache()
    try:
        payload = execute_sec_filings_lookup(
            RuntimeToolContext(),
            parse_sec_filings_lookup_arguments(json.dumps({"ticker": "NVDA"})),
        )
    finally:
        reset_digital_oracle_settings_cache()
    assert provider.calls == []
    assert payload["filings"] == []
    assert payload["warnings"] == [
        {
            "code": EDGAR_CONTACT_EMAIL_MISSING_CODE,
            "message": EDGAR_CONTACT_EMAIL_MISSING_MESSAGE,
            "details": [
                {"key": "operation", "value": "sec_filings"},
                {"key": "provider", "value": "edgar"},
            ],
        }
    ]


def test_sec_filings_runtime_executor_degrades_provider_failure_and_redacts_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeDigitalOracleSecFilingsProvider(
        filings=(),
        failure=DigitalOracleProviderError(
            "SEC EDGAR rate limited api_key=sk-edgar-secret",
            code="provider_rate_limited",
            details={"request_id": "edgar-123", "api_key": "sk-edgar-secret"},
        ),
    )
    monkeypatch.setattr(
        "oracle_plugin.runtime_sec_filings.create_sec_filings_provider_adapter",
        lambda: provider,
    )
    reset_digital_oracle_settings_cache()
    try:
        payload = execute_sec_filings_lookup(
            RuntimeToolContext(secrets={"edgar_contact_email": "sec-contact@example.test"}),
            parse_sec_filings_lookup_arguments(json.dumps({"ticker": "NVDA"})),
        )
    finally:
        reset_digital_oracle_settings_cache()
    assert provider.calls[0].edgar_contact_email == "sec-contact@example.test"
    assert payload["filings"] == []
    warning_json = json.dumps(payload["warnings"])
    assert "sk-edgar-secret" not in warning_json
    assert payload["warnings"] == [
        {
            "code": "sec_filings_provider_rate_limited",
            "message": "SEC EDGAR rate limited api_key=<redacted>",
            "details": [
                {"key": "operation", "value": "sec_filings"},
                {"key": "provider", "value": "edgar"},
                {"key": "requestId", "value": "edgar-123"},
            ],
        },
        {
            "code": "sec_filings_unavailable",
            "message": "No sec_filings data available from configured providers.",
            "details": [{"key": "operation", "value": "sec_filings"}],
        },
    ]


def test_sec_filings_runtime_executor_returns_empty_warning_for_configured_edgar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeDigitalOracleSecFilingsProvider(filings=())
    monkeypatch.setattr(
        "oracle_plugin.runtime_sec_filings.create_sec_filings_provider_adapter",
        lambda: provider,
    )
    reset_digital_oracle_settings_cache()
    try:
        payload = execute_sec_filings_lookup(
            RuntimeToolContext(secrets={"edgar_contact_email": "sec-contact@example.test"}),
            parse_sec_filings_lookup_arguments(json.dumps({"ticker": "NVDA"})),
        )
    finally:
        reset_digital_oracle_settings_cache()
    assert provider.calls[0].edgar_contact_email == "sec-contact@example.test"
    assert payload["filings"] == []
    assert payload["warnings"] == [
        {
            "code": "sec_filings_empty",
            "message": "No sec_filings data returned from edgar.",
            "details": [
                {"key": "operation", "value": "sec_filings"},
                {"key": "provider", "value": "edgar"},
            ],
        }
    ]


def test_macro_rates_parser_normalizes_sources_families_dates_and_filters() -> None:
    arguments = parse_macro_rates_lookup_arguments(
        json.dumps(
            {
                "query": "  Fed   rates  ",
                "sources": [" FRED ", "treasury", "fred"],
                "families": [" Policy_Rates ", "yield_curve", "policy_rates"],
                "seriesIds": [" DGS10 ", "DGS10", "FEDFUNDS"],
                "countries": [" us ", "United States", "US"],
                "startDate": "2026-01-01",
                "endDate": "2026-01-31",
                "asOfDate": "2026-02-01",
                "itemLimit": 3,
            }
        )
    )
    assert arguments == {
        "query": "Fed rates",
        "sources": ("fred", "treasury"),
        "families": ("policy_rates", "yield_curve"),
        "series_ids": ("DGS10", "FEDFUNDS"),
        "countries": ("US", "UNITED STATES"),
        "start_date": date(2026, 1, 1),
        "end_date": date(2026, 1, 31),
        "as_of_date": date(2026, 2, 1),
        "item_limit": 3,
    }
    assert parse_macro_rates_lookup_arguments("{}") == {
        "query": None,
        "sources": None,
        "families": None,
        "series_ids": None,
        "countries": None,
        "start_date": None,
        "end_date": None,
        "as_of_date": None,
        "item_limit": None,
    }
    with pytest.raises(RuntimeToolError, match="sources must use"):
        _ = parse_macro_rates_lookup_arguments(json.dumps({"sources": ["ecb"]}))
    with pytest.raises(RuntimeToolError, match="families must use"):
        _ = parse_macro_rates_lookup_arguments(json.dumps({"families": ["rates"]}))
    with pytest.raises(RuntimeToolError, match="families must use"):
        _ = parse_macro_rates_lookup_arguments(json.dumps({"families": ["policy_rate"]}))
    with pytest.raises(RuntimeToolError, match="families must use"):
        _ = parse_macro_rates_lookup_arguments(json.dumps({"families": ["macro_indicator"]}))
    with pytest.raises(RuntimeToolError, match="startDate must be before or equal to endDate"):
        _ = parse_macro_rates_lookup_arguments(
            json.dumps({"startDate": "2026-02-01", "endDate": "2026-01-01"})
        )
    with pytest.raises(RuntimeToolError, match="itemLimit must be at most 50"):
        _ = parse_macro_rates_lookup_arguments(json.dumps({"itemLimit": 51}))


def test_macro_rates_providers_map_public_payloads_to_normalized_series() -> None:
    client = FakeJsonClient(
        {
            "fred/series/observations": {
                "observations": [
                    {"date": "2026-01-02", "value": "4.33"},
                    {"date": "2026-01-03", "value": "."},
                ]
            },
            "treasury.gov": {
                "data": [
                    {
                        "record_date": "2026-01-02",
                        "security_desc": "10-Year Treasury Constant Maturity",
                        "avg_interest_rate_amt": "4.15",
                        "security_term": "10 Yr",
                    }
                ]
            },
            "bis.org": {
                "observations": [
                    {
                        "date": "2026-01-02",
                        "value": "5.25",
                        "country": "US",
                        "series_id": "BIS-US-POLICY",
                        "label": "United States policy rate",
                    }
                ]
            },
        }
    )
    fred_query = DigitalOracleMacroRatesProviderQuery(
        source="fred",
        query="Fed funds",
        families=("macro_indicators",),
        series_ids=("FEDFUNDS",),
        countries=("US",),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        as_of_date=None,
        item_limit=5,
        timeout_seconds=2.5,
        fred_api_key="fred-key",
    )
    treasury_query = replace(
        fred_query, source="treasury", families=("yield_curve",), fred_api_key=None
    )
    bis_query = replace(fred_query, source="bis", families=("policy_rates",), fred_api_key=None)
    fred_result = FredMacroRatesProvider(client).lookup_macro_rates(fred_query)
    treasury_result = TreasuryMacroRatesProvider(client).lookup_macro_rates(treasury_query)
    bis_result = BisMacroRatesProvider(client).lookup_macro_rates(bis_query)
    assert fred_result.series[0].provider == "fred"
    assert fred_result.series[0].family == "macro_indicators"
    assert fred_result.series[0].series_id == "FEDFUNDS"
    assert fred_result.series[0].date == date(2026, 1, 2)
    assert fred_result.series[0].value == Decimal("4.33")
    assert [warning.code for warning in fred_result.warnings] == ["macro_rates_malformed_payload"]
    assert treasury_result.series[0].tenor == "10Y"
    assert treasury_result.series[0].family == "yield_curve"
    assert bis_result.series[0].family == "policy_rates"
    assert bis_result.series[0].country == "US"
    non_fred_calls = [call for call in client.calls if call["provider"] != "fred"]
    assert "fred-key" not in json.dumps(non_fred_calls)


def test_macro_rates_runtime_executor_returns_normalized_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fred_provider = FakeDigitalOracleProvider(
        "fred",
        series=(
            DigitalOracleMacroRatesSeries(
                provider="fred",
                family="macro_indicators",
                series_id="FEDFUNDS",
                label="Federal Funds Effective Rate",
                country="US",
                currency="USD",
                unit="percent",
                date=date(2026, 1, 2),
                value=Decimal("4.33"),
                source_url="https://fred.stlouisfed.org/series/FEDFUNDS",
            ),
        ),
    )
    treasury_provider = FakeDigitalOracleProvider(
        "treasury",
        series=(
            DigitalOracleMacroRatesSeries(
                provider="treasury",
                family="yield_curve",
                series_id="UST-10Y",
                label="US Treasury 10Y par yield",
                country="US",
                currency="USD",
                unit="percent",
                date=date(2026, 1, 2),
                value=Decimal("4.15"),
                tenor="10Y",
                source_url="https://home.treasury.gov/",
            ),
        ),
    )
    bis_provider = FakeDigitalOracleProvider(
        "bis",
        series=(
            DigitalOracleMacroRatesSeries(
                provider="bis",
                family="policy_rates",
                series_id="BIS-US-POLICY",
                label="United States policy rate",
                country="US",
                currency="USD",
                unit="percent",
                date=date(2026, 1, 2),
                value=Decimal("5.25"),
                source_url="https://www.bis.org/statistics/",
            ),
        ),
    )
    monkeypatch.setattr(
        "oracle_plugin.runtime_macro_rates.create_macro_rates_providers",
        lambda: (fred_provider, treasury_provider, bis_provider),
    )
    reset_digital_oracle_settings_cache()
    try:
        payload = execute_macro_rates_lookup(
            RuntimeToolContext(secrets={"fred_api_key": "fred-key"}),
            parse_macro_rates_lookup_arguments(
                json.dumps(
                    {
                        "query": "rates",
                        "sources": ["fred", "treasury", "bis"],
                        "itemLimit": 3,
                    }
                )
            ),
        )
    finally:
        reset_digital_oracle_settings_cache()
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert payload["toolKey"] == MACRO_RATES_LOOKUP_TOOL_KEY
    assert payload["query"] == "rates"
    series = cast(list[dict[str, object]], payload["series"])
    assert [item["provider"] for item in series] == ["fred", "treasury", "bis"]
    assert [item["seriesId"] for item in series] == [
        "FEDFUNDS",
        "UST-10Y",
        "BIS-US-POLICY",
    ]
    assert series[1]["tenor"] == "10Y"
    assert payload["warnings"] == []


def test_macro_rates_runtime_executor_uses_context_fred_api_key_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fred_provider = FakeDigitalOracleProvider(
        "fred",
        series=(
            DigitalOracleMacroRatesSeries(
                provider="fred",
                family="macro_indicators",
                series_id="FEDFUNDS",
                label="Federal Funds Effective Rate",
                country="US",
                currency="USD",
                unit="percent",
                date=date(2026, 1, 2),
                value=Decimal("4.33"),
            ),
        ),
    )
    monkeypatch.setattr(
        "oracle_plugin.runtime_macro_rates.create_macro_rates_providers",
        lambda: (fred_provider,),
    )
    reset_digital_oracle_settings_cache()
    try:
        payload = execute_macro_rates_lookup(
            RuntimeToolContext(secrets={"fred_api_key": "caller-fred-key"}),
            parse_macro_rates_lookup_arguments(
                json.dumps({"sources": ["fred"], "seriesIds": ["FEDFUNDS"], "itemLimit": 1})
            ),
        )
    finally:
        reset_digital_oracle_settings_cache()
    assert fred_provider.calls[0].fred_api_key == "caller-fred-key"
    assert payload["series"] == [
        {
            "provider": "fred",
            "family": "macro_indicators",
            "seriesId": "FEDFUNDS",
            "label": "Federal Funds Effective Rate",
            "country": "US",
            "currency": "USD",
            "unit": "percent",
            "date": "2026-01-02",
            "value": "4.33",
            "tenor": None,
            "sourceUrl": None,
        }
    ]
    assert "caller-fred-key" not in json.dumps(payload)


def test_macro_rates_runtime_executor_preserves_partial_warnings_without_fred_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treasury_provider = FakeDigitalOracleProvider(
        "treasury",
        series=(
            DigitalOracleMacroRatesSeries(
                provider="treasury",
                family="yield_curve",
                series_id="UST-10Y",
                label="US Treasury 10Y par yield",
                country="US",
                currency="USD",
                unit="percent",
                date=date(2026, 1, 2),
                value=Decimal("4.15"),
                tenor="10Y",
                source_url="https://home.treasury.gov/",
            ),
        ),
    )
    bis_provider = FakeDigitalOracleProvider(
        "bis",
        failure=DigitalOracleProviderError(
            "BIS timed out while fetching policy rates",
            code="provider_timeout",
            details={"provider": "bis"},
        ),
    )
    fred_provider = FakeDigitalOracleProvider("fred")
    monkeypatch.setattr(
        "oracle_plugin.runtime_macro_rates.create_macro_rates_providers",
        lambda: (treasury_provider, bis_provider, fred_provider),
    )
    reset_digital_oracle_settings_cache()
    try:
        payload = execute_macro_rates_lookup(
            RuntimeToolContext(),
            parse_macro_rates_lookup_arguments(
                json.dumps({"sources": ["treasury", "bis", "fred"], "itemLimit": 5})
            ),
        )
    finally:
        reset_digital_oracle_settings_cache()
    assert fred_provider.calls == []
    assert treasury_provider.calls[0].source == "treasury"
    assert bis_provider.calls[0].source == "bis"
    series = cast(list[dict[str, object]], payload["series"])
    warnings = cast(list[dict[str, object]], payload["warnings"])
    assert [item["provider"] for item in series] == ["treasury"]
    assert [warning["code"] for warning in warnings] == [
        FRED_API_KEY_MISSING_CODE,
        "macro_rates_provider_timeout",
        "macro_rates_partial_result",
    ]
    assert warnings[0]["message"] == FRED_API_KEY_MISSING_MESSAGE
    assert warnings[0]["details"] == [
        {"key": "operation", "value": "macro_rates"},
        {"key": "provider", "value": "fred"},
    ]
    assert warnings[1]["details"] == [
        {"key": "operation", "value": "macro_rates"},
        {"key": "provider", "value": "bis"},
    ]


def test_market_sentiment_parser_normalizes_indicator_and_as_of_date() -> None:
    arguments = parse_market_sentiment_lookup_arguments(
        json.dumps({"indicator": " Fear_Greed ", "asOfDate": "2026-01-02"})
    )
    assert arguments == {"indicator": "fear_greed", "as_of_date": date(2026, 1, 2)}
    with pytest.raises(RuntimeToolError) as invalid_indicator:
        _ = parse_market_sentiment_lookup_arguments(json.dumps({"indicator": "social_sentiment"}))
    assert (
        invalid_indicator.value.message
        == "signaldeck_digital_oracle_market_sentiment_lookup indicator must use: fear_greed."
    )
    with pytest.raises(RuntimeToolError, match="unsupported fields"):
        _ = parse_market_sentiment_lookup_arguments(
            json.dumps({"indicator": "fear_greed", "symbol": "NVDA"})
        )


def test_fear_greed_provider_maps_snapshot_to_normalized_market_sentiment() -> None:
    client = FakeJsonClient(
        payload={
            "fear_and_greed": {
                "score": 72.4,
                "rating": "Greed",
                "timestamp": "2026-01-02T03:04:05Z",
                "previous_close": 70.1,
                "previous_1_week": "64",
                "previous_1_month": 55.4,
                "previous_1_year": 41,
            }
        }
    )
    result = FearGreedMarketSentimentProvider(http_client=client).lookup_market_sentiment(
        DigitalOracleMarketSentimentProviderQuery(
            indicator="fear_greed",
            as_of_date=None,
            source_url=MARKET_SENTIMENT_SOURCE_URL,
            timeout_seconds=2.5,
        )
    )
    assert client.calls[0]["timeout"] == 2.5
    assert client.calls[0]["sourceUrl"] == MARKET_SENTIMENT_SOURCE_URL
    assert result.provider == "fear_greed"
    assert result.score == 72
    assert result.label == "greed"
    assert result.as_of_date == date(2026, 1, 2)
    assert result.previous_close == 70
    assert result.week_ago == 64
    assert result.month_ago == 55
    assert result.year_ago == 41
    assert result.source_url == MARKET_SENTIMENT_SOURCE_URL
    assert result.warnings == ()


def test_fear_greed_provider_warns_for_sparse_history_without_inventing_values() -> None:
    client = FakeJsonClient(
        payload={
            "fear_and_greed": {
                "score": 18,
                "timestamp": 1767225600000,
                "previous_close": 21,
                "previous_1_week": 30,
                "previous_1_month": 44,
            }
        }
    )
    result = FearGreedMarketSentimentProvider(http_client=client).lookup_market_sentiment(
        DigitalOracleMarketSentimentProviderQuery(
            indicator="fear_greed",
            as_of_date=None,
            source_url=MARKET_SENTIMENT_SOURCE_URL,
            timeout_seconds=2.5,
        )
    )
    assert result.score == 18
    assert result.label == "extreme_fear"
    assert result.as_of_date == date(2026, 1, 1)
    assert result.year_ago is None
    assert result.warnings == (
        RuntimeToolWarning(
            code="market_sentiment_sparse_history",
            message=(
                "Fear & Greed history is incomplete for the requested " "market sentiment snapshot."
            ),
            details={
                "operation": "market_sentiment",
                "provider": "fear_greed",
                "missingFields": "yearAgo",
            },
        ),
    )


@pytest.mark.parametrize(
    ("score", "expected_label"),
    [
        (24, "extreme_fear"),
        (25, "fear"),
        (44, "fear"),
        (45, "neutral"),
        (55, "neutral"),
        (74, "greed"),
        (75, "extreme_greed"),
    ],
)
def test_fear_greed_provider_derives_missing_rating_with_required_thresholds(
    score: int, expected_label: str
) -> None:
    client = FakeJsonClient(
        payload={
            "fear_and_greed": {
                "score": score,
                "timestamp": "2026-01-02",
                "previous_close": 70,
                "previous_1_week": 64,
                "previous_1_month": 55,
                "previous_1_year": 41,
            }
        }
    )
    result = FearGreedMarketSentimentProvider(http_client=client).lookup_market_sentiment(
        DigitalOracleMarketSentimentProviderQuery(
            indicator="fear_greed",
            as_of_date=None,
            source_url=MARKET_SENTIMENT_SOURCE_URL,
            timeout_seconds=2.5,
        )
    )
    assert result.label == expected_label
    assert result.score == score
    assert result.source_url == MARKET_SENTIMENT_SOURCE_URL
    assert result.warnings == ()


def test_market_sentiment_runtime_executor_returns_normalized_fear_greed_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeDigitalOracleProvider(
        DigitalOracleMarketSentimentProviderResult(
            provider="fear_greed",
            score=79,
            label="extreme_greed",
            as_of_date=date(2026, 1, 2),
            previous_close=74,
            week_ago=66,
            month_ago=58,
            year_ago=42,
        )
    )
    monkeypatch.setattr(
        "oracle_plugin.runtime_market_sentiment.create_market_sentiment_provider_adapter",
        lambda: provider,
    )
    payload = execute_market_sentiment_lookup(
        RuntimeToolContext(),
        parse_market_sentiment_lookup_arguments(
            json.dumps({"indicator": "fear_greed", "asOfDate": "2026-01-02"})
        ),
    )
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert provider.calls[0].indicator == "fear_greed"
    assert provider.calls[0].as_of_date == date(2026, 1, 2)
    assert provider.calls[0].source_url == MARKET_SENTIMENT_SOURCE_URL
    assert payload == {
        "toolKey": MARKET_SENTIMENT_LOOKUP_TOOL_KEY,
        "indicator": "fear_greed",
        "asOfDate": "2026-01-02",
        "provider": "fear_greed",
        "score": 79,
        "label": "extreme_greed",
        "previousClose": 74,
        "weekAgo": 66,
        "monthAgo": 58,
        "yearAgo": 42,
        "sourceUrl": MARKET_SENTIMENT_SOURCE_URL,
        "warnings": [],
    }


def test_market_sentiment_runtime_executor_returns_empty_warning_for_empty_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeDigitalOracleProvider(
        DigitalOracleMarketSentimentProviderResult(provider="fear_greed")
    )
    monkeypatch.setattr(
        "oracle_plugin.runtime_market_sentiment.create_market_sentiment_provider_adapter",
        lambda: provider,
    )
    payload = execute_market_sentiment_lookup(
        RuntimeToolContext(),
        parse_market_sentiment_lookup_arguments(json.dumps({"indicator": "fear_greed"})),
    )
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert provider.calls[0].source_url == MARKET_SENTIMENT_SOURCE_URL
    assert payload["score"] is None
    assert payload["label"] is None
    assert payload["warnings"] == [
        {
            "code": "market_sentiment_empty",
            "message": "No market_sentiment data returned from fear_greed.",
            "details": [
                {"key": "operation", "value": "market_sentiment"},
                {"key": "provider", "value": "fear_greed"},
            ],
        }
    ]


def test_market_sentiment_service_degrades_malformed_payload_to_warning() -> None:
    client = FakeJsonClient(payload={"unexpected": {}})
    provider = FearGreedMarketSentimentProvider(http_client=client)
    service = DigitalOraclePhase1Service(market_sentiment_provider=provider)
    payload = map_market_sentiment_result(
        service.lookup_market_sentiment(DigitalOracleMarketSentimentQuery())
    ).model_dump(mode="json", by_alias=True)
    _assert_native_runtime_payload_is_json_safe_and_camel(payload)
    assert client.calls[0]["sourceUrl"] == MARKET_SENTIMENT_SOURCE_URL
    assert payload["score"] is None
    assert payload["sourceUrl"] == MARKET_SENTIMENT_SOURCE_URL
    assert payload["warnings"] == [
        {
            "code": "market_sentiment_provider_error",
            "message": "Fear & Greed provider returned malformed market sentiment data",
            "details": [
                {"key": "operation", "value": "market_sentiment"},
                {"key": "provider", "value": "fear_greed"},
            ],
        }
    ]


def test_market_sentiment_runtime_executor_preserves_upstream_failure_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeDigitalOracleProvider(
        failure=DigitalOracleProviderError(
            "Fear & Greed endpoint failed with token=sk-runtime-secret",
            code="provider_unavailable",
            details={"token": "sk-runtime-secret", "request_id": "fg-123"},
        )
    )
    monkeypatch.setattr(
        "oracle_plugin.runtime_market_sentiment.create_market_sentiment_provider_adapter",
        lambda: provider,
    )
    payload = execute_market_sentiment_lookup(
        RuntimeToolContext(),
        parse_market_sentiment_lookup_arguments(json.dumps({"indicator": "fear_greed"})),
    )
    assert provider.calls[0].indicator == "fear_greed"
    assert payload["toolKey"] == MARKET_SENTIMENT_LOOKUP_TOOL_KEY
    assert payload["score"] is None
    assert payload["label"] is None
    assert payload["sourceUrl"] == MARKET_SENTIMENT_SOURCE_URL
    assert payload["warnings"] == [
        {
            "code": "market_sentiment_provider_unavailable",
            "message": "Fear & Greed endpoint failed with token=<redacted>",
            "details": [
                {"key": "operation", "value": "market_sentiment"},
                {"key": "provider", "value": "fear_greed"},
                {"key": "requestId", "value": "fg-123"},
            ],
        }
    ]


def _assert_native_runtime_payload_is_json_safe_and_camel(payload: dict[str, object]) -> None:
    _ = json.dumps(payload)
    _assert_no_snake_case_keys(payload, path="$")


def _assert_no_snake_case_keys(value: object, *, path: str) -> None:
    if isinstance(value, dict):
        payload = cast(dict[object, object], value)
        for key, nested_value in payload.items():
            assert isinstance(key, str)
            assert "_" not in key, f"snake_case key leaked at {path}.{key}"
            _assert_no_snake_case_keys(nested_value, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        payload = cast(list[object], value)
        for index, nested_value in enumerate(payload):
            _assert_no_snake_case_keys(nested_value, path=f"{path}[{index}]")


_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _block_unmocked_oracle_http(monkeypatch):
    import httpx

    def reject_request(*args, **kwargs):
        raise AssertionError("Provider tests must use an explicit transport fixture")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject_request)


def test_missing_optional_yfinance_returns_plugin_warning_without_runtime_registry(
    monkeypatch,
):
    import importlib

    import_module = importlib.import_module

    def unavailable(module):
        if module == "yfinance":
            raise ImportError("No module named yfinance")
        return import_module(module)

    monkeypatch.setattr(
        "oracle_plugin.factory.importlib.util.find_spec",
        lambda module: None if module == "yfinance" else object(),
    )
    monkeypatch.setattr(
        "oracle_plugin.runtime_options_providers.importlib.import_module", unavailable
    )
    reset_digital_oracle_settings_cache()
    try:
        payload = execute_options_lookup(
            RuntimeToolContext(),
            parse_options_lookup_arguments(
                json.dumps({"symbols": ["AAPL"], "includeGreeks": True})
            ),
        )
    finally:
        reset_digital_oracle_settings_cache()
    assert payload["chains"] == []
    assert [warning["code"] for warning in payload["warnings"]] == [
        "digital_oracle_yfinance_missing",
        "options_provider_unavailable",
        "options_unavailable",
    ]
    assert payload["warnings"][0]["details"] == [
        {"key": "dependency", "value": "yfinance"},
        {"key": "operation", "value": "options"},
        {"key": "provider", "value": "yfinance"},
    ]


def test_cftc_positioning_plugin_executor_preserves_provider_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeDigitalOracleProvider(
        result=DigitalOracleCftcPositioningProviderResult(
            provider="cftc",
            reports=(
                DigitalOracleCftcPositioningReport(
                    provider="cftc",
                    report_type="legacy_futures_only",
                    report_date=date(2026, 6, 16),
                    rows=(
                        DigitalOracleCftcPositioningRow(
                            market="BITCOIN - CME",
                            managed_money_long=Decimal("7200"),
                            managed_money_short=Decimal("6800"),
                            managed_money_net=Decimal("400"),
                        ),
                    ),
                ),
            ),
        )
    )
    monkeypatch.setattr(
        "oracle_plugin.runtime_cftc_positioning.create_cftc_positioning_providers",
        lambda: (provider,),
    )
    payload = CFTC_POSITIONING_LOOKUP_TOOL_SPEC.executor(
        RuntimeToolContext(),
        CFTC_POSITIONING_LOOKUP_TOOL_SPEC.parser(
            json.dumps(
                {"markets": ["Bitcoin"], "reportTypes": ["legacy_futures_only"], "itemLimit": 1}
            )
        ),
    )
    assert provider.calls[0].item_limit == 1
    assert payload["toolKey"] == CFTC_POSITIONING_LOOKUP_TOOL_KEY
    reports = cast(list[dict[str, object]], payload["reports"])
    row = cast(list[dict[str, object]], reports[0]["rows"])[0]
    assert row["managedMoneyNet"] == "400"


def test_macro_rates_plugin_executor_preserves_provider_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = FakeDigitalOracleProvider(
        "treasury",
        series=(
            DigitalOracleMacroRatesSeries(
                provider="treasury",
                family="yield_curve",
                series_id="UST-3M",
                label="US Treasury 3M bill rate",
                country="US",
                currency="USD",
                unit="percent",
                date=date(2026, 1, 2),
                value=Decimal("4.01"),
                tenor="3M",
                source_url="https://home.treasury.gov/",
            ),
        ),
    )
    monkeypatch.setattr(
        "oracle_plugin.runtime_macro_rates.create_macro_rates_providers", lambda: (provider,)
    )
    payload = MACRO_RATES_LOOKUP_TOOL_SPEC.executor(
        RuntimeToolContext(),
        MACRO_RATES_LOOKUP_TOOL_SPEC.parser(
            json.dumps({"sources": ["treasury"], "families": ["yield_curve"]})
        ),
    )
    assert provider.calls[0].families == ("yield_curve",)
    assert payload["toolKey"] == MACRO_RATES_LOOKUP_TOOL_KEY
    assert len(cast(list[dict[str, object]], payload["series"])) == 1


@pytest.mark.parametrize(
    "spec, arguments, message",
    [
        (
            PREDICTION_MARKETS_LOOKUP_TOOL_SPEC,
            {"query": "   "},
            "signaldeck_digital_oracle_prediction_markets_lookup query must not be empty.",
        ),
        (
            SEC_FILINGS_LOOKUP_TOOL_SPEC,
            {"ticker": "NVDA", "startDate": "2026-12-31", "endDate": "2026-01-01"},
            (
                "signaldeck_digital_oracle_sec_filings_lookup "
                "startDate must be before or equal to endDate."
            ),
        ),
        (
            MARKET_SENTIMENT_LOOKUP_TOOL_SPEC,
            {"indicator": "fear_greed", "asOfDate": "not-a-date"},
            "signaldeck_digital_oracle_market_sentiment_lookup asOfDate must be a valid ISO date.",
        ),
    ],
)
def test_invalid_plugin_arguments_fail_before_provider_construction(
    monkeypatch, spec, arguments, message
):
    def fail_provider_factory():
        raise AssertionError("Invalid tool arguments must not construct providers")

    for path in [
        "runtime_prediction_markets.create_prediction_market_providers",
        "runtime_sec_filings.create_sec_filings_provider_adapter",
        "runtime_market_sentiment.create_market_sentiment_provider_adapter",
    ]:
        monkeypatch.setattr("oracle_plugin." + path, fail_provider_factory)
    with pytest.raises(RuntimeToolError) as failure:
        spec.executor(RuntimeToolContext(), spec.parser(json.dumps(arguments)))
    assert failure.value.code == "agent_tool_call_invalid"
    assert failure.value.message == message
