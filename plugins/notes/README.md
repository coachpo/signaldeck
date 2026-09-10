# Notes workspace

Notes 1.2.0 serves a read-only workspace at `/`, alongside its existing immutable MCP create/search tools. The page is plain HTML, CSS and JavaScript shipped inside the plugin artifact. Set `PLUGIN_PAGE_URL` to its browser-reachable base URL (default `http://localhost:8093/`), independently of `PLUGIN_ENDPOINT` for MCP. Deploy it behind the same trusted-network or authenticated proxy boundary as the other business plugins. The operator page can browse all Notes collections; MCP resource grants still limit each Agent invocation to its bound collection.

## HTTP contract

- `GET /api/collections` returns `{collections: [{name, count}]}`, ordered by collection name.
- `GET /api/notes?collection=research&query=text&limit=20&after=...` returns `{notes: [{id, collection, title, text, sourceKind, sourceNoteIds}], nextCursor}`. Collection is required; query is a case-insensitive literal substring of title or text. `%`, `_` and backslash are literal. Limit is 1–50 (default 20). The optional cursor is the previous response's `nextCursor`; null means the end. Records are ordered by immutable ID, with strict `id > after` keyset pagination. Newly inserted records before the cursor are visible on a new first-page search; pagination is not a snapshot or chronological ordering.
- `GET /api/note?id=...` returns one full note or a safe 404 error. IDs and collection names are at most 200 characters. IDs travel in URL query parameters, including slashes, `?`, `#`, Unicode and long operation identities; use ordinary URL parameter encoding, not path interpolation.

Reads do not create operations or modify notes. Errors use `{code, message, details: []}`. There are no HTTP edit/delete or secondary write endpoints.

The workspace keeps collection, literal query and the cursor chain in its URL; detail uses `noteId`, so refresh, direct links, browser navigation and return-to-list preserve context. Content is rendered as text and can be copied. Unknown IDs and unavailable reads have explicit messages.

## Frozen result links

The `example/notes/create` descriptor declares `signaldeck.resultLink/1`, key `note`, empty relative path, and query `{noteId: tool.output.id}`. Both bundled Notes workflows select that declaration from `nodes.save.output`. Core resolves confirmed output against the Run's frozen plugin release; it does not infer Notes routes. Old releases without a link retain generic content. Keep their original artifact and endpoint when upgrading; do not overwrite a release serving frozen Runs.

## Validation

From `backend`, run `uv run pytest tests/test_notes_workspace.py tests/test_independent_plugins.py tests/test_result_declarations.py -q`. Tests use isolated PostgreSQL and real MCP transport, covering literal search, collection isolation, pagination, 200-character identity limits, read-only behavior and frozen projections. Browser evidence and the joint acceptance boundary are recorded in [PU-S6 verification](../../docs/planning/personal-use-s6-verification.md).

## Provenance and retrieval

The closed 1.2.0 create contract accepts optional `sourceKind` (`original` or `derived`) and `sourceNoteIds` (unique IDs, at most 50). Omitting classification records `unclassified`, never inferred from titles or body. Only derived notes may cite source notes. Each reference must resolve to an existing immutable note in the invocation's granted collection; invalid, missing, duplicate or cross-collection references reject the entire write. Confirmation means this authoritative resolution, not a claim that a model read or verified the source's assertions. The research package passes the exact IDs returned by its search node, without asking the model to manufacture references.

Notes, the `note_provenance` sidecar (`note_id`, `source_kind`, `source_ids`) and the operation receipt commit in the same journal transaction. Startup creates the new table but never alters or backfills existing `notes`. Historical rows without sidecars remain visible as `unclassified`, and their bodies and operation receipts remain unchanged. Existing deployments require a separately published immutable artifact/endpoint; do not replace artifacts serving frozen runs or convert original instance data as part of this change.

MCP search returns both `notes` and `sourceNoteIds` identifying exactly those returned notes. Optional `includeDerived` defaults to true for generic callers. False excludes only explicit `derived` rows and retains original and historical unclassified notes. The read-only HTTP list accepts the same filter. The Notes page defaults to original/unclassified and offers an explicit “包含派生内容” selector, displays classification and provides source links in detail.

The revised research workflow explicitly defaults `includeDerived` to false, saves derived results with search references, preserves conflicting original claims, and never makes its saved summaries new default search inputs. Capture marks new material original. Users may explicitly include derived material. Every new run searches current records, so new originals remain discoverable; the query and 20-record limit still bound the selected result set. This is explicit package data, not platform memory or title-based filtering.
