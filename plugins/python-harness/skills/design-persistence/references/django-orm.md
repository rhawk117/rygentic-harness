# Django ORM

Use Django ORM when the project already uses Django or needs its integrated application,
administration, authentication, and migration capabilities.

- Keep HTTP serializers/forms, domain decisions, and ORM models conceptually separate.
- Derive manager/queryset methods from real access patterns instead of generic helper
  layers.
- Use `transaction.atomic()` at the application operation boundary; do not scatter nested
  commits.
- Use database constraints for durable invariants and translate expected
  `IntegrityError` conflicts.
- Make `select_related()` and `prefetch_related()` deliberate for known access paths.
- Use `select_for_update()` only for a demonstrated serialized decision.
- Review migration operations, data migrations, locks, defaults, and old/new application
  coexistence.
- Remember that Django's async ORM surface and connection behavior are version-specific.
  Inspect the installed version before promising fully async execution.

Do not introduce Django solely to obtain an ORM when the selected service architecture
does not need the rest of the framework.
