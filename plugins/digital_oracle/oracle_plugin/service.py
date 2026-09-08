from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from typing import cast

from oracle_plugin.contracts import RuntimeToolWarning
from plugin_runtime.formatting import normalize_symbol

from .config import (
    CFTC_POSITIONING_REPORT_TYPES,
    CRYPTO_DERIVATIVES_DATA_TYPES,
    CRYPTO_DERIVATIVES_VENUES,
    MACRO_RATES_FAMILIES,
    MACRO_RATES_SOURCES,
    PREDICTION_MARKET_VENUES,
    CftcPositioningReportType,
    CryptoDerivativesDataType,
    CryptoDerivativesVenue,
    DigitalOracleSettings,
    MacroRatesFamily,
    MacroRatesSource,
    PredictionMarketVenue,
)
from .factory import (
    DigitalOraclePhase1ProviderBundle,
    DigitalOracleProviderFailure,
    create_digital_oracle_phase1_provider_bundle,
)
from .types import (
    DigitalOracleCftcPositioningProvider,
    DigitalOracleCftcPositioningProviderQuery,
    DigitalOracleCftcPositioningProviderResult,
    DigitalOracleCftcPositioningQuery,
    DigitalOracleCftcPositioningReport,
    DigitalOracleCftcPositioningResult,
    DigitalOracleCryptoDerivativesGlobalMetrics,
    DigitalOracleCryptoDerivativesOptionSummary,
    DigitalOracleCryptoDerivativesOrderBook,
    DigitalOracleCryptoDerivativesProvider,
    DigitalOracleCryptoDerivativesProviderQuery,
    DigitalOracleCryptoDerivativesProviderResult,
    DigitalOracleCryptoDerivativesQuery,
    DigitalOracleCryptoDerivativesResult,
    DigitalOracleCryptoDerivativesSpotQuote,
    DigitalOracleCryptoDerivativesTermPoint,
    DigitalOracleMacroRatesProvider,
    DigitalOracleMacroRatesProviderQuery,
    DigitalOracleMacroRatesProviderResult,
    DigitalOracleMacroRatesQuery,
    DigitalOracleMacroRatesResult,
    DigitalOracleMacroRatesSeries,
    DigitalOracleMarketSentimentProvider,
    DigitalOracleMarketSentimentProviderQuery,
    DigitalOracleMarketSentimentQuery,
    DigitalOracleMarketSentimentResult,
    DigitalOracleOptionsChain,
    DigitalOracleOptionsProvider,
    DigitalOracleOptionsProviderQuery,
    DigitalOracleOptionsProviderResult,
    DigitalOracleOptionsQuery,
    DigitalOracleOptionsResult,
    DigitalOraclePredictionMarketEvent,
    DigitalOraclePredictionMarketProvider,
    DigitalOraclePredictionMarketsProviderQuery,
    DigitalOraclePredictionMarketsProviderResult,
    DigitalOraclePredictionMarketsQuery,
    DigitalOraclePredictionMarketsResult,
    DigitalOracleProviderError,
    DigitalOracleSecFiling,
    DigitalOracleSecFilingsProvider,
    DigitalOracleSecFilingsProviderQuery,
    DigitalOracleSecFilingsQuery,
    DigitalOracleSecFilingsResult,
    DigitalOracleSecOwnershipTransaction,
    DigitalOracleSecSearchHit,
)
from .warnings import (
    empty_result_warning,
    partial_result_warning,
    provider_unavailable_warning,
    truncated_result_warning,
    unavailable_result_warning,
    warning_from_provider_error,
    warning_from_provider_failure,
    warning_from_unhandled_provider_error,
)

_PREDICTION_MARKETS_MAX_ITEM_LIMIT = 20
_PREDICTION_MARKETS_MAX_DEPTH_LIMIT = 10
_SEC_FILINGS_MAX_ITEM_LIMIT = 50
_PREDICTION_MARKETS_OPERATION = "prediction_markets"
_SEC_FILINGS_OPERATION = "sec_filings"
_MARKET_SENTIMENT_OPERATION = "market_sentiment"
_MACRO_RATES_OPERATION = "macro_rates"
_CRYPTO_DERIVATIVES_OPERATION = "crypto_derivatives"
_CFTC_POSITIONING_OPERATION = "cftc_positioning"
_OPTIONS_OPERATION = "options"
_MACRO_RATES_MAX_ITEM_LIMIT = 50
_CRYPTO_DERIVATIVES_MAX_ITEM_LIMIT = 50
_CRYPTO_DERIVATIVES_MAX_DEPTH_LIMIT = 10
_CFTC_POSITIONING_MAX_ITEM_LIMIT = 50
_OPTIONS_MAX_ITEM_LIMIT = 50
_RESOLVED_PREDICTION_MARKET_STATUSES = {"closed", "expired", "resolved", "settled"}


@dataclass(frozen=True, slots=True)
class _ProviderCall[T]:
    provider: str
    call: Callable[[], T]


@dataclass(frozen=True, slots=True)
class _ProviderOutcome[T]:
    provider: str
    result: T | None = None
    warning: RuntimeToolWarning | None = None


