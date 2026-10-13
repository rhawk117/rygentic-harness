---
paths:
  - "GLOB_ONE"
---

<scope>
Governs FILES_IN_WORDS when Claude reads, writes or edits them. Does not cover CARVE_OUTS.
</scope>

<conventions>
1. STRENGTH_WORD CONVENTION_ONE, because REASON.
2. STRENGTH_WORD CONVENTION_TWO, because REASON.
</conventions>

<examples>
CONVENTION_ONE

Before:

```LANG
BEFORE_SNIPPET
```

After:

```LANG
AFTER_SNIPPET
```

</examples>

<anti_patterns>

- GENERIC_ANTI_PATTERN; do INSTEAD. When an existing file already does this, EXISTING_VIOLATION_POLICY.

</anti_patterns>

<verification>
Before finishing a change to a matching file, CHECK_COMMAND_OR_QUESTION. A reviewer can confirm by REVIEWER_CHECK.
</verification>
