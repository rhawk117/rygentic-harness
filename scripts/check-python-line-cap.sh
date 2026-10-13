#!/usr/bin/env bash

set -euo pipefail

readonly CAPPED_DIRECTORIES=(plugins/mightymodels plugins/mighty-copilot)
readonly MAXIMUM_LINES=500

repository_root=$(git rev-parse --show-toplevel)
cd "${repository_root}"
# shellcheck source=scripts/log.sh
source scripts/log.sh

mapfile -d '' -t tracked_files < <(git ls-files -z -- "${CAPPED_DIRECTORIES[@]/%//*.py}")

files_over_cap=()
for tracked_file in "${tracked_files[@]}"; do
  [[ -f ${tracked_file} ]] || continue
  line_count=$(wc -l <"${tracked_file}")
  if ((line_count > MAXIMUM_LINES)); then
    files_over_cap+=("${tracked_file} (${line_count} lines)")
  fi
done

if ((${#files_over_cap[@]} > 0)); then
  log::error "Python files under ${CAPPED_DIRECTORIES[*]} over ${MAXIMUM_LINES} lines:"
  printf '  - %s\n' "${files_over_cap[@]}" >&2
  exit 1
fi

log::success "${#tracked_files[@]} Python files under ${CAPPED_DIRECTORIES[*]}, none over ${MAXIMUM_LINES} lines"
