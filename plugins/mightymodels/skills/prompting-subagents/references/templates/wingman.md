# Template: wingman dispatch

For one stuck decision, sent by ask-an-adult. wingman holds no tool, so the packet is its only evidence and everything it needs is in it, the ticket's text included; its contract (independence, verdict first, at most three questions) lives in the wingman agent file. Missing sections are the usual reason it comes back at low confidence.

**Ten-second checklist:** one decision, not a symptom · every option carries its cost · the ticket fields are copied from `ticket.yml`, or the section says "none" · every fact carries its citation (file:line, URL#heading, command output), and assumptions are marked as assumptions · scout findings pass through as they came back, never summarized into conclusions · your lean is stated plainly, or "none".

```text
<decision>The single choice at stake, in one sentence.</decision>
<options>Each option under consideration, and what it costs.</options>
<ticket>
  From ticket.yml, verbatim: task, summary, every context line, companion-docs and
  handoff-context. "none" when no ticket is active.
</ticket>
<facts>
  Everything gathered, with citations: file:line, scout findings, command output, test
  results. Mark anything you assumed rather than confirmed.
</facts>
<constraints>Deadlines, policy, toolchain, prior user decisions.</constraints>
<attempted>What has already been tried and how it failed.</attempted>
<lean>Your own preference, stated plainly, or "none".</lean>
```

Slots: decision · options with costs · ticket fields · cited facts · constraints · attempts · lean.
