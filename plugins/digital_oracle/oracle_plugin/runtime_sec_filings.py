from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol, cast
from urllib.parse import urlencode
from xml.etree import ElementTree

import httpx
from oracle_plugin.config import DigitalOracleSettings
from oracle_plugin.contracts import (
    RuntimeToolContext,
    RuntimeToolError,
    RuntimeToolSpec,
    RuntimeToolWarning,
)
from oracle_plugin.factory import (
    DigitalOracleProviderSecrets,
    create_digital_oracle_phase1_provider_bundle,
    create_sec_filings_provider,
)
from oracle_plugin.mappers import map_sec_filings_result
from oracle_plugin.ownership import (
    DIGITAL_ORACLE_DENIED_CODE,
    DIGITAL_ORACLE_DENIED_MESSAGES,
    DIGITAL_ORACLE_EXTENSION_KEY,
)
from oracle_plugin.runtime_types import SEC_FILINGS_LOOKUP_TOOL_KEY
from oracle_plugin.service import DigitalOraclePhase1Service
from oracle_plugin.types import (
    DigitalOracleProviderError,
    DigitalOracleSecFiling,
    DigitalOracleSecFilingsProvider,
    DigitalOracleSecFilingsProviderQuery,
    DigitalOracleSecFilingsProviderResult,
    DigitalOracleSecFilingsQuery,
    DigitalOracleSecOwnershipTransaction,
    DigitalOracleSecSearchHit,
)
from plugin_runtime.formatting import normalize_symbol, to_utc

SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME = "signaldeck_digital_oracle_sec_filings_lookup"
SEC_FILINGS_LOOKUP_ACCESS_DENIED_CODE = DIGITAL_ORACLE_DENIED_CODE
SEC_FILINGS_LOOKUP_ACCESS_DENIED_MESSAGE = DIGITAL_ORACLE_DENIED_MESSAGES[
    SEC_FILINGS_LOOKUP_TOOL_KEY
]

_SEC_FILINGS_MAX_ITEM_LIMIT = 50
_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SEARCH_INDEX_URL = "https://efts.sec.gov/LATEST/search-index"
_SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik}.json"
_ARCHIVES_DOCUMENT_URL_TEMPLATE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}"
_SEC_FILINGS_LOOKUP_DESCRIPTION = (
    "Read normalized SEC EDGAR filing summaries, search hits, and Form 4 summaries."
)
_SEC_FILINGS_LOOKUP_GUIDANCE = (
    "When you need SEC filing facts, call signaldeck_digital_oracle_sec_filings_lookup "
    "with a ticker or CIK and optional form/date/query filters. Use only returned "
    "filing summaries, search hits, and Form 4 ownership summaries; disclose warnings "
    "for empty, stale, partial, or config-blocked EDGAR coverage; never invent filing "
    "facts or ask for the configured EDGAR contact email."
)
_SEC_FILINGS_LOOKUP_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string", "minLength": 1},
        "query": {"type": "string", "minLength": 1, "maxLength": 200},
        "cik": {"type": "string", "minLength": 1, "maxLength": 13},
        "formTypes": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 1,
        },
        "startDate": {"type": "string"},
        "endDate": {"type": "string"},
        "itemLimit": {"type": "integer", "minimum": 1, "maximum": _SEC_FILINGS_MAX_ITEM_LIMIT},
        "includeOwnershipTransactions": {"type": "boolean"},
    },
    "required": [],
    "unevaluatedProperties": False,
}


class _EdgarJsonClient(Protocol):
    def get_json(
        self,
        url: str,
        *,
        timeout: float,
        contact_email: str,
    ) -> object: ...

    def get_text(
        self,
        url: str,
        *,
        timeout: float,
        contact_email: str,
    ) -> str: ...


