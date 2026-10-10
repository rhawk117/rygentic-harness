from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from vibe_code_cli.tune.collisions import Bm25CollisionDetector, CollisionDetector
from vibe_code_cli.tune.domain.state import LoopState, RunSetup, start_loop
from vibe_code_cli.tune.domain.values import Judge, JudgeRecord, LoopOptions, Stage
from vibe_code_cli.tune.errors import JudgeNotRoutedError, PacketNotPendingError, StateExistsError
from vibe_code_cli.tune.policy import (
    LoopOptionsPolicy,
    RunStagePolicy,
    SkillPolicy,
    TransitionPolicies,
    TriggerSetPolicy,
)
from vibe_code_cli.tune.report import MarkdownReport
from vibe_code_cli.tune.repository import (
    FileSkillRepository,
    SkillRepository,
    TriggerSetReader,
    YamlTriggerSetReader,
)
from vibe_code_cli.tune.routing import Router, RouterFactory
from vibe_code_cli.tune.schemas import (
    ApplyResult,
    DoneWork,
    JudgePacket,
    JudgeWork,
    ProposalAnswer,
    ProposePacket,
    RouteWork,
    StatusSummary,
    Work,
    applied_change,
    judge_packets,
    propose_packet,
    status_summary,
    verdicts_from_answer,
)
from vibe_code_cli.tune.store import (
    LoopStore,
    PacketPublisher,
    RandomRunIds,
    RunIdSource,
    decode_answer,
)

FINISHED = DoneWork(message='tuning finished; run `report`, then `apply`')
NOTHING_LEFT = DoneWork(message='no training failures remain; tuning finished')


@dataclass(slots=True, kw_only=True, frozen=True)
class StartRequest:
    skills: tuple[Path, ...]
    triggers: Path
    options: LoopOptions
    force: bool = False


@dataclass(slots=True, kw_only=True, frozen=True)
class TuningService:
    store: LoopStore[LoopState]
    packets: PacketPublisher[JudgePacket]
    skills: SkillRepository = field(default_factory=FileSkillRepository)
    triggers: TriggerSetReader = field(default_factory=YamlTriggerSetReader)
    collisions: CollisionDetector = field(default_factory=Bm25CollisionDetector)
    run_ids: RunIdSource = field(default_factory=RandomRunIds)
    names: SkillPolicy = field(default_factory=SkillPolicy)
    trigger_sets: TriggerSetPolicy = field(default_factory=TriggerSetPolicy)
    stages: RunStagePolicy = field(default_factory=RunStagePolicy)
    option_limits: LoopOptionsPolicy = field(default_factory=LoopOptionsPolicy)
    transitions: TransitionPolicies = field(default_factory=TransitionPolicies)

    def start(self, request: StartRequest) -> StatusSummary:
        if problem := self.option_limits.get_options_problem(request.options):
            raise problem
        with self.store.transaction() as session:
            if session.exists() and not request.force:
                raise StateExistsError(self.store.path)
            state = start_loop(self.load_setup(request))
            session.commit(state)
        return status_summary(state)

    def load_setup(self, request: StartRequest) -> RunSetup:
        examples = self.triggers.read(request.triggers, request.options)
        skills = self.skills.discover(request.skills)
        if problem := self.names.get_skill_name_problem(skills):
            raise problem
        names = frozenset(skill.name for skill in skills)
        if problem := self.trigger_sets.get_trigger_set_problem(examples, names):
            raise problem
        return RunSetup(
            run_id=self.run_ids.new_id(),
            skills=skills,
            examples=examples,
            options=request.options,
        )

    def next_work(self) -> Work:
        with self.store.transaction() as session:
            state, work = self.plan_work(session.read())
            session.commit(state)
        return work

    def plan_work(self, state: LoopState) -> tuple[LoopState, Work]:
        if state.stage is Stage.JUDGING:
            return self.judging_work(state)
        if state.stage is Stage.PROPOSING:
            return self.proposal_work(state)
        return state, FINISHED

    def judging_work(self, state: LoopState) -> tuple[LoopState, JudgeWork | RouteWork]:
        planned = state.with_judging_planned()
        if planned.setup.options.judge.routed:
            remaining = len(planned.setup.examples) - len(planned.in_progress.verdicts)
            return planned, RouteWork(requests=remaining)
        published = self.packets.publish(judge_packets(planned))
        return planned, JudgeWork(packets=published)

    def proposal_work(self, state: LoopState) -> tuple[LoopState, ProposePacket | DoneWork]:
        assigned = state.with_proposal_assigned()
        collisions = self.collisions.find(assigned.accepted.descriptions)
        packet = propose_packet(assigned, collisions)
        if packet is None:
            return assigned, NOTHING_LEFT
        return assigned, packet

    def submit(self, packet_id: str, answer: bytes) -> StatusSummary:
        with self.store.transaction() as session:
            state = session.read()
            if problem := self.stages.get_finished_run_problem(state.stage):
                raise problem
            updated = self.apply_answer(state, packet_id, answer)
            session.commit(updated)
        return status_summary(updated)

    def apply_answer(self, state: LoopState, packet_id: str, answer: bytes) -> LoopState:
        records = {record.packet_id: record for record in state.pending_judge_records}
        if record := records.get(packet_id):
            size = len(record.request_ids)
            answers = self.transitions.answers
            verdicts = verdicts_from_answer(packet_id, answer, size, answers=answers)
            return state.with_verdicts(packet_id, verdicts, self.transitions)
        proposal = state.pending_proposal
        if proposal is None or proposal.packet_id != packet_id:
            raise PacketNotPendingError(packet_id)
        decoded = decode_answer(packet_id, answer, ProposalAnswer)
        return state.with_proposal(packet_id, decoded.description, self.transitions)

    def status(self) -> StatusSummary:
        return status_summary(self.store.read())


