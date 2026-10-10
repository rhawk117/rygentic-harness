from pathlib import Path


class TuneError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class StateMissingError(TuneError):
    def __init__(self, path: Path) -> None:
        super().__init__(f'no tuning run at {path}; run `vibe-code tune init` first')


class StateExistsError(TuneError):
    def __init__(self, path: Path) -> None:
        super().__init__(f'a tuning run already exists at {path}; pass --force to replace it')


class IncompatibleStateError(TuneError):
    def __init__(self, path: Path) -> None:
        super().__init__(
            f'{path} was written by another version of vibe-code; finish that run with the '
            'version that started it, or start over with `init --force`'
        )


class MalformedAnswerError(TuneError):
    def __init__(self, packet_id: str, reason: str) -> None:
        super().__init__(f'answer for packet {packet_id} has the wrong shape: {reason}')


class MissingFrontmatterError(TuneError):
    def __init__(self, path: Path) -> None:
        super().__init__(f'{path} has no YAML frontmatter with name and description')


class UnknownSkillError(TuneError):
    def __init__(self, request: str, skill: str) -> None:
        super().__init__(f'the trigger set names unknown skill {skill!r} for {request!r}')


class InvalidSkillNameError(TuneError):
    def __init__(self, name: str) -> None:
        super().__init__(f'skill name {name!r} must be lowercase letters, digits and hyphens')


class UnsafeSkillNameError(TuneError):
    def __init__(self, name: str) -> None:
        super().__init__(f'skill name {name!r} would stage outside the routing project')


class MalformedTriggerSetError(TuneError):
    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f'{path} is not a valid trigger set: {reason}')


class DuplicateSkillError(TuneError):
    def __init__(self, name: str) -> None:
        super().__init__(f'two skill files declare the name {name!r}')


class DuplicateRequestError(TuneError):
    def __init__(self, request: str) -> None:
        super().__init__(f'the trigger set lists {request!r} more than once')


class TruncatedRequestError(TuneError):
    def __init__(self, request: str) -> None:
        super().__init__(
            f'request {request!r} was cut short by a YAML comment; quote any request '
            'that contains #'
        )


class EmptySplitError(TuneError):
    def __init__(self, split: str) -> None:
        super().__init__(f'the {split} split is empty; add more trigger examples')


class PacketNotPendingError(TuneError):
    def __init__(self, packet_id: str) -> None:
        super().__init__(f'packet {packet_id!r} is not awaiting an answer; run `next`')


class InvalidVerdictError(TuneError):
    def __init__(self, packet_id: str, reason: str) -> None:
        super().__init__(f'rejected answer for {packet_id}: {reason}')


class InvalidProposalError(TuneError):
    def __init__(self, reason: str) -> None:
        super().__init__(f'rejected proposal: {reason}')


class RunFinishedError(TuneError):
    def __init__(self) -> None:
        super().__init__('the run is finished; use `report` or `apply`')


class RouterUnavailableError(TuneError):
    def __init__(self, executable: str) -> None:
        super().__init__(
            f'{executable!r} is not on PATH; pass its location with --claude, '
            'or start the run with --judge subagent'
        )


class RoutingFailedError(TuneError):
    def __init__(self, request: str, detail: str) -> None:
        reason = detail or 'no output'
        super().__init__(
            f'the headless session for {request!r} ended without a verdict ({reason}); '
            'rerun `route`, finished packets are kept'
        )


class NothingToRouteError(TuneError):
    def __init__(self, stage: str) -> None:
        super().__init__(f'the run is {stage}, not waiting on routing; run `next`')


class StaleSkillError(TuneError):
    def __init__(self, path: Path) -> None:
        super().__init__(f'{path} changed since `init`; rerun the tuning instead of overwriting it')


class RewriteMismatchError(TuneError):
    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f'refusing to write {path}: {reason}')


class JudgeNotRoutedError(TuneError):
    def __init__(self, judge: str) -> None:
        super().__init__(f'the {judge} judge has no router; use `next` and judge the packets')


class InvalidOptionsError(TuneError):
    def __init__(self, reason: str) -> None:
        super().__init__(f'invalid options: {reason}')
