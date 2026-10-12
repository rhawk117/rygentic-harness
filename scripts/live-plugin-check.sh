#!/usr/bin/env bash

set -uo pipefail

readonly PLUGIN_NAME=mightymodels
readonly PLUGIN_DIRECTORY=plugins/${PLUGIN_NAME}
readonly STATE_TOOL_PREFIX=mcp__plugin_${PLUGIN_NAME}_state__

repository_root=$(git rev-parse --show-toplevel) || exit 1
cd "${repository_root}" || exit 1
# shellcheck source=scripts/log.sh
source scripts/log.sh

# An agent type listed here is expected to be REFUSED instead of ANSWERED.
declare -A DISPATCH_OUTCOME=()

REQUIRE_STATE=false
FAILURES=()

usage() {
  printf 'usage: %s [--require-state] [--expect-type AGENT_TYPE]\n' "${0##*/}" >&2
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

preloaded_heading_prompt() {
  cat <<PROMPT
Call the Agent tool once with subagent_type "$1", model "haiku" and the prompt below.

Call no tool except the one that hands your answer back. Search your whole context, this message included, for the line that begins with "Base directory for this skill:" and ends with the folder name $2. Answer with one line: PRELOADED-HEADING, a space, then the first line below it that begins with "# ", copied verbatim. Answer with the one line PRELOADED-HEADING none when there is no such line.

Never retry the call. When it has returned, write one final message that is the agent's answer, copied verbatim, with no code fence and no list markers, or the one line REFUSED when the call failed or was denied.
PROMPT
}

nested_session() {
  local session_name=$1
  local prompt=$2

  log::info "nested session: ${session_name}"
  claude -p --plugin-dir "${PLUGIN_DIRECTORY}" --setting-sources project,local \
    --model haiku --output-format stream-json --verbose --allowedTools 'Agent' \
    -- "${prompt}" </dev/null >"${work_directory}/${session_name}.jsonl"
}

last_message() {
  local session_name=$1

  jq -r 'select(.type == "result") | .result' "${work_directory}/${session_name}.jsonl"
}

state_server_started() {
  local session_name=$1

  jq -e --arg prefix "${STATE_TOOL_PREFIX}" \
    'select(.type == "system" and .subtype == "init") | any(.tools[]; startswith($prefix))' \
    "${work_directory}/${session_name}.jsonl" >/dev/null
}

# A check that needs the plugin's state server starts with:
#   requires_state <check> <session> || return 0
requires_state() {
  local check=$1
  local session_name=$2

  state_server_started "${session_name}" && return 0
  if [[ ${REQUIRE_STATE} == false ]]; then
    printf 'skip %s (state server did not start)\n' "${check}"
    return 1
  fi
  printf 'FAIL %s (state server did not start)\n' "${check}"
  FAILURES+=("${check}")
  return 1
}

expect_line() {
  local check=$1
  local expected_line=$2
  local session_name=$3

  if grep -Fxq -- "${expected_line}" <(last_message "${session_name}"); then
    printf 'ok %s\n' "${check}"
    return
  fi
  printf 'FAIL %s (no line "%s")\n' "${check}" "${expected_line}"
  FAILURES+=("${check}")
}

check_dispatch() {
  local agent_type

  nested_session dispatch "$(dispatch_prompt "$@")"
  for agent_type in "$@"; do
    expect_line "dispatch-${agent_type}" \
      "${DISPATCH_OUTCOME[${agent_type}]:-ANSWERED} ${agent_type}" dispatch
  done
}

check_state_server_starts() {
  requires_state state-server-starts dispatch || return 0
  printf 'ok %s\n' state-server-starts
}

check_engineer_preloaded_skills() {
  nested_session engineer-preloaded-skills \
    "$(preloaded_skills_prompt "${PLUGIN_NAME}:workers:engineer")"
  expect_line 'engineer-preloads-agent-debugging' \
    'PRELOADED-SKILL agent-debugging' engineer-preloaded-skills
}

check_uncle_bob_preloaded_doctrine() {
  local doctrine_skill=becoming-uncle-bob
  local doctrine_heading

  doctrine_heading=$(grep -m 1 '^# ' "${PLUGIN_DIRECTORY}/skills/${doctrine_skill}/SKILL.md")
  nested_session uncle-bob-preloaded-doctrine \
    "$(preloaded_heading_prompt "${PLUGIN_NAME}:review:uncle-bob" "${doctrine_skill}")"
  expect_line 'uncle-bob-preloads-its-doctrine' \
    "PRELOADED-HEADING ${doctrine_heading}" uncle-bob-preloaded-doctrine
}

mapfile -t expected_agent_types < <(agent_types_on_disk)

while (($# > 0)); do
  case "$1" in
    --require-state)
      REQUIRE_STATE=true
      shift
      ;;
    --expect-type)
      if [[ -z ${2:-} ]]; then
        usage
        exit 2
      fi
      expected_agent_types+=("$2")
      shift 2
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

for required_command in claude jq; do
  if ! command -v "${required_command}" >/dev/null; then
    log::error "${required_command} not on PATH"
    exit 1
  fi
done

work_directory=$(mktemp -d "${TMPDIR:-/tmp}/live-plugin-check.XXXXXX") || exit 1

check_dispatch "${expected_agent_types[@]}"
check_state_server_starts
check_engineer_preloaded_skills
check_uncle_bob_preloaded_doctrine

if ((${#FAILURES[@]} > 0)); then
  log::error "live plugin checks failed; the nested sessions' output is in ${work_directory}"
  exit 1
fi

rm -r "${work_directory}"
log::success 'live plugin checks passed'
