from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from operator import attrgetter
from typing import Self

import msgspec
from msgspec.structs import replace

from vibe_code_cli.tune.domain.sampling import seeded_rng, shuffled
from vibe_code_cli.tune.domain.scoring import (
    SkillFailures,
    score_verdicts,
    skill_failures,
)
from vibe_code_cli.tune.domain.values import (
    Evaluation,
    JudgeRecord,
    LoopOptions,
    ProposalRecord,
    RoundResult,
    Skill,
    Stage,
    TriggerExample,
)
from vibe_code_cli.tune.errors import PacketNotPendingError
from vibe_code_cli.tune.policy import Proposal, RoundPolicy, TransitionPolicies


class RunSetup(msgspec.Struct, frozen=True, kw_only=True):
    run_id: str
    skills: tuple[Skill, ...]
    examples: tuple[TriggerExample, ...]
    options: LoopOptions

    @property
    def skill_names(self) -> frozenset[str]:
        return frozenset(skill.name for skill in self.skills)

    @property
    def skills_by_name(self) -> dict[str, Skill]:
        return {skill.name: skill for skill in self.skills}

    @property
    def original_descriptions(self) -> dict[str, str]:
        return {skill.name: skill.description for skill in self.skills}

    @property
    def requests_by_id(self) -> dict[str, str]:
        return {example.request_id: example.request for example in self.examples}

    def packet_id(self, kind: str, number: int) -> str:
        return f"{kind}{number}-{self.run_id}"

    def plan_record(self, number: int, batch: tuple[str, ...]) -> JudgeRecord:
        rng = seeded_rng(self.options.seed, f"judge{number}")
        skill_order = shuffled(sorted(self.skill_names), rng)
        packet_id = self.packet_id("j", number)
        return JudgeRecord(
            packet_id=packet_id, request_ids=batch, skill_order=skill_order
        )

    def plan_records(
        self, first: int, request_ids: Sequence[str]
    ) -> tuple[JudgeRecord, ...]:
        size = self.options.batch_size
        rng = seeded_rng(self.options.seed, f"batch{first}")
        order = shuffled(request_ids, rng)
        batches = [order[start : start + size] for start in range(0, len(order), size)]
        numbered = enumerate(batches, start=first)
        return tuple(self.plan_record(number, batch) for number, batch in numbered)

    def changed(self, descriptions: Mapping[str, str]) -> tuple[Skill, ...]:
        return tuple(
            skill
            for skill in self.skills
            if descriptions[skill.name] != skill.description
        )


class Judging(msgspec.Struct, frozen=True, kw_only=True):
    evaluation: Evaluation
    pending: tuple[JudgeRecord, ...] = ()

    @property
    def judged_ids(self) -> frozenset[str]:
        return frozenset(self.evaluation.verdicts)

    @property
    def assigned_ids(self) -> frozenset[str]:
        pending = (
            request_id for record in self.pending for request_id in record.request_ids
        )
        return self.judged_ids | frozenset(pending)

    def record(self, packet_id: str) -> JudgeRecord | None:
        matching = (record for record in self.pending if record.packet_id == packet_id)
        return next(matching, None)

    def with_records(self, records: Sequence[JudgeRecord]) -> Self:
        return replace(self, pending=(*self.pending, *records))

    def with_answer(
        self, record: JudgeRecord, verdicts: Mapping[str, frozenset[str]]
    ) -> Self:
        merged = {**self.evaluation.verdicts, **verdicts}
        evaluation = replace(self.evaluation, verdicts=merged)
        pending = tuple(entry for entry in self.pending if entry is not record)
        return replace(self, evaluation=evaluation, pending=pending)

    def complete(self, total: int) -> bool:
        return len(self.evaluation.verdicts) == total


@dataclass(slots=True, kw_only=True, frozen=True)
class RankedFailure:
    failures: SkillFailures
    attempts: int

    @property
    def priority(self) -> tuple[float, int, str]:
        return self.failures.f1, self.attempts, self.failures.skill


class History(msgspec.Struct, frozen=True, kw_only=True):
    baseline: Evaluation | None = None
    accepted: Evaluation | None = None
    rounds: tuple[RoundResult, ...] = ()
    stale_rounds: int = 0

    @property
    def attempts(self) -> Counter[str]:
        return Counter(result.skill for result in self.rounds)

    def rejected_descriptions(self, skill: str) -> tuple[str, ...]:
        return tuple(
            result.description
            for result in self.rounds
            if result.skill == skill and not result.accepted
        )

    def with_baseline(self, evaluation: Evaluation) -> Self:
        return replace(self, baseline=evaluation, accepted=evaluation)

    def with_candidate(
        self, candidate: Evaluation, setup: RunSetup, policy: RoundPolicy
    ) -> Self:
        if self.accepted is None or candidate.tuned_skill is None:
            return self.with_baseline(candidate)

        skill = candidate.tuned_skill
        current = score_verdicts(setup.examples, self.accepted.verdicts)
        challenger = score_verdicts(setup.examples, candidate.verdicts)
        won = policy.is_winning_candidate(current, challenger, setup.options)

        result = RoundResult(
            number=len(self.rounds) + 1,
            skill=skill,
            description=candidate.descriptions[skill],
            train=challenger.train,
            validation=challenger.validation,
            accepted=won,
        )

        played = (*self.rounds, result)
        if won:
            return replace(
                self,
                accepted=candidate,
                rounds=played,
                stale_rounds=0,
            )

        return replace(self, rounds=played, stale_rounds=self.stale_rounds + 1)

    def weakest(self, failures: Sequence[SkillFailures]) -> str | None:
        attempts = self.attempts
        ranked = [
            RankedFailure(failures=item, attempts=attempts[item.skill])
            for item in failures
            if item.count
        ]
        best = min(ranked, key=attrgetter("priority"), default=None)
        if best is None:
            return None
        return best.failures.skill


