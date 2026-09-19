# Restore

## Drill (non-destructive)

`signaldeck_restore_check.py execute` proves a backup is usable without touching the live stack:

1. Validate the manifest path, the complete artifact set, every artifact hash against the manifest and `SHA256SUMS`, and the preflight hash.
2. Start a networkless container of the manifest's exact PostgreSQL image, create each owner role and database, and restore every dump with `pg_restore --single-transaction --exit-on-error --no-owner --no-acl --role=<owner>`.
3. For a quiesced backup, require the restored application row counts to equal the manifest; list every volume archive and require its recorded entry count.
4. Remove the container in all cases.

## Switching a live instance (explicit authorization only)

There is no script for this; it replaces live state and needs a current, explicit decision naming the manifest. Keep every original instead of dropping it:

1. Run the drill on the chosen manifest and record the current image references, pins and row counts with `$signaldeck-ops-inspect`.
2. Stop every writer: `docker compose --env-file <env> -f <compose> stop app dispatcher worker temporal` and the plugin services.
3. For each database in the manifest, rename the live database aside (`ALTER DATABASE <name> RENAME TO <name>_pre_restore_<stamp>`), create an empty one with the recorded owner, and restore its dump as above.
4. For each volume, first archive its current content next to the backup, then empty it and extract the manifest archive into it with a helper container.
5. Restore `backend.env` only when the key or passwords changed since the backup; the encryption key must match the restored credentials.
6. Start the stack with `deploy.sh start <stack> --version <app_image_ref version>` from the manifest, verify `/ready`, `/health`, container identity and row counts, and keep the renamed databases and volume archives until a separate decision removes them.

On failure, stop the writers again, rename the restored databases aside, rename the originals back, restore the archived volume content and start the original image.
