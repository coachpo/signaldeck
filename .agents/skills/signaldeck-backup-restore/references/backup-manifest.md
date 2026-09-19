# Backup manifest

A managed backup lives in `<deploy root>/backups/<project>/<UTC stamp>-managed/`. The directory is mode `0700` and every file `0600`. It stays unusable while `.incomplete` exists, and `manifest.json` is written atomically last.

## Scope

- Every non-template PostgreSQL database except `postgres` (Core, Finance, Notes and both Temporal databases): `db-<name>.dump` in the custom format and the successful `pg_restore --list` output `db-<name>.list`. The dumps carry no ownership or privileges (`--no-owner --no-acl`); the manifest records each database's owner role.
- Every project volume as `volume-<name>.tar.gz`, except the PostgreSQL data volume (covered by the dumps) and the uv cache (re-downloadable). Archives are listed back and their entry count recorded.
- `config-backend.env`, `config-compose.yml` and `config-plugin-defaults.json`: exact copies of the private runtime configuration and the files that change per deployment. `backend.env` carries the database passwords and the resource encryption key; without the same key, stored credentials cannot be decrypted.

## Consistency

A quiesced backup stops `app`, `dispatcher`, `worker` and `temporal` with a graceful timeout, keeps PostgreSQL healthy, and only then captures evidence and dumps; its evidence is `quiesced_exact`. Idle plugins keep running because nothing can call them. Online evidence is `online_advisory`.

## Files

- `preflight.json`: service states before quiescing, immutable image references, pins, databases, application row counts and the discovered topology.
- `SHA256SUMS`: hashes of every dump, listing, archive and configuration copy, re-read independently from the backup directory.
- `manifest.json` (`schema_version: 1`, `status: verified`): self-describing JSON that lists every artifact with its hash and size, the databases with owners, the volumes with entry counts, the row counts, the pins, `app_image_ref`, `db_image_ref`, `evidence_consistency` and the preflight hash.

`pg_dump`, `pg_restore --list`, archive, copy and checksum errors are fatal. Before anything is stopped, free capacity must exceed twice the database size (eight times at compression level 0) plus the volume size plus 5 GiB.
