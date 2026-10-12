# Design brief: {SCRIPT_NAME}

**Request:** {ONE_LINE_RESTATEMENT}
**Domain:** {DOMAIN} (suggested from: {SIGNALS}; the user confirmed or changed it)
**Script:** `./scripts/{SCRIPT_NAME}.py`, run with `uv run ./scripts/{SCRIPT_NAME}.py --help`
**Python:** `requires-python = ">={PYTHON}"` ({WHY_THIS_VERSION})

## Packages

| need   | recommended | alternatives     | why the recommendation           | version   |
| ------ | ----------- | ---------------- | -------------------------------- | --------- |
| {NEED} | {PACKAGE}   | {ALT_1}, {ALT_2} | {REASON_TIED_TO_USER_CONSTRAINT} | {VERSION} |

## Design choices

| decision                | recommended | alternatives | why      |
| ----------------------- | ----------- | ------------ | -------- |
| input and output        | {CHOICE}    | {ALTS}       | {REASON} |
| failure policy          | {CHOICE}    | {ALTS}       | {REASON} |
| idempotency and dry-run | {CHOICE}    | {ALTS}       | {REASON} |
| secrets and config      | {CHOICE}    | {ALTS}       | {REASON} |
| scheduling              | {CHOICE}    | {ALTS}       | {REASON} |
| terminal output         | {CHOICE}    | {ALTS}       | {REASON} |
| report rendering        | {CHOICE}    | {ALTS}       | {REASON} |

## Concurrency

- **Workload kind:** {cpu | subprocess | io | library} because {EVIDENCE_FROM_REQUEST}
- **Mechanism:** {MECHANISM} ({WHY})
- **Level:** {sequential | moderate | a lot | toaster}, mapped by the skill's bundled parallelism script, `parallelism.py`, to {NUMBERS}
- **Hard caps kept at every level:** {PER_HOST_LIMIT, RATE_LIMIT, TIMEOUTS, MEMORY, FILE_DESCRIPTORS}

## User overrides

{NONE, or one line per override:}

- You asked for **{X}**; the analysis suggests **{Y}** because {Z}. Keeping **{X}**, implemented as {HOW_X_IS_DONE_WELL}.

## What the script will do

1. {STEP}
2. {STEP}

## Verification after writing

The skill's bundled checker, `check_script.py`, on `./scripts/{SCRIPT_NAME}.py`, then `uv run ./scripts/{SCRIPT_NAME}.py --help`, then `--dry-run` {WHEN_SAFE | skipped because REASON}.
