#!/usr/bin/env bash
set -eu
cat > pyproject.toml <<'TOML'
[project]
name = "checkout-metrics"
version = "0.1.0"
requires-python = ">=3.12"
TOML
cat > latency.csv <<'CSV'
day,provider,latency_ms
2026-09-01,old-cdn,412
2026-09-02,old-cdn,398
2026-09-03,new-cdn,351
2026-09-04,new-cdn,367
2026-09-05,new-cdn,340
2026-09-06,new-cdn,389
CSV
