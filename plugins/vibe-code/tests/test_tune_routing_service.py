import asyncio
import dataclasses

import msgspec
import pytest
from vibe_code_cli.tune.domain.values import Judge, Stage
from vibe_code_cli.tune.errors import JudgeNotRoutedError, NothingToRouteError, RoutingFailedError
from vibe_code_cli.tune.services import StartRequest
from vibe_code_cli.tune.tests.support import MemoryRun


class TestRoutingService:
    @pytest.fixture
    def routed(self, memory_run: MemoryRun, start_request: StartRequest) -> MemoryRun:
        options = msgspec.structs.replace(start_request.options, judge=Judge.CLAUDE_CODE)
        memory_run.tuning.start(dataclasses.replace(start_request, options=options))
        return memory_run

    def test_route_judges_every_request(self, routed: MemoryRun) -> None:
        status = asyncio.run(routed.routing.route_pending())
        assert status.stage == Stage.PROPOSING.value
        assert routed.state.history.baseline is not None
        assert len(routed.state.history.baseline.verdicts) == len(routed.state.setup.examples)

    def test_failure_keeps_packets_already_routed(self, routed: MemoryRun) -> None:
        routed.routers.fail_on = 'haiku'
        with pytest.raises(RoutingFailedError):
            asyncio.run(routed.routing.route_pending())
        judged = len(routed.state.in_progress.verdicts)
        routed.routers.fail_on = None
        asyncio.run(routed.routing.route_pending())
        assert 0 < judged < len(routed.state.setup.examples)
        assert routed.state.stage is Stage.PROPOSING

    def test_route_outside_judging_is_refused(self, routed: MemoryRun) -> None:
        asyncio.run(routed.routing.route_pending())
        with pytest.raises(NothingToRouteError):
            asyncio.run(routed.routing.route_pending())
        assert routed.routers.built == 1

    def test_unrouted_judge_is_refused(
        self, memory_run: MemoryRun, start_request: StartRequest
    ) -> None:
        memory_run.tuning.start(start_request)
        with pytest.raises(JudgeNotRoutedError):
            asyncio.run(memory_run.routing.route_pending())
        assert memory_run.routers.built == 0

    def test_competitors_are_recorded_on_the_state_after_a_route(self, routed: MemoryRun) -> None:
        asyncio.run(routed.routing.route_pending())
        assert set(routed.state.competitors) == {'code-review', 'debug'}
