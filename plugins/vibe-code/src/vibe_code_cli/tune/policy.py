import re
import string
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from vibe_code_cli.tune.domain.scoring import Scorecard
from vibe_code_cli.tune.domain.values import (
    JudgeRecord,
    LoopOptions,
    RoundResult,
    Skill,
    Split,
    Stage,
    TriggerExample,
)
from vibe_code_cli.tune.errors import (
    DuplicateRequestError,
    EmptySplitError,
    InvalidOptionsError,
    InvalidProposalError,
    InvalidSkillNameError,
    InvalidVerdictError,
    NothingToRouteError,
    RewriteMismatchError,
    RunFinishedError,
    StaleSkillError,
    UnknownSkillError,
)

FORBIDDEN_DESCRIPTION_CHARACTERS = frozenset("<>")
SKILL_NAME_CHARACTERS = frozenset(string.ascii_lowercase + string.digits + "-")

type FrontmatterMapping = dict[str, object]
type TriggerSetProblem = UnknownSkillError | DuplicateRequestError | EmptySplitError
type Checks = tuple[tuple[bool, str], ...]


def first_failure(checks: Checks) -> str | None:
    failed = (message for failed, message in checks if failed)
    return next(failed, None)


@runtime_checkable
class RoundTally(Protocol):
    @property
    def rounds(self) -> tuple[RoundResult, ...]: ...

    @property
    def stale_rounds(self) -> int: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class SkillPolicy:
    name_characters: frozenset[str] = SKILL_NAME_CHARACTERS

    def is_valid_skill_name(self, name: str) -> bool:
        return (
            bool(name)
            and set(name) <= self.name_characters
            and not name.startswith("-")
        )

    def get_skill_name_problem(
        self, skills: Sequence[Skill]
    ) -> InvalidSkillNameError | None:
        invalid = (
            skill.name for skill in skills if not self.is_valid_skill_name(skill.name)
        )
        if not (name := next(invalid, None)):
            return None

        return InvalidSkillNameError(name)


