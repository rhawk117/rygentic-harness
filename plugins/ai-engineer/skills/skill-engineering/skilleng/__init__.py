"""skilleng — a measurement harness for agent skills.

Design rules, enforced by tests in tests/:
  1. One schema. Every artifact carries schema_version + provenance.
  2. Code owns paths. Nothing constructs a workspace path from prose.
  3. Errors are a third outcome class, never folded into "fail".
  4. Deltas are computed from named arm roles, never positional order.
  5. A report may only make claims its rigor tier permits.
"""

__version__ = "1.0.0"
SCHEMA_VERSION = 1
