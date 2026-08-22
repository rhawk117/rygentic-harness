# Uncle Bob Code Quality Report — uploadsvc
Mode: pure · Grade: C

## Findings
### Blocker
- **[G4] Overridden safety: shell execution with string concatenation** — `scripts/deploy.py:4`
  subprocess.run("deploy.sh " + target, shell=True)
  Disabled safeties; Martin's G4. Fix: argument-vector invocation without shell.
### Low
- **[N1] Unrevealing name `target`** — `scripts/deploy.py:3`
  Parameter name reveals neither type nor constraint. Fix: rename to deploy_target_host.
