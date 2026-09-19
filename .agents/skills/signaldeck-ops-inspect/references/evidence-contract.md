# Evidence contract

## Snapshot fields

The JSON snapshot uses `schema_version: 1` and contains:

- `observed_at`, `host`, and `repository`: root, HEAD, branch, cleanliness, GitHub slug, tags at HEAD, latest `v*` tag, the six release version surfaces and the GitHub workflow runs for HEAD when reachable;
- `deployment`: discovered topology (config file, env file path, deploy name, application repository and roles, backup root, version variable); per service each container's state, health, restarts, exit code, configured and immutable image reference, OCI revision and version and published ports; `/health` and `/ready`; the pinned version, profile and plugin lines of the env file and the image they select; PostgreSQL version, databases with owners and sizes, exact row counts for the application databases; volume sizes; backup inventory; free backup capacity; and the deployment repository HEAD with dirty paths under the stack;
- `checks`: invariant failures; `limitations`: unavailable tools or evidence.

Default output is stdout. `--output` writes the same JSON atomically after the caller asked for retained evidence.

## Secret handling

- Never return container environment values, `backend.env` contents beyond the pinned version, profile and plugin lines, database URLs, encryption keys, credentials or provider payloads.
- Configuration and backup artifacts are represented by path, mode, size, timestamp and SHA-256 only.
- Remote output containing secret-looking words is rejected; command errors are returned as redacted tails.
- Do not dump `docker inspect` or `docker compose config` output wholesale; select named fields.

## Check semantics

`--check` exits 1 when the repository version surfaces disagree, the deployment snapshot is unavailable, `app`, `db` or `temporal` is not healthy, `dispatcher` or `worker` is not running, the application roles run different images, the env file pins a different application image than the one running, `/ready` fails, or any container is restarting or exited non-zero. Discovery errors (missing project or ambiguous required container) surface as an unavailable snapshot.