@dataclass(slots=True, kw_only=True, frozen=True)
class TriggerSetPolicy:
    required_splits: tuple[Split, ...] = tuple(Split)

    def find_duplicate_request(self, examples: Sequence[TriggerExample]) -> str | None:
        requests = [example.request for example in examples]
        repeated = (request for request in requests if requests.count(request) > 1)
        return next(repeated, None)

    def find_unknown_skill(
        self,
        examples: Sequence[TriggerExample],
        skill_names: frozenset[str],
    ) -> tuple[str, str] | None:
        unknown = (
            (example.request, skill)
            for example in examples
            for skill in sorted(example.expected - skill_names)
        )
        return next(unknown, None)

    def find_missing_split(self, examples: Sequence[TriggerExample]) -> Split | None:
        present = {example.split for example in examples}
        missing = (split for split in self.required_splits if split not in present)
        return next(missing, None)

    def get_duplicate_request_problem(
        self,
        examples: Sequence[TriggerExample],
    ) -> DuplicateRequestError | None:
        if not (duplicate := self.find_duplicate_request(examples)):
            return None

        return DuplicateRequestError(duplicate)

    def get_unknown_skill_problem(
        self,
        examples: Sequence[TriggerExample],
        skill_names: frozenset[str],
    ) -> UnknownSkillError | None:
        if not (unknown := self.find_unknown_skill(examples, skill_names)):
            return None

        request, skill = unknown
        return UnknownSkillError(request, skill)

    def get_empty_split_problem(
        self,
        examples: Sequence[TriggerExample],
    ) -> EmptySplitError | None:
        if not (missing := self.find_missing_split(examples)):
            return None

        return EmptySplitError(missing)

    def get_trigger_set_problem(
        self,
        examples: Sequence[TriggerExample],
        skill_names: frozenset[str],
    ) -> TriggerSetProblem | None:
        return (
            self.get_duplicate_request_problem(examples)
            or self.get_unknown_skill_problem(examples, skill_names)
            or self.get_empty_split_problem(examples)
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class RunStagePolicy:
    def get_finished_run_problem(self, stage: Stage) -> RunFinishedError | None:
        if stage is not Stage.DONE:
            return None

        return RunFinishedError()

    def get_routing_stage_problem(self, stage: Stage) -> NothingToRouteError | None:
        if stage is Stage.JUDGING:
            return None

        return NothingToRouteError(stage)


@dataclass(slots=True, kw_only=True, frozen=True)
class AnswerPolicy:
    def expected_answer_keys(self, size: int) -> set[str]:
        return {f"q{index}" for index in range(1, size + 1)}

    def find_stray_skills(
        self,
        record: JudgeRecord,
        verdicts: Sequence[frozenset[str]],
    ) -> list[str]:
        named = frozenset[str]().union(*verdicts)
        return sorted(named - frozenset(record.skill_order))

    def get_answer_keys_problem(
        self,
        packet_id: str,
        keys: Collection[str],
        size: int,
    ) -> InvalidVerdictError | None:
        expected = self.expected_answer_keys(size)
        if set(keys) == expected:
            return None

        ordered = sorted(expected)
        return InvalidVerdictError(packet_id, f"answer keys must be exactly {ordered}")

    def get_verdict_problem(
        self,
        record: JudgeRecord,
        verdicts: Sequence[frozenset[str]],
    ) -> InvalidVerdictError | None:
        expected = len(record.request_ids)
        received = len(verdicts)
        if received != expected:
            reason = f"expected {expected} verdicts, got {received}"
            return InvalidVerdictError(record.packet_id, reason)

        if stray := self.find_stray_skills(record, verdicts):
            return InvalidVerdictError(record.packet_id, f"unknown skill names {stray}")

        return None


@dataclass(slots=True, kw_only=True, frozen=True)
class Proposal:
    description: str
    current: str
    when_to_use: str
    rejected: tuple[str, ...]

    @property
    def text(self) -> str:
        return self.description.strip()

    @property
    def listing_chars(self) -> int:
        return len(self.text) + len(self.when_to_use)


@dataclass(slots=True, kw_only=True, frozen=True)
class ProposalPolicy:
    forbidden_characters: frozenset[str] = FORBIDDEN_DESCRIPTION_CHARACTERS

    def is_printable(self, text: str) -> bool:
        return all(character.isprintable() or character == "\n" for character in text)

    def has_forbidden_characters(self, text: str) -> bool:
        return bool(self.forbidden_characters & set(text))

    def limit_checks(self, proposal: Proposal, options: LoopOptions) -> Checks:
        description_limit = options.max_description_chars
        listing_limit = options.max_listing_chars
        return (
            (
                len(proposal.text) > description_limit,
                f"longer than {description_limit} characters",
            ),
            (
                proposal.listing_chars > listing_limit,
                f"with when_to_use it passes the {listing_limit}-character listing limit",
            ),
        )

    def text_checks(self, proposal: Proposal) -> Checks:
        text = proposal.text
        return (
            (not text, "the description is empty"),
            (
                self.has_forbidden_characters(text),
                "angle brackets are not allowed in descriptions",
            ),
            (not self.is_printable(text), "control characters are not allowed"),
            (text == proposal.current.strip(), "identical to the current description"),
            (
                text in proposal.rejected,
                "this exact description was already tried and rejected",
            ),
        )

    def get_proposal_problem(
        self, proposal: Proposal, options: LoopOptions
    ) -> InvalidProposalError | None:
        checks = (*self.text_checks(proposal), *self.limit_checks(proposal, options))
        reason = first_failure(checks)
        if reason is None:
            return None
        return InvalidProposalError(reason)


@dataclass(slots=True, kw_only=True, frozen=True)
class RoundPolicy:
    def is_winning_candidate(
        self, current: Scorecard, candidate: Scorecard, options: LoopOptions
    ) -> bool:
        validation_gain = candidate.validation - current.validation
        if validation_gain > options.min_gain:
            return True
        return validation_gain >= 0 and candidate.train > current.train

    def is_run_exhausted(self, tally: RoundTally, options: LoopOptions) -> bool:
        out_of_rounds = len(tally.rounds) >= options.max_rounds
        out_of_patience = tally.stale_rounds >= options.patience
        return out_of_rounds or out_of_patience


@dataclass(slots=True, kw_only=True, frozen=True)
class LoopOptionsPolicy:
    def option_checks(self, options: LoopOptions) -> Checks:
        routing = options.routing
        return (
            (options.batch_size < 1, "--batch-size must be at least 1"),
            (options.max_rounds < 1, "--max-rounds must be at least 1"),
            (options.patience < 1, "--patience must be at least 1"),
            (
                not 0 < options.validation_fraction < 1,
                "--validation-fraction must be between 0 and 1",
            ),
            (routing.concurrency < 1, "--concurrency must be at least 1"),
            (routing.timeout_seconds <= 0, "--timeout must be positive"),
            (
                options.max_description_chars < 1,
                "max description length must be positive",
            ),
        )

    def get_options_problem(self, options: LoopOptions) -> InvalidOptionsError | None:
        reason = first_failure(self.option_checks(options))
        if reason is None:
            return None
        return InvalidOptionsError(reason)


def without_description(mapping: FrontmatterMapping) -> FrontmatterMapping:
    return {key: value for key, value in mapping.items() if key != "description"}


@dataclass(slots=True, kw_only=True, frozen=True)
class Rewrite:
    path: Path
    description: str
    original: FrontmatterMapping
    rewritten: FrontmatterMapping | None


@dataclass(slots=True, kw_only=True, frozen=True)
class SkillFilePolicy:
    def is_unchanged_since_init(
        self,
        skill: Skill,
        original: FrontmatterMapping,
    ) -> bool:
        current = str(original.get("description", "")).strip()
        return current == skill.description

    def get_stale_skill_problem(
        self,
        skill: Skill,
        original: FrontmatterMapping,
    ) -> StaleSkillError | None:
        if self.is_unchanged_since_init(skill, original):
            return None
        return StaleSkillError(Path(skill.path))

    def rewrite_checks(
        self,
        rewrite: Rewrite,
        rewritten: FrontmatterMapping,
    ) -> Checks:
        kept = without_description(rewrite.original)
        return (
            (
                rewritten.get("description") != rewrite.description,
                "the description would not read back intact",
            ),
            (
                without_description(rewritten) != kept,
                "other frontmatter keys would change",
            ),
        )

    def get_rewrite_problem(self, rewrite: Rewrite) -> RewriteMismatchError | None:
        if not (rewritten := rewrite.rewritten):
            return RewriteMismatchError(rewrite.path, "the frontmatter would not parse")

        rewrite_checks = self.rewrite_checks(rewrite, rewritten)
        if reason := first_failure(rewrite_checks):
            return RewriteMismatchError(rewrite.path, reason)

        return None


@dataclass(slots=True, kw_only=True, frozen=True)
class TransitionPolicies:
    answers: AnswerPolicy = field(default_factory=AnswerPolicy)
    proposals: ProposalPolicy = field(default_factory=ProposalPolicy)
    rounds: RoundPolicy = field(default_factory=RoundPolicy)
