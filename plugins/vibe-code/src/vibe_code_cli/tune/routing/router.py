import asyncio
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

import msgspec

from vibe_code_cli.tune.domain.values import RoutingOptions, Skill
from vibe_code_cli.tune.errors import RouterUnavailableError, RoutingFailedError
from vibe_code_cli.tune.routing.policy import SessionPolicy
from vibe_code_cli.tune.routing.staging import StubProject
from vibe_code_cli.tune.routing.transcript import (
    SKILL_TOOL,
    SessionTranscript,
    parse_transcript,
)

DEFAULT_EXECUTABLE = "claude"
HEADLESS_FLAGS = (
    "-p",
    "--setting-sources",
    "project",
    "--strict-mcp-config",
    "--no-session-persistence",
    "--permission-prompts",
    "none",
    "--max-turns",
    "1",
    "--tools",
    SKILL_TOOL,
    "--output-format",
    "stream-json",
    "--verbose",
)


@dataclass(slots=True, kw_only=True, frozen=True)
class RoutedBatch:
    verdicts: list[frozenset[str]]
    competitors: frozenset[str]


@runtime_checkable
class Router(Protocol):
    async def route(
        self, descriptions: Mapping[str, str], requests: Sequence[str]
    ) -> RoutedBatch: ...


@runtime_checkable
class RouterFactory(Protocol):
    def build(self, skills: tuple[Skill, ...], options: RoutingOptions) -> Router: ...


@dataclass(slots=True, kw_only=True, frozen=True)
class SessionOutput:
    stdout: str
    stderr: str


async def stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        process.kill()
        await process.wait()


@dataclass(slots=True, kw_only=True, frozen=True)
class ClaudeCodeRouter:
    executable: str
    skills: tuple[Skill, ...]
    options: RoutingOptions
    sessions: SessionPolicy = field(default_factory=SessionPolicy)

    def command(self) -> list[str]:
        command = [self.executable, *HEADLESS_FLAGS]
        if self.options.model:
            command.extend(["--model", self.options.model])

        return command

    async def start_session(
        self, project: StubProject, request: str
    ) -> asyncio.subprocess.Process:
        try:
            return await asyncio.create_subprocess_exec(
                *self.command(),
                cwd=project.root,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as problem:
            raise RoutingFailedError(request, str(problem)) from problem

    async def collect_output(
        self,
        process: asyncio.subprocess.Process,
        request: str,
    ) -> SessionOutput:
        encoded_request = request.encode()
        try:
            async with asyncio.timeout(self.options.timeout_seconds):
                stdout, stderr = await process.communicate(encoded_request)
        except TimeoutError as err:
            raise RoutingFailedError(request, "timed out") from err

        return SessionOutput(
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
        )

    def read_transcript(self, output: SessionOutput, request: str) -> SessionTranscript:
        try:
            transcript = parse_transcript(output.stdout)
        except (msgspec.DecodeError, msgspec.ValidationError) as problem:
            raise RoutingFailedError(request, f"unreadable output: {problem}") from None

        if problem := self.sessions.get_outcome_problem(
            transcript, request, output.stderr
        ):
            raise problem

        return transcript

    async def run_session(
        self, project: StubProject, request: str
    ) -> SessionTranscript:
        process = await self.start_session(project, request)

        try:
            output = await self.collect_output(process, request)
        finally:
            await stop_process(process)

        transcript = self.read_transcript(output, request)
        if problem := self.sessions.get_listing_problem(
            transcript, request, project.team
        ):
            raise problem

        return transcript

    async def route_one(
        self,
        project: StubProject,
        request: str,
        gate: asyncio.Semaphore,
    ) -> SessionTranscript:
        async with gate:
            return await self.run_session(project, request)

    async def route_staged(
        self,
        project: StubProject,
        requests: Sequence[str],
    ) -> list[SessionTranscript]:
        gate = asyncio.Semaphore(self.options.concurrency)

        try:
            async with asyncio.TaskGroup() as group:
                tasks = [
                    group.create_task(self.route_one(project, request, gate))
                    for request in requests
                ]
        except* RoutingFailedError as failures:
            raise failures.exceptions[0] from None

        return [task.result() for task in tasks]

    async def route(
        self,
        descriptions: Mapping[str, str],
        requests: Sequence[str],
    ) -> RoutedBatch:
        with tempfile.TemporaryDirectory(prefix="skill-routing-") as root:
            project = StubProject(
                root=Path(root),
                skills=self.skills,
            )
            project.stage(descriptions)
            transcripts = await self.route_staged(project, requests)

        team = project.team
        verdicts = [transcript.loaded_skills(team) for transcript in transcripts]
        listed = frozenset(
            name for transcript in transcripts for name in transcript.listed
        )
        return RoutedBatch(verdicts=verdicts, competitors=listed - team)


@dataclass(slots=True, kw_only=True, frozen=True)
class ClaudeCodeRouterFactory:
    executable: str | None = None

    def build(self, skills: tuple[Skill, ...], options: RoutingOptions) -> Router:
        requested = self.executable or DEFAULT_EXECUTABLE
        resolved = shutil.which(requested)
        if resolved is None:
            raise RouterUnavailableError(requested)

        return ClaudeCodeRouter(
            executable=resolved,
            skills=skills,
            options=options,
        )
