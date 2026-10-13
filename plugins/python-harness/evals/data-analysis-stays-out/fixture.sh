#!/usr/bin/env bash
set -eu
cat > pyproject.toml <<'TOML'
[project]
name = "sales-export"
version = "0.1.0"
requires-python = ">=3.12"
TOML
cat > sales.csv <<'CSV'
order_id,amt,region
1001,25.50,north
1002,13.00,south
1003,48.25,north
CSV
