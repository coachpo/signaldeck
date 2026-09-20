# Rollout gates

`signaldeck_rollout.py execute` runs these stages in order and stops at the first failure, except that the informational plugin comparison records its errors (`unavailable` for the whole stage, `unknown` for one plugin) and continues. Evidence for every stage, including failures, is written to `artifacts/evidence/signaldeck-ops/rollouts/<stamp>-<tag>.json` under the current directory (ignored by Git at the repository root) unless `--evidence` names another path.

1. **Revalidate images**: all four manifest images still resolve on the host to the recorded digest, single manifest, release revision and version, and the host architecture.
2. **Preflight** (read-only): discover the Compose project; `app`, `db` and `temporal` healthy, `dispatcher` and `worker` running; the application repository matches the manifest; record the running application image as the rollback target and the image of every non-application service.
3. **Schema compatibility** (read-only): pull the release image and run `python -m app.infrastructure.schema_compatibility` from it against the live Core database through `docker compose run --rm --no-deps`. `create_all` never alters existing tables, so any missing model column or unmapped required column stops the rollout before anything changes; tables the release adds are created on start.
4. **Plugin comparison** (informational): for each current plugin in `plugin-defaults.json`, pull the release image and describe that plugin role from it under the running service's environment, without network, then compare the result with the running release descriptor. `changed: true` means the release carries plugin changes that this rollout will not deploy, because the plugin services stay pinned to their own image reference.
5. **Quiesced backup** through `$signaldeck-backup-restore`; it leaves the writers stopped.
6. **Cutover**: `<deploy root>/deploy.sh start <stack> --version <tag>@sha256:<digest>`, the deployment repository's canonical entry. It pulls and runs `up -d`, which recreates only the application roles and restarts the quiesced services; volumes and pinned services stay.
7. **Post-deploy gates**: `/ready` passes and `/health` reports the release version; every application role runs the release reference, long-running roles are running and one-shot roles exited 0; every other service kept its image and state; no durable table lost rows compared with the quiesced backup (leases, rate state and the read cache are ephemeral); the live schema check reports every table `ok`; read-only API list endpoints and every registered plugin page mount return 200.
8. **Persistent pin**: set the stack's version variable (`SIGNALDECK_VERSION`) in its env file to `<tag>@sha256:<digest>`, preserving the file mode and every other line, then render `docker compose config` without an override and require every application role to resolve to the release reference. The quiesced backup holds the previous file.
9. **Observation**: for `--observe-seconds` (default 300) sample every 10 seconds that `app`, `dispatcher`, `worker`, `db` and `temporal` keep their containers, restart counts, health and release image, and that `/ready` and `/health` stay green.
10. **Retention**: `not_requested` unless `--confirm-prune <project>:keep-3` was given; then keep three, protecting the new backup.

## Failure behavior

- Image, preflight or schema failure: no host writes beyond pulling the release image.
- Backup failure: the backup script restarts the quiesced services and reports.
- Any failure from the cutover on: stop `app`, `dispatcher` and `worker`, keep PostgreSQL, Temporal, plugins and the backup, and record `rollback_command` (`deploy.sh start <stack> --version <previous immutable reference>`). Rolling back after tables were created is compatible because older code ignores new tables, but it still needs an explicit decision; restoring data follows the backup skill's restore procedure. An application image older than v0.2.4 does not move existing schedules to its own Core: they keep firing on the Core they were last written for until each is re-saved.
- Never retry deploys in a loop or relax a gate to finish a rollout.