class _HttpxEdgarJsonClient:
    def get_json(
        self,
        url: str,
        *,
        timeout: float,
        contact_email: str,
    ) -> object:
        headers = {
            "Accept": "application/json",
            "User-Agent": f"signaldeck-backend/0.1 sec-filings ({contact_email})",
        }
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(url, headers=headers)
                _ = response.raise_for_status()
                return cast(object, response.json())
        except httpx.TimeoutException as exc:
            raise DigitalOracleProviderError(
                "SEC EDGAR timed out while fetching filings",
                code="provider_timeout",
                details={"provider": "edgar"},
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise _http_status_provider_error(exc) from exc
        except httpx.HTTPError as exc:
            raise DigitalOracleProviderError(
                "SEC EDGAR is unavailable for filing lookup",
                code="provider_unavailable",
                details={"provider": "edgar"},
            ) from exc
        except ValueError as exc:
            raise DigitalOracleProviderError(
                "SEC EDGAR returned malformed filing data",
                details={"provider": "edgar"},
            ) from exc

    def get_text(
        self,
        url: str,
        *,
        timeout: float,
        contact_email: str,
    ) -> str:
        headers = {
            "Accept": "application/xml,text/xml,text/plain",
            "User-Agent": f"signaldeck-backend/0.1 sec-filings ({contact_email})",
        }
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(url, headers=headers)
                _ = response.raise_for_status()
                return response.text
        except httpx.TimeoutException as exc:
            raise DigitalOracleProviderError(
                "SEC EDGAR timed out while fetching ownership filing summary",
                code="provider_timeout",
                details={"provider": "edgar"},
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise _http_status_provider_error(exc) from exc
        except httpx.HTTPError as exc:
            raise DigitalOracleProviderError(
                "SEC EDGAR is unavailable for ownership filing lookup",
                code="provider_unavailable",
                details={"provider": "edgar"},
            ) from exc


class EdgarSecFilingsProvider:
    provider_name: str = "edgar"

    def __init__(self, http_client: _EdgarJsonClient | None = None) -> None:
        self._http_client: _EdgarJsonClient = http_client or _HttpxEdgarJsonClient()
        self._ticker_cik_cache: dict[str, tuple[str, str | None]] = {}
        self._cik_company_cache: dict[str, tuple[str | None, str | None]] = {}

    def lookup_sec_filings(
        self,
        query: DigitalOracleSecFilingsProviderQuery,
    ) -> DigitalOracleSecFilingsProviderResult:
        ticker = query.ticker
        cik = query.cik
        entity_name: str | None = None
        if cik is None and ticker is not None:
            cached_company = self._ticker_cik_cache.get(ticker)
            if cached_company is None:
                company_payload = self._http_client.get_json(
                    _COMPANY_TICKERS_URL,
                    timeout=query.timeout_seconds,
                    contact_email=query.edgar_contact_email,
                )
                company = _company_for_ticker(company_payload, ticker)
                if company is None:
                    return DigitalOracleSecFilingsProviderResult(
                        provider=self.provider_name,
                        ticker=ticker,
                        warnings=(_ticker_not_found_warning(ticker),),
                    )

                cik = _company_cik(company)
                if cik is None:
                    raise DigitalOracleProviderError(
                        "SEC EDGAR returned malformed ticker mapping",
                        details={"provider": self.provider_name, "ticker": ticker},
                    )
                entity_name = _text(company.get("title"))
                self._ticker_cik_cache[ticker] = (cik, entity_name)
                self._cik_company_cache[cik] = (ticker, entity_name)
            else:
                cik, entity_name = cached_company
        elif cik is not None:
            cached_cik_company = self._cik_company_cache.get(cik)
            if cached_cik_company is None:
                company_payload = self._http_client.get_json(
                    _COMPANY_TICKERS_URL,
                    timeout=query.timeout_seconds,
                    contact_email=query.edgar_contact_email,
                )
                company = _company_for_cik(company_payload, cik)
                if company is not None:
                    ticker = _text(company.get("ticker")) or ticker
                    entity_name = _text(company.get("title"))
                    self._cik_company_cache[cik] = (ticker, entity_name)
                    if ticker is not None:
                        self._ticker_cik_cache[ticker] = (cik, entity_name)
                else:
                    self._cik_company_cache[cik] = (ticker, None)
            else:
                cached_ticker, entity_name = cached_cik_company
                ticker = cached_ticker or ticker
        if cik is None:
            raise DigitalOracleProviderError(
                "SEC EDGAR lookup requires a ticker or CIK",
                details={"provider": self.provider_name},
            )
        submissions_payload = self._http_client.get_json(
            _SUBMISSIONS_URL_TEMPLATE.format(cik=cik),
            timeout=query.timeout_seconds,
            contact_email=query.edgar_contact_email,
        )
        submissions = _mapping_payload(submissions_payload, label="company submissions")
        entity_name = _text(submissions.get("name")) or entity_name
        recent = _recent_filings_payload(submissions)
        warnings: list[RuntimeToolWarning] = []
        filings = _map_recent_filings(recent, cik=cik, warnings=warnings)
        if not filings and _has_archived_filings(submissions):
            warnings.append(_stale_archive_warning(ticker or cik, cik=cik))
        search_hits: tuple[DigitalOracleSecSearchHit, ...] = ()
        if query.query is not None:
            search_hits = tuple(
                _search_edgar_filings(
                    query,
                    cik=cik,
                    ticker=ticker,
                    entity_name=entity_name,
                    http_client=self._http_client,
                    warnings=warnings,
                )
            )
        ownership_transactions: tuple[DigitalOracleSecOwnershipTransaction, ...] = ()
        if query.include_ownership_transactions:
            ownership_transactions = tuple(
                _ownership_transactions_from_filings(
                    _ownership_candidate_filings(filings, query),
                    http_client=self._http_client,
                    timeout=query.timeout_seconds,
                    contact_email=query.edgar_contact_email,
                    warnings=warnings,
                    transaction_limit=query.item_limit,
                    warn_when_no_form4=_should_warn_for_missing_ownership_forms(query),
                )
            )

        return DigitalOracleSecFilingsProviderResult(
            provider=self.provider_name,
            ticker=ticker,
            cik=cik,
            entity_name=entity_name,
            filings=tuple(filings),
            search_hits=search_hits,
            ownership_transactions=ownership_transactions,
            warnings=tuple(warnings),
        )


def create_sec_filings_provider_adapter() -> DigitalOracleSecFilingsProvider:
    return EdgarSecFilingsProvider()


def create_sec_filings_service(
    *,
    settings: DigitalOracleSettings | None = None,
    provider_secrets: DigitalOracleProviderSecrets | None = None,
    sec_filings_provider: DigitalOracleSecFilingsProvider | None = None,
) -> DigitalOraclePhase1Service:
    provider_bundle = replace(
        create_digital_oracle_phase1_provider_bundle(
            settings,
            provider_secrets=provider_secrets,
        ),
        sec_filings=create_sec_filings_provider(settings, provider_secrets=provider_secrets),
    )
    return DigitalOraclePhase1Service(
        provider_bundle=provider_bundle,
        sec_filings_provider=sec_filings_provider or create_sec_filings_provider_adapter(),
    )


def parse_sec_filings_lookup_arguments(arguments_json: str) -> dict[str, object]:
    raw_arguments = _parse_json_object(
        arguments_json,
        function_name=SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    _reject_unexpected_keys(
        raw_arguments,
        allowed_keys={
            "ticker",
            "query",
            "cik",
            "formTypes",
            "startDate",
            "endDate",
            "itemLimit",
            "includeOwnershipTransactions",
        },
        function_name=SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    start_date = _parse_optional_date_argument(raw_arguments.get("startDate"), "startDate")
    end_date = _parse_optional_date_argument(raw_arguments.get("endDate"), "endDate")
    _validate_date_bounds(start_date, end_date)
    ticker = _parse_optional_ticker_argument(raw_arguments.get("ticker"))
    cik = _parse_optional_cik_argument(raw_arguments.get("cik"))
    if ticker is None and cik is None:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} ticker or cik is required.",
        )
    return {
        "ticker": ticker,
        "query": _parse_optional_text_argument(raw_arguments.get("query"), "query"),
        "cik": cik,
        "form_types": _parse_form_types_argument(raw_arguments.get("formTypes")),
        "start_date": start_date,
        "end_date": end_date,
        "item_limit": _parse_optional_integer_argument(
            raw_arguments.get("itemLimit"),
            field_name="itemLimit",
            minimum=1,
            maximum=_SEC_FILINGS_MAX_ITEM_LIMIT,
        ),
        "include_ownership_transactions": _parse_optional_bool_argument(
            raw_arguments.get("includeOwnershipTransactions"),
            "includeOwnershipTransactions",
        ),
    }


def execute_sec_filings_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    service = create_sec_filings_service(
        provider_secrets=DigitalOracleProviderSecrets(
            edgar_contact_email=context.resolve_secret_value("edgar_contact_email"),
        )
    )
    result = service.lookup_sec_filings(
        DigitalOracleSecFilingsQuery(
            ticker=cast(str | None, arguments["ticker"]),
            query=cast(str | None, arguments["query"]),
            cik=cast(str | None, arguments["cik"]),
            form_types=cast(tuple[str, ...] | None, arguments["form_types"]),
            start_date=cast(date | None, arguments["start_date"]),
            end_date=cast(date | None, arguments["end_date"]),
            item_limit=cast(int | None, arguments["item_limit"]),
            include_ownership_transactions=cast(
                bool,
                arguments["include_ownership_transactions"],
            ),
        )
    )
    runtime_result = map_sec_filings_result(result)
    return cast(dict[str, object], runtime_result.model_dump(mode="json", by_alias=True))


def _parse_json_object(arguments_json: str, *, function_name: str) -> dict[str, object]:
    try:
        raw_payload = cast(object, json.loads(arguments_json))
    except json.JSONDecodeError as exc:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"OpenAI response requested {function_name} with invalid JSON arguments.",
        ) from exc
    if not isinstance(raw_payload, dict):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} arguments must be a JSON object.",
        )
    return cast(dict[str, object], raw_payload)