class DigitalOraclePhase1Service:
    def __init__(
        self,
        *,
        settings: DigitalOracleSettings | None = None,
        provider_bundle: DigitalOraclePhase1ProviderBundle | None = None,
        prediction_market_providers: Sequence[DigitalOraclePredictionMarketProvider] = (),
        sec_filings_provider: DigitalOracleSecFilingsProvider | None = None,
        market_sentiment_provider: DigitalOracleMarketSentimentProvider | None = None,
        macro_rates_providers: Sequence[DigitalOracleMacroRatesProvider] = (),
        crypto_derivatives_providers: Sequence[DigitalOracleCryptoDerivativesProvider] = (),
        cftc_positioning_providers: Sequence[DigitalOracleCftcPositioningProvider] = (),
        options_providers: Sequence[DigitalOracleOptionsProvider] = (),
    ) -> None:
        self._provider_bundle: DigitalOraclePhase1ProviderBundle = (
            provider_bundle or create_digital_oracle_phase1_provider_bundle(settings)
        )
        self._prediction_market_providers_by_venue: dict[
            PredictionMarketVenue,
            DigitalOraclePredictionMarketProvider,
        ] = {provider.venue: provider for provider in prediction_market_providers}
        self._sec_filings_provider: DigitalOracleSecFilingsProvider | None = sec_filings_provider
        self._market_sentiment_provider: DigitalOracleMarketSentimentProvider | None = (
            market_sentiment_provider
        )
        self._macro_rates_providers_by_source: dict[
            MacroRatesSource,
            DigitalOracleMacroRatesProvider,
        ] = {provider.source: provider for provider in macro_rates_providers}
        self._crypto_derivatives_providers_by_venue: dict[
            CryptoDerivativesVenue,
            DigitalOracleCryptoDerivativesProvider,
        ] = {provider.venue: provider for provider in crypto_derivatives_providers}
        self._cftc_positioning_providers_by_name: dict[
            str,
            DigitalOracleCftcPositioningProvider,
        ] = {provider.provider_name: provider for provider in cftc_positioning_providers}
        self._options_providers_by_name: dict[str, DigitalOracleOptionsProvider] = {
            provider.provider_name: provider for provider in options_providers
        }

    def lookup_prediction_markets(
        self,
        query: DigitalOraclePredictionMarketsQuery,
    ) -> DigitalOraclePredictionMarketsResult:
        normalized_query = _normalize_text(query.query, field_name="query")
        construction = self._provider_bundle.prediction_markets
        if isinstance(construction, DigitalOracleProviderFailure):
            return DigitalOraclePredictionMarketsResult(
                query=normalized_query,
                events=(),
                warnings=(
                    warning_from_provider_failure(
                        construction,
                        operation=_PREDICTION_MARKETS_OPERATION,
                    ),
                ),
            )
        provider_bundle = construction
        venues = _normalize_prediction_venues(query.venues or provider_bundle.venues)
        item_limit = _normalize_limit(
            query.item_limit,
            default_limit=provider_bundle.default_item_limit,
            max_limit=_PREDICTION_MARKETS_MAX_ITEM_LIMIT,
            field_name="itemLimit",
        )
        depth_limit = _normalize_prediction_market_depth_limit(query.depth_limit)
        warnings: list[RuntimeToolWarning] = []
        uncovered_providers: set[str] = set()
        calls: list[_ProviderCall[DigitalOraclePredictionMarketsProviderResult]] = []

        descriptor_by_key = {descriptor.key: descriptor for descriptor in provider_bundle.providers}
        for venue in venues:
            descriptor = descriptor_by_key.get(venue)
            provider = self._prediction_market_providers_by_venue.get(venue)
            if descriptor is None or provider is None:
                warnings.append(
                    provider_unavailable_warning(
                        operation=_PREDICTION_MARKETS_OPERATION,
                        provider=venue,
                    )
                )
                uncovered_providers.add(venue)
                continue
            provider_query = DigitalOraclePredictionMarketsProviderQuery(
                query=normalized_query,
                venue=venue,
                item_limit=item_limit,
                include_resolved=query.include_resolved,
                include_order_book=query.include_order_book,
                depth_limit=depth_limit,
                timeout_seconds=descriptor.timeout_seconds,
            )
            calls.append(
                _ProviderCall(
                    provider=venue,
                    call=cast(
                        Callable[[], DigitalOraclePredictionMarketsProviderResult],
                        lambda provider=provider, provider_query=provider_query: (
                            provider.lookup_prediction_markets(provider_query)
                        ),
                    ),
                )
            )

        events: list[DigitalOraclePredictionMarketEvent] = []
        for outcome in _gather_provider_calls(calls, operation=_PREDICTION_MARKETS_OPERATION):
            if outcome.warning is not None:
                warnings.append(outcome.warning)
                uncovered_providers.add(outcome.provider)
                continue
            provider_result = cast(DigitalOraclePredictionMarketsProviderResult, outcome.result)
            warnings.extend(provider_result.warnings)
            provider_events = _filter_prediction_market_events(
                provider_result.events,
                include_resolved=query.include_resolved,
            )
            if not provider_events:
                warnings.append(
                    empty_result_warning(
                        operation=_PREDICTION_MARKETS_OPERATION,
                        provider=outcome.provider,
                    )
                )
                uncovered_providers.add(outcome.provider)
                continue
            events.extend(provider_events)

        if len(events) > item_limit:
            events = events[:item_limit]
            warnings.append(
                truncated_result_warning(
                    operation=_PREDICTION_MARKETS_OPERATION,
                    limit=item_limit,
                )
            )
        _append_coverage_warning(
            warnings,
            operation=_PREDICTION_MARKETS_OPERATION,
            requested_providers=venues,
            uncovered_providers=tuple(sorted(uncovered_providers)),
            has_results=bool(events),
        )
        return DigitalOraclePredictionMarketsResult(
            query=normalized_query,
            events=tuple(events),
            warnings=tuple(warnings),
        )

    def lookup_sec_filings(
        self,
        query: DigitalOracleSecFilingsQuery,
    ) -> DigitalOracleSecFilingsResult:
        ticker = _normalize_optional_symbol_query(query.ticker, field_name="ticker")
        cik = _normalize_optional_cik_query(query.cik)
        search_query = _normalize_optional_text(query.query, field_name="query")
        if ticker is None and cik is None:
            raise ValueError("ticker or cik is required")
        construction = self._provider_bundle.sec_filings
        if isinstance(construction, DigitalOracleProviderFailure):
            return DigitalOracleSecFilingsResult(
                ticker=ticker,
                query=search_query,
                cik=cik,
                warnings=(
                    warning_from_provider_failure(
                        construction,
                        operation=_SEC_FILINGS_OPERATION,
                    ),
                ),
            )
        provider_bundle = construction
        if self._sec_filings_provider is None:
            return DigitalOracleSecFilingsResult(
                ticker=ticker,
                query=search_query,
                cik=cik,
                warnings=(
                    provider_unavailable_warning(
                        operation=_SEC_FILINGS_OPERATION,
                        provider="edgar",
                    ),
                    unavailable_result_warning(operation=_SEC_FILINGS_OPERATION),
                ),
            )

        _validate_date_bounds(query.start_date, query.end_date)
        form_types = _normalize_form_types(query.form_types)
        item_limit = _normalize_limit(
            query.item_limit,
            default_limit=provider_bundle.default_item_limit,
            max_limit=_SEC_FILINGS_MAX_ITEM_LIMIT,
            field_name="itemLimit",
        )
        provider_query = DigitalOracleSecFilingsProviderQuery(
            ticker=ticker,
            query=search_query,
            cik=cik,
            form_types=form_types,
            start_date=query.start_date,
            end_date=query.end_date,
            item_limit=item_limit,
            edgar_contact_email=provider_bundle.edgar_contact_email,
            timeout_seconds=provider_bundle.provider.timeout_seconds,
            include_ownership_transactions=query.include_ownership_transactions,
        )
        warnings: list[RuntimeToolWarning] = []
        try:
            provider_result = self._sec_filings_provider.lookup_sec_filings(provider_query)
        except DigitalOracleProviderError as exc:
            warnings.append(
                warning_from_provider_error(
                    exc,
                    operation=_SEC_FILINGS_OPERATION,
                    provider="edgar",
                )
            )
            warnings.append(unavailable_result_warning(operation=_SEC_FILINGS_OPERATION))
            return DigitalOracleSecFilingsResult(
                ticker=ticker,
                query=search_query,
                cik=cik,
                warnings=tuple(warnings),
            )
        except Exception as exc:
            warnings.append(
                warning_from_unhandled_provider_error(
                    exc,
                    operation=_SEC_FILINGS_OPERATION,
                    provider="edgar",
                )
            )
            warnings.append(unavailable_result_warning(operation=_SEC_FILINGS_OPERATION))
            return DigitalOracleSecFilingsResult(
                ticker=ticker,
                query=search_query,
                cik=cik,
                warnings=tuple(warnings),
            )

        warnings.extend(provider_result.warnings)
        filtered_filings = _filter_sec_filings(
            provider_result.filings,
            form_types=form_types,
            start_date=query.start_date,
            end_date=query.end_date,
        )
        if len(filtered_filings) > item_limit:
            filtered_filings = filtered_filings[:item_limit]
            warnings.append(
                truncated_result_warning(operation=_SEC_FILINGS_OPERATION, limit=item_limit)
            )
        if not filtered_filings:
            warnings.append(
                empty_result_warning(operation=_SEC_FILINGS_OPERATION, provider="edgar")
            )
        search_hits = _filter_sec_search_hits(
            provider_result.search_hits,
            form_types=form_types,
            start_date=query.start_date,
            end_date=query.end_date,
            item_limit=item_limit,
        )
        if not search_hits:
            search_hits = _search_sec_filings(
                filtered_filings,
                query=search_query,
                cik=provider_result.cik,
                ticker=provider_result.ticker or ticker,
                entity_name=provider_result.entity_name,
            )
        if search_query is not None and not search_hits:
            warnings.append(empty_result_warning(operation="sec_filings_search", provider="edgar"))
        return DigitalOracleSecFilingsResult(
            ticker=provider_result.ticker or ticker,
            query=search_query,
            cik=provider_result.cik,
            entity_name=provider_result.entity_name,
            filings=tuple(filtered_filings),
            search_hits=tuple(search_hits),
            ownership_transactions=tuple(
                _ownership_transactions_for_filings(
                    provider_result.ownership_transactions,
                    filtered_filings,
                )
            ),
            warnings=tuple(warnings),
        )

    def lookup_market_sentiment(
        self,
        query: DigitalOracleMarketSentimentQuery,
    ) -> DigitalOracleMarketSentimentResult:
        construction = self._provider_bundle.market_sentiment
        if isinstance(construction, DigitalOracleProviderFailure):
            return DigitalOracleMarketSentimentResult(
                indicator=query.indicator,
                provider="fear_greed",
                as_of_date=query.as_of_date,
                warnings=(
                    warning_from_provider_failure(
                        construction,
                        operation=_MARKET_SENTIMENT_OPERATION,
                    ),
                ),
            )
        provider_bundle = construction
        if self._market_sentiment_provider is None:
            return DigitalOracleMarketSentimentResult(
                indicator=query.indicator,
                provider="fear_greed",
                as_of_date=query.as_of_date,
                source_url=provider_bundle.source_url,
                warnings=(
                    provider_unavailable_warning(
                        operation=_MARKET_SENTIMENT_OPERATION,
                        provider="fear_greed",
                    ),
                    unavailable_result_warning(operation=_MARKET_SENTIMENT_OPERATION),
                ),
            )

        provider_query = DigitalOracleMarketSentimentProviderQuery(
            indicator=query.indicator,
            as_of_date=query.as_of_date,
            source_url=provider_bundle.source_url,
            timeout_seconds=provider_bundle.provider.timeout_seconds,
        )
        warnings: list[RuntimeToolWarning] = []
        try:
            provider_result = self._market_sentiment_provider.lookup_market_sentiment(
                provider_query
            )
        except DigitalOracleProviderError as exc:
            warnings.append(
                warning_from_provider_error(
                    exc,
                    operation=_MARKET_SENTIMENT_OPERATION,
                    provider="fear_greed",
                )
            )
            return DigitalOracleMarketSentimentResult(
                indicator=query.indicator,
                provider="fear_greed",
                as_of_date=query.as_of_date,
                source_url=provider_bundle.source_url,
                warnings=tuple(warnings),
            )
        except Exception as exc:
            warnings.append(
                warning_from_unhandled_provider_error(
                    exc,
                    operation=_MARKET_SENTIMENT_OPERATION,
                    provider="fear_greed",
                )
            )
            return DigitalOracleMarketSentimentResult(
                indicator=query.indicator,
                provider="fear_greed",
                as_of_date=query.as_of_date,
                source_url=provider_bundle.source_url,
                warnings=tuple(warnings),
            )

        warnings.extend(provider_result.warnings)
        if provider_result.score is None and provider_result.label is None:
            warnings.append(
                empty_result_warning(
                    operation=_MARKET_SENTIMENT_OPERATION,
                    provider=provider_result.provider or "fear_greed",
                )
            )
        return DigitalOracleMarketSentimentResult(
            indicator=query.indicator,
            provider=provider_result.provider,
            as_of_date=provider_result.as_of_date or query.as_of_date,
            score=provider_result.score,
            label=provider_result.label,
            previous_close=provider_result.previous_close,
            week_ago=provider_result.week_ago,
            month_ago=provider_result.month_ago,
            year_ago=provider_result.year_ago,
            source_url=provider_result.source_url or provider_bundle.source_url,
            warnings=tuple(warnings),
        )

    def lookup_macro_rates(
        self,
        query: DigitalOracleMacroRatesQuery,
    ) -> DigitalOracleMacroRatesResult:
        normalized_query = _normalize_optional_text(query.query, field_name="query")
        construction = self._provider_bundle.macro_rates
        if isinstance(construction, DigitalOracleProviderFailure):
            return DigitalOracleMacroRatesResult(
                query=normalized_query,
                warnings=(
                    warning_from_provider_failure(
                        construction,
                        operation=_MACRO_RATES_OPERATION,
                    ),
                ),
            )
        provider_bundle = construction
        sources = _normalize_macro_sources(query.sources or MACRO_RATES_SOURCES)
        families = _normalize_macro_families(query.families)
        _validate_date_bounds(query.start_date, query.end_date)
        item_limit = _normalize_limit(
            query.item_limit,
            default_limit=provider_bundle.default_item_limit,
            max_limit=_MACRO_RATES_MAX_ITEM_LIMIT,
            field_name="itemLimit",
        )
        warnings: list[RuntimeToolWarning] = []
        uncovered_providers: set[str] = set()
        calls: list[_ProviderCall[DigitalOracleMacroRatesProviderResult]] = []
        descriptor_by_key = {descriptor.key: descriptor for descriptor in provider_bundle.providers}
        failed_sources = {
            str(failure.details.get("provider")): failure
            for failure in provider_bundle.source_failures
        }
        for source in sources:
            source_failure = failed_sources.get(source)
            if source_failure is not None:
                warnings.append(
                    warning_from_provider_failure(source_failure, operation=_MACRO_RATES_OPERATION)
                )
                uncovered_providers.add(source)
                continue
            descriptor = descriptor_by_key.get(source)
            provider = self._macro_rates_providers_by_source.get(source)
            if descriptor is None or provider is None:
                warnings.append(
                    provider_unavailable_warning(
                        operation=_MACRO_RATES_OPERATION,
                        provider=source,
                    )
                )
                uncovered_providers.add(source)
                continue
            provider_query = DigitalOracleMacroRatesProviderQuery(
                source=source,
                query=normalized_query,
                families=families,
                series_ids=query.series_ids,
                countries=query.countries,
                start_date=query.start_date,
                end_date=query.end_date,
                as_of_date=query.as_of_date,
                item_limit=item_limit,
                timeout_seconds=descriptor.timeout_seconds,
                fred_api_key=provider_bundle.fred_api_key if source == "fred" else None,
            )
            calls.append(
                _ProviderCall(
                    provider=source,
                    call=cast(
                        Callable[[], DigitalOracleMacroRatesProviderResult],
                        lambda provider=provider, provider_query=provider_query: (
                            provider.lookup_macro_rates(provider_query)
                        ),
                    ),
                )
            )

        series: list[DigitalOracleMacroRatesSeries] = []
        for outcome in _gather_provider_calls(calls, operation=_MACRO_RATES_OPERATION):
            if outcome.warning is not None:
                warnings.append(outcome.warning)
                uncovered_providers.add(outcome.provider)
                continue
            provider_result = cast(DigitalOracleMacroRatesProviderResult, outcome.result)
            warnings.extend(provider_result.warnings)
            provider_series = _filter_macro_rates_series(
                provider_result.series,
                families=families,
                series_ids=query.series_ids,
                countries=query.countries,
                start_date=query.start_date,
                end_date=query.end_date,
                as_of_date=query.as_of_date,
            )
            if not provider_series:
                warnings.append(
                    empty_result_warning(
                        operation=_MACRO_RATES_OPERATION,
                        provider=outcome.provider,
                    )
                )
                uncovered_providers.add(outcome.provider)
                continue
            series.extend(provider_series)

        if len(series) > item_limit:
            series = series[:item_limit]
            warnings.append(
                truncated_result_warning(
                    operation=_MACRO_RATES_OPERATION,
                    limit=item_limit,
                )
            )
        _append_coverage_warning(
            warnings,
            operation=_MACRO_RATES_OPERATION,
            requested_providers=sources,
            uncovered_providers=tuple(sorted(uncovered_providers)),
            has_results=bool(series),
        )
        return DigitalOracleMacroRatesResult(
            query=normalized_query,
            series=tuple(series),
            warnings=tuple(warnings),
        )

    def lookup_crypto_derivatives(
        self,
        query: DigitalOracleCryptoDerivativesQuery,
    ) -> DigitalOracleCryptoDerivativesResult:
        construction = self._provider_bundle.crypto_derivatives
        assets = _normalize_crypto_assets(query.assets)
        if isinstance(construction, DigitalOracleProviderFailure):
            return DigitalOracleCryptoDerivativesResult(
                assets=assets,
                warnings=(
                    warning_from_provider_failure(
                        construction,
                        operation=_CRYPTO_DERIVATIVES_OPERATION,
                    ),
                ),
            )
        provider_bundle = construction
        venues = _normalize_crypto_venues(query.venues or CRYPTO_DERIVATIVES_VENUES)
        data_types = _normalize_crypto_data_types(query.data_types)
        item_limit = _normalize_limit(
            query.item_limit,
            default_limit=provider_bundle.default_item_limit,
            max_limit=_CRYPTO_DERIVATIVES_MAX_ITEM_LIMIT,
            field_name="itemLimit",
        )
        depth_limit = _normalize_limit(
            query.depth_limit,
            default_limit=5,
            max_limit=_CRYPTO_DERIVATIVES_MAX_DEPTH_LIMIT,
            field_name="depthLimit",
        )
        warnings: list[RuntimeToolWarning] = []
        uncovered_providers: set[str] = set()
        calls: list[_ProviderCall[DigitalOracleCryptoDerivativesProviderResult]] = []
        descriptor_by_key = {descriptor.key: descriptor for descriptor in provider_bundle.providers}
        for venue in venues:
            descriptor = descriptor_by_key.get(venue)
            provider = self._crypto_derivatives_providers_by_venue.get(venue)
            if descriptor is None or provider is None:
                warnings.append(
                    provider_unavailable_warning(
                        operation=_CRYPTO_DERIVATIVES_OPERATION,
                        provider=venue,
                    )
                )
                uncovered_providers.add(venue)
                continue
            provider_query = DigitalOracleCryptoDerivativesProviderQuery(
                venue=venue,
                assets=assets,
                data_types=data_types,
                expirations=query.expirations,
                include_order_book=query.include_order_book,
                depth_limit=depth_limit,
                item_limit=item_limit,
                timeout_seconds=descriptor.timeout_seconds,
            )
            calls.append(
                _ProviderCall(
                    provider=venue,
                    call=cast(
                        Callable[[], DigitalOracleCryptoDerivativesProviderResult],
                        lambda provider=provider, provider_query=provider_query: (
                            provider.lookup_crypto_derivatives(provider_query)
                        ),
                    ),
                )
            )

        spot: list[DigitalOracleCryptoDerivativesSpotQuote] = []
        global_metrics: list[DigitalOracleCryptoDerivativesGlobalMetrics] = []
        term_structure: list[DigitalOracleCryptoDerivativesTermPoint] = []
        options: list[DigitalOracleCryptoDerivativesOptionSummary] = []
        order_books: list[DigitalOracleCryptoDerivativesOrderBook] = []
        for outcome in _gather_provider_calls(calls, operation=_CRYPTO_DERIVATIVES_OPERATION):
            if outcome.warning is not None:
                warnings.append(outcome.warning)
                uncovered_providers.add(outcome.provider)
                continue
            provider_result = cast(DigitalOracleCryptoDerivativesProviderResult, outcome.result)
            warnings.extend(provider_result.warnings)
            spot.extend(provider_result.spot)
            global_metrics.extend(provider_result.global_metrics)
            term_structure.extend(provider_result.term_structure)
            options.extend(provider_result.options)
            order_books.extend(provider_result.order_books)
            if not _crypto_provider_has_results(provider_result):
                warnings.append(
                    empty_result_warning(
                        operation=_CRYPTO_DERIVATIVES_OPERATION,
                        provider=outcome.provider,
                    )
                )
                uncovered_providers.add(outcome.provider)

        has_results = bool(spot or global_metrics or term_structure or options or order_books)
        _append_coverage_warning(
            warnings,
            operation=_CRYPTO_DERIVATIVES_OPERATION,
            requested_providers=venues,
            uncovered_providers=tuple(sorted(uncovered_providers)),
            has_results=has_results,
        )
        return DigitalOracleCryptoDerivativesResult(
            assets=assets,
            spot=tuple(spot[:item_limit]),
            global_metrics=tuple(global_metrics[:item_limit]),
            term_structure=tuple(term_structure[:item_limit]),
            options=tuple(options[:item_limit]),
            order_books=tuple(order_books[:item_limit]),
            warnings=tuple(warnings),
        )

    def lookup_cftc_positioning(
        self,
        query: DigitalOracleCftcPositioningQuery,
    ) -> DigitalOracleCftcPositioningResult:
        construction = self._provider_bundle.cftc_positioning
        markets = _normalize_cftc_markets(query.markets)
        if isinstance(construction, DigitalOracleProviderFailure):
            return DigitalOracleCftcPositioningResult(
                warnings=(
                    warning_from_provider_failure(
                        construction,
                        operation=_CFTC_POSITIONING_OPERATION,
                    ),
                ),
            )
        provider_bundle = construction
        report_types = _normalize_cftc_report_types(
            query.report_types or CFTC_POSITIONING_REPORT_TYPES
        )
        _validate_date_bounds(query.start_date, query.end_date)
        item_limit = _normalize_limit(
            query.item_limit,
            default_limit=provider_bundle.default_item_limit,
            max_limit=_CFTC_POSITIONING_MAX_ITEM_LIMIT,
            field_name="itemLimit",
        )
        warnings: list[RuntimeToolWarning] = []
        uncovered_providers: set[str] = set()
        calls: list[_ProviderCall[DigitalOracleCftcPositioningProviderResult]] = []
        descriptor_by_key = {descriptor.key: descriptor for descriptor in provider_bundle.providers}
        for descriptor in provider_bundle.providers:
            provider = self._cftc_positioning_providers_by_name.get(descriptor.key)
            if provider is None:
                warnings.append(
                    provider_unavailable_warning(
                        operation=_CFTC_POSITIONING_OPERATION,
                        provider=descriptor.key,
                    )
                )
                uncovered_providers.add(descriptor.key)
                continue
            provider_query = DigitalOracleCftcPositioningProviderQuery(
                markets=markets,
                report_types=report_types,
                start_date=query.start_date,
                end_date=query.end_date,
                item_limit=item_limit,
                timeout_seconds=descriptor_by_key[descriptor.key].timeout_seconds,
            )
            calls.append(
                _ProviderCall(
                    provider=descriptor.key,
                    call=cast(
                        Callable[[], DigitalOracleCftcPositioningProviderResult],
                        lambda provider=provider, provider_query=provider_query: (
                            provider.lookup_cftc_positioning(provider_query)
                        ),
                    ),
                )
            )

        reports: list[DigitalOracleCftcPositioningReport] = []
        for outcome in _gather_provider_calls(calls, operation=_CFTC_POSITIONING_OPERATION):
            if outcome.warning is not None:
                warnings.append(outcome.warning)
                uncovered_providers.add(outcome.provider)
                continue
            provider_result = cast(DigitalOracleCftcPositioningProviderResult, outcome.result)
            warnings.extend(provider_result.warnings)
            provider_reports = _filter_cftc_reports(
                provider_result.reports,
                markets=markets,
                report_types=report_types,
                start_date=query.start_date,
                end_date=query.end_date,
            )
            if not provider_reports:
                warnings.append(
                    empty_result_warning(
                        operation=_CFTC_POSITIONING_OPERATION,
                        provider=outcome.provider,
                    )
                )
                uncovered_providers.add(outcome.provider)
                continue
            reports.extend(provider_reports)

        if len(reports) > item_limit:
            reports = reports[:item_limit]
            warnings.append(
                truncated_result_warning(operation=_CFTC_POSITIONING_OPERATION, limit=item_limit)
            )
        _append_coverage_warning(
            warnings,
            operation=_CFTC_POSITIONING_OPERATION,
            requested_providers=tuple(descriptor.key for descriptor in provider_bundle.providers),
            uncovered_providers=tuple(sorted(uncovered_providers)),
            has_results=bool(reports),
        )
        return DigitalOracleCftcPositioningResult(
            reports=tuple(reports),
            warnings=tuple(warnings),
        )

    def lookup_options(self, query: DigitalOracleOptionsQuery) -> DigitalOracleOptionsResult:
        symbols = _normalize_options_symbols(query.symbols)
        result_symbol = ",".join(symbols)
        construction = self._provider_bundle.options
        if isinstance(construction, DigitalOracleProviderFailure):
            return DigitalOracleOptionsResult(
                symbol=result_symbol,
                warnings=(
                    warning_from_provider_failure(
                        construction,
                        operation=_OPTIONS_OPERATION,
                    ),
                ),
            )
        provider_bundle = construction
        item_limit = _normalize_limit(
            query.item_limit,
            default_limit=provider_bundle.default_item_limit,
            max_limit=_OPTIONS_MAX_ITEM_LIMIT,
            field_name="itemLimit",
        )
        warnings: list[RuntimeToolWarning] = []
        uncovered_providers: set[str] = set()
        calls: list[_ProviderCall[DigitalOracleOptionsProviderResult]] = []
        descriptor_by_key = {descriptor.key: descriptor for descriptor in provider_bundle.providers}
        for failure in provider_bundle.source_failures:
            failed_provider = str(failure.details.get("provider"))
            warnings.append(warning_from_provider_failure(failure, operation=_OPTIONS_OPERATION))
            uncovered_providers.add(failed_provider)
        for descriptor in provider_bundle.providers:
            provider = self._options_providers_by_name.get(descriptor.key)
            if provider is None:
                warnings.append(
                    provider_unavailable_warning(
                        operation=_OPTIONS_OPERATION,
                        provider=descriptor.key,
                    )
                )
                uncovered_providers.add(descriptor.key)
                continue
            for symbol in symbols:
                provider_query = DigitalOracleOptionsProviderQuery(
                    symbol=symbol,
                    expirations=query.expirations,
                    include_greeks=query.include_greeks,
                    moneyness=query.moneyness,
                    item_limit=item_limit,
                    timeout_seconds=descriptor_by_key[descriptor.key].timeout_seconds,
                )
                calls.append(
                    _ProviderCall(
                        provider=descriptor.key,
                        call=cast(
                            Callable[[], DigitalOracleOptionsProviderResult],
                            lambda provider=provider, provider_query=provider_query: (
                                provider.lookup_options(provider_query)
                            ),
                        ),
                    )
                )

        chains: list[DigitalOracleOptionsChain] = []
        for outcome in _gather_provider_calls(calls, operation=_OPTIONS_OPERATION):
            if outcome.warning is not None:
                warnings.append(outcome.warning)
                uncovered_providers.add(outcome.provider)
                continue
            provider_result = cast(DigitalOracleOptionsProviderResult, outcome.result)
            warnings.extend(provider_result.warnings)
            provider_chains = tuple(
                chain for chain in provider_result.chains if chain.calls or chain.puts
            )
            if not provider_chains:
                warnings.append(
                    empty_result_warning(operation=_OPTIONS_OPERATION, provider=outcome.provider)
                )
                uncovered_providers.add(outcome.provider)
                continue
            chains.extend(provider_chains)

        _append_coverage_warning(
            warnings,
            operation=_OPTIONS_OPERATION,
            requested_providers=tuple(descriptor.key for descriptor in provider_bundle.providers),
            uncovered_providers=tuple(sorted(uncovered_providers)),
            has_results=bool(chains),
        )
        return DigitalOracleOptionsResult(
            symbol=result_symbol,
            chains=tuple(chains[:item_limit]),
            warnings=tuple(warnings),
        )


