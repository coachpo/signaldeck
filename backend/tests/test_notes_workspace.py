"""Notes reads preserve immutable records and use literal, collection-scoped cursors."""

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.test_independent_plugins import descriptor, invocation, notes_app


def test_notes_workspace_literal_search_pagination_and_encoded_identity(database_url):
    app = notes_app(database_url)
    create = "example/notes/create"
    special = " /?#&+%_中文" + "x" * 180
    with TestClient(app) as client:
        for index in range(45):
            app.state.execute(
                create,
                {"title": f"Note {index}", "text": "literal %_\\ content"},
                invocation(create, f"note-{index:03}"),
            )
        context = invocation(create, special)
        context["resourceBindings"]["notes-workspace"]["collection"] = "separate"
        saved = app.state.execute(
            create,
            {"title": "Special identity", "text": "<script>not executable</script>"},
            context,
        )
        with app.state.engine.connect() as connection:
            before = connection.execute(text("SELECT count(*) FROM plugin_operations")).scalar()
        assert client.get("/api/collections").json() == {
            "collections": [
                {"name": "research", "count": 45},
                {"name": "separate", "count": 1},
            ]
        }
        ids = []
        after = None
        while True:
            params = {"collection": "research", "query": "%_\\", "limit": 20}
            if after is not None:
                params["after"] = after
            response = client.get("/api/notes", params=params)
            assert response.status_code == 200
            data = response.json()
            ids.extend(note["id"] for note in data["notes"])
            after = data["nextCursor"]
            if after is None:
                break
        assert ids == [f"note-{index:03}" for index in range(45)]
        assert (
            client.get("/api/notes", params={"collection": "separate", "query": "%"}).json()[
                "notes"
            ]
            == []
        )
        assert client.get("/api/note", params={"id": special}).json() == saved
        assert client.get("/api/note", params={"id": "unknown"}).status_code == 404
        assert (
            client.get("/api/notes", params={"collection": "research", "limit": 51}).status_code
            == 422
        )
        assert client.get("/").status_code == 200
        assert client.get("/assets/app.js").status_code == 200
        assert client.delete("/api/note", params={"id": special}).status_code == 405
        with app.state.engine.connect() as connection:
            assert connection.execute(text("SELECT count(*) FROM notes")).scalar() == 46
            assert (
                connection.execute(text("SELECT count(*) FROM plugin_operations")).scalar()
                == before
            )
    app.state.engine.dispose()


def test_notes_link_is_frozen_and_old_release_has_no_implicit_link(database_url):
    from copy import deepcopy

    from app.application.result_projection import project_result
    from app.domain.tool_contracts import PluginRelease, tool_contract_digest
    from tests.test_result_declarations import evidence, run_fixture

    app = notes_app(database_url)
    binding = descriptor(app)
    release = PluginRelease.model_validate(binding)
    run = run_fixture()
    sections = run.spec.definition["workflows"]["main"]["presentation"]["sections"]
    sections[1].update(toolId="example/notes/create", linkKey="note")
    unusual = " /?#&+%_中文" + "x" * 180
    run.spec.plugin_releases = [deepcopy(binding)]
    run.evidence = [
        evidence("node", {"text": "Saved body"}),
        evidence(
            "tool",
            {
                "id": unusual,
                "text": "Saved body",
                "collection": "research",
                "title": "Saved",
            },
            tool_id="example/notes/create",
            operation_id=unusual,
        ),
    ]
    link = project_result(run).sections[1]
    assert parse_qs(urlparse(link.href).query) == {"noteId": [unusual]}
    # A catalog upgrade cannot mutate a run's release snapshot.
    binding["pageUrl"] = "https://unrelated.invalid/"
    assert project_result(run).sections[1].href == link.href
    legacy_tools = tuple(tool.model_copy(update={"result_links": ()}) for tool in release.tools)
    legacy = release.model_copy(
        update={
            "tools": legacy_tools,
            "page_url": None,
            "contract_digest": tool_contract_digest(legacy_tools),
        }
    )
    old_run = run.model_copy(deep=True)
    old_run.spec.plugin_releases = [legacy.model_dump(mode="json", by_alias=True)]
    assert all(section.kind != "link" for section in project_result(old_run).sections)
    assert project_result(old_run).sections[0].value == "Saved body"
    assert project_result(run).sections[0].value == "Saved body"
    app.state.engine.dispose()
