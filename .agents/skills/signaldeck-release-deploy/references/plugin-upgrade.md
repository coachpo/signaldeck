# Plugin upgrade

An application rollout never replaces a plugin. Runs and page mounts bind to a plugin endpoint and artifact digest, so a changed plugin is deployed as a new service beside the old one. Do this only when the plugin comparison reports `changed: true` and the current request explicitly authorizes the upgrade.

On `capy` the stack lives in the deployment repository's `signaldeck/` directory, which has its own `AGENTS.md`; read it first. Work from the release manifest's plugin reference (`ghcr.io/<owner>/signaldeck-<plugin>:vX.Y.Z@sha256:<digest>`) and the release SHA prefix for the service name.

1. Back up with `$signaldeck-backup-restore` (quiesced).
2. `compose.yml`: pin the superseded current service (for example `notes-84c3ec46`) to its literal image and move it to `profiles: ["legacy-plugins"]`; add `<plugin>-<release sha8>` with the plugin's profile, `${SIGNALDECK_<PLUGIN>_VERSION:-<tag>@sha256:<digest>}` and its own `PLUGIN_ENDPOINT`, copying the remaining fields.
3. `backend.env`: point `SIGNALDECK_<PLUGIN>_VERSION` at `<tag>@sha256:<digest>`, changing only that line and keeping mode 0600.
4. `plugin-defaults.json`: move the plugin's `descriptorUrl` and `uiUpstream` to the new service.
5. `README.md` of the stack: state the plugin's current release, as that repository requires.
6. Validate with `bash -n signaldeck/*.sh` and `docker compose --env-file signaldeck/backend.env -f signaldeck/compose.yml config --quiet`, then `./deploy.sh start signaldeck --version <current application version>`.
7. Refresh the catalog once: `docker compose --env-file signaldeck/backend.env -f signaldeck/compose.yml run --rm --no-deps -e SIGNALDECK_BOOTSTRAP_REFRESH=1 bootstrap`.
8. The app renders the plugin page map at start; when its image did not change, `docker compose … restart app` regenerates it. Wait for `/ready`.
9. Verify the new service runs the new image, the catalog points at the new artifact digest, every plugin page mount returns 200 and the old services still run. Commit the tracked stack files (never `backend.env`) in the deployment repository within its rules.
