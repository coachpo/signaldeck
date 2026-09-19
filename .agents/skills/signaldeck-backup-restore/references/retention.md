# Keep-three retention

Retention runs per Compose project, only after a new managed backup is verified. During a rollout, defer it until the rollout passes every gate.

An eligible directory must:

- be a direct, non-symlink child of the exact resolved `<backup root>/<project>` directory without `.incomplete`;
- contain regular `manifest.json` and `SHA256SUMS` files, with `schema_version: 1`, `status: verified` and the matching project;
- list exactly the dumps, listings, archives and configuration copies its manifest describes, each a regular file whose bytes match both the manifest and `SHA256SUMS`, plus a matching `preflight.json`;
- not be named by `--protect` or be among the newest three eligible backups.

`plan` lists candidates without deleting. `execute` requires the exact `<project>:keep-3` token, re-runs discovery immediately before deletion, refuses any drift and any path whose real parent is not the project backup root. Incomplete, unmanaged, malformed and symlinked paths stay visible in the inventory and are never deleted automatically.
