#!/usr/bin/env bash

set -uo pipefail

readonly PLUGIN_NAME=mightymodels
readonly PLUGIN_DIRECTORY=plugins/${PLUGIN_NAME}

repository_root=$(git rev-parse --show-toplevel) || exit 1
cd "${repository_root}" || exit 1
# shellcheck source=scripts/log.sh
source scripts/log.sh

# An agent type listed here is expected to be REFUSED instead of ANSWERED.
declare -A DISPATCH_OUTCOME=()

FAILURES=()

usage() {
  printf 'usage: %s [--expect-type AGENT_TYPE]\n' "${0##*/}" >&2
}

agent_types_on_disk() {
  local agent_file folder

  for agent_file in "${PLUGIN_DIRECTORY}"/agents/*/*.md; do
    folder=${agent_file%/*}
    printf '%s:%s:%s\n' "${PLUGIN_NAME}" "${folder##*/}" "$(basename "${agent_file}" .md)"
  done
}

dispatch_prompt() {
  cat <<'PROMPT'
Dispatch every agent type listed at the end of this message with the Agent tool: one call per type, all of the calls in one message, each with model "haiku" and the prompt below, in which TYPE stands for the agent type being called.

Call no tool except the one that hands your answer back. Your whole answer is this one line: ANSWERED TYPE

Call each type exactly as it is spelled. Never retry a call and never call a type that is not listed. When every call has returned, write one final message of one line per listed type and nothing else, with no code fence and no list markers. A type's line is the agent's answer, copied verbatim, when the call returned one, and REFUSED TYPE when the call failed or was denied.

Agent types:
PROMPT
  printf '%s\n' "$@"
}

preloaded_skills_prompt() {
  cat <<PROMPT
Call the Agent tool once with subagent_type "$1", model "haiku" and the prompt below.

Call no tool except the one that hands your answer back. Search your whole context, this message included, for lines that begin with "Base directory for this skill:". Answer with one line for each: PRELOADED-SKILL, a space, then the last folder name of the path on that line. Answer with the one line PRELOADED-SKILL none when there is no such line.

Never retry the call. When it has returned, write one final message that is the agent's answer, copied verbatim, with no code fence and no list markers, or the one line REFUSED when the call failed or was denied.
PROMPT
}

nested_session() {
  local session_name=$1
  local prompt=$2
  local session_output=${work_directory}/${session_name}.json

  log::info "nested session: ${session_name}" >&2
  claude -p --plugin-dir "${PLUGIN_DIRECTORY}" --setting-sources project,local \
    --model haiku --output-format json --allowedTools 'Agent' \
    -- "${prompt}" </dev/null >"${session_output}" || return 1
  jq -r .result "${session_output}"
}

expect_line() {
  local check=$1
  local expected_line=$2
  local last_message=$3

  if grep -Fxq -- "${expected_line}" <<<"${last_message}"; then
    printf 'ok %s\n' "${check}"
    return
  fi
  printf 'FAIL %s (no line "%s")\n' "${check}" "${expected_line}"
  FAILURES+=("${check}")
}

check_dispatch() {
  local agent_type last_message

  last_message=$(nested_session dispatch "$(dispatch_prompt "$@")")
  for agent_type in "$@"; do
    expect_line "dispatch-${agent_type}" \
      "${DISPATCH_OUTCOME[${agent_type}]:-ANSWERED} ${agent_type}" "${last_message}"
  done
}

check_engineer_preloaded_skills() {
  local last_message

  last_message=$(nested_session engineer-preloaded-skills \
    "$(preloaded_skills_prompt "${PLUGIN_NAME}:workers:engineer")")
  expect_line 'engineer-preloads-agent-debugging' \
    'PRELOADED-SKILL agent-debugging' "${last_message}"
}

mapfile -t expected_agent_types < <(agent_types_on_disk)

case "${1:-}" in
  '') ;;
  --expect-type)
    if [[ -z ${2:-} ]]; then
      usage
      exit 2
    fi
    expected_agent_types+=("$2")
    ;;
  *)
    usage
    exit 2
    ;;
esac

for required_command in claude jq; do
  if ! command -v "${required_command}" >/dev/null; then
    log::error "${required_command} not on PATH"
    exit 1
  fi
done

work_directory=$(mktemp -d "${TMPDIR:-/tmp}/live-plugin-check.XXXXXX") || exit 1

check_dispatch "${expected_agent_types[@]}"
check_engineer_preloaded_skills

if ((${#FAILURES[@]} > 0)); then
  log::error "live plugin checks failed; the nested sessions' output is in ${work_directory}"
  exit 1
fi

rm -r "${work_directory}"
log::success 'live plugin checks passed'
