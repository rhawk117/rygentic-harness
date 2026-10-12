# Infrastructure, lifecycle, and observability

The application factory constructs immutable properties and settings, then creates one
lifespan state object. The infrastructure aggregate owns process resources and their
disposal.

## Infrastructure aggregate and lifespan

```python
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import cast

from fastapi import FastAPI, Request
from redis.asyncio import Redis


@dataclass(slots=True)
class InfrastructureComponents:
    database: SQLAlchemyAdapter
    redis: Redis

    async def healthcheck(self, *, fail_fast: bool) -> None:
        await self.database.healthcheck()
        await self.redis.ping()

    async def dispose(self) -> None:
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(self.database.dispose())
            tasks.create_task(self.redis.aclose())


@dataclass(slots=True, frozen=True)
class APILifespanState:
    infrastructure: InfrastructureComponents
    properties: ServiceProperties


@asynccontextmanager
async def asgi_lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
    state = cast(APILifespanState, app.state.lifespan_state)
    try:
        await state.infrastructure.healthcheck(fail_fast=True)
        yield {
            'infrastructure': state.infrastructure,
            'properties': state.properties,
        }
    finally:
        await state.infrastructure.dispose()


def get_infrastructure(request: Request) -> InfrastructureComponents:
    return cast(InfrastructureComponents, request.state.infrastructure)


def get_properties(request: Request) -> ServiceProperties:
    return cast(ServiceProperties, request.state.properties)
```

Putting the healthcheck inside `try` matters: a failed startup check must still dispose
resources that were already created. `TaskGroup` attempts independent cleanup operations
and surfaces failures as an exception group rather than silently leaking the second
resource.

When construction itself can fail after opening some resources, use `AsyncExitStack`
during infrastructure creation so partially constructed resources are also closed.

## Structured logging

Bridge standard-library and library logs through one `structlog` processor pipeline:

- merge `contextvars`;
- add level and logger name;
- format positional arguments and exceptions;
- add UTC timestamps;
- render pretty console logs only for local development;
- render JSON in deployed environments;
- allow `uvicorn`, `sqlalchemy`, `redis`, `httpx`, queue, and scheduler loggers to
  propagate into the configured root handler.

```python
import logging.config
from collections.abc import Sequence
from typing import Any

import structlog


def shared_processors(*extras: Any) -> Sequence[Any]:
    return (
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        structlog.processors.format_exc_info,
        structlog.processors.TimeStamper(fmt='iso', utc=True),
        *extras,
    )
```

Do not log authorization tokens, cookies, database parameters, or unbounded request bodies.
Bind safe subject, tenant, route, request, trace, and job identifiers when available.

## Request correlation middleware

Prefer a small ASGI middleware when only the ASGI scope and send path are needed. It can
bind request context, set one request ID in a `ContextVar`, add the response header, and
clear all context in `finally`.

```python
import uuid
from dataclasses import dataclass

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send


@dataclass(slots=True)
class CorrelationSend:
    request_id: str
    send: Send

    async def __call__(self, message: Message) -> None:
        if message['type'] == 'http.response.start':
            headers = list(message.get('headers', []))
            headers.append((b'x-request-id', self.request_id.encode('ascii')))
            message['headers'] = headers
        await self.send(message)


def request_correlation_middleware(app: ASGIApp) -> ASGIApp:
    async def middleware(scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        client = scope.get('client')
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            http_method=scope.get('method', ''),
            http_scheme=scope.get('scheme', ''),
            http_path=scope.get('path', ''),
            network_peer_address=client[0] if client else None,
        )
        try:
            await app(scope, receive, CorrelationSend(request_id, send))
        finally:
            structlog.contextvars.clear_contextvars()

    return middleware
```

If the application accepts an inbound request ID, validate its length and character set
before reusing it; otherwise generate a new ID and record the inbound value separately.

## OpenTelemetry

Instrument owned clients and resources after providers are configured and before serving
requests:

- logging correlation;
- Redis client operations;
- SQLAlchemy engine operations;
- selected system/runtime metrics;
- FastAPI/ASGI and outbound HTTP clients where useful.

For SQLAlchemy async engines, the instrumentation package commonly receives
`async_engine.sync_engine`; inspect the installed instrumentation version before relying
on the exact call:

```python
SQLAlchemyInstrumentor().instrument(engine=async_engine.sync_engine)
RedisInstrumentor().instrument_client(redis)
LoggingInstrumentor().instrument(set_logging_format=False)
```

Do not create duplicate global instrumentation per application factory call. Record which
component owns provider shutdown and exporter flush. Tests must be able to construct the
app without leaking global instrumentors between cases.

## Service properties

Keep immutable service identity separate from environment settings. Useful resource
attributes include service name/version, deployment environment, hostname, process ID,
worker role, and a stable process instance ID. Derive version from packaged metadata or
the build artifact when possible; reading `pyproject.toml` is acceptable only when that
file is guaranteed to exist in the deployment.