def _reject_unexpected_keys(
    raw_arguments: dict[str, object],
    *,
    allowed_keys: set[str],
    function_name: str,
) -> None:
    unexpected_keys = sorted(set(raw_arguments) - allowed_keys)
    if unexpected_keys:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{function_name} arguments contained unsupported fields: "
                f"{', '.join(unexpected_keys)}"
            ),
        )


def _parse_optional_ticker_argument(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} ticker must be a string.",
        )
    normalized = normalize_symbol(value)
    if not normalized:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} ticker must not be empty.",
        )
    return normalized


def _parse_optional_text_argument(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} {field_name} must be a string.",
        )
    normalized = " ".join(value.split()).strip()
    if not normalized:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} {field_name} must not be empty.",
        )
    if len(normalized) > 200:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} {field_name} "
                "must be at most 200 characters."
            ),
        )
    return normalized


def _parse_optional_cik_argument(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} cik must be a string.",
        )
    raw_value = value.strip().upper()
    if raw_value.startswith("CIK"):
        raw_value = raw_value[3:]
    digits = "".join(character for character in raw_value if character.isdigit())
    if not digits or len(digits) > 10 or digits != raw_value:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} cik must contain 1 to 10 digits.",
        )
    return digits.zfill(10)


def _parse_optional_bool_argument(value: object, field_name: str) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} {field_name} must be a boolean.",
        )
    return value


