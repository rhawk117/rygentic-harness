# FastAPI and Pydantic v2

Use this as the primary recipe for a greenfield or compatible service.

## Application shape

- Create the app through an application factory.
- Own async resources through a FastAPI lifespan context manager.
- Organize routers by capability or operation, not by technical layer alone.
- Use `Annotated` dependencies with explicit types.
- Load configuration through the project's established settings mechanism; for greenfield
  FastAPI services, use `pydantic-settings`.
- Keep database migrations outside application startup.

## Backend-only or BFF

Resolve this before route and response design.

- **Backend-only:** define API consumers, media types, compatibility, CORS, and any
  externally hosted frontend boundary.
- **BFF with Jinja + plain CSS/JavaScript:** use for limited interactivity; define template
  context types, escaping, forms, CSRF, static assets, and progressive enhancement.
- **BFF with TypeScript + a client-side framework:** use when complex client reactivity
  justifies a separate build and state-management boundary.
- **BFF with TypeScript + a client-side framework + Tailwind CSS:** use when the team
  accepts the most setup complexity for scalable component styling, less feature-level CSS,
  and a productive established toolchain.

For a BFF, define whether FastAPI renders HTML, serves built assets, or fronts a separately
deployed client. Resolve same-origin cookies versus bearer tokens, CSRF, CORS, CSP,
SameSite, frontend routing, asset caching, source maps, and coordinated deployment.

## Pydantic v2 boundaries

- Use distinct request models, response models, domain objects, and ORM models.
- Use `ConfigDict(extra='forbid')` for request models unless compatibility requires unknown
  fields.
- Apply strict validation selectively; do not enable global strict mode without considering
  JSON coercion and client compatibility.
- Prefer reusable `Annotated` constraints for boundary value types.
- Use field or model validators only for shape-local invariants. Database, authorization,
  and workflow rules belong elsewhere.
- Use `from_attributes=True` only in explicit response or adapter models.
- Do not put application services or persistence behavior on `BaseModel`.
- Make aliases, enum values, timezone handling, null versus unset, and response exclusion
  behavior deliberate.

### Request and response example

```python
from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

type ExportLabel = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]


class ExportFormat(StrEnum):
    CSV = 'csv'
    JSONL = 'jsonl'


class CreateExportRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        frozen=True,
    )

    label: ExportLabel
    resource_ids: Annotated[tuple[UUID, ...], Field(min_length=1, max_length=100)]
    format: ExportFormat

    @field_validator('resource_ids')
    @classmethod
    def unique_resource_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError('resource_ids must be unique')
        return value


class ExportJobResponse(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        from_attributes=True,
    )

    job_id: UUID
    state: str
    created_at: datetime
```

This validator owns only request-shape uniqueness. It does not establish resource
authorization, database uniqueness, or workflow legality.

Translate the request into a domain/application command explicitly:

```python
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class RequestExport:
    subject_id: UUID
    label: str
    resource_ids: tuple[UUID, ...]
    format: ExportFormat


def to_command(
    request: CreateExportRequest,
    *,
    subject_id: UUID,
) -> RequestExport:
    return RequestExport(
        subject_id=subject_id,
        label=request.label,
        resource_ids=request.resource_ids,
        format=request.format,
    )
```

The application command is not a `BaseModel`, and the ORM entity is not accepted as an
HTTP response accidentally.

### Settings example

```python
from enum import StrEnum

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(StrEnum):
    DEVELOPMENT = 'development'
    STAGING = 'staging'
    PRODUCTION = 'production'


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix='DATABASE_',
        case_sensitive=False,
        extra='ignore',
        env_file='.env',
        env_file_encoding='utf-8',
        frozen=True,
    )

    url: str
    pool_size: int = 5
    max_overflow: int = 5


class ApplicationSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix='APP_',
        case_sensitive=False,
        extra='ignore',
        env_file='.env',
        env_file_encoding='utf-8',
        frozen=True,
    )

    environment: AppEnvironment = AppEnvironment.DEVELOPMENT
    pretty_logs: bool = False
```

Keep settings immutable after construction. A typed settings provider or application
container may group independently owned settings and permit explicit test overrides; do
not turn a global mutable dictionary into hidden configuration state.

## Identity and authorization

Preserve the existing identity mechanism. For external OAuth2/OIDC:

- validate issuer, audience, signature, expiry, and required claims;
- distinguish machine and user identities;
- do not trust caller-supplied tenant or owner fields over verified identity;
- keep resource authorization explicit in the application behavior selected by the user;
- scope persistence reads/writes consistently with that behavior;
- define whether forbidden resources return 403 or are concealed as 404.

Authentication success never implies permission to every resource.

## Three failure layers

1. **Infrastructure errors:** adapters raise typed infrastructure failures. HTTP handlers
   map unavailable dependencies to `503 Service Unavailable` and safe retry information.
2. **Application errors:** application use cases raise typed errors with an explicit
   `http.HTTPStatus`, safe detail/code, and required headers. A shared handler serializes
   the stable public error contract.
3. **Framework HTTP exceptions:** normal application behavior does not intentionally raise
   FastAPI or Starlette `HTTPException`. Register handlers for them so method-not-allowed,
   routing, and other framework-generated failures have consistent responses and separate
   suspicious-request telemetry.

Preserve causes in logs/traces without exposing infrastructure details to callers.

## HTTP and OpenAPI review

- Choose status codes, headers, locations, retry semantics, and idempotency deliberately.
- Keep commands and queries distinct where HTTP semantics matter.
- Review generated OpenAPI against representative caller examples.
- Bound request bodies, uploads, streams, and pagination.
- Define trusted proxies and forwarded-header behavior before using client address or
  scheme for security decisions.
- Verify resulting state for mutations; a 2xx response alone is insufficient.

## Testing

- Test application/domain behavior at stable boundaries first.
- Use intentionally designed in-memory repository behavior for use-case tests when a
  repository boundary exists.
- Run repository/adapter tests against the intended database when dialect semantics matter.
- Use HTTPX ASGI tests for important request paths and explicitly enter lifespan.
- Distinguish unauthenticated, unauthorized, validation, application, infrastructure, and
  framework-generated failures.