def create_digital_oracle_phase1_service(
    *,
    settings: DigitalOracleSettings | None = None,
    provider_bundle: DigitalOraclePhase1ProviderBundle | None = None,
    prediction_market_providers: Sequence[DigitalOraclePredictionMarketProvider] = (),
    sec_filings_provider: DigitalOracleSecFilingsProvider | None = None,
    market_sentiment_provider: DigitalOracleMarketSentimentProvider | None = None,
    macro_rates_providers: Sequence[DigitalOracleMacroRatesProvider] = (),
    crypto_derivatives_providers: Sequence[DigitalOracleCryptoDerivativesProvider] = (),
    cftc_positioning_providers: Sequence[DigitalOracleCftcPositioningProvider] = (),
    options_providers: Sequence[DigitalOracleOptionsProvider] = (),
) -> DigitalOraclePhase1Service:
    return DigitalOraclePhase1Service(
        settings=settings,
        provider_bundle=provider_bundle,
        prediction_market_providers=prediction_market_providers,
        sec_filings_provider=sec_filings_provider,
        market_sentiment_provider=market_sentiment_provider,
        macro_rates_providers=macro_rates_providers,
        crypto_derivatives_providers=crypto_derivatives_providers,
        cftc_positioning_providers=cftc_positioning_providers,
        options_providers=options_providers,
    )


