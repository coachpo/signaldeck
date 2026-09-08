from __future__ import annotations

from oracle_plugin.runtime_types import (
    RuntimeCftcPositioningLookupResult,
    RuntimeCryptoDerivativesLookupResult,
    RuntimeMacroRatesLookupResult,
    RuntimeMarketSentimentLookupResult,
    RuntimeOptionsLookupResult,
    RuntimePredictionMarketContract,
    RuntimePredictionMarketEvent,
    RuntimePredictionMarketOrderBook,
    RuntimePredictionMarketOrderBookLevel,
    RuntimePredictionMarketsLookupResult,
    RuntimeSecFiling,
    RuntimeSecFilingsLookupResult,
    RuntimeSecOwnershipTransaction,
    RuntimeSecSearchHit,
)

from .types import (
    DigitalOracleCftcPositioningResult,
    DigitalOracleCryptoDerivativesResult,
    DigitalOracleMacroRatesResult,
    DigitalOracleMarketSentimentResult,
    DigitalOracleOptionsResult,
    DigitalOraclePredictionMarketContract,
    DigitalOraclePredictionMarketEvent,
    DigitalOraclePredictionMarketOrderBook,
    DigitalOraclePredictionMarketOrderBookLevel,
    DigitalOraclePredictionMarketsResult,
    DigitalOracleSecFiling,
    DigitalOracleSecFilingsResult,
    DigitalOracleSecOwnershipTransaction,
    DigitalOracleSecSearchHit,
)


def map_prediction_markets_result(
    result: DigitalOraclePredictionMarketsResult,
) -> RuntimePredictionMarketsLookupResult:
    return RuntimePredictionMarketsLookupResult(
        query=result.query,
        events=[_map_prediction_market_event(event) for event in result.events],
        warnings=list(result.warnings),
    )


def map_sec_filings_result(
    result: DigitalOracleSecFilingsResult,
) -> RuntimeSecFilingsLookupResult:
    return RuntimeSecFilingsLookupResult(
        ticker=result.ticker,
        query=result.query,
        cik=result.cik,
        entity_name=result.entity_name,
        filings=[_map_sec_filing(filing) for filing in result.filings],
        search_hits=[_map_sec_search_hit(hit) for hit in result.search_hits],
        ownership_transactions=[
            _map_sec_ownership_transaction(transaction)
            for transaction in result.ownership_transactions
        ],
        warnings=list(result.warnings),
    )


def map_market_sentiment_result(
    result: DigitalOracleMarketSentimentResult,
) -> RuntimeMarketSentimentLookupResult:
    return RuntimeMarketSentimentLookupResult(
        indicator=result.indicator,
        as_of_date=result.as_of_date,
        provider=result.provider,
        score=result.score,
        label=result.label,
        previous_close=result.previous_close,
        week_ago=result.week_ago,
        month_ago=result.month_ago,
        year_ago=result.year_ago,
        source_url=result.source_url,
        warnings=list(result.warnings),
    )


def map_macro_rates_result(result: DigitalOracleMacroRatesResult) -> RuntimeMacroRatesLookupResult:
    return RuntimeMacroRatesLookupResult.model_validate(result)


def map_crypto_derivatives_result(
    result: DigitalOracleCryptoDerivativesResult,
) -> RuntimeCryptoDerivativesLookupResult:
    return RuntimeCryptoDerivativesLookupResult.model_validate(result)


def map_cftc_positioning_result(
    result: DigitalOracleCftcPositioningResult,
) -> RuntimeCftcPositioningLookupResult:
    return RuntimeCftcPositioningLookupResult.model_validate(result)


def map_options_result(result: DigitalOracleOptionsResult) -> RuntimeOptionsLookupResult:
    return RuntimeOptionsLookupResult.model_validate(result)


def _map_prediction_market_event(
    event: DigitalOraclePredictionMarketEvent,
) -> RuntimePredictionMarketEvent:
    return RuntimePredictionMarketEvent(
        venue=event.venue,
        event_id=event.event_id,
        title=event.title,
        status=event.status,
        url=event.url,
        end_date=event.end_date,
        contracts=[_map_prediction_market_contract(contract) for contract in event.contracts],
    )


def _map_prediction_market_contract(
    contract: DigitalOraclePredictionMarketContract,
) -> RuntimePredictionMarketContract:
    return RuntimePredictionMarketContract(
        contract_id=contract.contract_id,
        title=contract.title,
        probability=contract.probability,
        yes_price=contract.yes_price,
        no_price=contract.no_price,
        volume=contract.volume,
        open_interest=contract.open_interest,
        order_book=(
            _map_prediction_market_order_book(contract.order_book)
            if contract.order_book is not None
            else None
        ),
    )


def _map_prediction_market_order_book(
    order_book: DigitalOraclePredictionMarketOrderBook,
) -> RuntimePredictionMarketOrderBook:
    return RuntimePredictionMarketOrderBook(
        bids=[_map_prediction_market_order_book_level(level) for level in order_book.bids],
        asks=[_map_prediction_market_order_book_level(level) for level in order_book.asks],
        spread=order_book.spread,
        depth_limit=order_book.depth_limit,
    )


def _map_prediction_market_order_book_level(
    level: DigitalOraclePredictionMarketOrderBookLevel,
) -> RuntimePredictionMarketOrderBookLevel:
    return RuntimePredictionMarketOrderBookLevel(
        price=level.price,
        size=level.size,
    )


def _map_sec_filing(filing: DigitalOracleSecFiling) -> RuntimeSecFiling:
    return RuntimeSecFiling(
        accession_number=filing.accession_number,
        form_type=filing.form_type,
        filing_date=filing.filing_date,
        accepted_at=filing.accepted_at,
        primary_document=filing.primary_document,
        url=filing.url,
        description=filing.description,
    )


def _map_sec_search_hit(hit: DigitalOracleSecSearchHit) -> RuntimeSecSearchHit:
    return RuntimeSecSearchHit(
        accession_number=hit.accession_number,
        form_type=hit.form_type,
        filing_date=hit.filing_date,
        cik=hit.cik,
        ticker=hit.ticker,
        entity_name=hit.entity_name,
        primary_document=hit.primary_document,
        url=hit.url,
        description=hit.description,
        matched_text=hit.matched_text,
    )


def _map_sec_ownership_transaction(
    transaction: DigitalOracleSecOwnershipTransaction,
) -> RuntimeSecOwnershipTransaction:
    return RuntimeSecOwnershipTransaction(
        accession_number=transaction.accession_number,
        filing_date=transaction.filing_date,
        issuer_name=transaction.issuer_name,
        issuer_ticker=transaction.issuer_ticker,
        reporting_owner_name=transaction.reporting_owner_name,
        transaction_date=transaction.transaction_date,
        transaction_code=transaction.transaction_code,
        acquired_disposed_code=transaction.acquired_disposed_code,
        shares=transaction.shares,
        price=transaction.price,
        ownership_nature=transaction.ownership_nature,
    )


__all__ = [
    "map_cftc_positioning_result",
    "map_crypto_derivatives_result",
    "map_macro_rates_result",
    "map_market_sentiment_result",
    "map_options_result",
    "map_prediction_markets_result",
    "map_sec_filings_result",
]
