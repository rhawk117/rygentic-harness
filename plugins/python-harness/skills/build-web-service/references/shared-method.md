# Shared operating method

`build-web-service` owns the outcome, progressive interview, complexity classification,
and final integration. Contributing skills receive one shared brief and ask only questions
missing from it.

The order is:

1. requirements and complexity;
2. contracts;
3. persistence and data-layer decisions;
4. scenario tests;
5. implementation phase;
6. lifecycle and resulting-state verification;
7. expansion using proven conventions.

One mutable artifact has one owner. The contract phase owns public declarations, Design
Persistence owns persistence decisions, Test Engineer owns scenario tests, and the implementation phase
owns the permitted production slice. Contributors return conflicts to the lead rather
than silently rewriting another owner's artifact.

Report design inspection, manual walkthrough, and implementation-backed checks separately.