def _gather_provider_calls[
    T
](calls: Sequence[_ProviderCall[T]], *, operation: str,) -> tuple[_ProviderOutcome[T], ...]:
    if not calls:
        return ()
    if len(calls) == 1:
        return (_execute_provider_call(calls[0], operation=operation),)

    outcomes_by_index: dict[int, _ProviderOutcome[T]] = {}
    with ThreadPoolExecutor(max_workers=len(calls)) as executor:
        future_by_index = {
            executor.submit(_execute_provider_call, call, operation=operation): index
            for index, call in enumerate(calls)
        }
        for future in as_completed(future_by_index):
            outcomes_by_index[future_by_index[future]] = future.result()
    return tuple(outcomes_by_index[index] for index in sorted(outcomes_by_index))


def _execute_provider_call[
    T
](call: _ProviderCall[T], *, operation: str,) -> _ProviderOutcome[T]:
    try:
        return _ProviderOutcome(provider=call.provider, result=call.call())
    except DigitalOracleProviderError as exc:
        return _ProviderOutcome(
            provider=call.provider,
            warning=warning_from_provider_error(
                exc,
                operation=operation,
                provider=call.provider,
            ),
        )
    except Exception as exc:
        return _ProviderOutcome(
            provider=call.provider,
            warning=warning_from_unhandled_provider_error(
                exc,
                operation=operation,
                provider=call.provider,
            ),
        )


