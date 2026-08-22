#!/usr/bin/env bash
# Install mightymodels skills and agents into GitHub Copilot CLI's user directories.
#
# By default, entries are copied. Pass --link to create symlinks instead.
# Uninstall removes only entries represented by this checkout and leaves
# unrelated personal Copilot skills and agents untouched.
#
# Usage:
#   ./scripts/install.sh
#   ./scripts/install.sh --link
#   ./scripts/install.sh --uninstall
#
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"

copilot_dir="${COPILOT_DIR:-$HOME/.copilot}"
mode="copy"
action="install"

usage() {
	cat <<EOF
Usage: $(basename -- "$0") [--link] [--uninstall]

Options:
  --link       Symlink entries instead of copying them.
  --uninstall  Remove mightymodels entries installed from this checkout.
  -h, --help   Show this help message.
EOF
}

die() {
	printf 'error: %s\n' "$*" >&2
	exit 1
}

parse_args() {
	while (( $# > 0 )); do
		case "$1" in
		--link)
			mode="link"
			;;
		--uninstall)
			action="uninstall"
			;;
		-h | --help)
			usage
			exit 0
			;;
		*)
			printf 'error: unknown argument: %s\n\n' "$1" >&2
			usage >&2
			exit 2
			;;
		esac

		shift
	done
}

validate_checkout() {
	[[ -d "$repo_root/skills" ]] ||
		die "not an mightymodels checkout: $repo_root"
}

install_entry() {
	local src="$1"
	local dest="$2"

	rm -rf -- "$dest"

	case "$mode" in
	copy)
		cp -R -- "$src" "$dest"
		;;
	link)
		ln -s -- "$src" "$dest"
		;;
	esac
}

install_entries() {
	local source_glob="$1"
	local dest_dir="$2"
	local label="$3"

	local src
	local count=0

	for src in $source_glob; do
		[[ -e "$src" ]] || continue

		install_entry "$src" "$dest_dir/$(basename -- "$src")"
		((count += 1))
	done

	printf 'installed %d %s into %s (%s)\n' \
		"$count" "$label" "$dest_dir" "$mode"
}

remove_entries() {
	local source_glob="$1"
	local dest_dir="$2"

	local src
	local dest
	local removed=0

	for src in $source_glob; do
		[[ -e "$src" ]] || continue

		dest="$dest_dir/$(basename -- "$src")"
		[[ -e "$dest" || -L "$dest" ]] || continue

		rm -rf -- "$dest"
		((removed += 1))
	done

	printf '%d\n' "$removed"
}

install() {
	mkdir -p -- "$copilot_dir/skills" "$copilot_dir/agents"

	install_entries \
		"$repo_root/skills/"'*/' \
		"$copilot_dir/skills" \
		"skills"

	install_entries \
		"$repo_root/agents/"'*.agent.md' \
		"$copilot_dir/agents" \
		"agents"

	printf '%s\n' \
		'verify inside a session with /agents and by invoking a skill, e.g. /lets-investigate'
}

uninstall() {
	local skills_removed
	local agents_removed

	skills_removed="$(
		remove_entries \
			"$repo_root/skills/"'*/' \
			"$copilot_dir/skills"
	)"

	agents_removed="$(
		remove_entries \
			"$repo_root/agents/"'*.agent.md' \
			"$copilot_dir/agents"
	)"

	printf 'removed %d mightymodels entries from %s\n' \
		"$((skills_removed + agents_removed))" \
		"$copilot_dir"
}

main() {
	parse_args "$@"
	validate_checkout

	case "$action" in
	install)
		install
		;;
	uninstall)
		uninstall
		;;
	esac
}

main "$@"