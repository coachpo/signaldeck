# Release manifest

## Release flow

`release.sh`, its six version surfaces and the tag-triggered, CI-gated image workflow are described in [CONTRIBUTING.md](../../../../CONTRIBUTING.md#发布); image names and tags in [docker/deployment.md](../../../../docker/deployment.md#发布与镜像版本). Do not push `main` while a release is in flight: the CI concurrency group cancels the release commit's CI, and the image workflow then refuses to publish.

## Acceptance and source identity

Record the accepted source SHA and its test evidence before releasing. The release commit must differ from it only in the six version surfaces; otherwise validate the extra changes before treating the earlier acceptance as release evidence.

## Published artifact

`signaldeck_release.py execute` writes schema version 1 JSON only after publishing succeeds. It records the release (`version`, `tag`, full `release_sha`, commit subject and the six aligned version surfaces), the `CI` and `Docker Images` runs bound to the release SHA on `main` and to the tag, and for `app`, `finance`, `notes` and `digital-oracle` the immutable `ref` (`repository:tag@sha256:digest`) with its manifest digest and media type, platform and OCI revision and version.

Each image must be a single-platform manifest whose OCI revision is the release SHA, whose OCI version is the release version, and whose platform matches the deployment host. The script uses `GITHUB_TOKEN` only when already set, never prints it, and otherwise uses the public API. A failure writes no manifest; if `release.sh` leaves a partial state, stop and report it instead of reverting or tagging again.

`recover --spec X.Y.Z --confirm-release vX.Y.Z` rebuilds the same manifest from existing facts only: clean, current `main`, identical local and remote tags, the tag commit in `main` history, aligned surfaces, green release workflows and matching image identity. Apart from fetching `origin/main` and tags, it never changes Git or the registry, and it refuses to overwrite a manifest.
