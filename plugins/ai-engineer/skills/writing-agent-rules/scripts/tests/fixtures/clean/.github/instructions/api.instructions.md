---
applyTo: "src/api/**/*.ts"
---

# API guidelines

- Return the shared error envelope from `src/api/errors.ts`, which defines the only shape
  consumers parse.
