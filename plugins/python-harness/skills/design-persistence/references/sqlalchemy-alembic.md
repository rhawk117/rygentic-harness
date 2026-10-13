# SQLAlchemy 2 and Alembic

Use this recipe only after the service selects relational persistence and SQLAlchemy.

## Async model and session rules

- Use SQLAlchemy 2 typed declarative mappings with `Mapped` and `mapped_column`.
- Make the declarative base inherit from `AsyncAttrs`.
- Set every relationship to `lazy='raise'`. Load required relationships explicitly.
- Use `select()` and other 2.x statement APIs; avoid legacy query patterns.
- Configure `async_sessionmaker(..., expire_on_commit=False, autobegin=False)`.
- Create one `AsyncSession` per request or work unit. Never share it across concurrent
  tasks.
- Repositories may add and `flush()` but never commit independently.
- Put durable uniqueness, referential, and scalar invariants in named database constraints
  where possible.
- Translate expected named integrity conflicts at the application boundary while
  preserving the original cause for diagnostics.

```python
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase


class Base(AsyncAttrs, DeclarativeBase):
    pass
```

## Adapter and unit of work

`SQLAlchemyAdapter` owns the engine lifecycle and sessionmaker. Construct it from database
settings, or make ownership transfer explicit when an engine is injected. Its dependency
context explicitly enters both session and transaction and yields the core `AsyncSession`.
Its `dispose()` method must be called from application lifespan shutdown:

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class SQLAlchemyAdapter:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessions = async_sessionmaker(
            engine,
            expire_on_commit=False,
            autobegin=False,
        )

    @classmethod
    def from_url(cls, database_url: str) -> 'SQLAlchemyAdapter':
        return cls(create_async_engine(database_url, pool_pre_ping=True))

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._sessions() as session:
            async with session.begin():
                yield session

    async def healthcheck(self) -> None:
        async with self._engine.connect() as connection:
            await connection.execute(text('SELECT 1'))

    async def dispose(self) -> None:
        await self._engine.dispose()
```

Application use cases control the work unit by entering this dependency. Unit-of-work
classes consume the yielded session and materialize operation-specific repositories:

```python
class ExportUnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self.exports = SQLAlchemyExportRepository(session)


async with adapter.session() as session:
    unit_of_work = ExportUnitOfWork(session)
    result = await request_export.execute(command, unit_of_work)
```

The adapter owns construction and transaction mechanics. The use case owns when the work
unit begins and ends. The unit of work owns repository materialization. Repositories own
queries and writes but not commit.

The application infrastructure aggregate owns the adapter and calls `await adapter.dispose()` during lifespan shutdown. Do not rely on interpreter exit or garbage
collection to close the engine pool.

## Query and concurrency review

- Derive repository methods from use-case access patterns.
- Inspect emitted SQL for known reads and writes.
- Use explicit eager loading such as `selectinload()` or joined loading where justified.
- Do not hide I/O behind property access.
- Use unique constraints for allocation/idempotency races, version columns for optimistic
  concurrency, and row locks only for a demonstrated serialized decision.
- Catch `IntegrityError` only around the expected operation; identify the named constraint
  or dialect-safe conflict before translating it.
- Test dialect-dependent behavior against the intended database.

## Alembic

- Review autogenerate output line by line. It is a draft, not proof.
- Name constraints so conflicts and migrations are diagnosable.
- Separate schema changes from data backfills.
- When application versions coexist, use expand, backfill, and contract phases.
- Require explicit data and compatibility verification before beginning the contract phase.
- Measure existing rows before enabling required values or uniqueness.
- Avoid table-rewrite and blocking-index surprises; use the selected database's supported
  online/concurrent mechanisms when required.
- Do not run production migrations from FastAPI startup.
- Define whether downgrade is supported; otherwise document and test forward repair.
