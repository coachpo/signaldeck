# Release manifest

## Release flow

`release.sh` owns six version surfaces: `VERSION`, `backend/VERSION`, `backend/pyproject.toml`, the project entry in `backend/uv.lock`, `frontend/VERSION` and `frontend/package.json`. Plugin versions stay independent. It requires a clean `main` that contains `origin/main`, a forward version and an unused tag; verifies the lockfile, the `/health` version test and the frontend build; then commits `chore: bump version to X.Y.Z`, tags `vX.Y.Z` and pushes `main` and the tag.

The tag triggers `.github/workflows/docker-images.yml`. Its `verify-ci` job waits for the `CI` workflow on the tagged commit and refuses to publish unless it concludes `success`. It then builds four `linux/arm64` single-manifest images on native ARM runners without provenance or SBOM attestations: `signaldeck`, `signaldeck-finance`, `signaldeck-notes` and `signaldeck-digital-oracle`, tagged `vX.Y.Z`, `X.Y.Z`, `X.Y`, `sha-<full SHA>` and `latest`. Manual runs publish only `manual-<sha>` tags and never move `latest`. A later push to `main` cancels the release commit's CI through the CI concurrency group, so do not push while a release is in flight.

## Acceptance and source identity

Record the accepted source SHA and its test evidence before releasing. The release commit must differ from it only in the six version surfaces; otherwise validate the extra changes before treating the earlier acceptance as release evidence.

## Published artifact

`signaldeck_release.py execute` writes schema version 1 JSON only after publishing succeeds:

- `status: published`, `created_at`, `repository`, `release_spec`, `version`, `tag`, full `release_sha`, commit subject and the six aligned version surfaces;
- the `CI` and `Docker Images` workflow IDs, URLs, status and conclusion, bound to the release SHA on `main` and to the tag;
- `images.<service>` for `app`, `finance`, `notes` and `digital-oracle`: repository, immutable `ref` (`repository:tag@sha256:digest`), manifest digest and media type, OS, architecture, OCI revision and version.

Each image must be a single-platform manifest whose OCI revision is the release SHA, whose OCI version is the release version, and whose platform matches the deployment host. The script uses `GITHUB_TOKEN` only when already set, never prints it, and otherwise uses the public API. A failure writes no manifest; if `release.sh` leaves a partial state, stop and report it instead of reverting or tagging again.

`recover --spec X.Y.Z --confirm-release vX.Y.Z` rebuilds the same manifest from existing facts only: clean, current `main`, identical local and remote tags, the tag commit in `main` history, aligned surfaces, green release workflows and matching image identity. It never mutates Git or the registry and refuses to overwrite a manifest.
