"""Finance HTTP contracts exercise the independent plugin and its own database."""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

PLUGINS = Path(__file__).resolve().parents[2] / "plugins"
for directory in ("runtime", "finance"):
    sys.path.insert(0, str(PLUGINS / directory))

from finance_plugin.main import create_app  # noqa: E402
from finance_plugin.models.report import Report  # noqa: E402
from finance_plugin.providers.quote_provider import DeterministicQuoteProvider  # noqa: E402
from finance_plugin.schemas.report import ReportRead  # noqa: E402
from finance_plugin.services.report_service import ReportService  # noqa: E402
from plugin_runtime.errors import ApiError  # noqa: E402

UTC_TZ = timezone.utc  # noqa: UP017


@pytest.fixture
def finance_app(database_url: str) -> Iterator[FastAPI]:
    app = create_app(database_url, DeterministicQuoteProvider())
    with TestClient(app) as client:
        app.state.test_client = client
        yield app
    app.state.engine.dispose()


@pytest.fixture
def client(finance_app: FastAPI) -> TestClient:
    return finance_app.state.test_client


@pytest.fixture
def session_factory(finance_app: FastAPI) -> sessionmaker[Session]:
    return finance_app.state.sessions


def create_template(
    client: TestClient,
    *,
    name: str = "Daily Summary",
    content: str = "# Summary\n\n{{reports}}",
) -> dict[str, object]:
    response = client.post(
        "/api/templates",
        json={"name": name, "content": content},
    )
    assert response.status_code == 201, response.json()
    return response.json()


def insert_report_row(
    session_factory: sessionmaker[Session],
    *,
    name: str,
    slug: str,
    source: str,
    content: str = "# Report",
    metadata: dict[str, object] | None = None,
) -> int:
    with session_factory() as session:
        report = Report(
            name=name,
            slug=slug,
            source=source,
            content=content,
            metadata_=metadata or {},
        )
        session.add(report)
        session.flush()
        report_id = report.id
        session.commit()
        return report_id


