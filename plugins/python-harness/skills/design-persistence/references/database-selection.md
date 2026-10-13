# Database selection

Ask the user whether the service requires SQL or NoSQL before choosing a product. Explain
trade-offs against the actual access patterns, consistency, scale, deployment, and
operations requirements.

## Relational starting points

| Choice                 | Appropriate evidence                                                | Important cost                                                        |
| ---------------------- | ------------------------------------------------------------------- | --------------------------------------------------------------------- |
| SQLite + `aiosqlite`   | simple single-node service, low write concurrency, local deployment | scales poorly for concurrent writes and multi-process service growth  |
| PostgreSQL + `asyncpg` | transactional service, concurrency, rich constraints, growth        | separate database operation, pooling, migrations, and more deployment |
| MySQL + `asyncmy`      | existing MySQL estate or MySQL-specific operational fit             | more driver/dialect and deployment complexity                         |
| MySQL + `aiomysql`     | pure-Python packaging is more important than likely driver speed    | older implementation approach and lower expected throughput           |

For a new MySQL async service, prefer `mysql+asyncmy://` when native wheels or build
tooling are acceptable. It is more actively maintained, covers newer Python versions, and
uses a Cython/native protocol implementation. Treat project benchmark claims as evidence
to validate against the real workload, not as an application-level guarantee. Use
`mysql+aiomysql://` when pure-Python packaging or PyMySQL familiarity is more important.

## NoSQL branch

Do not treat NoSQL as one architecture. Require:

- exact item/aggregate and partition key;
- read and write query shapes;
- consistency and transaction limits;
- secondary-index and hot-partition behavior;
- item size and history growth;
- duplicate, conditional-write, and retry semantics;
- backup, migration, local-test, and operational ownership.

If the access model is still relational and transactional, say so rather than selecting
NoSQL for anticipated scale.
