#!/usr/bin/env bash
set -euo pipefail

# The Ubuntu x64 jobs use the same CLI/server pair as the recovery and E2E tests.
if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
  echo "This CI installer requires Linux x86_64" >&2
  exit 1
fi

download_dir="$(mktemp -d "${RUNNER_TEMP:?}/temporal-download.XXXXXX")"
trap 'rm -rf "$download_dir"' EXIT
cli_dir="${RUNNER_TEMP}/temporal-cli-1.8.3"
archive="${download_dir}/temporal.tar.gz"

curl --fail --location --silent --show-error --retry 3 \
  https://github.com/temporalio/cli/releases/download/v1.8.3/temporal_cli_1.8.3_linux_amd64.tar.gz \
  --output "$archive"
# Published in temporalio/cli v1.8.3 checksums.txt; verify before extracting.
printf '%s  %s\n' \
  6f0afac1e9ddea71f480c43a49f5db5167a244c21db923707f069a79bcabdfea \
  "$archive" | sha256sum --check --strict
mkdir -p "$cli_dir"
tar -xzf "$archive" -C "$cli_dir" temporal
"${cli_dir}/temporal" --version | grep -E '^temporal version 1\.8\.3 \(Server 1\.31\.2[,)]'
printf 'TEMPORAL_CLI=%s/temporal\n' "$cli_dir" >> "${GITHUB_ENV:?}"