def _normalize_macro_sources(
    sources: Sequence[MacroRatesSource],
) -> tuple[MacroRatesSource, ...]:
    normalized: list[MacroRatesSource] = []
    seen: set[MacroRatesSource] = set()
    for raw_source in sources:
        source = cast(MacroRatesSource, str(raw_source).strip().lower())
        if source in MACRO_RATES_SOURCES and source not in seen:
            normalized.append(source)
            seen.add(source)
    if not normalized:
        return MACRO_RATES_SOURCES
    return tuple(normalized)


def _normalize_macro_families(
    families: Sequence[MacroRatesFamily] | None,
) -> tuple[MacroRatesFamily, ...] | None:
    if families is None:
        return None
    normalized: list[MacroRatesFamily] = []
    seen: set[MacroRatesFamily] = set()
    for raw_family in families:
        family = cast(MacroRatesFamily, str(raw_family).strip().lower())
        if family in MACRO_RATES_FAMILIES and family not in seen:
            normalized.append(family)
            seen.add(family)
    return tuple(normalized) or None


def _filter_macro_rates_series(
    series: Sequence[DigitalOracleMacroRatesSeries],
    *,
    families: tuple[MacroRatesFamily, ...] | None,
    series_ids: tuple[str, ...] | None,
    countries: tuple[str, ...] | None,
    start_date: date | None,
    end_date: date | None,
    as_of_date: date | None,
) -> list[DigitalOracleMacroRatesSeries]:
    family_filter = set(families or ())
    series_id_filter = {value.casefold() for value in series_ids or ()}
    country_filter = {value.casefold() for value in countries or ()}
    filtered: list[DigitalOracleMacroRatesSeries] = []
    for item in series:
        if family_filter and item.family not in family_filter:
            continue
        if series_id_filter and item.series_id.casefold() not in series_id_filter:
            continue
        if country_filter and (
            item.country is None or item.country.casefold() not in country_filter
        ):
            continue
        if start_date is not None and item.date < start_date:
            continue
        if end_date is not None and item.date > end_date:
            continue
        if as_of_date is not None and item.date > as_of_date:
            continue
        filtered.append(item)
    return sorted(
        filtered,
        key=lambda item: (item.date, item.provider, item.series_id),
        reverse=True,
    )


