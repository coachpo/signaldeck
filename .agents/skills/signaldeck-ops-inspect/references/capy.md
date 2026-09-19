# capy adapter

Use this adapter only when the deployment host is `capy` or the request names its `signaldeck` Compose project.

## Expected topology

- SSH alias `capy` (arm64). Commands typed by an agent must start with `ssh capy` to match the local permission rule; the scripts call `ssh -o BatchMode=yes capy` themselves.
- The deployment repository `coachpo/curse` has lived at `/home/ubuntu/orange_work/curse`, with the canonical `deploy.sh`, the `signaldeck/` stack and its own `AGENTS.md` files. Discover the Compose config file, env file, services and volumes before using any path.
- Compose project `signaldeck`: the application image runs as `app`, `dispatcher`, `worker` and the one-shot `plugin-mounts` and `bootstrap`; `db` (PostgreSQL with the Core, Finance, Notes and two Temporal databases), `temporal` and its one-shot initializers; independently pinned plugin services, including historical services under the `legacy-plugins` profile.
- `signaldeck/backend.env` is private (mode 0600, ignored by Git). Its `SIGNALDECK_VERSION` pins the application image for any plain Compose invocation; `deploy.sh start signaldeck --version X` overrides it for that run only, and without `--version` it deploys `latest`.
- The app is published on the LAN at port 8089 over plain HTTP. `/ready` checks Nginx, API and PostgreSQL; `/health` reports the release version from 0.2.0 onward.
- Backups belong under `/home/ubuntu/orange_work/curse/backups/signaldeck/`, next to the Prism backups of the same repository.

Do not encode the current version, digests, container IDs, row counts, backup timestamps or plugin service names here; discover them.