def _parse_form_types_argument(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} formTypes must be an array of strings."
            ),
        )
    form_types: list[str] = []
    seen: set[str] = set()
    for raw_form_type in cast(list[object], value):
        if not isinstance(raw_form_type, str):
            raise RuntimeToolError(
                code="agent_tool_call_invalid",
                message=(
                    f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} "
                    "formTypes must be an array of strings."
                ),
            )
        form_type = raw_form_type.strip().upper()
        if not form_type:
            raise RuntimeToolError(
                code="agent_tool_call_invalid",
                message=(
                    f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} "
                    "formTypes must not contain empty values."
                ),
            )
        if form_type not in seen:
            form_types.append(form_type)
            seen.add(form_type)
    if not form_types:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} "
                "formTypes must contain at least one form type."
            ),
        )
    return tuple(form_types)


def _parse_optional_date_argument(value: object, field_name: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} {field_name} must be a string date."
            ),
        )
    raw_value = value.strip()
    if not raw_value:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} {field_name} must be a valid ISO date."
            ),
        )
    try:
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} {field_name} must be a valid ISO date."
            ),
        ) from exc


def _validate_date_bounds(start_date: date | None, end_date: date | None) -> None:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} startDate "
                "must be before or equal to endDate."
            ),
        )


def _parse_optional_integer_argument(
    value: object,
    *,
    field_name: str,
    minimum: int,
    maximum: int,
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} {field_name} must be an integer."),
        )
    if value < minimum:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} {field_name} "
                f"must be at least {minimum}."
            ),
        )
    if value > maximum:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} {field_name} must be at most {maximum}."
            ),
        )
    return int(value)


def _company_for_ticker(payload: object, ticker: str) -> Mapping[str, object] | None:
    rows = _company_rows(payload)
    for row in rows:
        row_ticker = _text(row.get("ticker"))
        if row_ticker is not None and normalize_symbol(row_ticker) == ticker:
            return row
    return None


def _company_for_cik(payload: object, cik: str) -> Mapping[str, object] | None:
    rows = _company_rows(payload)
    for row in rows:
        row_cik = _company_cik(row)
        if row_cik == cik:
            return row
    return None


def _company_rows(payload: object) -> tuple[Mapping[str, object], ...]:
    if isinstance(payload, Mapping):
        values = cast(Mapping[str, object], payload).values()
        return tuple(
            cast(Mapping[str, object], value) for value in values if isinstance(value, Mapping)
        )
    if isinstance(payload, list):
        list_values = cast(list[object], payload)
        return tuple(
            cast(Mapping[str, object], value) for value in list_values if isinstance(value, Mapping)
        )
    raise DigitalOracleProviderError(
        "SEC EDGAR returned malformed ticker mapping",
        details={"provider": "edgar"},
    )


