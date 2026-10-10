from collections.abc import Mapping, Sequence
from typing import Literal

import msgspec

from vibe_code_cli.tune.collisions import Collision
from vibe_code_cli.tune.domain.scoring import score_verdicts
from vibe_code_cli.tune.domain.state import LoopState
from vibe_code_cli.tune.domain.values import (
    Evaluation,
    JudgeRecord,
    Skill,
    TriggerExample,
)
from vibe_code_cli.tune.policy import AnswerPolicy
from vibe_code_cli.tune.store import PacketFile, decode_answer

JUDGE_MESSAGE = (
    "give each packet file to its own fresh subagent; do not open the files yourself, "
    "they hold validation requests that must stay hidden from you"
)
ROUTE_MESSAGE = (
    "run `vibe-code tune route`: one headless claude session per request, saved after each "
    "packet; rerun it if it is interrupted"
)


class JudgePacket(msgspec.Struct, frozen=True, kw_only=True):
    kind: Literal["judge"] = "judge"
    packet_id: str
    skills: dict[str, str]
    requests: dict[str, str]


class ProposePacket(msgspec.Struct, frozen=True, kw_only=True):
    kind: Literal["propose"] = "propose"
    packet_id: str
    skill: str
    current: str
    when_to_use: str
    other_skills: dict[str, str]
    missed: tuple[str, ...]
    false_triggers: tuple[str, ...]
    rejected: tuple[str, ...]
    collisions: tuple[str, ...]
    max_chars: int


class JudgeWork(msgspec.Struct, frozen=True, kw_only=True):
    kind: Literal["judge"] = "judge"
    packets: tuple[PacketFile, ...]
    message: str = JUDGE_MESSAGE


class RouteWork(msgspec.Struct, frozen=True, kw_only=True):
    kind: Literal["route"] = "route"
    requests: int
    message: str = ROUTE_MESSAGE


class DoneWork(msgspec.Struct, frozen=True, kw_only=True):
    kind: Literal["done"] = "done"
    message: str


type Work = JudgeWork | RouteWork | ProposePacket | DoneWork


class ProposalAnswer(msgspec.Struct, frozen=True, kw_only=True):
    description: str


class AppliedChange(msgspec.Struct, frozen=True, kw_only=True):
    skill: str
    path: str
    description: str


class ApplyResult(msgspec.Struct, frozen=True, kw_only=True):
    written: bool
    changes: tuple[AppliedChange, ...]


class ScoreSummary(msgspec.Struct, frozen=True, kw_only=True):
    train: float
    validation: float


class StatusSummary(msgspec.Struct, frozen=True, kw_only=True):
    stage: str
    judge: str
    rounds: int
    accepted_rounds: int
    stale_rounds: int
    pending_packets: tuple[str, ...]
    baseline: ScoreSummary | None
    current: ScoreSummary | None


def listing_text(description: str, when_to_use: str) -> str:
    if not when_to_use:
        return description
    return f"{description}\n{when_to_use}"


def listed_skills(
    record: JudgeRecord,
    evaluation: Evaluation,
    skills: Mapping[str, Skill],
) -> dict[str, str]:
    return {
        name: listing_text(evaluation.descriptions[name], skills[name].when_to_use)
        for name in record.skill_order
    }


def numbered_requests(
    record: JudgeRecord, requests_by_id: Mapping[str, str]
) -> dict[str, str]:
    numbered = enumerate(record.request_ids, start=1)
    return {f"q{index}": requests_by_id[request_id] for index, request_id in numbered}


def judge_packet(record: JudgeRecord, state: LoopState) -> JudgePacket:
    skills = listed_skills(record, state.in_progress, state.setup.skills_by_name)
    requests = numbered_requests(record, state.setup.requests_by_id)
    return JudgePacket(packet_id=record.packet_id, skills=skills, requests=requests)


def judge_packets(state: LoopState) -> list[JudgePacket]:
    return [judge_packet(record, state) for record in state.pending_judge_records]


def propose_packet(
    state: LoopState, collisions: Sequence[Collision]
) -> ProposePacket | None:
    record = state.pending_proposal
    if record is None:
        return None

    skill = record.skill
    descriptions = state.accepted.descriptions
    failures = state.failures_for(skill)
    others = {name: text for name, text in descriptions.items() if name != skill}

    involved = tuple(
        collision.describe() for collision in collisions if collision.involves(skill)
    )
    return ProposePacket(
        packet_id=record.packet_id,
        skill=skill,
        current=descriptions[skill],
        when_to_use=state.setup.skills_by_name[skill].when_to_use,
        other_skills=others,
        missed=failures.missed,
        false_triggers=failures.false_triggers,
        rejected=state.history.rejected_descriptions(skill),
        collisions=involved,
        max_chars=state.setup.options.max_description_chars,
    )


def verdicts_from_answer(
    packet_id: str,
    data: bytes,
    size: int,
    *,
    answers: AnswerPolicy | None = None,
) -> tuple[frozenset[str], ...]:
    policy = answers or AnswerPolicy()
    answer = decode_answer(packet_id, data, dict[str, list[str]])
    if problem := policy.get_answer_keys_problem(packet_id, answer, size):
        raise problem

    return tuple(frozenset(answer[f"q{index}"]) for index in range(1, size + 1))


def applied_change(skill: Skill, description: str) -> AppliedChange:
    return AppliedChange(
        skill=skill.name,
        path=skill.path,
        description=description,
    )


def score_summary(
    examples: tuple[TriggerExample, ...],
    evaluation: Evaluation | None,
) -> ScoreSummary | None:
    if evaluation is None:
        return None

    card = score_verdicts(examples, evaluation.verdicts)
    return ScoreSummary(
        train=round(card.train, 3),
        validation=round(card.validation, 3),
    )


def pending_packet_ids(state: LoopState) -> tuple[str, ...]:
    judged = tuple(record.packet_id for record in state.pending_judge_records)
    proposal = state.pending_proposal
    if proposal is None:
        return judged

    return (*judged, proposal.packet_id)


def status_summary(state: LoopState) -> StatusSummary:
    history = state.history
    examples = state.setup.examples

    return StatusSummary(
        stage=state.stage.value,
        judge=state.setup.options.judge.value,
        rounds=len(history.rounds),
        accepted_rounds=sum(result.accepted for result in history.rounds),
        stale_rounds=history.stale_rounds,
        pending_packets=pending_packet_ids(state),
        baseline=score_summary(examples, history.baseline),
        current=score_summary(examples, history.accepted),
    )
