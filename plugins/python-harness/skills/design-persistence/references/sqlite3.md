# sqlite3

Use stdlib `sqlite3` for local tools, fixtures, and simple single-node state when its write
concurrency and deployment limits fit. In an async SQLAlchemy service, use `aiosqlite`
only after acknowledging that the database remains SQLite.

- Enable foreign keys explicitly for each connection.
- Define transaction mode rather than relying on surprising implicit behavior.
- Use parameterized statements and explicit row conversion.
- Name and test uniqueness, check, and foreign-key behavior.
- Keep one connection owner per work unit; do not share a connection concurrently.
- Exercise rollback and process-restart behavior with a real file when durability matters.
- Treat `:memory:` databases carefully: connection pooling can create separate databases,
  and their locking/durability behavior does not represent a file or production database.
- Plan schema changes explicitly. SQLite may require table recreation for changes that
  another database performs in place.

SQLite is the simplest relational option but scales poorly for concurrent writes and
multi-process growth. Do not present it as a transparent development substitute for
PostgreSQL or MySQL when dialect behavior is part of the contract.