def test_template_crud_and_compile_flow(client: TestClient) -> None:
    template = create_template(
        client,
        name="Input Summary",
        content=("# Summary\n\n" "Ticker: {{inputs.ticker}}\n" "All inputs:\n{{inputs}}"),
    )

    list_response = client.get("/api/templates")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [template["id"]]

    get_response = client.get(f"/api/templates/{template['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Input Summary"

    compile_response = client.post(
        f"/api/templates/{template['id']}/compile",
        json={"inputs": {"ticker": "AAPL"}},
    )
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]
    assert "Ticker: AAPL" in compiled
    assert "- ticker: AAPL" in compiled

    update_response = client.patch(
        f"/api/templates/{template['id']}",
        json={"name": "Weekly Summary", "content": "# Updated"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Weekly Summary"
    assert update_response.json()["content"] == "# Updated"

    delete_response = client.delete(f"/api/templates/{template['id']}")
    assert delete_response.status_code == 204

    missing_response = client.get(f"/api/templates/{template['id']}")
    assert missing_response.status_code == 404
    assert missing_response.json()["code"] == "not_found"


def test_template_compile_accepts_runtime_inputs(client: TestClient) -> None:
    aapl_report = client.post(
        "/api/reports",
        json={
            "name": "AAPL Saved Analysis",
            "content": "AAPL prior view",
            "metadata": {
                "tags": ["aapl_loop"],
                "analysis": {"ticker": "AAPL"},
            },
        },
    )
    assert aapl_report.status_code == 201

    tsla_report = client.post(
        "/api/reports",
        json={
            "name": "TSLA Saved Analysis",
            "content": "TSLA prior view",
            "metadata": {
                "tags": ["tsla_loop"],
                "analysis": {"ticker": "TSLA"},
            },
        },
    )
    assert tsla_report.status_code == 201

    template = create_template(
        client,
        name="Reusable Loop Template",
        content=(
            "Ticker: {{inputs.ticker}}\n"
            "Tagged prior: {{reports.by_tag(inputs.analysis_tag).latest.name}}\n"
            "Latest ticker analysis: {{reports.latest(inputs.ticker).content}}"
        ),
    )

    inline_aapl = client.post(
        "/api/templates/compile",
        json={
            "content": template["content"],
            "inputs": {
                "ticker": "AAPL",
                "analysis_tag": "aapl_loop",
            },
        },
    )
    assert inline_aapl.status_code == 200
    assert inline_aapl.json()["compiled"] == (
        "Ticker: AAPL\n"
        "Tagged prior: AAPL Saved Analysis\n"
        "Latest ticker analysis: AAPL prior view"
    )

    stored_tsla = client.post(
        f"/api/templates/{template['id']}/compile",
        json={
            "inputs": {
                "ticker": "TSLA",
                "analysis_tag": "tsla_loop",
            }
        },
    )
    assert stored_tsla.status_code == 200
    assert stored_tsla.json()["compiled"] == (
        "Ticker: TSLA\n"
        "Tagged prior: TSLA Saved Analysis\n"
        "Latest ticker analysis: TSLA prior view"
    )


def test_template_compile_surfaces_missing_runtime_inputs(client: TestClient) -> None:
    response = client.post(
        "/api/templates/compile",
        json={
            "content": (
                "Ticker: {{inputs.ticker}}\n" "Latest: {{reports.latest(inputs.ticker).name}}"
            ),
            "inputs": {},
        },
    )

    assert response.status_code == 200
    assert response.json()["compiled"] == (
        "Ticker: [Missing input: ticker]\n" "Latest: [Missing input: ticker]"
    )


def test_report_compile_crud_and_download(client: TestClient) -> None:
    template = create_template(
        client,
        name="Monthly Report",
        content="# Report\n\nTicker: {{inputs.ticker}}",
    )

    compile_response = client.post(
        f"/api/reports/compile/{template['id']}",
        json={"inputs": {"ticker": "AAPL"}},
    )
    assert compile_response.status_code == 201
    report = compile_response.json()
    assert report["name"].startswith("monthly_report_")
    assert report["slug"].startswith("monthly_report_")
    assert report["source"] == "compiled"
    assert "metadata" in report
    assert "Ticker: AAPL" in report["content"]
    assert "createdAt" in report
    assert "updatedAt" in report

    list_response = client.get("/api/reports")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["id"] == report["id"]

    get_response = client.get(f"/api/reports/{report['slug']}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == report["name"]
    assert get_response.json()["content"] == report["content"]

    update_response = client.patch(
        f"/api/reports/{report['slug']}",
        json={"content": "# Edited Report\n\nManual edit."},
    )
    assert update_response.status_code == 200
    assert update_response.json()["content"] == "# Edited Report\n\nManual edit."
    assert update_response.json()["name"] == report["name"]

    download_response = client.get(f"/api/reports/{report['slug']}/download")
    assert download_response.status_code == 200
    assert "text/markdown" in download_response.headers["content-type"]
    assert f'filename="{report["slug"]}.md"' in download_response.headers["content-disposition"]
    assert download_response.text == "# Edited Report\n\nManual edit."

    delete_response = client.delete(f"/api/reports/{report['slug']}")
    assert delete_response.status_code == 204

    missing_response = client.get(f"/api/reports/{report['slug']}")
    assert missing_response.status_code == 404
    assert missing_response.json()["code"] == "not_found"


def test_report_compile_nonexistent_template(client: TestClient) -> None:
    response = client.post("/api/reports/compile/99999")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_report_name_generation_and_uniqueness(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed_now = datetime(2026, 3, 18, 10, 56, 51, tzinfo=UTC_TZ)
    monkeypatch.setattr(
        "finance_plugin.services.report_service.utcnow",
        lambda: fixed_now,
    )

    template = create_template(
        client,
        name="Q1 Summary",
        content="# Q1",
    )

    first = client.post(f"/api/reports/compile/{template['id']}")
    assert first.status_code == 201
    first_name = first.json()["name"]
    first_slug = first.json()["slug"]
    assert first_name.startswith("q1_summary_")
    assert first_slug == first_name

    second = client.post(f"/api/reports/compile/{template['id']}")
    assert second.status_code == 201
    second_name = second.json()["name"]
    second_slug = second.json()["slug"]
    assert second_name != first_name
    assert second_name.startswith("q1_summary_")
    assert second_name.endswith("_2")
    assert second_slug == second_name


def test_report_name_normalization(client: TestClient) -> None:
    template = create_template(
        client,
        name="My Report — March",
        content="# March",
    )

    response = client.post(f"/api/reports/compile/{template['id']}")
    assert response.status_code == 201
    name = response.json()["name"]
    assert re.fullmatch(r"my_report_march_\d{8}_\d{6}", name)


def test_report_update_name_immutability(client: TestClient) -> None:
    template = create_template(client, name="Test", content="# Test")
    report = client.post(f"/api/reports/compile/{template['id']}").json()

    response = client.patch(
        f"/api/reports/{report['slug']}",
        json={"content": "# Updated", "name": "new_name"},
    )
    assert response.status_code == 422


def test_report_update_validation(client: TestClient) -> None:
    template = create_template(client, name="Test", content="# Test")
    report = client.post(f"/api/reports/compile/{template['id']}").json()

    empty_payload = client.patch(f"/api/reports/{report['slug']}", json={})
    assert empty_payload.status_code == 422

    whitespace_content = client.patch(
        f"/api/reports/{report['slug']}",
        json={"content": "   "},
    )
    assert whitespace_content.status_code == 422


def test_report_404s(client: TestClient) -> None:
    assert client.get("/api/reports/99999").status_code == 404
    assert client.patch("/api/reports/99999", json={"content": "x"}).status_code == 404
    assert client.delete("/api/reports/99999").status_code == 404
    assert client.get("/api/reports/99999/download").status_code == 404


def test_report_name_timestamp_format(client: TestClient) -> None:
    import re

    template = create_template(client, name="Timestamp Test", content="# Test")
    report = client.post(f"/api/reports/compile/{template['id']}").json()
    name = report["name"]

    pattern = r"^timestamp_test_\d{8}_\d{6}$"
    assert re.match(pattern, name), f"Name '{name}' does not match expected format"


def test_report_name_max_length_truncation(client: TestClient) -> None:
    long_name = "A" * 100
    template = create_template(client, name=long_name, content="# Long")
    report = client.post(f"/api/reports/compile/{template['id']}").json()
    assert len(report["name"]) <= 200


def test_report_upload_crud_and_download(client: TestClient) -> None:
    upload_response = client.post(
        "/api/reports/upload",
        files={
            "file": (
                "Quarterly Update.md",
                b"# Uploaded Report\n\nBody text.",
                "text/markdown",
            )
        },
        data={
            "slug": "quarterly_update",
            "author": "Analyst",
            "description": "Uploaded from disk",
            "tags": "quarterly, finance",
        },
    )
    assert upload_response.status_code == 201
    report = upload_response.json()
    assert report["name"] == "Quarterly Update"
    assert report["slug"] == "quarterly_update"
    assert report["source"] == "uploaded"
    assert report["metadata"] == {
        "author": "Analyst",
        "description": "Uploaded from disk",
        "tags": ["quarterly", "finance"],
    }

    get_response = client.get(f"/api/reports/{report['slug']}")
    assert get_response.status_code == 200
    assert get_response.json()["content"] == "# Uploaded Report\n\nBody text."

    update_response = client.patch(
        f"/api/reports/{report['slug']}",
        json={"content": "# Uploaded Report\n\nEdited body text."},
    )
    assert update_response.status_code == 200
    assert update_response.json()["content"] == "# Uploaded Report\n\nEdited body text."

    download_response = client.get(f"/api/reports/{report['slug']}/download")
    assert download_response.status_code == 200
    assert f'filename="{report["slug"]}.md"' in download_response.headers["content-disposition"]
    assert download_response.text == "# Uploaded Report\n\nEdited body text."

    delete_response = client.delete(f"/api/reports/{report['slug']}")
    assert delete_response.status_code == 204


@pytest.mark.parametrize(
    ("filename", "content", "content_type", "expected_code"),
    [
        ("notes.txt", b"# Not markdown", "text/plain", "invalid_file_type"),
        (
            "broken.md",
            b"\xff\xfe\x00",
            "application/octet-stream",
            "invalid_file_encoding",
        ),
    ],
)
def test_report_upload_validation(
    client: TestClient,
    filename: str,
    content: bytes,
    content_type: str,
    expected_code: str,
) -> None:
    response = client.post(
        "/api/reports/upload",
        files={"file": (filename, content, content_type)},
    )
    assert response.status_code == 400
    assert response.json()["code"] == expected_code


def test_report_compile_normalizes_declared_metadata(client: TestClient) -> None:
    template = create_template(client, name="Weekly Review", content="# Weekly")

    response = client.post(
        f"/api/reports/compile/{template['id']}",
        json={
            "metadata": {
                "author": " Analyst ",
                "tags": [" weekly_review ", "reflection"],
                "analysis": {
                    "ticker": "aapl",
                },
            }
        },
    )

    assert response.status_code == 201
    report = response.json()
    assert report["source"] == "compiled"
    assert report["metadata"]["author"] == "Analyst"
    assert report["metadata"]["tags"] == ["weekly_review", "reflection"]
    assert report["metadata"]["analysis"]["ticker"] == "AAPL"


def test_report_compile_accepts_runtime_inputs(client: TestClient) -> None:
    client.post(
        "/api/reports",
        json={
            "name": "MSFT Prior Analysis",
            "content": "MSFT prior report body",
            "metadata": {
                "tags": ["msft_loop"],
                "analysis": {"ticker": "MSFT"},
            },
        },
    )

    template = create_template(
        client,
        name="Runtime Report Template",
        content=("Ticker: {{inputs.ticker}}\n" "Prior: {{reports.latest(inputs.ticker).content}}"),
    )

    response = client.post(
        f"/api/reports/compile/{template['id']}",
        json={
            "inputs": {
                "ticker": "MSFT",
            },
            "metadata": {
                "tags": ["runtime_compile"],
            },
        },
    )

    assert response.status_code == 201
    report = response.json()
    assert report["content"] == ("Ticker: MSFT\n" "Prior: MSFT prior report body")
    assert report["metadata"]["tags"] == ["runtime_compile"]


def test_report_create_external_json(client: TestClient) -> None:
    response = client.post(
        "/api/reports",
        json={
            "name": "AAPL Weekly Reflection",
            "content": "# AAPL\n\nReview body.",
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "aapl",
                    "reviewType": "weekly_review",
                },
            },
        },
    )

    assert response.status_code == 201
    report = response.json()
    assert report["name"] == "AAPL Weekly Reflection"
    assert report["slug"] == "aapl_weekly_reflection"
    assert report["source"] == "external"
    assert report["metadata"]["tags"] == ["weekly_review"]
    assert report["metadata"]["analysis"]["ticker"] == "AAPL"
    assert report["metadata"]["analysis"]["reviewType"] == "weekly_review"

    get_response = client.get(f"/api/reports/{report['slug']}")
    assert get_response.status_code == 200
    assert get_response.json()["source"] == "external"


def test_report_external_non_agent_update_and_delete_remains_allowed(
    client: TestClient,
) -> None:
    create_response = client.post(
        "/api/reports",
        json={
            "name": "AAPL External Follow Up",
            "content": "# AAPL\n\nOriginal body.",
            "metadata": {
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                    "versionGroup": "weekly_review/v1",
                },
            },
        },
    )
    assert create_response.status_code == 201
    report = create_response.json()

    update_response = client.patch(
        f"/api/reports/{report['slug']}",
        json={"content": "# AAPL\n\nEdited external body."},
    )
    assert update_response.status_code == 200
    assert update_response.json()["source"] == "external"
    assert update_response.json()["content"] == "# AAPL\n\nEdited external body."

    delete_response = client.delete(f"/api/reports/{report['slug']}")
    assert delete_response.status_code == 204
    assert client.get(f"/api/reports/{report['slug']}").status_code == 404


def test_report_create_external_slug_conflict(client: TestClient) -> None:
    first = client.post(
        "/api/reports",
        json={
            "name": "External One",
            "slug": "external_one",
            "content": "# One",
        },
    )
    assert first.status_code == 201

    second = client.post(
        "/api/reports",
        json={
            "name": "External Two",
            "slug": "external_one",
            "content": "# Two",
        },
    )
    assert second.status_code == 409
    assert second.json()["code"] == "slug_conflict"


def test_report_list_filters_and_pagination(client: TestClient) -> None:
    template = create_template(client, name="AAPL Weekly Template", content="# Weekly")

    compiled = client.post(
        f"/api/reports/compile/{template['id']}",
        json={
            "metadata": {
                "tags": ["weekly_review", "reflection"],
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                },
            }
        },
    ).json()

    external_aapl = client.post(
        "/api/reports",
        json={
            "name": "AAPL Monthly Reflection",
            "content": "# AAPL Monthly",
            "metadata": {
                "tags": ["monthly_review"],
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "monthly_review",
                },
            },
        },
    ).json()

    external_msft = client.post(
        "/api/reports",
        json={
            "name": "MSFT Weekly Reflection",
            "content": "# MSFT Weekly",
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "MSFT",
                    "reviewType": "weekly_review",
                },
            },
        },
    ).json()

    uploaded = client.post(
        "/api/reports/upload",
        files={
            "file": (
                "Uploaded Note.md",
                b"# Uploaded Note\n\nArchive body.",
                "text/markdown",
            )
        },
        data={
            "slug": "uploaded_note",
            "tags": "archive",
        },
    ).json()

    all_reports = client.get("/api/reports")
    assert all_reports.status_code == 200
    assert [report["id"] for report in all_reports.json()] == [
        uploaded["id"],
        external_msft["id"],
        external_aapl["id"],
        compiled["id"],
    ]

    by_ticker = client.get("/api/reports", params={"ticker": "aapl"})
    assert by_ticker.status_code == 200
    assert [report["id"] for report in by_ticker.json()] == [
        external_aapl["id"],
        compiled["id"],
    ]

    by_tag = client.get("/api/reports", params={"tag": "weekly_review"})
    assert by_tag.status_code == 200
    assert [report["id"] for report in by_tag.json()] == [
        external_msft["id"],
        compiled["id"],
    ]

    by_review_type = client.get("/api/reports", params={"reviewType": "weekly_review"})
    assert by_review_type.status_code == 200
    assert [report["id"] for report in by_review_type.json()] == [
        external_msft["id"],
        compiled["id"],
    ]

    by_source = client.get("/api/reports", params={"source": "external"})
    assert by_source.status_code == 200
    assert [report["id"] for report in by_source.json()] == [
        external_msft["id"],
        external_aapl["id"],
    ]

    combined = client.get(
        "/api/reports",
        params={
            "ticker": "AAPL",
            "reviewType": "weekly_review",
        },
    )
    assert combined.status_code == 200
    assert [report["id"] for report in combined.json()] == [compiled["id"]]

    paginated = client.get(
        "/api/reports",
        params={"source": "external", "limit": 1, "offset": 1},
    )
    assert paginated.status_code == 200
    assert [report["id"] for report in paginated.json()] == [external_aapl["id"]]


