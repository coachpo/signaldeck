---
name: signaldeck-backup-restore
description: Create, validate, inventory, retain and restore-test SignalDeck backups of the PostgreSQL databases, persistent volumes and private deployment configuration, with quiesced snapshots, checksum manifests, strict keep-three pruning and a disposable restore drill. Use for SignalDeck backup, rollback preparation, restore or disaster-recovery work; execution always needs current explicit authorization.
metadata:
  short-description: Back up and restore-test SignalDeck with safe gates
---

# SignalDeck Backup Restore

## Outcome

Produce a verified, secret-safe backup of one SignalDeck Compose project; prove a backup restores in a disposable container; or enforce keep-three retention when separately authorized. Live data is never overwritten by these scripts.

The scripts support only the deployment-repository layout: one Compose file at `<deploy root>/<stack>/compose.yml` with `backend.env` and `plugin-defaults.json` beside it, and backups under `<deploy root>/backups/` unless `--backup-root` names another absolute path. A stack whose env file is `.env`, or a host run from `docker/compose.production.yml` with `~/.config/signaldeck/production.env`, is outside this layout; a backup there would omit the env file and its encryption key.

Script paths below are relative to this skill; run them from the repository root as `python3 .agents/skills/signaldeck-backup-restore/scripts/<script>.py`.

## Authorization

- `plan` subcommands are read-only.
- Backup execution requires current authorization plus `--confirm-backup <project>`.
- The restore drill requires `--confirm-drill <manifest-sha-prefix>`; it only creates and removes its own networkless containers.
- Pruning requires `--confirm-prune <project>:keep-3`. Switching a live instance to a backup is a separate destructive scope described in [references/restore.md](references/restore.md).
- A current deployment request covers its necessary verified backup; do not ask again for that step. Deployment or backup authorization does not authorize pruning or a live restore, and past authorization does not carry into a new task.

## Backup

1. Run `python3 scripts/signaldeck_backup.py plan --host <host> --project <project>`.
2. Prefer `quiesced` for upgrade and rollback points. `online` is allowed only when the caller accepts that writes after the dump are outside the restore point.
3. Read [references/backup-manifest.md](references/backup-manifest.md), then run `execute` with `--confirm-backup`. A valid backup writes its manifest last. A quiesced backup leaves `app`, `dispatcher`, `worker` and `temporal` stopped for the caller's cutover unless `--restart-on-success` is given; on failure it restarts them.
4. If backup or the restart fails, report both failures and the final observed service state.

## Restore drill

Run `python3 scripts/signaldeck_restore_check.py plan --manifest <remote manifest.json>`, then `execute` with the printed `--confirm-drill` token. It restores every dump into a throwaway container of the same PostgreSQL image, compares row counts with a quiesced manifest and lists every volume archive.

## Retention

Use `python3 scripts/signaldeck_prune_backups.py` with [references/retention.md](references/retention.md). Keep the newest three complete, byte-verified managed backups; incomplete, unmanaged, malformed and symlinked paths are never deleted. Without explicit prune authorization, report retention as `not_requested`.

For `capy`, read [../signaldeck-ops-inspect/references/capy.md](../signaldeck-ops-inspect/references/capy.md).

## Completion

- Report configuration and credential evidence only as the [secret rule](../signaldeck-ops-inspect/SKILL.md#autonomy) allows; never print `backend.env`.
- Lead with the outcome, then manifest and backup identity, verification results, retained or deleted paths, the state of the stack, failures, limitations and the next required action.