def _normalize_crypto_assets(assets: Sequence[str] | None) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_asset in assets or ("BTC",):
        asset = normalize_symbol(raw_asset)
        if asset and asset not in seen:
            normalized.append(asset)
            seen.add(asset)
    if not normalized:
        raise ValueError("assets must contain at least one value")
    return tuple(normalized)


def _normalize_crypto_venues(
    venues: Sequence[CryptoDerivativesVenue],
) -> tuple[CryptoDerivativesVenue, ...]:
    normalized: list[CryptoDerivativesVenue] = []
    seen: set[CryptoDerivativesVenue] = set()
    for raw_venue in venues:
        venue = cast(CryptoDerivativesVenue, str(raw_venue).strip().lower())
        if venue in CRYPTO_DERIVATIVES_VENUES and venue not in seen:
            normalized.append(venue)
            seen.add(venue)
    if not normalized:
        return CRYPTO_DERIVATIVES_VENUES
    return tuple(normalized)


def _normalize_crypto_data_types(
    data_types: Sequence[CryptoDerivativesDataType] | None,
) -> tuple[CryptoDerivativesDataType, ...]:
    normalized: list[CryptoDerivativesDataType] = []
    seen: set[CryptoDerivativesDataType] = set()
    for raw_data_type in data_types or CRYPTO_DERIVATIVES_DATA_TYPES:
        data_type = cast(CryptoDerivativesDataType, str(raw_data_type).strip().lower())
        if data_type in CRYPTO_DERIVATIVES_DATA_TYPES and data_type not in seen:
            normalized.append(data_type)
            seen.add(data_type)
    return tuple(normalized) or CRYPTO_DERIVATIVES_DATA_TYPES


