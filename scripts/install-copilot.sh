#!/usr/bin/env bash
# Install mightymodels skills and agents into GitHub Copilot CLI's user directories.
#
# By default, entries are copied. Pass --link to create symlinks instead.
# Every entry the installer creates is recorded in a manifest
# ($COPILOT_DIR/.mightymodels-manifest). The installer never deletes a
# destination it does not own (recorded in the manifest, or a symlink into
# this checkout): install aborts before changing anything when a same-named
# personal skill or agent is in the way, and uninstall skips it.
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
manifest="$copilot_dir/.mightymodels-manifest"
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
	while (($# > 0)); do
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

owned_by_installer() {
	local dest="$1"
	local target

	if [[ -L "$dest" ]]; then
		target="$(readlink -f -- "$dest" 2>/dev/null || true)"
		[[ "$target" == "$repo_root"/* ]] && return 0
	fi

	[[ -f "$manifest" ]] && grep -Fxq -- "$dest" "$manifest"
}

check_conflicts() {
	local source_glob="$1"
	local dest_dir="$2"

	local src
	local dest
	local conflicts=0

	for src in $source_glob; do
		[[ -e "$src" ]] || continue

		dest="$dest_dir/$(basename -- "$src")"
		[[ -e "$dest" || -L "$dest" ]] || continue

		if ! owned_by_installer "$dest"; then
			printf 'conflict: %s exists and was not installed by mightymodels\n' \
				"$dest" >&2
			conflicts=1
		fi
	done

	return "$conflicts"
}

prune_manifest() {
	[[ -f "$manifest" ]] || return 0

	local tmp
	tmp="$(mktemp)"

	while IFS= read -r dest; do
		if [[ -e "$dest" || -L "$dest" ]]; then
			printf '%s\n' "$dest"
		fi
	done <"$manifest" | sort -u >"$tmp"

	if [[ -s "$tmp" ]]; then
		mv -- "$tmp" "$manifest"
	else
		rm -f -- "$tmp" "$manifest"
	fi
}

install_entry() {
	local src="$1"
	local dest="$2"

	if [[ -e "$dest" || -L "$dest" ]]; then
		owned_by_installer "$dest" ||
			die "refusing to overwrite $dest: not installed by mightymodels"
		rm -rf -- "$dest"
	fi

	case "$mode" in
	copy)
		cp -R -- "$src" "$dest"
		;;
	link)
		ln -s -- "$src" "$dest"
		;;
	esac

	printf '%s\n' "$dest" >>"$manifest"
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

		if ! owned_by_installer "$dest"; then
			printf 'skipping %s: not installed by mightymodels\n' "$dest" >&2
			continue
		fi

		rm -rf -- "$dest"
		((removed += 1))
	done

	printf '%d\n' "$removed"
}

install() {
	mkdir -p -- "$copilot_dir/skills" "$copilot_dir/agents"

	local conflicted=0
	check_conflicts "$repo_root/skills/"'*/' "$copilot_dir/skills" || conflicted=1
	check_conflicts "$repo_root/agents/"'*.agent.md' "$copilot_dir/agents" ||
		conflicted=1
	if ((conflicted)); then
		die 'aborting: nothing was installed or removed — move the listed entries aside (or delete them yourself) and re-run'
	fi

	install_entries \
		"$repo_root/skills/"'*/' \
		"$copilot_dir/skills" \
		"skills"

	install_entries \
		"$repo_root/agents/"'*.agent.md' \
		"$copilot_dir/agents" \
		"agents"

	prune_manifest

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

	prune_manifest

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
