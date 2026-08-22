## ASKED
objective: remove --legacy-export flag parsing
acceptance:
  - AC-1: grep -rn "legacy-export" src/ returns nothing
verification: python -m pytest -q
files-in-scope: [src/cli.py]
## DONE
what: flag removed
commit: a1
commands-run: pytest -q -> passed
