import inspect
from pathlib import Path
from types import MethodType
from typing import TypeAliasType, get_args

import pytest
from mcp.types import Tool
from mightymodels.core.slug import (
    SLUG_LIMIT,
    SLUG_PATTERN,
    InvalidSlugError,
    Slug,
    parsed_slug,
)
from mightymodels.core.tests.hostile_slugs import HOSTILE
from mightymodels.core.workspace import workspace_at
from mightymodels.server import TOOLS
from mightymodels.tools.review.schema import StartPayload
from mightymodels.tools.tests.support import StateServer
from pydantic import BaseModel, ValidationError


def request_variants(tool: MethodType) -> tuple[type[BaseModel], ...]:
    request = inspect.signature(tool).parameters['request'].annotation
    if not isinstance(request, TypeAliasType):
        return (request,)
    joined, _discriminator = get_args(request.__value__)
    return get_args(joined)


def required_slugs(tool: Tool) -> list[object]:
    return [
        model['properties']['slug']
        for model in tool.input_schema['$defs'].values()
        if 'slug' in model.get('required', ())
    ]


class TestSlugType:
    @pytest.mark.parametrize('raw', HOSTILE)
    def test_slug_confinement_refuses_a_separator_or_a_parent_reference(self, raw: str) -> None:
        assert isinstance(parsed_slug(raw), InvalidSlugError)
        with pytest.raises(ValidationError):
            Slug(raw)

    @pytest.mark.parametrize('raw', ['retry-queue', 'T3', '20260928-missing', 'a_b', 'x' * 64])
    def test_slug_confinement_keeps_every_path_under_the_state_directory(
        self, raw: str, tmp_path: Path
    ) -> None:
        slug = Slug(raw)
        state = tmp_path.joinpath('.mightymodels')

        assert workspace_at(tmp_path).ticket_file(slug) == state.joinpath(raw, 'ticket.yml')
        assert workspace_at(tmp_path).task_brief(slug, 3) == state.joinpath(
            raw, 'briefs', 'task-03.md'
        )

    def test_slug_confinement_every_slug_taking_tool_uses_the_one_slug_type(self) -> None:
        slugs = {
            tool.__name__: [
                variant.model_fields['slug'].annotation
                for variant in request_variants(tool)
                if 'slug' in variant.model_fields
            ]
            for tool in TOOLS
        }
        taking_a_slug = {name: annotations for name, annotations in slugs.items() if annotations}

        assert list(taking_a_slug) == [
            'ticket',
            'task',
            'contract',
            'snapshot',
            'close',
            'failed_fix',
        ]
        assert all(set(annotations) == {Slug} for annotations in taking_a_slug.values())

    def test_slug_confinement_the_one_slug_type_is_the_review_start_payloads_slug(self) -> None:
        assert StartPayload.model_fields['slug'].annotation == Slug | None

    def test_slug_confinement_every_tool_schema_carries_the_slug_pattern(
        self, state_server: StateServer
    ) -> None:
        taking_a_slug = {
            name: tool for name, tool in state_server.tools().items() if required_slugs(tool)
        }

        assert sorted(taking_a_slug) == [
            'close',
            'contract',
            'failed_fix',
            'snapshot',
            'task',
            'ticket',
        ]
        assert all(
            (
                slug,
                tool.input_schema['$defs']['Slug']['$ref'],
                tool.input_schema['$defs']['SlugText'],
            )
            == (
                {'$ref': '#/$defs/Slug'},
                '#/$defs/SlugText',
                {'maxLength': SLUG_LIMIT, 'pattern': SLUG_PATTERN, 'type': 'string'},
            )
            for tool in taking_a_slug.values()
            for slug in required_slugs(tool)
        )
