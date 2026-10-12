#!/usr/bin/env bash

set -uo pipefail

readonly PLUGIN_NAME=mightymodels
readonly PLUGIN_DIRECTORY=plugins/${PLUGIN_NAME}
readonly STATE_TOOL_PREFIX=mcp__plugin_${PLUGIN_NAME}_state__
readonly ASK_TICKET=hook-ask
readonly ASK_BRANCH=live-check/hook-ask
readonly ASK_FILE=asked-edit.txt

repository_root=$(git rev-parse --show-toplevel) || exit 1
cd "${repository_root}" || exit 1
# shellcheck source=scripts/log.sh
source scripts/log.sh

# An agent type listed here has its dispatch decided by a plugin hook, and its entry is the
# outcome expected instead of ANSWERED. In a session where Claude Code cannot create the plugin's
# data directory no plugin hook runs, so such a dispatch is checked only when the state server
# started, as requires_state tells. The dispatch hook refuses the intern unless a task owning
# exactly one file is started for it, and a nested session starts none.
declare -A DISPATCH_OUTCOME=(["${PLUGIN_NAME}:workers:intern"]=REFUSED)

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
Dispatch every agent type listed at the end of this message with the Agent tool: one call per type, all of the calls in one message, each with model "haiku" and the prompt below.

This only checks that you can be dispatched. Do no work and call no tool except the one that hands your answer back. Answer in one short line.

Call each type exactly as it is spelled. Never retry a call and never call a type that is not listed. When every call has returned, write the one word DONE.

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

skill_listing_prompt() {
  cat <<PROMPT
Call no tool. Your context holds a list of the skills available to you, each entry a name followed by a description. Write one line for every entry whose name begins with "${PLUGIN_NAME}:" and nothing else, with no code fence and no list markers. An entry's line is DESCRIBED-SKILL, a space, the name without "${PLUGIN_NAME}:", a space, then the first word of its description with no punctuation after it. For an entry that holds a name and no description, the line is UNDESCRIBED-SKILL, a space, then the name without "${PLUGIN_NAME}:".
PROMPT
}

