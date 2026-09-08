"""Finance translates database races without leaving a failed transaction."""

from collections.abc import Callable

import pytest
from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from tests import test_finance_api as finance

finance_app = finance.finance_app
session_factory = finance.session_factory
from finance_plugin.models.report import Report  # noqa: E402
from finance_plugin.models.text_template import TextTemplate  # noqa: E402
from finance_plugin.schemas.text_template import TextTemplateCreate  # noqa: E402
from finance_plugin.services.report_service import ReportService  # noqa: E402
from finance_plugin.services.text_template_service import TextTemplateService  # noqa: E402
from plugin_runtime.errors import ApiError  # noqa: E402


def _race_once_on_commit(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    winner: Callable[[], None],
) -> None:
    original_commit = session.commit
    raced = False

    def racing_commit() -> None:
        nonlocal raced
        if not raced:
            raced = True
            winner()
        original_commit()

    monkeypatch.setattr(session, "commit", racing_commit)


def _assert_session_is_usable(session: Session) -> None:
    assert session.scalar(select(1)) == 1


def test_template_create_translates_commit_time_name_conflict(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with session_factory() as session:
        service = TextTemplateService(session)

        def insert_duplicate() -> None:
            with session_factory() as winner_session:
                winner_session.add(TextTemplate(name="Race Template", content="# Winner"))
                winner_session.commit()

        _race_once_on_commit(monkeypatch, session, insert_duplicate)

        with pytest.raises(ApiError) as excinfo:
            _ = service.create_template(TextTemplateCreate(name="Race Template", content="# Loser"))

        assert excinfo.value.status_code == status.HTTP_400_BAD_REQUEST
        assert excinfo.value.code == "duplicate_template_name"
        _assert_session_is_usable(session)


def test_report_external_create_translates_commit_time_slug_conflict(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with session_factory() as session:
        service = ReportService(session)

        def insert_duplicate() -> None:
            with session_factory() as winner_session:
                winner_session.add(
                    Report(
                        name="Winner Report",
                        slug="race_report",
                        source="external",
                        content="# Winner",
                        metadata_={},
                    )
                )
                winner_session.commit()

        _race_once_on_commit(monkeypatch, session, insert_duplicate)

        with pytest.raises(ApiError) as excinfo:
            _ = service.create_external_report(
                content="# Loser",
                name="Loser Report",
                slug="race_report",
            )

        assert excinfo.value.status_code == status.HTTP_409_CONFLICT
        assert excinfo.value.code == "slug_conflict"
        _assert_session_is_usable(session)
