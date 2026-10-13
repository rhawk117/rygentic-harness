from pathlib import Path

import msgspec
from vibe_code_cli.tune.routing import parse_transcript

FIXTURES = Path(__file__).parent.joinpath('fixtures', 'tune')


def init_event(*skills: str) -> dict[str, object]:
    return {'type': 'system', 'subtype': 'init', 'skills': list(skills)}


def skill_call(name: str) -> dict[str, object]:
    block = {'type': 'tool_use', 'name': 'Skill', 'input': {'skill': name}}
    return {'type': 'assistant', 'message': {'content': [block]}}


def other_tool_call(name: str) -> dict[str, object]:
    block = {'type': 'tool_use', 'name': name, 'input': {'path': 'x'}}
    return {'type': 'assistant', 'message': {'content': [block]}}


def result_event(subtype: str, *, is_error: bool = False, result: str = '') -> dict[str, object]:
    return {'type': 'result', 'subtype': subtype, 'is_error': is_error, 'result': result}


def stream_lines(*events: dict[str, object]) -> str:
    return '\n'.join(msgspec.json.encode(event).decode() for event in events)


class TestParseTranscript:
    finished = stream_lines(
        init_event('jira', 'pysymbols'),
        {'type': 'stream_event'},
        skill_call('jira'),
        skill_call('security-review'),
        other_tool_call('Read'),
        result_event('error_max_turns', is_error=True),
    )

    def test_only_team_skill_calls_count(self) -> None:
        transcript = parse_transcript(self.finished)
        assert transcript.loaded_skills(frozenset({'jira', 'pysymbols'})) == frozenset({'jira'})

    def test_error_max_turns_result_marks_a_finished_session(self) -> None:
        assert parse_transcript(self.finished).finished

    def test_no_result_event_is_not_finished(self) -> None:
        assert not parse_transcript('warning: something on stdout\n').finished

    def test_success_with_is_error_is_not_finished(self) -> None:
        failed = stream_lines(result_event('success', is_error=True, result='Invalid API key'))
        transcript = parse_transcript(failed)
        assert not transcript.finished
        assert transcript.failure_detail == 'Invalid API key'

    def test_a_subtype_without_a_result_message_falls_back_to_the_subtype(self) -> None:
        failed = stream_lines(result_event('error_during_execution'))
        assert parse_transcript(failed).failure_detail == 'error_during_execution'

    def test_skills_listed_but_not_staged_are_reported_as_unlisted(self) -> None:
        stream = stream_lines(init_event('jira'))
        transcript = parse_transcript(stream)
        assert transcript.unlisted(frozenset({'jira', 'terraform'})) == ['terraform']

    def test_a_skill_argument_that_is_not_a_string_is_not_an_invocation(self) -> None:
        block = {'type': 'tool_use', 'name': 'Skill', 'input': {'skill': {'nested': True}}}
        stream = stream_lines({'type': 'assistant', 'message': {'content': [block]}})
        assert parse_transcript(stream).invoked == ()


class TestRealClaudeCodeStream:
    fixture = FIXTURES.joinpath('claude-2.1.296-skill-route.jsonl')

    def test_parses_a_captured_claude_code_2_1_296_session(self) -> None:
        transcript = parse_transcript(self.fixture.read_text(encoding='utf-8'))
        assert transcript.invoked == ('zebra-facts',)
        assert {'zebra-facts', 'code-review'} <= transcript.listed
        assert transcript.finished
