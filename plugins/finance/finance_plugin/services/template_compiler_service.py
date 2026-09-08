from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from finance_plugin.models.report import Report
from finance_plugin.repositories.report import ReportRepository
from plugin_runtime.formatting import decimal_to_string, to_utc
from sqlalchemy.orm import Session

_PLACEHOLDER_RE = re.compile(r"\{\{(.+?)\}\}")
_INPUT_REFERENCE_RE = re.compile(r"^inputs\.(?P<name>[A-Za-z_][A-Za-z0-9_]*)$")
_REPORT_LATEST_RE = re.compile(
    r"^\.latest(?:\(\s*(?P<argument>.*?)\s*\))?(?:\.(?P<field>[A-Za-z_][A-Za-z0-9_]*))?$"
)
_REPORT_INDEX_RE = re.compile(r"^\[(?P<index>\d+)\](?:\.(?P<field>[A-Za-z_][A-Za-z0-9_]*))?$")
_REPORT_BY_TAG_LATEST_RE = re.compile(
    r"^\.by_tag\(\s*(?P<argument>.*?)\s*\)\.latest(?:\.(?P<field>[A-Za-z_][A-Za-z0-9_]*))?$"
)
_REPORT_SCALAR_FIELDS = frozenset({"name", "created_at"})


@dataclass(slots=True)
class ReportSelection:
    matched: bool
    report: Report | None
    field: str | None = None
    report_name: str | None = None
    error: str | None = None


