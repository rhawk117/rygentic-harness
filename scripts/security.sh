#!/usr/bin/env bash
# Scan agent-facing instruction files for prompt-injection indicators.
#
# Skills and agent definitions are consumed as instructions by agents with real
# tool access, so hostile instruction text should be treated as executable code.
# This scanner intentionally uses simple, high-signal patterns and expects zero
# findings on a clean tree.
#
# Indicators:
#   INJ1  Instruction-override phrasing aimed at the reading agent.
#   INJ2  Fetch-and-execute or encoded-payload execution.
#   INJ3  Credential and secret-store references.
#   INJ4  Invisible or bidirectional Unicode that can hide instructions.
#   INJ5  Pre-approved tool grants in skill frontmatter.
#   INJ6  Plaintext HTTP links an agent might be instructed to fetch.
#
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"

readonly script_dir
readonly repo_root
readonly -a scan_dirs=(plugins/mightymodels/skills plugins/mightymodels/agents)

findings=0

die() {
	printf 'security.sh: %s\n' "$*" >&2
	exit 2
}

validate_checkout() {
	local dir

	for dir in "${scan_dirs[@]}"; do
		[[ -d "$repo_root/$dir" ]] ||
			die "missing scan directory: $repo_root/$dir"
	done
}

report_matches() {
	local id="$1"
	local description="$2"
	local matches="$3"

	[[ -n "$matches" ]] || return 0

	findings=1

	printf '\n[%s] %s\n' "$id" "$description"
	printf '%s\n' "$matches" | head -n 20
}

scan_ere() {
	local id="$1"
	local description="$2"
	local pattern="$3"

	local matches
	local rc

	if matches="$(
		grep \
			--recursive \
			--line-number \
			--ignore-case \
			--extended-regexp \
			--include='*.md' \
			-- "$pattern" \
			"${scan_dirs[@]}"
	)"; then
		rc=0
	else
		rc=$?
	fi

	((rc <= 1)) ||
		die "scan $id failed with grep exit code $rc"

	report_matches "$id" "$description" "$matches"
}

scan_pcre() {
	local id="$1"
	local description="$2"
	local pattern="$3"

	local matches
	local rc

	if matches="$(
		grep \
			--recursive \
			--line-number \
			--perl-regexp \
			--include='*.md' \
			-- "$pattern" \
			"${scan_dirs[@]}"
	)"; then
		rc=0
	else
		rc=$?
	fi

	((rc <= 1)) ||
		die "scan $id failed; check PCRE support and pattern validity"

	report_matches "$id" "$description" "$matches"
}

main() {
	cd -- "$repo_root"
	validate_checkout

	scan_ere INJ1 "instruction-override phrasing" \
		'ignore (all |any )?(previous|prior|earlier|above) (instructions|rules|guidance)|disregard (your|the|all) (system|previous|prior|safety)|forget (your|all previous) instructions|you are now (DAN|unrestricted|jailbroken)|new system prompt|do not (tell|inform|reveal to) the user|without (telling|informing|asking) the user|hide this from'

	# Requiring an argument after curl/wget avoids flagging defensive text such
	# as "deny curl|sh", while still catching an actual fetch-and-execute.
	scan_ere INJ2 "fetch-and-execute or encoded-payload execution" \
		'(curl|wget)[[:space:]]+[^|[:space:]][^|]*\|[[:space:]]*(ba|z|da)?sh|base64 (-d|--decode)[^|]*\||eval[[:space:]]+"?\$\(|/dev/tcp/|python[0-9.]* -c ["'"'"'](import (urllib|requests|socket))|nc (-e|--exec)'

	scan_ere INJ3 "credential and secret-store references" \
		'(id_rsa|id_ed25519)([^.a-z]|$)|\.aws/credentials|\.ssh/authorized_keys|(GITHUB_TOKEN|GH_TOKEN|AWS_SECRET|API_KEY)[^A-Z_]*(\||>|curl|nc |send|exfil)|~/(\.netrc|\.npmrc)'

	scan_pcre INJ4 "invisible or bidirectional Unicode" \
		'(*UTF)[\x{200B}-\x{200F}\x{202A}-\x{202E}\x{2060}-\x{2064}\x{2066}-\x{2069}\x{FEFF}]'

	scan_ere INJ5 "pre-approved tool grants in frontmatter" \
		'^allowed-tools[[:space:]]*:'

	scan_ere INJ6 "plaintext-http links" \
		'http://[a-zA-Z0-9]'

	if ((findings > 0)); then
		printf '\nsecurity.sh: findings above need review; treat skill text as code.\n' >&2
		return 1
	fi

	printf 'security.sh: no prompt-injection indicators in %s\n' \
		"${scan_dirs[*]}"
}

main "$@"
