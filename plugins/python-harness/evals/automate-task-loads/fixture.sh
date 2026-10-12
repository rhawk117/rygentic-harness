#!/usr/bin/env bash
set -eu
mkdir -p reports
cat > pyproject.toml <<'TOML'
[project]
name = "office-chores"
version = "0.1.0"
requires-python = ">=3.12"
TOML
cat > reports/q3-summary.txt <<'TXT'
Quarter 3 summary
Revenue: 120
Costs: 80
TXT
cat > reports/q3-notes.txt <<'TXT'
Check the figures with finance before sending.
TXT
