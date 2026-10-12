#!/usr/bin/env bash
set -eu
cat > pyproject.toml <<'TOML'
[project]
name = "events-loader"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["pandas"]
TOML
cat > events.csv <<'CSV'
event_id,account_id,kind
1,10,login
2,11,login
3,10,purchase
CSV
cat > accounts.csv <<'CSV'
account_id,plan
10,free
10,pro
11,free
CSV
cat > load.py <<'PY'
import pandas as pd

events = pd.read_csv("events.csv")
accounts = pd.read_csv("accounts.csv")
print(events.merge(accounts, on="account_id"))
PY
