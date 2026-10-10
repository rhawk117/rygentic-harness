import asyncio
import dataclasses
import os
import stat
import subprocess
from pathlib import Path

import msgspec
import pytest
from vibe_code_cli.tune.domain.values import RoutingOptions, Skill
from vibe_code_cli.tune.errors import RouterUnavailableError, RoutingFailedError
from vibe_code_cli.tune.repository import FileSkillRepository
from vibe_code_cli.tune.routing import HEADLESS_FLAGS, ClaudeCodeRouter, ClaudeCodeRouterFactory
from vibe_code_cli.tune.tests import fake_claude as fake_claude_module


def recorded_pids(directory: Path) -> list[int]:
    return [int(path.name) for path in directory.iterdir()]


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def snapshot_sources(skills: tuple[Skill, ...]) -> dict[str, bytes]:
    return {skill.path: Path(skill.path).read_bytes() for skill in skills}


class TestClaudeCodeRouter:
    def test_candidate_descriptions_drive_routing(self, router: ClaudeCodeRouter) -> None:
        requests = ['move the sprint ticket', 'who calls parse_config']
        original = {skill.name: skill.description for skill in router.skills}
        tuned = {**original, 'jira': 'Use for sprint tickets.'}
        assert asyncio.run(router.route(original, requests)).verdicts == [
            frozenset(),
            frozenset(),
        ]
        assert asyncio.run(router.route(tuned, requests)).verdicts == [
            frozenset({'jira'}),
            frozenset(),
        ]

    def test_error_max_turns_outcome_counts_as_a_verdict(self, router: ClaudeCodeRouter) -> None:
        original = {skill.name: skill.description for skill in router.skills}
        tuned = {**original, 'jira': 'Use for sprint tickets.'}
        batch = asyncio.run(router.route(tuned, ['move the sprint ticket to done']))
        assert batch.verdicts == [frozenset({'jira'})]

    def test_listed_skills_outside_the_team_are_competitors(self, router: ClaudeCodeRouter) -> None:
        descriptions = {skill.name: skill.description for skill in router.skills}
        batch = asyncio.run(router.route(descriptions, ['anything at all']))
        assert batch.competitors == frozenset({'code-review', 'debug'})

    def test_source_skill_files_are_never_touched(self, router: ClaudeCodeRouter) -> None:
        before = snapshot_sources(router.skills)
        descriptions = {skill.name: 'Use for everything.' for skill in router.skills}
        asyncio.run(router.route(descriptions, ['anything at all']))
        assert snapshot_sources(router.skills) == before

    def test_flag_like_request_is_passed_as_text_on_stdin(
        self, router: ClaudeCodeRouter, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        prompts = tmp_path.joinpath('prompts')
        prompts.mkdir()
        monkeypatch.setenv('FAKE_CLAUDE_PROMPT_LOG', str(prompts))
        descriptions = {skill.name: skill.description for skill in router.skills}
        request = '--force push went wrong'
        batch = asyncio.run(router.route(descriptions, [request]))
        assert batch.verdicts == [frozenset()]
        logged = [path.read_text(encoding='utf-8') for path in prompts.iterdir()]
        assert logged == [request]

    def test_stub_project_is_removed_once_the_route_finishes(
        self, router: ClaudeCodeRouter, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr('tempfile.tempdir', None)
        monkeypatch.setenv('TMPDIR', str(tmp_path))
        before = set(tmp_path.iterdir())
        descriptions = {skill.name: skill.description for skill in router.skills}
        asyncio.run(router.route(descriptions, ['anything at all']))
        assert set(tmp_path.iterdir()) == before

    def test_model_option_is_appended_to_the_command(self, router: ClaudeCodeRouter) -> None:
        with_model = dataclasses.replace(
            router, options=msgspec.structs.replace(router.options, model='opus')
        )
        assert with_model.command()[-2:] == ['--model', 'opus']

    def test_command_carries_every_flag_the_fake_requires(self, router: ClaudeCodeRouter) -> None:
        assert set(router.command()) >= fake_claude_module.REQUIRED_ARGS

    def test_unknown_executable_is_refused_up_front(self, skills_dir: Path) -> None:
        factory = ClaudeCodeRouterFactory(executable='/nonexistent/claude')
        skills = FileSkillRepository().discover([skills_dir])
        with pytest.raises(RouterUnavailableError):
            factory.build(skills, RoutingOptions())


class TestFakeClaudeLockdown:
    def test_a_missing_required_flag_is_refused(self, fake_claude: Path) -> None:
        result = subprocess.run(  # noqa: S603  # fixed launcher path, no shell, missing a flag
            [str(fake_claude), *HEADLESS_FLAGS[:-1]],
            input=b'',
            capture_output=True,
            check=False,
        )
        assert result.returncode == fake_claude_module.EXIT_REFUSED


class TestRouterFailures:
    def test_hung_session_is_killed_and_reported(
        self, router: ClaudeCodeRouter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv('FAKE_CLAUDE_HANG_ON', 'stuck')
        impatient = dataclasses.replace(
            router, options=msgspec.structs.replace(router.options, timeout_seconds=0.5)
        )
        descriptions = {skill.name: skill.description for skill in router.skills}
        with pytest.raises(RoutingFailedError, match='timed out'):
            asyncio.run(impatient.route(descriptions, ['a stuck request']))

    def test_auth_error_surfaces_claudes_own_result_text(
        self, router: ClaudeCodeRouter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv('FAKE_CLAUDE_AUTH_ERROR', '1')
        descriptions = {skill.name: skill.description for skill in router.skills}
        with pytest.raises(RoutingFailedError, match='Invalid API key'):
            asyncio.run(router.route(descriptions, ['anything']))

    def test_staged_skills_that_were_never_listed_fail_the_route(
        self, router: ClaudeCodeRouter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv('FAKE_CLAUDE_UNLISTED', '1')
        descriptions = {skill.name: skill.description for skill in router.skills}
        with pytest.raises(RoutingFailedError, match='staged skills were not listed'):
            asyncio.run(router.route(descriptions, ['anything']))

    def test_failure_kills_sibling_sessions(
        self, router: ClaudeCodeRouter, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        pids = tmp_path.joinpath('pids')
        pids.mkdir()
        monkeypatch.setenv('FAKE_CLAUDE_PID_DIR', str(pids))
        monkeypatch.setenv('FAKE_CLAUDE_CRASH_ON', 'crash')
        monkeypatch.setenv('FAKE_CLAUDE_HANG_ON', 'stuck')
        descriptions = {skill.name: skill.description for skill in router.skills}
        with pytest.raises(RoutingFailedError):
            asyncio.run(router.route(descriptions, ['stuck one', 'stuck two', 'crash now']))
        assert not [pid for pid in recorded_pids(pids) if process_alive(pid)]


class TestUnreadableOutput:
    def test_malformed_stream_line_is_a_routing_failure(
        self, skills_dir: Path, tmp_path: Path
    ) -> None:
        launcher = tmp_path.joinpath('broken-claude')
        launcher.write_text('#!/bin/sh\necho "{not json"\n', encoding='utf-8')
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
        router = ClaudeCodeRouter(
            executable=str(launcher),
            skills=FileSkillRepository().discover([skills_dir]),
            options=RoutingOptions(),
        )
        descriptions = {skill.name: skill.description for skill in router.skills}
        with pytest.raises(RoutingFailedError, match='unreadable output'):
            asyncio.run(router.route(descriptions, ['anything']))