@dataclass(slots=True, kw_only=True, frozen=True)
class RoutingService:
    store: LoopStore[LoopState]
    routers: Mapping[Judge, RouterFactory]
    stages: RunStagePolicy = field(default_factory=RunStagePolicy)
    transitions: TransitionPolicies = field(default_factory=TransitionPolicies)

    async def route_pending(self) -> StatusSummary:
        with self.store.transaction() as session:
            state = session.read()
            if problem := self.stages.get_routing_stage_problem(state.stage):
                raise problem
            router = self.router_for(state)
            state = state.with_judging_planned()
            session.commit(state)
            for record in state.pending_judge_records:
                state = await self.route_record(router, state, record)
                session.commit(state)
        return status_summary(state)

    async def route_record(
        self, router: Router, state: LoopState, record: JudgeRecord
    ) -> LoopState:
        requests = state.setup.requests_by_id
        batch = [requests[request_id] for request_id in record.request_ids]
        routed = await router.route(state.in_progress.descriptions, batch)
        seen = state.with_competitors(routed.competitors)
        return seen.with_verdicts(record.packet_id, routed.verdicts, self.transitions)

    def router_for(self, state: LoopState) -> Router:
        judge = state.setup.options.judge
        factory = self.routers.get(judge)
        if factory is None:
            raise JudgeNotRoutedError(judge)
        return factory.build(state.setup.skills, state.setup.options.routing)


@dataclass(slots=True, kw_only=True, frozen=True)
class PublishingService:
    store: LoopStore[LoopState]
    skills: SkillRepository = field(default_factory=FileSkillRepository)
    collisions: CollisionDetector = field(default_factory=Bm25CollisionDetector)

    def report(self) -> str:
        state = self.store.read()
        collisions = self.collisions.find(state.accepted.descriptions)
        return MarkdownReport(state=state, collisions=collisions).render()

    def apply(self, *, dry_run: bool) -> ApplyResult:
        state = self.store.read()
        final = state.accepted.descriptions
        targets = state.setup.changed(final)
        planned = [self.skills.plan_write(skill, final[skill.name]) for skill in targets]
        if not dry_run:
            for write in planned:
                write.commit()
        changes = tuple(applied_change(skill, final[skill.name]) for skill in targets)
        return ApplyResult(written=not dry_run, changes=changes)

    def lint(self, locations: Sequence[Path]) -> list[str]:
        skills = self.skills.discover(locations)
        descriptions = {skill.name: skill.description for skill in skills}
        return [collision.describe() for collision in self.collisions.find(descriptions)]