def _crypto_provider_has_results(result: DigitalOracleCryptoDerivativesProviderResult) -> bool:
    return bool(
        result.spot
        or result.global_metrics
        or result.term_structure
        or result.options
        or result.order_books
    )


def _normalize_cftc_markets(markets: Sequence[str] | None) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_market in markets or ():
        market = " ".join(raw_market.split()).strip()
        dedupe_key = market.casefold()
        if market and dedupe_key not in seen:
            normalized.append(market)
            seen.add(dedupe_key)
    return tuple(normalized)


def _normalize_cftc_report_types(
    report_types: Sequence[CftcPositioningReportType],
) -> tuple[CftcPositioningReportType, ...]:
    normalized: list[CftcPositioningReportType] = []
    seen: set[CftcPositioningReportType] = set()
    for raw_report_type in report_types:
        report_type = cast(CftcPositioningReportType, str(raw_report_type).strip().lower())
        if report_type in CFTC_POSITIONING_REPORT_TYPES and report_type not in seen:
            normalized.append(report_type)
            seen.add(report_type)
    return tuple(normalized) or CFTC_POSITIONING_REPORT_TYPES


def _normalize_options_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_symbol in symbols:
        symbol = normalize_symbol(raw_symbol)
        if symbol and symbol not in seen:
            normalized.append(symbol)
            seen.add(symbol)
    if not normalized:
        raise ValueError("symbols must contain at least one value")
    return tuple(normalized)


def _filter_cftc_reports(
    reports: Sequence[DigitalOracleCftcPositioningReport],
    *,
    markets: tuple[str, ...],
    report_types: tuple[CftcPositioningReportType, ...],
    start_date: date | None,
    end_date: date | None,
) -> list[DigitalOracleCftcPositioningReport]:
    market_filters = tuple(market.casefold() for market in markets)
    report_type_filter = set(report_types)
    filtered: list[DigitalOracleCftcPositioningReport] = []
    for report in reports:
        if report.report_type not in report_type_filter:
            continue
        if start_date is not None and report.report_date < start_date:
            continue
        if end_date is not None and report.report_date > end_date:
            continue
        rows = tuple(
            row
            for row in report.rows
            if not market_filters
            or any(
                market in row.market.casefold()
                or (
                    row.contract_market_code is not None
                    and market in row.contract_market_code.casefold()
                )
                for market in market_filters
            )
        )
        if rows:
            filtered.append(
                DigitalOracleCftcPositioningReport(
                    provider=report.provider,
                    report_type=report.report_type,
                    report_date=report.report_date,
                    rows=rows,
                )
            )
    return sorted(filtered, key=lambda item: item.report_date, reverse=True)


def _normalize_prediction_venues(
    venues: Sequence[PredictionMarketVenue],
) -> tuple[PredictionMarketVenue, ...]:
    normalized: list[PredictionMarketVenue] = []
    seen: set[PredictionMarketVenue] = set()
    for raw_venue in venues:
        venue = cast(PredictionMarketVenue, str(raw_venue).strip().lower())
        if venue in PREDICTION_MARKET_VENUES and venue not in seen:
            normalized.append(venue)
            seen.add(venue)
    if not normalized:
        return PREDICTION_MARKET_VENUES
    return tuple(normalized)


