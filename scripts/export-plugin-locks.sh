#!/usr/bin/env bash

set -euo pipefail

repository_root=$(git rev-parse --show-toplevel)
cd "${repository_root}"

exported=$(mktemp)
trap 'rm -f -- "${exported}"' EXIT

if ! uv lock --check >/dev/null 2>&1; then
  uv lock
fi

for pyproject in plugins/*/pyproject.toml; do
  lock_file="${pyproject%pyproject.toml}requirements.lock"
  package=$(awk -F'"' '/^name = /{print $2; exit}' "${pyproject}")
  NO_COLOR=1 uv export --package "${package}" --no-dev --no-emit-workspace --no-hashes --frozen \
    >"${exported}"
  cmp -s "${exported}" "${lock_file}" || cat "${exported}" >"${lock_file}"
done
