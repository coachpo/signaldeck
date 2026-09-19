---
name: signaldeck-ops-inspect
description: Inspect the SignalDeck repository and self-hosted Compose deployment read-only, including release/CI identity, version surfaces, container and image identity, health and version, pinned image drift, PostgreSQL databases and row counts, volumes, backup inventory and capacity. Use for SignalDeck operations reconnaissance, rollout preflight, audits or status reports; do not mutate, deploy, back up, restore or prune.
metadata:
  short-description: Inspect SignalDeck operational state safely
---

# SignalDeck Ops Inspect

## Outcome

Produce a timestamped, secret-safe snapshot and a concise report of current facts, drift, limitations and the next safe action. This skill never mutates the repository or the deployment.

## Inspect

1. Resolve the repository root and read the root `AGENTS.md`, `STATUS.md`, `release.sh` and `docker/deployment.md`.
2. Read [references/evidence-contract.md](references/evidence-contract.md). Read [references/capy.md](references/capy.md) for work on `capy` or the `signaldeck` Compose project there.
3. Run `python3 scripts/signaldeck_ops_snapshot.py --check` with the requested `--host` and `--project`. Use stdout by default; use `--output` only when retained evidence was requested, under ignored `artifacts/evidence/signaldeck-ops/`.
4. Treat discovered Compose labels, mounts, image identity, health, databases and counts as observation-time truth. Treat adapter values as assertions to verify.

## Autonomy

- Read-only files, Git, GitHub runs, SSH inventory, Docker/Compose inspection, health requests and read-only SQL are in scope without further confirmation.
- Do not release, deploy, pull, back up, restore, prune, restart or edit deployment files. Route authorized changes to `$signaldeck-release-deploy` or `$signaldeck-backup-restore`.
- Report configuration and credentials only as presence, path, mode, size or hash. Never expose `backend.env` lines other than the version, profile and plugin selections, database URLs, keys or provider payloads.

## Completion

- If `--check` fails or sources conflict, stop at diagnosis and name the exact drift and the smallest missing evidence.
- Lead with the operational conclusion, then supporting identities and counts, material caveats, unverified scope and the next safe action. Omit raw command noise.
