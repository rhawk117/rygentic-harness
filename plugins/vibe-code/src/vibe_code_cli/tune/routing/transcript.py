from dataclasses import dataclass

import msgspec

SKILL_TOOL = 'Skill'
CLEAN_SUBTYPES = frozenset({'success', 'error_max_turns'})


class StreamEvent(msgspec.Struct, frozen=True):
    type: str
    subtype: str = ''
    skills: list[str] = []
    message: msgspec.Raw = msgspec.Raw(b'null')
    is_error: bool = False
    result: str = ''


class ContentBlock(msgspec.Struct, frozen=True):
    type: str
    name: str = ''
    input: dict[str, object] = {}

    @property
    def invoked_skill(self) -> str | None:
        if self.type != 'tool_use' or self.name != SKILL_TOOL:
            return None
        skill = self.input.get('skill')
        if not isinstance(skill, str):
            return None
        return skill


class AssistantMessage(msgspec.Struct, frozen=True):
    content: list[ContentBlock] = []


@dataclass(slots=True, kw_only=True, frozen=True)
class SessionEvents:
    events: tuple[StreamEvent, ...]

    def of_type(self, kind: str) -> list[StreamEvent]:
        return [event for event in self.events if event.type == kind]

    def listed(self) -> frozenset[str]:
        inits = [event for event in self.of_type('system') if event.subtype == 'init']
        return frozenset(name for event in inits for name in event.skills)

    def invoked(self) -> tuple[str, ...]:
        messages = [
            msgspec.json.decode(event.message, type=AssistantMessage)
            for event in self.of_type('assistant')
        ]
        blocks = [block for message in messages for block in message.content]
        return tuple(skill for block in blocks if (skill := block.invoked_skill))

    def outcome(self) -> StreamEvent | None:
        results = self.of_type('result')
        if not results:
            return None
        return results[-1]


def read_events(stream: str) -> SessionEvents:
    lines = [line for line in stream.splitlines() if line.startswith('{')]
    events = tuple(msgspec.json.decode(line, type=StreamEvent) for line in lines)
    return SessionEvents(events=events)


@dataclass(slots=True, kw_only=True, frozen=True)
class SessionTranscript:
    outcome: StreamEvent | None
    listed: frozenset[str]
    invoked: tuple[str, ...]

    @property
    def finished(self) -> bool:
        outcome = self.outcome
        if outcome is None or outcome.subtype not in CLEAN_SUBTYPES:
            return False
        return outcome.subtype != 'success' or not outcome.is_error

    @property
    def failure_detail(self) -> str:
        outcome = self.outcome
        if outcome is None:
            return ''
        return outcome.result.strip() or outcome.subtype

    def unlisted(self, team: frozenset[str]) -> list[str]:
        return sorted(team - self.listed)

    def loaded_skills(self, team: frozenset[str]) -> frozenset[str]:
        return frozenset(skill for skill in self.invoked if skill in team)


def parse_transcript(stream: str) -> SessionTranscript:
    events = read_events(stream)
    return SessionTranscript(
        outcome=events.outcome(),
        listed=events.listed(),
        invoked=events.invoked(),
    )
