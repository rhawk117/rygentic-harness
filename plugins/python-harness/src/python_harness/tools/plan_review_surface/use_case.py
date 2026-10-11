"""Choose the codebase or diff target a request names and plan its review surface."""

from python_harness.core.workspace import Workspace
from python_harness.imports.domain import ProjectIndex
from python_harness.surface.domain import CodebaseTarget, DiffTarget, SurfacePlan, Target
from python_harness.surface.services import plan_surface
from python_harness.tools.errors import HeadWithoutBaseError, PathsWithDiffBaseError
from python_harness.tools.plan_review_surface.schema import SurfaceRequest


def check_target_choice(
    request: SurfaceRequest,
) -> PathsWithDiffBaseError | HeadWithoutBaseError | None:
    if request.diff_base is not None and request.paths is not None:
        return PathsWithDiffBaseError()
    if request.diff_base is None and request.diff_head is not None:
        return HeadWithoutBaseError(request.diff_head)
    return None


def diff_target_from(base: str, head: str | None) -> DiffTarget:
    if head is None:
        return DiffTarget(base)
    return DiffTarget(base, head)


def codebase_target_from(paths: tuple[str, ...] | None) -> CodebaseTarget:
    if paths is None:
        return CodebaseTarget()
    return CodebaseTarget(paths)


def target_from(request: SurfaceRequest) -> Target:
    if request.diff_base is not None:
        return diff_target_from(request.diff_base, request.diff_head)
    return codebase_target_from(request.paths)


def run(workspace: Workspace, index: ProjectIndex, request: SurfaceRequest) -> SurfacePlan:
    if (problem := check_target_choice(request)) is not None:
        raise problem
    return plan_surface(workspace, index, target_from(request))
