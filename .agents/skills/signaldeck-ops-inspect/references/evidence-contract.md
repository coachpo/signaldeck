# Evidence contract

## Snapshot fields

The snapshot is one JSON object with `schema_version: 1`, `observed_at` and `host`; `repository` (Git identity, the six release version surfaces and, when reachable, the GitHub workflow runs for HEAD); `deployment` (`null` when unavailable, otherwise the discovered topology, per-service container and image identity, `/health` and `/ready`, the env pins and the application image they select, databases, row counts, volumes, the backup inventory with each entry `verified` or `unmanaged_or_incomplete`, free backup capacity and the deployment repository state); `checks`; and `limitations`. `--output` writes the same JSON atomically and prints only `{output, checks}`.

The scripts enforce the [secret rule](../SKILL.md#autonomy): remote output containing secret-looking words is rejected, and command errors come back as redacted tails.

## Check semantics

`--check` exits 1 when the repository version surfaces disagree, the deployment snapshot is unavailable, `app`, `db` or `temporal` is not healthy, `dispatcher` or `worker` is not running, the application roles run different images, the env file pins a different application image than the one running, `/ready` fails, or any container is restarting or exited non-zero. Discovery errors (missing project or ambiguous required container) surface as an unavailable snapshot.
