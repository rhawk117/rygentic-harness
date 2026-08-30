# Security report — skill-engineering

What an installer is agreeing to run. Generated at package time; review before granting this skill shell access.

- Files packaged: **32**
- Files excluded by policy: **22**
- Executable scripts: **0**
- Distinct network endpoints referenced: **1**

## Network endpoints

On Copilot's cloud agent these must be on the firewall allowlist or the request is blocked and reported as a PR warning rather than a hard failure.

- `api.example.com`

## Permissions

- Declared `allowed-tools`: `(none)`
- Minimum implied by the bundled scripts: `(none)`

## Excluded by policy

- `skilleng/__pycache__/__init__.cpython-311.pyc`
- `skilleng/__pycache__/__main__.cpython-311.pyc`
- `skilleng/__pycache__/aggregate.cpython-311.pyc`
- `skilleng/__pycache__/cli.cpython-311.pyc`
- `skilleng/__pycache__/doctor.cpython-311.pyc`
- `skilleng/__pycache__/events.cpython-311.pyc`
- `skilleng/__pycache__/grade.cpython-311.pyc`
- `skilleng/__pycache__/hooks.cpython-311.pyc`
- `skilleng/__pycache__/hookshim.cpython-311.pyc`
- `skilleng/__pycache__/package.cpython-311.pyc`
- `skilleng/__pycache__/report.cpython-311.pyc`
- `skilleng/__pycache__/schema.cpython-311.pyc`
- `skilleng/__pycache__/skillmd.cpython-311.pyc`
- `skilleng/__pycache__/stats.cpython-311.pyc`
- `skilleng/__pycache__/trigger.cpython-311.pyc`
- `skilleng/__pycache__/workspace.cpython-311.pyc`
- `skilleng/runners/__pycache__/__init__.cpython-311.pyc`
- `skilleng/runners/__pycache__/base.cpython-311.pyc`
- `skilleng/runners/__pycache__/claude_code.cpython-311.pyc`
- `skilleng/runners/__pycache__/copilot_cli.cpython-311.pyc`
- `tests/__pycache__/test_regressions.cpython-311.pyc`
- `tests/__pycache__/test_stats.cpython-311.pyc`
