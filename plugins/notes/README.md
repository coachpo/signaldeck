# Notes workspace

Notes serves a read-only workspace at `/` beside its immutable MCP `create` and `search` tools. The page is plain HTML, CSS and JavaScript shipped inside the plugin artifact; page URL settings are in [the plugin guide](../README.md#build-and-run). Inside the platform, the page and its API are reached through the [plugin gateway](../../docs/writing-extensions.md#统一插件页面). The page can browse every Notes collection, while MCP resource grants still limit each Agent invocation to its bound collection. The provenance and retrieval contract of the MCP tools is in [writing-extensions.md](../../docs/writing-extensions.md#notes-来源与检索合同).

## HTTP contract

- `GET /api/collections` returns `{collections: [{name, count}]}`, ordered by collection name.
- `GET /api/notes?collection=research&query=text&includeDerived=false&limit=20&after=...` returns `{notes: [{id, collection, title, text, sourceKind, sourceNoteIds}], nextCursor}`. Collection is required; query is a case-insensitive literal substring of title or text, with `%`, `_` and backslash taken literally. `includeDerived` defaults to true; false excludes only explicitly derived notes. Limit is 1–50 (default 20). The optional cursor is the previous response's `nextCursor`; null means the end. Records are ordered by immutable ID with strict `id > after` keyset pagination, so records inserted before the cursor appear only on a new first-page search; pagination is not a snapshot or chronological ordering.
- `GET /api/note?id=...` returns one full note or a safe 404 error. IDs and collection names are at most 200 characters. IDs travel in URL query parameters, including slashes, `?`, `#`, Unicode and long operation identities; use ordinary URL parameter encoding, not path interpolation.

Reads do not create operations or modify notes. Errors use `{code, message, details: []}`. There are no HTTP edit, delete or secondary write endpoints.

The page keeps the collection, literal query, derived-content filter and cursor chain in its URL, and detail uses `noteId`, so refresh, direct links, browser navigation and return-to-list keep their context. It lists original and unclassified notes by default; the “包含整理结果” selector includes derived notes. Detail shows each note's classification and links its sources by note title. A derived note without references says its evidence must be checked in the body; an unavailable source leaves the main note readable, states that the source cannot be checked yet and offers a retry link. Bodies render as unchanged plain text and can be copied.

`example/notes/create` declares the result link `note`, which binds `tool.output.id` to the `noteId` query parameter, so a workflow result opens the saved note.

## Validation

From `backend`, run `uv run pytest tests/test_notes_workspace.py tests/test_notes_browser.py tests/test_independent_plugins.py tests/test_result_declarations.py -q`. The tests use isolated PostgreSQL databases and real MCP transport. The browser test needs the installed frontend dependencies and Playwright Chromium; it builds the shared plugin UI before starting Notes and writes screenshots to a Git-ignored directory.
