from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime

from finance_plugin.contracts import RuntimeToolWarning
from finance_plugin.providers.social_sentiment_provider import (
    ProviderSocialSentimentMetric,
    ProviderSocialSentimentSourceBlock,
    ProviderSocialSentimentWarning,
    SocialSentimentProviderError,
    SocialSentimentSource,
    SocialSentimentSourceAdapter,
)
from finance_plugin.providers.social_sentiment_snapshots import (
    SocialSentimentLookupResult as RuntimeSocialSentimentLookupResult,
)
from finance_plugin.providers.social_sentiment_snapshots import (
    SocialSentimentMetric as RuntimeSocialSentimentMetric,
)
from finance_plugin.providers.social_sentiment_snapshots import (
    SocialSentimentSourceBlock as RuntimeSocialSentimentSourceBlock,
)
from plugin_runtime.common import to_camel
from plugin_runtime.formatting import normalize_symbol, to_utc

_SECRET_ASSIGNMENT_RE = re.compile(
    r"\b(api[_ -]?key|token|secret|password|credential)(\s*[=:]\s*)([^\s,;]+)",
    re.IGNORECASE,
)
_SECRET_TOKEN_RE = re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9][A-Za-z0-9_-]*")
_SENSITIVE_WARNING_DETAIL_KEY_RE = re.compile(
    r"api[_-]?key|authorization|bearer|credential|password|secret|token",
    re.IGNORECASE,
)
_WARNING_DETAIL_KEY_TOKEN_RE = re.compile(r"[^A-Za-z0-9]+")
_SUPPORTED_SOURCE_BY_KEY: dict[str, SocialSentimentSource] = {
    "reddit": "reddit",
    "stocktwits": "stocktwits",
}