class TemplateCompilerService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.report_repo = ReportRepository(session)
        self._report_resolve_stack: set[str] = set()
        self._inputs: dict[str, str] = {}

    def compile(self, content: str, inputs: dict[str, str] | None = None) -> str:
        self._report_resolve_stack = set()
        self._inputs = inputs or {}
        return _PLACEHOLDER_RE.sub(lambda match: self._resolve(match.group(1).strip()), content)

    def get_placeholder_tree(self) -> dict[str, list[dict[str, object]]]:
        return {
            "reports": [
                {
                    "name": report.name,
                    "created_at": report.created_at,
                }
                for report in self.report_repo.list_all()
            ]
        }

    def _resolve(self, path: str) -> str:
        if path == "inputs" or path.startswith("inputs."):
            return self._resolve_inputs(path)
        if path == "reports" or path.startswith("reports.") or path.startswith("reports["):
            return self._resolve_reports_path(path)
        root = path.split(".", maxsplit=1)[0].strip()
        return f"[Unknown root: {root}]"

    def _resolve_inputs(self, path: str) -> str:
        if path == "inputs":
            return self._render_all_inputs()

        match = _INPUT_REFERENCE_RE.fullmatch(path)
        if match is None:
            return f"[Unknown input: {path}]"

        input_name = match.group("name")
        value = self._inputs.get(input_name)
        if value is None:
            return f"[Missing input: {input_name}]"
        return value

    def _render_all_inputs(self) -> str:
        if not self._inputs:
            return "*(no inputs)*"
        return "\n".join(f"- {key}: {value}" for key, value in sorted(self._inputs.items()))

    def _resolve_reports_path(self, path: str) -> str:
        if path == "reports":
            return self._render_all_reports()

        suffix = path[len("reports") :]
        dynamic_selection = self._parse_dynamic_report_selector(suffix)
        if dynamic_selection.matched:
            return self._render_report_selection(dynamic_selection, dynamic=True)

        exact_selection = self._parse_exact_report_selector(suffix)
        if exact_selection.matched:
            if exact_selection.report is None and self._looks_like_dynamic_report_selector(suffix):
                return f"[Invalid report selector: {path}]"
            return self._render_report_selection(exact_selection, dynamic=False)

        return f"[Invalid report selector: {path}]"

    @staticmethod
    def _looks_like_dynamic_report_selector(suffix: str) -> bool:
        return (
            suffix.startswith(".latest") or suffix.startswith(".by_tag(") or suffix.startswith("[")
        )

    def _parse_dynamic_report_selector(self, suffix: str) -> ReportSelection:
        latest_match = _REPORT_LATEST_RE.fullmatch(suffix)
        if latest_match is not None:
            field = latest_match.group("field")
            argument = latest_match.group("argument")
            ticker, error = self._resolve_argument(argument)
            if error is not None:
                return ReportSelection(matched=True, report=None, field=field, error=error)
            if ticker is None and argument is not None:
                return ReportSelection(
                    matched=True,
                    report=None,
                    field=field,
                    error="[Invalid selector argument: ]",
                )
            reports = self.report_repo.list_all(ticker=ticker.upper() if ticker else None, limit=1)
            return ReportSelection(
                matched=True,
                report=reports[0] if reports else None,
                field=field,
                error=error,
            )

        index_match = _REPORT_INDEX_RE.fullmatch(suffix)
        if index_match is not None:
            reports = self.report_repo.list_all(limit=1, offset=int(index_match.group("index")))
            return ReportSelection(
                matched=True,
                report=reports[0] if reports else None,
                field=index_match.group("field"),
            )

        by_tag_latest_match = _REPORT_BY_TAG_LATEST_RE.fullmatch(suffix)
        if by_tag_latest_match is not None:
            field = by_tag_latest_match.group("field")
            tag, error = self._resolve_argument(by_tag_latest_match.group("argument"))
            if error is not None:
                return ReportSelection(matched=True, report=None, field=field, error=error)
            if tag is None:
                return ReportSelection(
                    matched=True,
                    report=None,
                    field=field,
                    error="[Invalid selector argument: ]",
                )
            reports = self.report_repo.list_all(tag=tag, limit=1)
            return ReportSelection(
                matched=True,
                report=reports[0] if reports else None,
                field=field,
            )

        return ReportSelection(matched=False, report=None)

    def _parse_exact_report_selector(self, suffix: str) -> ReportSelection:
        if not suffix.startswith("."):
            return ReportSelection(matched=False, report=None)

        name, has_field_separator, field = suffix[1:].partition(".")
        if not name:
            return ReportSelection(matched=False, report=None)

        return ReportSelection(
            matched=True,
            report=self.report_repo.get_by_name(name),
            field=field if has_field_separator else None,
            report_name=name,
        )

    def _render_report_selection(self, selection: ReportSelection, *, dynamic: bool) -> str:
        if selection.error is not None:
            return selection.error

        report = selection.report
        if report is None:
            if dynamic:
                return ""
            return f"[Unknown report: {selection.report_name or ''}]"

        field = selection.field
        if field is None:
            return self._render_report_metadata(report)
        if field == "content":
            return self._resolve_report_content(report)
        if field in _REPORT_SCALAR_FIELDS:
            return self._format_value(getattr(report, field, None))
        return f"[Unknown report field: {field}]"

    def _resolve_argument(self, argument: str | None) -> tuple[str | None, str | None]:
        if argument is None:
            return None, None

        trimmed = argument.strip()
        if not trimmed:
            return None, "[Invalid selector argument: ]"

        if len(trimmed) >= 2 and trimmed.startswith('"') and trimmed.endswith('"'):
            value = trimmed[1:-1].strip()
            if not value:
                return None, "[Invalid selector argument: ]"
            return value, None

        input_match = _INPUT_REFERENCE_RE.fullmatch(trimmed)
        if input_match is None:
            return None, f"[Invalid selector argument: {trimmed}]"

        input_name = input_match.group("name")
        input_value = self._inputs.get(input_name)
        if input_value is None:
            return None, f"[Missing input: {input_name}]"
        return input_value, None

    def _render_all_reports(self) -> str:
        reports = self.report_repo.list_all()
        if not reports:
            return "*(no reports)*"
        return "\n".join(f"- {self._render_report_metadata(report)}" for report in reports)

    def _render_report_metadata(self, report: Report) -> str:
        return f"**{report.name}** ({self._format_value(report.created_at)})"

    def _resolve_report_content(self, report: Report) -> str:
        if report.name in self._report_resolve_stack:
            return f"[Circular report reference: {report.name}]"

        self._report_resolve_stack.add(report.name)
        try:
            return _PLACEHOLDER_RE.sub(
                lambda match: self._resolve(match.group(1).strip()),
                report.content,
            )
        finally:
            self._report_resolve_stack.discard(report.name)

    def _format_value(self, value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, Decimal):
            return decimal_to_string(value)
        from datetime import datetime

        if isinstance(value, datetime):
            return to_utc(value).isoformat().replace("+00:00", "Z")
        return str(value)