def test_report_source_filter_accepts_agent(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    external_response = client.post(
        "/api/reports",
        json={"name": "True External Filter Companion", "content": "# External"},
    )
    assert external_response.status_code == 201
    external_report = external_response.json()
    assert external_report["source"] == "external"
    agent_report_id = insert_report_row(
        session_factory,
        name="Agent Review Report",
        slug="agent_review_report",
        source="agent",
        content="# Agent Review",
        metadata={
            "createdBy": {
                "type": "agent",
                "runId": "run-101",
                "nodeId": "analyst",
                "invocationId": "invocation-101",
                "operationId": "operation-101",
            },
            "analysis": {
                "reviewType": "agent_review",
                "versionGroup": "agent_review/v1",
            },
        },
    )
    response = client.get("/api/reports", params={"source": "agent"})
    assert response.status_code == 200
    reports = response.json()
    assert [report["id"] for report in reports] == [agent_report_id]
    assert reports[0]["source"] == "agent"
    assert reports[0]["metadata"]["createdBy"]["nodeId"] == "analyst"


def test_report_read_schema_explicitly_owns_created_by_metadata(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    schema = ReportRead.model_json_schema(by_alias=True)
    metadata = schema["$defs"]["ReportReadMetadata"]
    assert "createdBy" in metadata["properties"]
    ownership = schema["$defs"]["ReportCreatedByMetadata"]
    fields = {"type", "runId", "nodeId", "invocationId", "operationId"}
    assert set(ownership["properties"]) == fields
    assert set(ownership["required"]) == fields
    provenance = {
        "type": "agent",
        "runId": "run-404",
        "nodeId": "analyst",
        "invocationId": "invocation-404",
        "operationId": "operation-404",
    }
    report_id = insert_report_row(
        session_factory,
        name="Explicit CreatedBy Read Contract",
        slug="explicit_created_by_read_contract",
        source="agent",
        content="# Agent Review",
        metadata={
            "createdBy": provenance,
            "analysis": {
                "reviewType": "agent_review",
                "versionGroup": "agent_review/v2",
            },
        },
    )
    response = client.get("/api/reports/explicit_created_by_read_contract")
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == report_id
    assert payload["metadata"]["createdBy"] == provenance
    assert payload["metadata"]["analysis"] == {
        "reviewType": "agent_review",
        "versionGroup": "agent_review/v2",
    }
    for body in ({"content": "overwrite"}, {"content": ""}):
        updated = client.patch("/api/reports/explicit_created_by_read_contract", json=body)
        assert updated.status_code == (409 if body["content"] else 422)
    deleted = client.delete("/api/reports/explicit_created_by_read_contract")
    assert deleted.status_code == 409
    preserved = client.get("/api/reports/explicit_created_by_read_contract").json()
    assert preserved["content"] == "# Agent Review"
    assert preserved["metadata"]["createdBy"] == provenance


def test_report_source_filter_external_excludes_agent_reports(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    external_response = client.post(
        "/api/reports", json={"name": "True External Report", "content": "# External"}
    )
    assert external_response.status_code == 201
    external_report = external_response.json()
    agent_report_id = insert_report_row(
        session_factory,
        name="Agent Review External Exclusion",
        slug="agent_review_external_exclusion",
        source="agent",
        content="# Agent Review",
        metadata={
            "createdBy": {
                "type": "agent",
                "runId": "run-202",
                "nodeId": "analyst",
                "invocationId": "invocation-202",
                "operationId": "operation-202",
            },
            "analysis": {
                "reviewType": "agent_review",
                "versionGroup": "agent_review/v1",
            },
        },
    )
    agent_response = client.get("/api/reports", params={"source": "agent"})
    response = client.get("/api/reports", params={"source": "external"})
    assert agent_response.status_code == 200
    agent_report_ids = [report["id"] for report in agent_response.json()]
    assert agent_report_ids == [agent_report_id]
    assert agent_response.json()[0]["metadata"]["createdBy"]["runId"] == "run-202"
    assert response.status_code == 200
    report_ids = [report["id"] for report in response.json()]
    assert report_ids == [external_report["id"]]
    assert response.json()[0]["source"] == "external"


def test_public_report_create_rejects_agent_created_by_provenance(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    created_by = {
        "type": "agent",
        "runId": 303,
        "agentKey": "spoofed-agent",
        "agentVersion": 1,
    }
    expected_message = (
        "Report createdBy provenance is server-owned and cannot be supplied for non-agent reports."
    )

    create_response = client.post(
        "/api/reports",
        json={
            "name": "Spoofed External Report",
            "content": "# Spoofed",
            "metadata": {"createdBy": created_by},
        },
    )

    assert create_response.status_code == 422
    assert create_response.json()["code"] == "validation_error"
    assert create_response.json()["details"] == []

    template = create_template(client, name="Spoofed Compile", content="# Compile")
    compile_response = client.post(
        f"/api/reports/compile/{template['id']}",
        json={"metadata": {"createdBy": created_by}},
    )

    assert compile_response.status_code == 422
    assert compile_response.json()["code"] == "validation_error"
    assert compile_response.json()["details"] == []

    with session_factory() as session:
        service = ReportService(session)
        with pytest.raises(ApiError) as upload_error:
            service.create_from_upload(
                content="# Uploaded Spoof",
                slug="uploaded_spoof",
                name="Uploaded Spoof",
                metadata={"createdBy": created_by},
            )
        with pytest.raises(ApiError) as external_error:
            service.create_external_report(
                content="# Snake Case Spoof",
                name="Snake Case Spoof",
                metadata={"created_by": created_by},
            )

    for error in (upload_error.value, external_error.value):
        assert error.status_code == 400
        assert error.code == "invalid_report_provenance"
        assert error.message == expected_message


def test_report_placeholder_all_paths(client: TestClient) -> None:
    source_template = create_template(
        client,
        name="Source",
        content="Name: {{inputs.name}}",
    )
    report_response = client.post(
        f"/api/reports/compile/{source_template['id']}",
        json={"inputs": {"name": "Growth"}},
    )
    assert report_response.status_code == 201
    report = report_response.json()
    report_name = report["name"]

    meta_template = create_template(
        client,
        name="Report Meta Test",
        content=(
            "All: {{reports}}\n"
            f"Single: {{{{reports.{report_name}}}}}\n"
            f"Content: {{{{reports.{report_name}.content}}}}\n"
            f"NameField: {{{{reports.{report_name}.name}}}}\n"
            f"Created: {{{{reports.{report_name}.created_at}}}}\n"
            "Unknown: {{reports.nonexistent_report}}\n"
            f"BadField: {{{{reports.{report_name}.unknown_field}}}}"
        ),
    )

    compile_response = client.get(f"/api/templates/{meta_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]

    assert compiled.startswith("All: - **")
    assert f"**{report_name}**" in compiled

    single_line = [line for line in compiled.split("\n") if line.startswith("Single: ")][0]
    assert single_line.startswith(f"Single: **{report_name}**")
    assert "(" in single_line and "Z)" in single_line

    assert "Content: Name: Growth" in compiled

    assert f"NameField: {report_name}" in compiled

    created_line = [line for line in compiled.split("\n") if line.startswith("Created: ")][0]
    created_value = created_line.replace("Created: ", "")
    assert created_value.endswith("Z")
    assert "T" in created_value

    assert "[Unknown report: nonexistent_report]" in compiled
    assert "[Unknown report field: unknown_field]" in compiled


def test_report_placeholder_recompilation(client: TestClient) -> None:
    source_template = create_template(
        client,
        name="Recomp Source",
        content="Original: {{inputs.name}}",
    )
    report = client.post(
        f"/api/reports/compile/{source_template['id']}",
        json={"inputs": {"name": "Recomp"}},
    ).json()
    report_name = report["name"]

    client.patch(
        f"/api/reports/{report['slug']}",
        json={"content": "Name: {{inputs.name}}\nTicker: {{inputs.ticker}}"},
    )

    embed_template = create_template(
        client,
        name="Embed Test",
        content=f"{{{{reports.{report_name}.content}}}}",
    )
    compile_response = client.get(f"/api/templates/{embed_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]

    assert "Name: [Missing input: name]" in compiled
    assert "Ticker: [Missing input: ticker]" in compiled


def test_report_placeholder_cycle_detection_self_reference(
    client: TestClient,
) -> None:
    source_template = create_template(client, name="Self Ref", content="# Self")
    report = client.post(f"/api/reports/compile/{source_template['id']}").json()
    report_name = report["name"]

    client.patch(
        f"/api/reports/{report['slug']}",
        json={"content": f"{{{{reports.{report_name}.content}}}}"},
    )

    embed_template = create_template(
        client,
        name="Self Ref Embed",
        content=f"{{{{reports.{report_name}.content}}}}",
    )
    compile_response = client.get(f"/api/templates/{embed_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]
    assert f"[Circular report reference: {report_name}]" in compiled


def test_report_placeholder_cycle_detection_indirect(
    client: TestClient,
) -> None:
    tmpl_a = create_template(client, name="Cycle A", content="# A")
    tmpl_b = create_template(client, name="Cycle B", content="# B")
    report_a = client.post(f"/api/reports/compile/{tmpl_a['id']}").json()
    report_b = client.post(f"/api/reports/compile/{tmpl_b['id']}").json()
    name_a = report_a["name"]
    name_b = report_b["name"]

    client.patch(
        f"/api/reports/{report_a['slug']}",
        json={"content": f"A includes B: {{{{reports.{name_b}.content}}}}"},
    )
    client.patch(
        f"/api/reports/{report_b['slug']}",
        json={"content": f"B includes A: {{{{reports.{name_a}.content}}}}"},
    )

    embed_template = create_template(
        client,
        name="Indirect Cycle",
        content=f"{{{{reports.{name_a}.content}}}}",
    )
    compile_response = client.get(f"/api/templates/{embed_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]
    assert (
        f"[Circular report reference: {name_a}]" in compiled
        or f"[Circular report reference: {name_b}]" in compiled
    )


def test_placeholder_tree_includes_reports(client: TestClient) -> None:
    source_template = create_template(client, name="Tree Test", content="# Tree")
    report = client.post(f"/api/reports/compile/{source_template['id']}").json()

    tree_response = client.get("/api/templates/placeholders")
    assert tree_response.status_code == 200
    tree = tree_response.json()

    assert "reports" in tree
    report_names = [r["name"] for r in tree["reports"]]
    assert report["name"] in report_names
    assert "createdAt" in tree["reports"][0]


def test_report_placeholder_dynamic_selectors(client: TestClient) -> None:
    source_template = create_template(client, name="Latest Report", content="Compiled AAPL")
    compiled_aapl = client.post(
        f"/api/reports/compile/{source_template['id']}",
        json={
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                },
            }
        },
    ).json()

    external_aapl = client.post(
        "/api/reports",
        json={
            "name": "AAPL Dynamic Latest",
            "content": "Dynamic AAPL: {{inputs.ticker}}",
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                },
            },
        },
    ).json()

    external_msft = client.post(
        "/api/reports",
        json={
            "name": "MSFT Dynamic Latest",
            "content": "MSFT body",
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "MSFT",
                    "reviewType": "weekly_review",
                },
            },
        },
    ).json()

    selector_template = create_template(
        client,
        name="Dynamic Selector Test",
        content=(
            "LatestMeta: {{reports.latest}}\n"
            "LatestName: {{reports.latest.name}}\n"
            'TickerLatestName: {{reports.latest("AAPL").name}}\n'
            'TickerLatestContent: {{reports.latest("AAPL").content}}\n'
            "IndexZeroName: {{reports[0].name}}\n"
            'TagLatestName: {{reports.by_tag("weekly_review").latest.name}}\n'
            'TagLatestContent: {{reports.by_tag("weekly_review").latest.content}}\n'
            'NoMatchInline: before{{reports.latest("NVDA").name}}after\n'
            "NoMatchIndex: before{{reports[99].content}}after\n"
            'InvalidSelector: {{reports.by_tag("weekly_review")}}\n'
            f"ExactNameReportName: {{{{reports.{compiled_aapl['name']}.name}}}}"
        ),
    )

    compile_response = client.get(f"/api/templates/{selector_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]

    latest_meta_line = [line for line in compiled.split("\n") if line.startswith("LatestMeta: ")][0]
    assert latest_meta_line.startswith(f"LatestMeta: **{external_msft['name']}**")
    assert f"LatestName: {external_msft['name']}" in compiled
    assert f"TickerLatestName: {external_aapl['name']}" in compiled
    assert "TickerLatestContent: Dynamic AAPL: [Missing input: ticker]" in compiled
    assert f"IndexZeroName: {external_msft['name']}" in compiled
    assert f"TagLatestName: {external_msft['name']}" in compiled
    assert "TagLatestContent: MSFT body" in compiled
    assert "NoMatchInline: beforeafter" in compiled
    assert "NoMatchIndex: beforeafter" in compiled
    assert 'InvalidSelector: [Invalid report selector: reports.by_tag("weekly_review")]' in compiled
    assert f"ExactNameReportName: {compiled_aapl['name']}" in compiled


def test_report_placeholder_dynamic_selector_cycle_detection(
    client: TestClient,
) -> None:
    source_template = create_template(client, name="Cycle Selector", content="# Start")
    report = client.post(
        f"/api/reports/compile/{source_template['id']}",
        json={
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                },
            }
        },
    ).json()

    client.patch(
        f"/api/reports/{report['slug']}",
        json={"content": '{{reports.latest("AAPL").content}}'},
    )

    embed_template = create_template(
        client,
        name="Dynamic Cycle Embed",
        content='{{reports.latest("AAPL").content}}',
    )
    compile_response = client.get(f"/api/templates/{embed_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]
    assert f"[Circular report reference: {report['name']}]" in compiled


def test_report_filters_and_dynamic_selectors_ignore_reports_without_analysis_metadata(
    client: TestClient,
) -> None:
    client.post(
        "/api/reports/upload",
        files={
            "file": (
                "Uploaded Note.md",
                b"# Uploaded Note\n\nLegacy body.",
                "text/markdown",
            )
        },
        data={"slug": "uploaded_note"},
    ).json()

    external = client.post(
        "/api/reports",
        json={
            "name": "AAPL Metadata Report",
            "content": "AAPL body",
            "metadata": {
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                }
            },
        },
    ).json()

    filtered = client.get("/api/reports", params={"ticker": "AAPL"})
    assert filtered.status_code == 200
    assert [report["id"] for report in filtered.json()] == [external["id"]]

    selector_template = create_template(
        client,
        name="Missing Analysis Selector",
        content=(
            'TickerLatest: {{reports.latest("AAPL").name}}\n'
            'NoTickerMatch: before{{reports.latest("MSFT").content}}after'
        ),
    )

    compile_response = client.get(f"/api/templates/{selector_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]

    assert compiled == f"TickerLatest: {external['name']}\nNoTickerMatch: beforeafter"


@pytest.mark.parametrize(
    "metadata",
    [
        {"customBlock": {"apiKey": "private-metadata-sentinel"}},
        {"analysis": {"customKey": "private-metadata-sentinel"}},
        {"createdBy": {"type": "agent", "runId": "private-metadata-sentinel"}},
        {"created_by": {"type": "agent", "runId": "private-metadata-sentinel"}},
    ],
)
def test_report_write_metadata_is_closed_and_errors_do_not_echo_input(
    client: TestClient,
    metadata: dict[str, object],
) -> None:
    template = create_template(client, name="Closed metadata", content="# Report")
    for path, body in [
        (
            "/api/reports",
            {"name": "Attempt", "content": "Report", "metadata": metadata},
        ),
        (f"/api/reports/compile/{template['id']}", {"metadata": metadata}),
    ]:
        response = client.post(path, json=body)
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"
        assert set(response.json()) == {"code", "message", "details"}
        assert "private-metadata-sentinel" not in response.text
    assert client.get("/api/reports").json() == []
