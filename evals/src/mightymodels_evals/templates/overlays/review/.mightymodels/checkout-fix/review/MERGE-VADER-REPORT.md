# merge-vader report — fix/checkout
VERDICT: BLOCK
"I find your lack of input hygiene disturbing."

## Findings
MV-1 | High | scripts/deploy.py:4 | subprocess.run("deploy.sh " + target, shell=True) | shell=True with concatenated caller input is command injection when target is attacker-influenced | Fix: use subprocess.run(["deploy.sh", target], shell=False) | Verify: grep -n "shell=True" scripts/deploy.py returns nothing | Confidence: High
MV-2 | Medium | README.md:2 | "Run tests with python -m pytest -q" | README omits the new DEPLOY_TARGET env var added on this branch, deploy docs now wrong | Fix: document DEPLOY_TARGET in README deploy section | Verify: grep -n "DEPLOY_TARGET" README.md returns a hit | Confidence: High

## Clean dimensions
sdlc: CI untouched, clean. plan: not supplied.