def _company_cik(company: Mapping[str, object]) -> str | None:
    raw_cik = company.get("cik_str") or company.get("cik")
    text = _text(raw_cik)
    if text is None:
        return None
    digits = "".join(character for character in text if character.isdigit())
    if not digits:
        return None
    return digits.zfill(10)


def _mapping_payload(payload: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(payload, Mapping):
        raise DigitalOracleProviderError(
            f"SEC EDGAR returned malformed {label}",
            details={"provider": "edgar"},
        )
    return cast(Mapping[str, object], payload)


def _recent_filings_payload(submissions: Mapping[str, object]) -> Mapping[str, object]:
    filings = submissions.get("filings")
    if not isinstance(filings, Mapping):
        return {}
    filings_payload = cast(Mapping[str, object], filings)
    recent = filings_payload.get("recent")
    if not isinstance(recent, Mapping):
        return {}
    return cast(Mapping[str, object], recent)


def _has_archived_filings(submissions: Mapping[str, object]) -> bool:
    filings = submissions.get("filings")
    if not isinstance(filings, Mapping):
        return False
    filings_payload = cast(Mapping[str, object], filings)
    files = filings_payload.get("files")
    if not isinstance(files, list):
        return False
    return len(cast(list[object], files)) > 0


def _map_recent_filings(
    recent: Mapping[str, object],
    *,
    cik: str,
    warnings: list[RuntimeToolWarning],
) -> list[DigitalOracleSecFiling]:
    filings: list[DigitalOracleSecFiling] = []
    accessions = _sequence_values(recent.get("accessionNumber"))
    for index, raw_accession in enumerate(accessions):
        accession_number = _text(raw_accession)
        form_type = _text_at(recent, "form", index)
        filing_date = _date_at(recent, "filingDate", index)
        if accession_number is None or form_type is None or filing_date is None:
            warnings.append(_malformed_warning("filing row"))
            continue
        primary_document = _text_at(recent, "primaryDocument", index)
        filings.append(
            DigitalOracleSecFiling(
                accession_number=accession_number,
                form_type=form_type.upper(),
                filing_date=filing_date,
                accepted_at=_datetime_at(recent, "acceptanceDateTime", index),
                primary_document=primary_document,
                url=_filing_url(cik, accession_number, primary_document),
                description=(
                    _text_at(recent, "primaryDocDescription", index)
                    or _text_at(recent, "description", index)
                ),
            )
        )
    return filings


def _search_edgar_filings(
    query: DigitalOracleSecFilingsProviderQuery,
    *,
    cik: str,
    ticker: str | None,
    entity_name: str | None,
    http_client: _EdgarJsonClient,
    warnings: list[RuntimeToolWarning],
) -> list[DigitalOracleSecSearchHit]:
    if query.query is None:
        return []
    try:
        payload = http_client.get_json(
            _search_url(query, cik=cik),
            timeout=query.timeout_seconds,
            contact_email=query.edgar_contact_email,
        )
    except DigitalOracleProviderError as exc:
        warnings.append(_search_unavailable_warning(str(exc)))
        return []

    try:
        search_hits = _map_search_hits(
            payload,
            fallback_cik=cik,
            fallback_ticker=ticker,
            fallback_entity_name=entity_name,
            query_text=query.query,
            limit=query.item_limit,
            warnings=warnings,
        )
    except DigitalOracleProviderError as exc:
        warnings.append(_search_unavailable_warning(str(exc)))
        return []
    if not search_hits:
        warnings.append(_search_empty_warning(query.query))
    return search_hits


def _search_url(query: DigitalOracleSecFilingsProviderQuery, *, cik: str) -> str:
    params: dict[str, object] = {
        "keys": query.query or "",
        "from": 0,
        "size": query.item_limit,
        "ciks": cik.lstrip("0") or cik,
    }
    if query.form_types:
        params["forms"] = ",".join(query.form_types)
    if query.start_date is not None:
        params["startdt"] = query.start_date.isoformat()
    if query.end_date is not None:
        params["enddt"] = query.end_date.isoformat()
    return f"{_SEARCH_INDEX_URL}?{urlencode(params)}"


def _map_search_hits(
    payload: object,
    *,
    fallback_cik: str,
    fallback_ticker: str | None,
    fallback_entity_name: str | None,
    query_text: str,
    limit: int,
    warnings: list[RuntimeToolWarning],
) -> list[DigitalOracleSecSearchHit]:
    rows = _search_hit_rows(payload)
    hits: list[DigitalOracleSecSearchHit] = []
    for row in rows:
        source = _search_hit_source(row)
        accession_number = _text(source.get("adsh") or source.get("accessionNumber"))
        form_type = _text(source.get("form") or source.get("formType"))
        filing_date = _search_hit_date(source)
        if accession_number is None or form_type is None or filing_date is None:
            warnings.append(_malformed_warning("search hit"))
            continue
        hit = DigitalOracleSecSearchHit(
            accession_number=accession_number,
            form_type=form_type.upper(),
            filing_date=filing_date,
            cik=_first_text_value(source.get("ciks")) or fallback_cik,
            ticker=_first_text_value(source.get("tickers")) or fallback_ticker,
            entity_name=(
                _text(source.get("companyName") or source.get("display_names"))
                or _first_text_value(source.get("display_names"))
                or fallback_entity_name
            ),
            primary_document=_text(source.get("fileName") or source.get("primaryDocument")),
            url=_text(source.get("linkToFilingDetails") or source.get("url")),
            description=_text(source.get("description") or source.get("fileDescription")),
            matched_text=_search_matched_text(source, query_text=query_text),
        )
        hits.append(hit)
        if len(hits) >= limit:
            break
    return hits


def _search_hit_rows(payload: object) -> tuple[Mapping[str, object], ...]:
    root = _mapping_payload(payload, label="search results")
    hits = root.get("hits")
    if isinstance(hits, Mapping):
        hit_rows = cast(Mapping[str, object], hits).get("hits")
    else:
        hit_rows = hits
    return tuple(
        cast(Mapping[str, object], row)
        for row in _sequence_values(hit_rows)
        if isinstance(row, Mapping)
    )


def _search_hit_source(row: Mapping[str, object]) -> Mapping[str, object]:
    source = row.get("_source")
    if isinstance(source, Mapping):
        return cast(Mapping[str, object], source)
    return row


def _search_hit_date(source: Mapping[str, object]) -> date | None:
    for key in ("filedAt", "filingDate", "filed"):
        raw_value = _text(source.get(key))
        if raw_value is None:
            continue
        try:
            return date.fromisoformat(raw_value[:10])
        except ValueError:
            return None
    return None


def _first_text_value(value: object) -> str | None:
    for item in _sequence_values(value):
        text = _text(item)
        if text is not None:
            return text
    return _text(value)


def _search_matched_text(source: Mapping[str, object], *, query_text: str) -> str | None:
    needle = query_text.casefold()
    for key in ("description", "fileDescription", "companyName", "fileName", "form", "adsh"):
        text = _text(source.get(key))
        if text is not None and needle in text.casefold():
            return text
    return _text(source.get("description") or source.get("fileDescription"))


def _ownership_transactions_from_filings(
    filings: Sequence[DigitalOracleSecFiling],
    *,
    http_client: _EdgarJsonClient,
    timeout: float,
    contact_email: str,
    warnings: list[RuntimeToolWarning],
    transaction_limit: int,
    warn_when_no_form4: bool = True,
) -> list[DigitalOracleSecOwnershipTransaction]:
    form4_filings = [
        filing for filing in filings if filing.form_type.strip().upper() in {"4", "4/A"}
    ]
    if not form4_filings:
        if warn_when_no_form4:
            warnings.append(
                _ownership_unavailable_warning("No Form 4 filing summaries were available.")
            )
        return []

    transactions: list[DigitalOracleSecOwnershipTransaction] = []
    for filing in form4_filings:
        if filing.url is None:
            warnings.append(_malformed_warning("ownership document url"))
            continue
        try:
            xml_payload = http_client.get_text(
                filing.url,
                timeout=timeout,
                contact_email=contact_email,
            )
            transactions.extend(_parse_form4_ownership_transactions(filing, xml_payload))
            if len(transactions) >= transaction_limit:
                return transactions[:transaction_limit]
        except DigitalOracleProviderError as exc:
            warnings.append(
                _ownership_unavailable_warning(
                    str(exc),
                    accession_number=filing.accession_number,
                )
            )
        except ElementTree.ParseError:
            warnings.append(_malformed_warning("ownership document"))
    if not transactions:
        warnings.append(_ownership_unavailable_warning("No Form 4 transactions were parsed."))
    return transactions


def _ownership_candidate_filings(
    filings: Sequence[DigitalOracleSecFiling],
    query: DigitalOracleSecFilingsProviderQuery,
) -> list[DigitalOracleSecFiling]:
    form_type_filter = set(query.form_types)
    candidates: list[DigitalOracleSecFiling] = []
    for filing in filings:
        if form_type_filter and filing.form_type.strip().upper() not in form_type_filter:
            continue
        if query.start_date is not None and filing.filing_date < query.start_date:
            continue
        if query.end_date is not None and filing.filing_date > query.end_date:
            continue
        candidates.append(filing)
    return sorted(candidates, key=lambda filing: filing.filing_date, reverse=True)[
        : query.item_limit
    ]


def _should_warn_for_missing_ownership_forms(query: DigitalOracleSecFilingsProviderQuery) -> bool:
    form_type_filter = set(query.form_types)
    return not form_type_filter or bool(form_type_filter & {"4", "4/A"})


def _parse_form4_ownership_transactions(
    filing: DigitalOracleSecFiling,
    xml_payload: str,
) -> list[DigitalOracleSecOwnershipTransaction]:
    root = ElementTree.fromstring(xml_payload)
    issuer_name = _first_xml_text(root, ("issuer", "issuerName"))
    issuer_ticker = _first_xml_text(root, ("issuer", "issuerTradingSymbol"))
    owner_name = _first_xml_text(root, ("reportingOwner", "reportingOwnerId", "rptOwnerName"))
    root_ownership_nature = _first_xml_text(
        root,
        ("ownershipNature", "directOrIndirectOwnership", "value"),
    )
    transaction_nodes = _xml_descendants(root, "nonDerivativeTransaction")
    if not transaction_nodes:
        return [
            DigitalOracleSecOwnershipTransaction(
                accession_number=filing.accession_number,
                filing_date=filing.filing_date,
                issuer_name=issuer_name,
                issuer_ticker=issuer_ticker,
                reporting_owner_name=owner_name,
                ownership_nature=root_ownership_nature,
            )
        ]
    return [
        DigitalOracleSecOwnershipTransaction(
            accession_number=filing.accession_number,
            filing_date=filing.filing_date,
            issuer_name=issuer_name,
            issuer_ticker=issuer_ticker,
            reporting_owner_name=owner_name,
            transaction_date=_optional_date_text(
                _first_xml_text(transaction, ("transactionDate", "value"))
            ),
            transaction_code=_first_xml_text(
                transaction,
                ("transactionCoding", "transactionCode"),
            ),
            acquired_disposed_code=_first_xml_text(
                transaction,
                ("transactionAmounts", "transactionAcquiredDisposedCode", "value"),
            ),
            shares=_optional_decimal_text(
                _first_xml_text(transaction, ("transactionAmounts", "transactionShares", "value"))
            ),
            price=_optional_decimal_text(
                _first_xml_text(
                    transaction,
                    ("transactionAmounts", "transactionPricePerShare", "value"),
                )
            ),
            ownership_nature=(
                _first_xml_text(
                    transaction,
                    ("ownershipNature", "directOrIndirectOwnership", "value"),
                )
                or root_ownership_nature
            ),
        )
        for transaction in transaction_nodes
    ]


def _xml_descendants(root: ElementTree.Element, local_name: str) -> list[ElementTree.Element]:
    return [element for element in root.iter() if _xml_local_name(element.tag) == local_name]


def _first_xml_text(root: ElementTree.Element, path: tuple[str, ...]) -> str | None:
    current_nodes = [root]
    for local_name in path:
        next_nodes: list[ElementTree.Element] = []
        for node in current_nodes:
            next_nodes.extend(
                child for child in list(node) if _xml_local_name(child.tag) == local_name
            )
        current_nodes = next_nodes
        if not current_nodes:
            return None
    for node in current_nodes:
        text = _text(node.text)
        if text is not None:
            return text
    return None


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


def _optional_date_text(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _optional_decimal_text(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _sequence_values(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    return ()


def _text_at(payload: Mapping[str, object], key: str, index: int) -> str | None:
    values = _sequence_values(payload.get(key))
    if index >= len(values):
        return None
    return _text(values[index])


def _date_at(payload: Mapping[str, object], key: str, index: int) -> date | None:
    value = _text_at(payload, key, index)
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _datetime_at(payload: Mapping[str, object], key: str, index: int) -> datetime | None:
    value = _text_at(payload, key, index)
    if value is None:
        return None
    return _parse_edgar_datetime(value)


def _parse_edgar_datetime(value: str) -> datetime | None:
    iso_value = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    try:
        return to_utc(datetime.fromisoformat(iso_value))
    except ValueError:
        compact = value.strip()
        try:
            parsed = datetime.strptime(compact, "%Y%m%d%H%M%S")
        except ValueError:
            return None
        return parsed.replace(tzinfo=UTC)


def _filing_url(cik: str, accession_number: str, primary_document: str | None) -> str:
    cik_path = cik.lstrip("0") or cik
    accession_path = accession_number.replace("-", "")
    base_url = _ARCHIVES_DOCUMENT_URL_TEMPLATE.format(cik=cik_path, accession=accession_path)
    if primary_document is None:
        return base_url
    return f"{base_url}/{primary_document}"


def _text(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if isinstance(value, int):
        return str(value)
    return None


def _ticker_not_found_warning(ticker: str) -> RuntimeToolWarning:
    return RuntimeToolWarning(
        code="sec_filings_ticker_not_found",
        message=f"SEC EDGAR ticker mapping was not found for {ticker}.",
        details={"operation": "sec_filings", "provider": "edgar", "ticker": ticker},
    )


def _malformed_warning(field: str) -> RuntimeToolWarning:
    return RuntimeToolWarning(
        code="sec_filings_malformed_payload",
        message=f"SEC EDGAR returned malformed filing {field}.",
        details={"operation": "sec_filings", "provider": "edgar", "field": field},
    )


def _stale_archive_warning(ticker: str, *, cik: str) -> RuntimeToolWarning:
    return RuntimeToolWarning(
        code="sec_filings_stale_archive",
        message=(
            "SEC EDGAR recent filing summaries were empty; older archived filings "
            "are not loaded by this lookup."
        ),
        details={"operation": "sec_filings", "provider": "edgar", "ticker": ticker, "cik": cik},
    )


def _search_empty_warning(query: str) -> RuntimeToolWarning:
    return RuntimeToolWarning(
        code="sec_filings_search_empty",
        message="SEC EDGAR search returned no filing hits; using company submissions fallback.",
        details={"operation": "sec_filings", "provider": "edgar", "query": query},
    )


def _search_unavailable_warning(message: str) -> RuntimeToolWarning:
    del message
    return RuntimeToolWarning(
        code="sec_filings_search_unavailable",
        message="SEC EDGAR search was unavailable; using company submissions fallback.",
        details={"operation": "sec_filings", "provider": "edgar", "scope": "search"},
    )


def _ownership_unavailable_warning(
    message: str,
    *,
    accession_number: str | None = None,
) -> RuntimeToolWarning:
    details = {"operation": "sec_filings", "provider": "edgar"}
    if accession_number is not None:
        details["accessionNumber"] = accession_number
    return RuntimeToolWarning(
        code="sec_filings_ownership_unavailable",
        message=message,
        details=details,
    )


def _http_status_provider_error(exc: httpx.HTTPStatusError) -> DigitalOracleProviderError:
    status_code = exc.response.status_code
    if status_code == 429:
        return DigitalOracleProviderError(
            "SEC EDGAR rate limited filing lookup",
            code="provider_rate_limited",
            details={"provider": "edgar", "status": str(status_code)},
        )
    if status_code >= 500:
        return DigitalOracleProviderError(
            "SEC EDGAR outage while fetching filings",
            code="provider_unavailable",
            details={"provider": "edgar", "status": str(status_code)},
        )
    return DigitalOracleProviderError(
        "SEC EDGAR failed while fetching filings",
        details={"provider": "edgar", "status": str(status_code)},
    )


SEC_FILINGS_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=SEC_FILINGS_LOOKUP_TOOL_KEY,
    openai_function_name=SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name="SEC Filings Lookup",
    description=_SEC_FILINGS_LOOKUP_DESCRIPTION,
    parameters_schema=_SEC_FILINGS_LOOKUP_PARAMETERS_SCHEMA,
    guidance=_SEC_FILINGS_LOOKUP_GUIDANCE,
    sort_order=87,
    denied_code=SEC_FILINGS_LOOKUP_ACCESS_DENIED_CODE,
    denied_message=SEC_FILINGS_LOOKUP_ACCESS_DENIED_MESSAGE,
    parser=parse_sec_filings_lookup_arguments,
    executor=execute_sec_filings_lookup,
    owner_extension_key=DIGITAL_ORACLE_EXTENSION_KEY,
)


__all__ = [
    "EdgarSecFilingsProvider",
    "SEC_FILINGS_LOOKUP_ACCESS_DENIED_CODE",
    "SEC_FILINGS_LOOKUP_ACCESS_DENIED_MESSAGE",
    "SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME",
    "SEC_FILINGS_LOOKUP_TOOL_SPEC",
    "create_sec_filings_provider_adapter",
    "create_sec_filings_service",
    "execute_sec_filings_lookup",
    "parse_sec_filings_lookup_arguments",
]
