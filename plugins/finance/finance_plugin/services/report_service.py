from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from typing import cast

from fastapi import status
from finance_plugin.models.report import Report
from finance_plugin.models.text_template import TextTemplate
from finance_plugin.repositories.report import ReportRepository
from finance_plugin.schemas.report import (
    ReportMetadata,
    ReportRead,
    ReportReadMetadata,
    ReportUpdate,
)
from plugin_runtime.db_errors import is_unique_constraint_violation
from plugin_runtime.errors import ApiError, not_found_error
from plugin_runtime.formatting import utcnow
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

_MAX_NAME_LENGTH = 200
_DATETIME_SUFFIX_LENGTH = 16
_DEFAULT_EXTERNAL_REPORT_BASENAME = "external_report"
_CREATED_BY_PROVENANCE_ERROR_MESSAGE = (
    "Report createdBy provenance is server-owned and cannot be supplied for non-agent reports."
)
_REPORT_SLUG_CONSTRAINTS = frozenset({"uq_reports_slug"})


class ReportService:
    def __init__(self, session: Session) -> None:
        self.session: Session = session
        self.repository: ReportRepository = ReportRepository(session)

    def list_reports(
        self,
        *,
        q: str | None = None,
        sort: str = "newest",
        ticker: str | None = None,
        tag: str | None = None,
        review_type: str | None = None,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ReportRead]:
        return self._list_report_reads(
            q=q,
            sort=sort,
            ticker=ticker,
            tag=tag,
            review_type=review_type,
            source=source,
            limit=limit,
            offset=offset,
        )

    def get_report(self, report_id: int) -> ReportRead:
        report = self._get_model(report_id)
        return ReportRead.model_validate(report)

    def get_report_model(self, report_id: int) -> Report:
        return self._get_model(report_id)

    def get_report_by_slug(self, slug: str) -> ReportRead:
        report = self._get_model_by_slug(slug)
        return ReportRead.model_validate(report)

    def get_report_model_by_slug(self, slug: str) -> Report:
        return self._get_model_by_slug(slug)

    def create_from_template(
        self,
        template: TextTemplate,
        compiled_content: str,
        metadata: ReportMetadata | Mapping[str, object] | None = None,
    ) -> ReportRead:
        name = self._generate_unique_name(template.name)
        return self._create_report_record(
            name=name,
            slug=self._generate_unique_slug(name),
            source="compiled",
            content=compiled_content,
            metadata=metadata,
        )

    def create_from_upload(
        self,
        *,
        content: str,
        slug: str,
        name: str,
        metadata: Mapping[str, object] | None = None,
    ) -> ReportRead:
        normalized_slug = self._normalize_name(slug)
        if not normalized_slug:
            raise ApiError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_slug",
                message="Slug must contain at least one alphanumeric character",
            )
        if len(normalized_slug) > _MAX_NAME_LENGTH:
            normalized_slug = normalized_slug[:_MAX_NAME_LENGTH].rstrip("_")

        if self.repository.get_by_slug(normalized_slug) is not None:
            raise self._slug_conflict_error(normalized_slug)

        self._ensure_non_agent_provenance_not_supplied(source="uploaded", metadata=metadata)
        validated_metadata = ReportMetadata.model_validate(metadata or {})

        report_name = name if name else normalized_slug
        if len(report_name) > _MAX_NAME_LENGTH:
            report_name = report_name[:_MAX_NAME_LENGTH]

        if self.repository.get_by_name(report_name) is not None:
            report_name = self._generate_unique_name(report_name)

        return self._create_report_record(
            name=report_name,
            slug=normalized_slug,
            source="uploaded",
            content=content,
            metadata=validated_metadata,
        )

    def create_external_report(
        self,
        *,
        content: str,
        name: str | None = None,
        slug: str | None = None,
        metadata: ReportMetadata | Mapping[str, object] | None = None,
    ) -> ReportRead:
        report_name = self._resolve_external_report_name(name)

        if slug is not None:
            normalized_slug = self._normalize_slug(slug)
            if self.repository.get_by_slug(normalized_slug) is not None:
                raise self._slug_conflict_error(normalized_slug)
        else:
            normalized_slug = self._generate_unique_slug(report_name)

        return self._create_report_record(
            name=report_name,
            slug=normalized_slug,
            source="external",
            content=content,
            metadata=metadata,
        )

    def update_report_by_slug(self, slug: str, payload: ReportUpdate) -> ReportRead:
        report = self._get_model_by_slug(slug)
        if report.source == "agent":
            raise ApiError(
                status_code=409,
                code="immutable_agent_report",
                message="Agent reports preserve the original run output",
            )
        if payload.content is not None:
            report.content = payload.content
        self.session.commit()
        self.session.refresh(report)
        return ReportRead.model_validate(report)

    def delete_report_by_slug(self, slug: str) -> None:
        report = self._get_model_by_slug(slug)
        if report.source == "agent":
            raise ApiError(
                status_code=409,
                code="immutable_agent_report",
                message="Agent reports preserve the original run output",
            )
        self.repository.delete(report)
        self.session.commit()

    def update_report(self, report_id: int, payload: ReportUpdate) -> ReportRead:
        report = self._get_model(report_id)
        if report.source == "agent":
            raise ApiError(
                status_code=409,
                code="immutable_agent_report",
                message="Agent reports preserve the original run output",
            )
        if payload.content is not None:
            report.content = payload.content
        self.session.commit()
        self.session.refresh(report)
        return ReportRead.model_validate(report)

    def delete_report(self, report_id: int) -> None:
        report = self._get_model(report_id)
        if report.source == "agent":
            raise ApiError(
                status_code=409,
                code="immutable_agent_report",
                message="Agent reports preserve the original run output",
            )
        self.repository.delete(report)
        self.session.commit()

    def _list_report_reads(
        self,
        *,
        q: str | None = None,
        sort: str = "newest",
        ticker: str | None = None,
        tag: str | None = None,
        review_type: str | None = None,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[ReportRead]:
        reports = self.repository.list_all(
            q=self._normalize_optional_filter(q),
            sort=sort,
            ticker=self._normalize_ticker_filter(ticker),
            tag=self._normalize_optional_filter(tag),
            review_type=self._normalize_optional_filter(review_type),
            source=source,
            limit=limit,
            offset=offset,
        )
        return [ReportRead.model_validate(report) for report in reports]

    def _get_model(self, report_id: int) -> Report:
        report = self.repository.get(report_id)
        if report is None:
            raise not_found_error("Report")
        return report

    def _get_model_by_slug(self, slug: str) -> Report:
        report = self.repository.get_by_slug(slug)
        if report is None:
            raise not_found_error("Report")
        return report

    def _generate_unique_name(self, template_name: str) -> str:
        normalized = self._normalize_name(template_name)
        if not normalized:
            normalized = re.sub(r"\s+", "_", template_name.strip()) or "report"
        now = utcnow()
        datetime_suffix = now.strftime("_%Y%m%d_%H%M%S")

        max_prefix_length = _MAX_NAME_LENGTH - _DATETIME_SUFFIX_LENGTH
        if len(normalized) > max_prefix_length:
            normalized = normalized[:max_prefix_length].rstrip("_")

        base_name = f"{normalized}{datetime_suffix}"

        if self.repository.get_by_name(base_name) is None:
            return base_name

        counter = 2
        while True:
            candidate = f"{base_name}_{counter}"
            if len(candidate) > _MAX_NAME_LENGTH:
                trim = len(candidate) - _MAX_NAME_LENGTH
                normalized_trimmed = normalized[: len(normalized) - trim].rstrip("_")
                candidate = f"{normalized_trimmed}{datetime_suffix}_{counter}"
            if self.repository.get_by_name(candidate) is None:
                return candidate
            counter += 1

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized = unicodedata.normalize("NFKD", name)
        lowered = normalized.lower()
        replaced = re.sub(r"[^a-z0-9]+", "_", lowered)
        collapsed = re.sub(r"_+", "_", replaced)
        return collapsed.strip("_")

    def _create_report_record(
        self,
        *,
        name: str,
        slug: str,
        source: str,
        content: str,
        metadata: ReportMetadata | Mapping[str, object] | None = None,
    ) -> ReportRead:
        self._ensure_non_agent_provenance_not_supplied(source=source, metadata=metadata)
        validated_metadata = self._validate_metadata(metadata)
        self._ensure_non_agent_provenance_not_supplied(source=source, metadata=validated_metadata)
        report = Report(
            name=name,
            slug=slug,
            source=source,
            content=content,
            metadata_=self._serialize_metadata(validated_metadata),
        )
        _ = self.repository.add(report)
        try:
            self.session.commit()
            self.session.refresh(report)
        except IntegrityError as exc:
            self.session.rollback()
            if is_unique_constraint_violation(exc, _REPORT_SLUG_CONSTRAINTS):
                raise self._slug_conflict_error(slug) from exc
            raise
        except Exception:
            self.session.rollback()
            raise
        return ReportRead.model_validate(report)

    @staticmethod
    def _slug_conflict_error(slug: str) -> ApiError:
        return ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="slug_conflict",
            message=f'A report with slug "{slug}" already exists',
        )

    def _validate_metadata(
        self, metadata: ReportMetadata | Mapping[str, object] | None
    ) -> ReportMetadata:
        if isinstance(metadata, ReportMetadata):
            return metadata
        return ReportMetadata.model_validate(metadata or {})

    def _ensure_non_agent_provenance_not_supplied(
        self,
        *,
        source: str,
        metadata: ReportMetadata | Mapping[str, object] | None,
    ) -> None:
        if source == "agent" or not self._metadata_has_created_by(metadata):
            return
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_report_provenance",
            message=_CREATED_BY_PROVENANCE_ERROR_MESSAGE,
        )

    @staticmethod
    def _metadata_has_created_by(
        metadata: ReportMetadata | Mapping[str, object] | None,
    ) -> bool:
        if metadata is None:
            return False
        if isinstance(metadata, Mapping):
            return "createdBy" in metadata or "created_by" in metadata
        payload = metadata.model_dump(by_alias=True, exclude_none=True)
        return "createdBy" in payload or "created_by" in payload

    def _serialize_metadata(self, metadata: ReportMetadata) -> dict[str, object]:
        payload = metadata.model_dump(by_alias=True)
        analysis = metadata.analysis
        if analysis is None:
            payload.pop("analysis", None)
        else:
            payload["analysis"] = analysis.model_dump(by_alias=True, exclude_none=True)
        if isinstance(metadata, ReportReadMetadata) and metadata.created_by is not None:
            payload["createdBy"] = metadata.created_by.model_dump(
                by_alias=True,
                exclude_none=True,
            )
        else:
            payload.pop("createdBy", None)
        return cast(dict[str, object], payload)

    def _resolve_external_report_name(self, name: str | None) -> str:
        if name is None:
            return self._generate_unique_name(_DEFAULT_EXTERNAL_REPORT_BASENAME)

        report_name = name.strip()
        if not report_name:
            return self._generate_unique_name(_DEFAULT_EXTERNAL_REPORT_BASENAME)

        if len(report_name) > _MAX_NAME_LENGTH:
            report_name = report_name[:_MAX_NAME_LENGTH]

        if self.repository.get_by_name(report_name) is not None:
            report_name = self._generate_unique_name(report_name)

        return report_name

    def _generate_unique_slug(self, base_value: str) -> str:
        normalized_slug = self._normalize_name(base_value)
        if not normalized_slug:
            normalized_slug = _DEFAULT_EXTERNAL_REPORT_BASENAME

        if len(normalized_slug) > _MAX_NAME_LENGTH:
            normalized_slug = normalized_slug[:_MAX_NAME_LENGTH].rstrip("_")

        if self.repository.get_by_slug(normalized_slug) is None:
            return normalized_slug

        counter = 2
        while True:
            suffix = f"_{counter}"
            max_base_length = _MAX_NAME_LENGTH - len(suffix)
            trimmed_base = normalized_slug[:max_base_length].rstrip("_")
            if not trimmed_base:
                trimmed_base = "report"
            candidate = f"{trimmed_base}{suffix}"
            if self.repository.get_by_slug(candidate) is None:
                return candidate
            counter += 1

    def _normalize_slug(self, value: str) -> str:
        normalized_slug = self._normalize_name(value)
        if not normalized_slug:
            raise ApiError(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="invalid_slug",
                message="Slug must contain at least one alphanumeric character",
            )
        if len(normalized_slug) > _MAX_NAME_LENGTH:
            normalized_slug = normalized_slug[:_MAX_NAME_LENGTH].rstrip("_")
        return normalized_slug

    @staticmethod
    def _normalize_optional_filter(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized

    def _normalize_ticker_filter(self, value: str | None) -> str | None:
        normalized = self._normalize_optional_filter(value)
        if normalized is None:
            return None
        return normalized.upper()