def _filter_prediction_market_events(
    events: Sequence[DigitalOraclePredictionMarketEvent],
    *,
    include_resolved: bool,
) -> tuple[DigitalOraclePredictionMarketEvent, ...]:
    if include_resolved:
        return tuple(events)
    return tuple(
        event
        for event in events
        if event.status.strip().lower() not in _RESOLVED_PREDICTION_MARKET_STATUSES
    )


def _filter_sec_filings(
    filings: Sequence[DigitalOracleSecFiling],
    *,
    form_types: tuple[str, ...],
    start_date: date | None,
    end_date: date | None,
) -> list[DigitalOracleSecFiling]:
    form_type_filter = set(form_types)
    filtered: list[DigitalOracleSecFiling] = []
    for filing in filings:
        if form_type_filter and filing.form_type.strip().upper() not in form_type_filter:
            continue
        if start_date is not None and filing.filing_date < start_date:
            continue
        if end_date is not None and filing.filing_date > end_date:
            continue
        filtered.append(filing)
    return sorted(filtered, key=lambda filing: filing.filing_date, reverse=True)


def _search_sec_filings(
    filings: Sequence[DigitalOracleSecFiling],
    *,
    query: str | None,
    cik: str | None,
    ticker: str | None,
    entity_name: str | None,
) -> list[DigitalOracleSecSearchHit]:
    if query is None:
        return []
    needle = query.casefold()
    hits: list[DigitalOracleSecSearchHit] = []
    for filing in filings:
        matched_text = _sec_filing_matched_text(
            filing,
            needle=needle,
            cik=cik,
            ticker=ticker,
            entity_name=entity_name,
        )
        if matched_text is None:
            continue
        hits.append(
            DigitalOracleSecSearchHit(
                accession_number=filing.accession_number,
                form_type=filing.form_type,
                filing_date=filing.filing_date,
                cik=cik,
                ticker=ticker,
                entity_name=entity_name,
                primary_document=filing.primary_document,
                url=filing.url,
                description=filing.description,
                matched_text=matched_text,
            )
        )
    return hits


def _filter_sec_search_hits(
    search_hits: Sequence[DigitalOracleSecSearchHit],
    *,
    form_types: tuple[str, ...],
    start_date: date | None,
    end_date: date | None,
    item_limit: int,
) -> list[DigitalOracleSecSearchHit]:
    form_type_filter = set(form_types)
    filtered: list[DigitalOracleSecSearchHit] = []
    for hit in search_hits:
        if form_type_filter and hit.form_type.strip().upper() not in form_type_filter:
            continue
        if start_date is not None and hit.filing_date < start_date:
            continue
        if end_date is not None and hit.filing_date > end_date:
            continue
        filtered.append(hit)
    return sorted(filtered, key=lambda hit: hit.filing_date, reverse=True)[:item_limit]


def _ownership_transactions_for_filings(
    transactions: Sequence[DigitalOracleSecOwnershipTransaction],
    filings: Sequence[DigitalOracleSecFiling],
) -> list[DigitalOracleSecOwnershipTransaction]:
    allowed_accessions = {filing.accession_number for filing in filings}
    return [
        transaction
        for transaction in transactions
        if transaction.accession_number in allowed_accessions
    ]


def _sec_filing_matched_text(
    filing: DigitalOracleSecFiling,
    *,
    needle: str,
    cik: str | None,
    ticker: str | None,
    entity_name: str | None,
) -> str | None:
    candidates = (
        filing.accession_number,
        filing.form_type,
        filing.primary_document,
        filing.description,
        cik,
        ticker,
        entity_name,
    )
    for candidate in candidates:
        if candidate is not None and needle in candidate.casefold():
            return candidate
    return None


def _append_coverage_warning(
    warnings: list[RuntimeToolWarning],
    *,
    operation: str,
    requested_providers: tuple[str, ...],
    uncovered_providers: tuple[str, ...],
    has_results: bool,
) -> None:
    if has_results and uncovered_providers:
        warnings.append(
            partial_result_warning(
                operation=operation,
                requested_providers=requested_providers,
                uncovered_providers=uncovered_providers,
            )
        )
    if not has_results:
        warnings.append(unavailable_result_warning(operation=operation))


def _normalize_form_types(form_types: Sequence[str] | None) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_form_type in form_types or ():
        form_type = str(raw_form_type).strip().upper()
        if form_type and form_type not in seen:
            normalized.append(form_type)
            seen.add(form_type)
    return tuple(normalized)


def _normalize_limit(
    value: int | None,
    *,
    default_limit: int,
    max_limit: int,
    field_name: str,
) -> int:
    if value is None:
        return default_limit
    if value < 1:
        raise ValueError(f"{field_name} must be at least 1")
    if value > max_limit:
        raise ValueError(f"{field_name} must be at most {max_limit}")
    return value


def _normalize_prediction_market_depth_limit(value: int | None) -> int:
    return _normalize_limit(
        value,
        default_limit=5,
        max_limit=_PREDICTION_MARKETS_MAX_DEPTH_LIMIT,
        field_name="depthLimit",
    )


def _normalize_text(value: str, *, field_name: str) -> str:
    normalized = " ".join(value.split()).strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _normalize_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _normalize_text(value, field_name=field_name)


def _normalize_symbol_query(value: str, *, field_name: str) -> str:
    normalized = normalize_symbol(value)
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _normalize_optional_symbol_query(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _normalize_symbol_query(value, field_name=field_name)


def _normalize_optional_cik_query(value: str | None) -> str | None:
    if value is None:
        return None
    raw_value = value.strip().upper()
    if raw_value.startswith("CIK"):
        raw_value = raw_value[3:]
    digits = "".join(character for character in raw_value if character.isdigit())
    if not digits or len(digits) > 10 or digits != raw_value:
        raise ValueError("cik must contain 1 to 10 digits")
    return digits.zfill(10)


def _validate_date_bounds(start_date: date | None, end_date: date | None) -> None:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("startDate must be before or equal to endDate")


__all__ = [
    "DigitalOraclePhase1Service",
    "create_digital_oracle_phase1_service",
]