hook_ask_prompt() {
  cat <<PROMPT
Make three tool calls, one per message, in the order below. Never retry a call, and go on to the next one whatever the call before it returned.

1. Call the ${STATE_TOOL_PREFIX}ticket tool with action "write", slug "${ASK_TICKET}" and these fields: summary "Live check of what a hook's ask does", context ["a scratch repository made by scripts/live-plugin-check.sh"], scope "sm", compaction false, branch "${ASK_BRANCH}".
2. Call the Bash tool with the command: git push
3. Call the Write tool with file_path "$1" and content "asked".

When the third call has returned, write the one word DONE.
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

# A session started in another repository, with the tools the hook ask check calls allowed, so
# that a Write that does not happen there was stopped by a hook and not by a missing permission.
session_in_repository() {
  local session_name=$1
  local directory=$2
  local prompt=$3

  log::info "nested session: ${session_name}"
  (
    cd "${directory}" || exit 1
    claude -p --plugin-dir "${repository_root}/${PLUGIN_DIRECTORY}" \
      --setting-sources project,local --model haiku --output-format stream-json --verbose \
      --allowedTools "${STATE_TOOL_PREFIX}ticket" 'Write' 'Bash(git push)' \
      -- "${prompt}" </dev/null >"${work_directory}/${session_name}.jsonl"
  )
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

# What the stream of a session holds for the main thread's first call of a tool, or for its first
# Agent call of an agent type when one is named, whatever the worker wrote: ANSWERED when the call
# has a tool_result that is not an error, REFUSED when its tool_result is an error, NO-RESULT when
# the call has no tool_result and NO-CALL when it was never made. A denial by a hook arrives as an
# error result. No plugin hook runs in a sandboxed session, so it is the run with --require-state
# outside the sandbox that proves REFUSED.
call_seen() {
  local session_name=$1
  local tool_name=$2
  local agent_type=${3:-}

  jq -rs --arg tool_name "${tool_name}" --arg agent_type "${agent_type}" '
    def blocks(kind): .message.content | arrays | .[] | select(.type == kind);
    [
      .[] | select(.type == "assistant" and .parent_tool_use_id == null) | blocks("tool_use")
      | select(.name == $tool_name and ($agent_type == "" or .input.subagent_type == $agent_type))
      | .id
    ][0] as $call
    | [.[] | select(.type == "user") | blocks("tool_result") | select(.tool_use_id == $call)][0]
      as $result
    | if $call == null then "NO-CALL"
      elif $result == null then "NO-RESULT"
      elif $result.is_error == true then "REFUSED"
      else "ANSWERED" end
  ' "${work_directory}/${session_name}.jsonl"
}

check_dispatch() {
  local agent_type check hook_decided_outcome expected_outcome seen_outcome

  nested_session dispatch "$(dispatch_prompt "$@")"
  for agent_type in "$@"; do
    check=dispatch-${agent_type}
    hook_decided_outcome=${DISPATCH_OUTCOME[${agent_type}]:-}
    if [[ -n ${hook_decided_outcome} ]]; then
      requires_state "${check}" dispatch || continue
    fi
    expected_outcome=${hook_decided_outcome:-ANSWERED}
    seen_outcome=$(call_seen dispatch Agent "${agent_type}")
    if [[ ${seen_outcome} == "${expected_outcome}" ]]; then
      printf 'ok %s\n' "${check}"
      continue
    fi
    printf 'FAIL %s (expected %s, saw %s)\n' "${check}" "${expected_outcome}" "${seen_outcome}"
    FAILURES+=("${check}")
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

check_reviewer_preloaded_doctrine() {
  local reviewer=$1
  local doctrine_skill=becoming-${reviewer}
  local doctrine_heading

  doctrine_heading=$(grep -m 1 '^# ' "${PLUGIN_DIRECTORY}/skills/${doctrine_skill}/SKILL.md")
  nested_session "${reviewer}-preloaded-doctrine" \
    "$(preloaded_heading_prompt "${PLUGIN_NAME}:review:${reviewer}" "${doctrine_skill}")"
  expect_line "${reviewer}-preloads-its-doctrine" \
    "PRELOADED-HEADING ${doctrine_heading}" "${reviewer}-preloaded-doctrine"
}

check_skill_listing_describes_every_skill() {
  local skill_file skill description_start

  nested_session skill-listing "$(skill_listing_prompt)"
  for skill_file in "${PLUGIN_DIRECTORY}"/skills/*/SKILL.md; do
    grep -q '^disable-model-invocation:[[:space:]]*true' "${skill_file}" && continue
    skill=${skill_file%/*}
    skill=${skill##*/}
    description_start=$(awk '/^description:/ {
      sub(/^description:[[:space:]]*(>-)?/, "")
      if (NF == 0) getline
      sub(/[^[:alnum:]]+$/, "", $1)
      print $1
      exit
    }' "${skill_file}")
    expect_line "listing-describes-${skill}" \
      "DESCRIBED-SKILL ${skill} ${description_start}" skill-listing
  done
}

# Records what a PreToolUse hook's `ask` does under `claude -p`. A scratch repository under the
# work directory gets its own branch and, through the session's first call, an unclosed ticket on
# it, so the main-thread hook holds the session's `git push` and answers `ask` to its Write of a
# file outside the ticket directory. The refusal of the push, read from the stream, shows that the
# hook ran and saw the ticket; without it nothing is recorded and the check fails. The outcome is
# EDITED when the file was written, REFUSED when the Write came back as an error and STOPPED when
# the Write has no result. The ticket's row stays in the plugin's data directory under the scratch
# repository's key.
check_hook_ask_under_print_mode() {
  local check=hook-ask-under-print-mode
  local scratch_repository=${work_directory}/hook-ask-repository
  local write_seen outcome

  requires_state "${check}" dispatch || return 0
  if ! git init --quiet --initial-branch "${ASK_BRANCH}" "${scratch_repository}"; then
    printf 'FAIL %s (no scratch repository)\n' "${check}"
    FAILURES+=("${check}")
    return
  fi
  session_in_repository hook-ask "${scratch_repository}" \
    "$(hook_ask_prompt "${scratch_repository}/${ASK_FILE}")"
  if ! grep -Fq "was refused: ticket ${ASK_TICKET}" "${work_directory}/hook-ask.jsonl"; then
    printf 'FAIL %s (the push was not held for ticket %s, so no ask was reached)\n' \
      "${check}" "${ASK_TICKET}"
    FAILURES+=("${check}")
    return
  fi
  write_seen=$(call_seen hook-ask Write)
  outcome=${write_seen}
  [[ ${write_seen} == NO-RESULT ]] && outcome=STOPPED
  [[ ${write_seen} != NO-CALL && -e ${scratch_repository}/${ASK_FILE} ]] && outcome=EDITED
  case "${outcome}" in
    EDITED | REFUSED | STOPPED)
      printf 'ok %s (a hook ask under claude -p: %s)\n' "${check}" "${outcome}"
      ;;
    *)
      printf 'FAIL %s (the Write call was %s and wrote no file)\n' "${check}" "${write_seen}"
      FAILURES+=("${check}")
      ;;
  esac
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
check_reviewer_preloaded_doctrine uncle-bob
check_reviewer_preloaded_doctrine merge-vader
check_skill_listing_describes_every_skill
check_hook_ask_under_print_mode

if ((${#FAILURES[@]} > 0)); then
  log::error "live plugin checks failed; the nested sessions' output is in ${work_directory}"
  exit 1
fi

rm -r "${work_directory}"
log::success 'live plugin checks passed'