class LoopState(msgspec.Struct, frozen=True, kw_only=True):
    setup: RunSetup
    stage: Stage
    judging: Judging | None = None
    history: History = msgspec.field(default_factory=History)
    pending_proposal: ProposalRecord | None = None
    packet_counter: int = 0
    competitors: tuple[str, ...] = ()

    @property
    def in_progress(self) -> Evaluation:
        if self.judging is not None:
            return self.judging.evaluation

        return Evaluation(descriptions=self.setup.original_descriptions)

    @property
    def accepted(self) -> Evaluation:
        if self.history.accepted is not None:
            return self.history.accepted

        return Evaluation(descriptions=self.setup.original_descriptions)

    @property
    def pending_judge_records(self) -> tuple[JudgeRecord, ...]:
        if self.judging is None:
            return ()

        return self.judging.pending

    def failures_for(self, skill: str) -> SkillFailures:
        return skill_failures(
            self.setup.examples,
            self.accepted.verdicts,
            skill,
        )

    def with_judging_planned(self) -> Self:
        judging = self.judging or Judging(evaluation=self.in_progress)
        assigned = judging.assigned_ids

        unassigned = [
            example.request_id
            for example in self.setup.examples
            if example.request_id not in assigned
        ]

        records = self.setup.plan_records(self.packet_counter + 1, unassigned)
        return replace(
            self,
            judging=judging.with_records(records),
            packet_counter=self.packet_counter + len(records),
        )

    def with_verdicts(
        self,
        packet_id: str,
        verdicts: Sequence[frozenset[str]],
        policies: TransitionPolicies | None = None,
    ) -> Self:
        if not (judging := self.judging):
            raise PacketNotPendingError(packet_id)

        if not (record := judging.record(packet_id)):
            raise PacketNotPendingError(packet_id)

        rules = policies or TransitionPolicies()
        if problem := rules.answers.get_verdict_problem(record, verdicts):
            raise problem

        answered = dict(zip(record.request_ids, verdicts, strict=True))
        updated = judging.with_answer(record, answered)

        if not updated.complete(len(self.setup.examples)):
            return replace(self, judging=updated)

        history = self.history.with_candidate(
            updated.evaluation,
            self.setup,
            rules.rounds,
        )

        out_of_budget = rules.rounds.is_run_exhausted(history, self.setup.options)
        finished = bool(history.rounds) and out_of_budget

        stage = Stage.DONE if finished else Stage.PROPOSING
        return replace(
            self,
            stage=stage,
            judging=None,
            history=history,
        )

    def with_competitors(self, names: frozenset[str]) -> Self:
        merged_competitors = set(self.competitors) | (names - self.setup.skill_names)
        merged = sorted(merged_competitors)
        return replace(self, competitors=tuple(merged))

    def with_proposal_assigned(self) -> Self:
        if self.pending_proposal is not None:
            return self

        failures = tuple(map(self.failures_for, self.setup.skill_names))
        if not (target := self.history.weakest(failures)):
            return replace(self, stage=Stage.DONE)

        number = self.packet_counter + 1
        record = ProposalRecord(
            packet_id=self.setup.packet_id("p", number),
            skill=target,
        )

        return replace(self, pending_proposal=record, packet_counter=number)

    def proposal_for(self, record: ProposalRecord, description: str) -> Proposal:
        skill = self.setup.skills_by_name[record.skill]
        return Proposal(
            description=description,
            current=self.accepted.descriptions[record.skill],
            when_to_use=skill.when_to_use,
            rejected=self.history.rejected_descriptions(record.skill),
        )

    def with_proposal(
        self,
        packet_id: str,
        description: str,
        policies: TransitionPolicies | None = None,
    ) -> Self:
        record = self.pending_proposal
        if record is None or record.packet_id != packet_id:
            raise PacketNotPendingError(packet_id)

        rules = policies or TransitionPolicies()
        proposal = self.proposal_for(record, description)
        if problem := rules.proposals.get_proposal_problem(
            proposal, self.setup.options
        ):
            raise problem

        descriptions = {**self.accepted.descriptions, record.skill: proposal.text}
        candidate = Evaluation(descriptions=descriptions, tuned_skill=record.skill)
        judging = Judging(evaluation=candidate)
        return replace(
            self,
            stage=Stage.JUDGING,
            judging=judging,
            pending_proposal=None,
        )


def start_loop(setup: RunSetup) -> LoopState:
    baseline = Evaluation(descriptions=setup.original_descriptions)
    return LoopState(
        setup=setup,
        stage=Stage.JUDGING,
        judging=Judging(evaluation=baseline),
    )
