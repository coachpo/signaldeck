#!/bin/sh
set -eu

# Use the schema bundled in the pinned admin-tools image; never overwrite history.
for kind in temporal visibility; do
    database=signaldeck_temporal
    version=1.19
    if [ "$kind" = visibility ]; then
        database=signaldeck_temporal_visibility
        version=1.14
    fi
    temporal-sql-tool --plugin postgres12 --ep db -p 5432 \
        -u signaldeck_temporal --db "$database" setup-schema -v 0.0
    temporal-sql-tool --plugin postgres12 --ep db -p 5432 \
        -u signaldeck_temporal --db "$database" update-schema \
        -d "/etc/temporal/schema/postgresql/v12/$kind/versioned" -v "$version"
done