class SocialSentimentService:
    default_item_limit: int = 25
    max_item_limit: int = 50
    supported_sources: tuple[SocialSentimentSource, ...] = tuple(_SUPPORTED_SOURCE_BY_KEY.values())

    def __init__(
        self,
        source_adapters: Sequence[SocialSentimentSourceAdapter] | None = None,
    ) -> None:
        self.source_adapters: tuple[SocialSentimentSourceAdapter, ...] = tuple(
            source_adapters or ()
        )

    def get_social_sentiment_snapshot(
        self,
        symbol: str,
        *,
        sources: Sequence[str] | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        item_limit: int | None = None,
    ) -> RuntimeSocialSentimentLookupResult:
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            raise SocialSentimentProviderError("Symbol is required")
        normalized_start = to_utc(start_date) if start_date is not None else None
        normalized_end = to_utc(end_date) if end_date is not None else None
        if (
            normalized_start is not None
            and normalized_end is not None
            and normalized_start > normalized_end
        ):
            raise SocialSentimentProviderError("startDate must be before or equal to endDate")
        normalized_sources = self._normalize_sources(sources)
        effective_limit = self._normalize_item_limit(item_limit)
        warnings: list[RuntimeToolWarning] = []
        source_blocks: list[RuntimeSocialSentimentSourceBlock] = []
        metrics: list[RuntimeSocialSentimentMetric] = []

        adapter_by_source = {adapter.source: adapter for adapter in self.source_adapters}
        if not adapter_by_source:
            warnings.extend(
                self._unavailable_warnings(
                    symbol=normalized_symbol,
                    sources=normalized_sources,
                    no_providers=True,
                )
            )
            return self._result(
                symbol=normalized_symbol,
                sources=normalized_sources,
                start_date=normalized_start,
                end_date=normalized_end,
                source_blocks=[],
                metrics=[],
                warnings=warnings,
            )

        attempted_sources: set[str] = set()
        uncovered_sources: set[str] = set()
        for source in normalized_sources:
            adapter = adapter_by_source.get(source)
            if adapter is None:
                uncovered_sources.add(source)
                warnings.append(
                    self._runtime_warning(
                        code="social_sentiment_provider_unavailable",
                        message=f"No social sentiment provider configured for {source}",
                        details={
                            "operation": "social_sentiment",
                            "symbol": normalized_symbol,
                            "source": source,
                        },
                    )
                )
                continue
            attempted_sources.add(source)
            try:
                provider_result = adapter.fetch_source_blocks(
                    normalized_symbol,
                    start_date=normalized_start,
                    end_date=normalized_end,
                    limit=effective_limit + 1,
                )
            except SocialSentimentProviderError as exc:
                uncovered_sources.add(source)
                warnings.append(
                    self._provider_error_warning(
                        exc,
                        symbol=normalized_symbol,
                        source=source,
                        provider=adapter.provider_name,
                    )
                )
                continue

            built_blocks = self._build_source_blocks(provider_result.source_blocks)
            if not built_blocks:
                uncovered_sources.add(source)
                warnings.append(
                    self._runtime_warning(
                        code="social_sentiment_empty_source",
                        message=f"No social sentiment returned for {source}",
                        details={"symbol": normalized_symbol, "source": source},
                    )
                )
            source_blocks.extend(built_blocks)
            metrics.extend(self._build_metrics(provider_result.metrics))
            warnings.extend(
                self._provider_warning(
                    warning,
                    symbol=normalized_symbol,
                    source=source,
                    provider=provider_result.provider,
                )
                for warning in provider_result.warnings
            )

        source_blocks.sort(key=self._source_block_sort_key, reverse=True)
        if len(source_blocks) > effective_limit:
            source_blocks = source_blocks[:effective_limit]
            warnings.append(
                self._runtime_warning(
                    code="social_sentiment_truncated",
                    message=f"Social sentiment results were truncated to {effective_limit} blocks",
                    details={"limit": str(effective_limit), "symbol": normalized_symbol},
                )
            )
        if source_blocks and uncovered_sources:
            warnings.append(
                self._runtime_warning(
                    code="social_sentiment_partial_result",
                    message="Social sentiment coverage is partial for the requested sources",
                    details={
                        "symbol": normalized_symbol,
                        "sources": ",".join(normalized_sources),
                        "uncoveredSources": ",".join(sorted(uncovered_sources)),
                    },
                )
            )
        if not source_blocks:
            if attempted_sources and not uncovered_sources:
                warnings.append(
                    self._runtime_warning(
                        code="social_sentiment_empty",
                        message="No social sentiment returned for the request",
                        details={
                            "symbol": normalized_symbol,
                            "sources": ",".join(normalized_sources),
                        },
                    )
                )
            elif attempted_sources or uncovered_sources:
                warnings.append(
                    self._unavailable_warning(
                        symbol=normalized_symbol,
                        sources=normalized_sources,
                    )
                )

        return self._result(
            symbol=normalized_symbol,
            sources=normalized_sources,
            start_date=normalized_start,
            end_date=normalized_end,
            source_blocks=source_blocks,
            metrics=metrics,
            warnings=warnings,
        )

    def _normalize_sources(
        self,
        sources: Sequence[str] | None,
    ) -> tuple[SocialSentimentSource, ...]:
        raw_sources = sources or self.supported_sources
        normalized_sources: list[SocialSentimentSource] = []
        seen_sources: set[SocialSentimentSource] = set()
        for raw_source in raw_sources:
            source_key = raw_source.strip().lower()
            source = self._normalize_source(source_key)
            if source in seen_sources:
                continue
            seen_sources.add(source)
            normalized_sources.append(source)
        if not normalized_sources:
            raise SocialSentimentProviderError("At least one social sentiment source is required")
        return tuple(normalized_sources)

    @staticmethod
    def _normalize_source(source: str) -> SocialSentimentSource:
        try:
            return _SUPPORTED_SOURCE_BY_KEY[source]
        except KeyError:
            raise SocialSentimentProviderError(
                f"Unsupported social sentiment source {source}"
            ) from None

    def _normalize_item_limit(self, item_limit: int | None) -> int:
        if item_limit is None:
            return self.default_item_limit
        if item_limit < 1:
            raise SocialSentimentProviderError("Social sentiment itemLimit must be at least 1")
        if item_limit > self.max_item_limit:
            raise SocialSentimentProviderError(
                f"Social sentiment itemLimit must be at most {self.max_item_limit}"
            )
        return item_limit

    def _build_source_blocks(
        self,
        blocks: Sequence[ProviderSocialSentimentSourceBlock],
    ) -> list[RuntimeSocialSentimentSourceBlock]:
        return [
            RuntimeSocialSentimentSourceBlock(
                source=block.source,
                provider=block.provider,
                title=block.title,
                summary=block.summary,
                url=block.url,
                as_of=to_utc(block.as_of) if block.as_of is not None else None,
                symbols=block.symbols,
                sentiment=block.sentiment,
                metrics=self._build_metrics(block.metrics),
            )
            for block in blocks
        ]

    def _build_metrics(
        self,
        metrics: Sequence[ProviderSocialSentimentMetric],
    ) -> list[RuntimeSocialSentimentMetric]:
        return [
            RuntimeSocialSentimentMetric(
                name=metric.name,
                value=metric.value,
                unit=metric.unit,
                source=metric.source,
                as_of=to_utc(metric.as_of) if metric.as_of is not None else None,
            )
            for metric in metrics
        ]

    def _provider_error_warning(
        self,
        error: SocialSentimentProviderError,
        *,
        symbol: str,
        source: str,
        provider: str,
    ) -> RuntimeToolWarning:
        return self._runtime_warning(
            code=self._provider_warning_code(error.code),
            message=str(error) or "Social sentiment provider failed",
            details={
                **error.details,
                "operation": "social_sentiment",
                "symbol": symbol,
                "source": source,
                "provider": provider,
            },
        )

    def _provider_warning(
        self,
        warning: ProviderSocialSentimentWarning,
        *,
        symbol: str,
        source: str,
        provider: str,
    ) -> RuntimeToolWarning:
        return self._runtime_warning(
            code=self._provider_warning_code(warning.code),
            message=warning.message,
            details={
                **warning.details,
                "operation": "social_sentiment",
                "symbol": symbol,
                "source": source,
                "provider": provider,
            },
        )

    def _provider_warning_code(self, provider_code: str) -> str:
        if provider_code == "provider_timeout":
            return "social_sentiment_provider_timeout"
        if provider_code == "provider_rate_limited":
            return "social_sentiment_provider_rate_limited"
        if provider_code == "provider_unavailable":
            return "social_sentiment_provider_unavailable"
        if provider_code == "source_partial":
            return "social_sentiment_source_partial"
        return "social_sentiment_provider_error"

    def _unavailable_warnings(
        self,
        *,
        symbol: str,
        sources: Sequence[str],
        no_providers: bool,
    ) -> list[RuntimeToolWarning]:
        warnings: list[RuntimeToolWarning] = []
        if no_providers:
            warnings.append(
                self._runtime_warning(
                    code="social_sentiment_provider_unavailable",
                    message="No social sentiment providers are configured.",
                    details={"operation": "social_sentiment", "symbol": symbol},
                )
            )
        warnings.append(self._unavailable_warning(symbol=symbol, sources=sources))
        return warnings

    def _unavailable_warning(
        self,
        *,
        symbol: str,
        sources: Sequence[str],
    ) -> RuntimeToolWarning:
        return self._runtime_warning(
            code="social_sentiment_unavailable",
            message="No social sentiment data available from configured providers.",
            details={
                "operation": "social_sentiment",
                "symbol": symbol,
                "sources": ",".join(sources),
            },
        )

    def _runtime_warning(
        self,
        *,
        code: str,
        message: str,
        details: dict[str, str],
    ) -> RuntimeToolWarning:
        return RuntimeToolWarning(
            code=code,
            message=self._public_warning_message(message),
            details=self._public_warning_details(details),
        )

    @staticmethod
    def _public_warning_message(message: str) -> str:
        redacted_assignments = _SECRET_ASSIGNMENT_RE.sub(
            lambda match: f"{match.group(1)}{match.group(2)}<redacted>",
            message,
        )
        return _SECRET_TOKEN_RE.sub("<redacted>", redacted_assignments)

    @classmethod
    def _public_warning_details(cls, details: dict[str, str]) -> dict[str, str]:
        public_details: dict[str, str] = {}
        for key, value in details.items():
            normalized_key = key.strip()
            if not normalized_key or _SENSITIVE_WARNING_DETAIL_KEY_RE.search(normalized_key):
                continue
            key_tokens = _WARNING_DETAIL_KEY_TOKEN_RE.sub("_", normalized_key).strip("_")
            if not key_tokens:
                continue
            public_details[to_camel(key_tokens)] = cls._public_warning_message(value)
        return public_details

    @staticmethod
    def _source_block_sort_key(block: RuntimeSocialSentimentSourceBlock) -> datetime:
        return block.as_of or datetime.min.replace(tzinfo=UTC)

    def _result(
        self,
        *,
        symbol: str,
        sources: Sequence[str],
        start_date: datetime | None,
        end_date: datetime | None,
        source_blocks: list[RuntimeSocialSentimentSourceBlock],
        metrics: list[RuntimeSocialSentimentMetric],
        warnings: list[RuntimeToolWarning],
    ) -> RuntimeSocialSentimentLookupResult:
        return RuntimeSocialSentimentLookupResult(
            symbol=symbol,
            sources=list(sources),
            start_date=start_date,
            end_date=end_date,
            source_blocks=source_blocks,
            metrics=metrics,
            warnings=warnings,
        )
