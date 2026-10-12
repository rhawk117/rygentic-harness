#!/usr/bin/env bash
set -eu
cat > pyproject.toml <<'TOML'
[project]
name = "events-loader"
version = "0.1.0"
requires-python = ">=3.12"
TOML
cat > events.csv <<'CSV'
event_id,account_id,kind
1,10,login
2,11,login
CSV
