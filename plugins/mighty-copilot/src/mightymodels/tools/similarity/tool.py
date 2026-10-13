"""The `similarity` tool: its handler takes the request and asks the similarity service.

`search` takes the text to look for, and the schema refuses a `search` without it. The kind
narrows the search to one kind of row.

`ResolvedSimilarity` is a plain assignment because the SDK does not see a `Resolve` marker behind
a PEP 695 `type` alias and would put the parameter in the tool's schema.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated

from mcp.server.mcpserver import Context, Resolve

from mightymodels.tools.protocol import (
    ActionHandler,
    ActionTool,
    ServedState,
    ServiceHandler,
    dispatch_to_service,
    served_services,
)
from mightymodels.tools.similarity.schema import (
    SimilarityAction,
    SimilarityRequest,
    SimilarityView,
)
from mightymodels.tools.similarity.service import SimilarityService


def search_similar(similarity: SimilarityService, request: SimilarityRequest) -> SimilarityView:
    return similarity.search(request.query, request.kind)


def lifespan_similarity(ctx: Context[ServedState]) -> SimilarityService:
    return served_services(ctx).similarity


ResolvedSimilarity = Annotated[SimilarityService, Resolve(lifespan_similarity)]


@dataclass(slots=True, kw_only=True, frozen=True)
class SimilarityTool:
    handlers: Mapping[
        SimilarityAction, ServiceHandler[SimilarityService, SimilarityRequest, SimilarityView]
    ]

    def similarity(
        self, request: SimilarityRequest, *, similar: ResolvedSimilarity
    ) -> SimilarityView:
        """Search the stored ledger entries, scout reports, review findings and crashouts."""
        return dispatch_to_service(self.handlers, request.action, request, service=similar)


similarity_tool = SimilarityTool(
    handlers=MappingProxyType(
        {SimilarityAction.SEARCH: ActionHandler(variant=SimilarityRequest, handle=search_similar)}
    )
)
similarity_action_tool: ActionTool[
    SimilarityAction, SimilarityService, SimilarityRequest, SimilarityView
] = similarity_tool
