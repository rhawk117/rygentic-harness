# Ledger schema (version 1)

Read when an entry is rejected, when another skill needs to read an investigation, or before changing the `investigation` tool. The tool is the only writer; lets-investigate and what-we-know read through it too. The snapshot and close tools and `ticket` `validate` read the rows directly by this schema (snapshot lifts decisions and open entries, close archives decisions, `validate` checks that every linked investigation has a ledger), so a change here updates those readers in the same change.

## Storage

One investigation is the rows of the `ledger_entries` table in the state database, `mightymodels.db` in the plugin data directory, keyed by the repository, `investigation_id` and `seq`. An investigation has no row of its own: it exists once `start` stores its target as entry 1. No file is written for an investigation, and no row is updated or deleted; an entry is retired by a later entry that names it. `ID` is `YYYYMMDD-slug-of-the-target`: the UTC date, then the redacted target in lowercase letters and digits separated by `-`, shortened to about 40 characters (`investigation` when nothing is left), with `-2`, `-3` appended on collision.

## Record

Every row holds:

| field        | type           | meaning                                                                                                                                                  |
| ------------ | -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `seq`        | int            | position in the investigation, starting at 1; shown as `eN`                                                                                              |
| `round`      | int            | 0 for framing, then the round number; `add` refuses a round earlier than the latest                                                                      |
| `kind`       | string         | `target`, `known`, `open`, `decision`, `resource`, `next`                                                                                                |
| `text`       | string         | the entry, after secret redaction                                                                                                                        |
| `source`     | string         | `code-scout`, `web-scout`, `user`, or `primary`                                                                                                          |
| `cite`       | string or null | `file:line`, `URL#heading`, or a path; for `target`, the classification (`behavior`, `claim`, `research` or `change`); a given cite is not blank          |
| `supersedes` | list of int    | earlier `seq` values this entry retires                                                                                                                  |
| `at`         | string         | UTC timestamp, ISO 8601, seconds                                                                                                                         |
| `head`       | string or null | the commit the repository was at when the entry was stored; null outside a repository, with no git binary, or on an unborn branch                       |

## Rules the tool enforces

| kind       | cite                              | allowed sources                                    |
| ---------- | --------------------------------- | -------------------------------------------------- |
| `target`   | classification                    | written only by `start`; `add` refuses it          |
| `known`    | required                          | any                                                |
| `open`     | optional (where the answer lives) | any                                                |
| `decision` | optional                          | `user` only                                        |
| `resource` | required                          | any                                                |
| `next`     | optional                          | `code-scout`, `web-scout`, `user` (who answers it) |

- A batch is checked whole, in order, before anything is stored: its round first, then each entry's text (not empty), kind, cite and source, and `supersedes`. One bad entry rejects the batch and stores nothing.
- `supersedes` may name only entries that already exist and are not the target, so an entry cannot retire another entry of its own batch. Retired entries stay stored and drop out of `render` and `knowns`.
- `render` shows the live entries by section (Knowns, Open, Decisions, Resources) and the `next` entries of the latest round only, since each round proposes its own. Its heading carries the latest round and its `Target:` line the classification.
- `knowns` prints a table of live entries (`entry`, `kind`, `claim`, `cite`, `source`, `round`, `status`). The `request` of its `payload` takes `kinds` (any of `known`, `open`, `decision`, `resource`, all four by default) and `limit` (at least 1, default 40); rows past the limit are counted in a closing line. Each row is `current` when its `head` equals the repository's HEAD now and `lead` otherwise, including every row when HEAD cannot be read: a lead is history to re-verify, not evidence.
- `list` prints each investigation id with its latest round, or `no investigations`.
- Text and cite matching a secret pattern (private keys, AWS, GitHub, Slack, Stripe and API-key tokens, JWTs, bearer tokens, credentials in URLs, `password=`-style assignments) are replaced with `[REDACTED:kind]` before they are stored, and so is the target before the investigation is named; `add` reports how many it redacted.
