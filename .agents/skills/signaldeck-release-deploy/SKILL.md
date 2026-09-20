---
name: signaldeck-release-deploy
description: Release, package and deploy SignalDeck through release.sh, release-commit CI, tag-built immutable GHCR images, a verified backup and a gated Compose rollout with schema, health, version, row-count, smoke, persistent-pin and observation checks. Use only for explicitly authorized SignalDeck release or deployment work; use signaldeck-ops-inspect for diagnosis-only requests.
metadata:
  short-description: Release and deploy SignalDeck with staged gates
---

# SignalDeck Release Deploy

## Outcome

Carry accepted source on `main` through `release.sh`, the release commit's CI, the tag's image workflow and an immutable release manifest, then roll the application image out to one Compose project. Complete only after backup, schema, health/version, container identity, row-count, read-only smoke, persistent pin and observation gates pass. Plugin upgrades and backup pruning are separately authorized operations.

Script paths below are relative to this skill. Run them from the repository root as `python3 .agents/skills/signaldeck-release-deploy/scripts/<script>.py`: `signaldeck_release.py --repo-root` defaults to the current directory and receives the release manifest, and `signaldeck_rollout.py` writes its evidence under the current directory unless `--evidence` is given; only the repository root's `artifacts/` is ignored by Git.

## Authorization

- `plan` subcommands are read-only.
- Release execution requires current release/tag/push authorization plus `--confirm-release vX.Y.Z`.
- Rollout requires current deployment authorization plus `--confirm-rollout <tag>@<release-sha-prefix>`. Pruning additionally requires `--confirm-prune <project>:keep-3`.
- Confirmation flags record authorization but never create it. A current request may authorize release and deployment together, including the verified backup; continue across covered stages without asking again. Past tasks are evidence, not authorization.

## Preparation

1. Read `STATUS.md`, `CONTRIBUTING.md` and the affected guides. Preserve unrelated local work. Merge, commit and push only within the current authorization, and reach a clean `main` identical to `origin/main`.
2. Confirm the latest `main` CI is green before releasing: the tag's image workflow refuses to publish when the release commit's CI is not green, and a red `main` usually stays red.
3. Run `$signaldeck-ops-inspect` for preflight: current image and version, health, pins, databases, counts, backup capacity and drift.

## Release stage

1. Run `python3 scripts/signaldeck_release.py plan --spec <patch|minor|major|X.Y.Z>`.
2. Read [references/release-manifest.md](references/release-manifest.md).
3. Run `python3 scripts/signaldeck_release.py execute --spec <spec> --confirm-release <tag>` once. It runs `release.sh`, waits for the release commit's CI and the tag's `Docker Images` workflow (up to `--timeout-seconds`, default 3600), verifies the published image on the host, and writes the manifest under ignored `artifacts/evidence/signaldeck-ops/releases/`.
4. If the tag and images were published but writing the manifest failed, use `recover --spec X.Y.Z --confirm-release vX.Y.Z`; it validates only and never re-tags, pushes or rebuilds.

## Rollout stage

1. Run `python3 scripts/signaldeck_rollout.py plan --manifest <published.json>`.
2. Read [references/rollout-gates.md](references/rollout-gates.md); for `capy`, also read [../signaldeck-ops-inspect/references/capy.md](../signaldeck-ops-inspect/references/capy.md).
3. Run `execute` with the printed token. Default observation is 300 seconds. The rollout replaces only the application image; when the plugin comparison reports a changed plugin, follow [references/plugin-upgrade.md](references/plugin-upgrade.md) as a separate, explicitly authorized step.
4. On failure, report the failed stage and the recorded rollback command ([failure behavior](references/rollout-gates.md#failure-behavior)). Do not roll back or restore without an explicit decision.

## Completion

- Never create a GitHub Release, rerun failed workflows, force-push, deploy `latest`, run `deploy.sh restart` or `deploy.sh force` ([pitfalls](../signaldeck-ops-inspect/references/capy.md#deploysh-pitfalls)) or `docker compose down -v`, or upgrade plugins inside an application rollout.
- Replace the previous deployment paragraph in `STATUS.md` (`## 部署与使用`) with the observed identity: release tag, immutable application image and how it is pinned, the running plugin builds, pending plugin upgrades and the verification time. Gate results and backup IDs stay in the rollout evidence. Commit or push that change only when covered by the current authorization.
- When the deployment repository documents the running release (for example `signaldeck/README.md` on `capy`), update that document within its own repository rules.
- Lead the handoff with tag and release SHA, CI and image evidence, the immutable image, backup identity, gate results, plugin comparison, stopped or unverified states and required operator actions.
