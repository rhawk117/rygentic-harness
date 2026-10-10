import stat
import sys
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

import msgspec
import pytest

from vibe_code_cli.tune.domain.state import LoopState
from vibe_code_cli.tune.domain.values import Judge, LoopOptions, RoutingOptions
from vibe_code_cli.tune.repository import FileSkillRepository
from vibe_code_cli.tune.routing import ClaudeCodeRouter
from vibe_code_cli.tune.services import (
    PublishingService,
    RoutingService,
    StartRequest,
    TuningService,
)
from vibe_code_cli.tune.tests.agent import ScriptedAgent
from vibe_code_cli.tune.tests.fakes import (
    MemoryLoopStore,
    MemoryPacketPublisher,
    OverlapRouterFactory,
    SequentialRunIds,
)

FAKE_CLAUDE = Path(str(files('vibe_code_cli.tune.tests').joinpath('fake_claude.py')))
SKILLS = {
    'jira': 'Use for Jira work.',
    'pysymbols': 'Use for Python code questions.',
    'terraform': 'Use for infrastructure as code.',
}
TRIGGERS = [
    {'request': 'my ticket is stuck in the backlog', 'skills': ['jira']},
    {'request': 'move the sprint ticket to done', 'skills': ['jira']},
    {'request': 'groom the backlog before sprint planning', 'skills': ['jira']},
    {'request': 'which epic owns this ticket', 'skills': ['jira']},
    {'request': 'who calls this function in the module', 'skills': ['pysymbols']},
    {'request': 'list the callers of parse_config', 'skills': ['pysymbols']},
    {'request': 'where is this function defined', 'skills': ['pysymbols']},
    {'request': 'find callers of the module loader', 'skills': ['pysymbols']},
    {'request': 'plan shows a resource replacement', 'skills': ['terraform']},
    {'request': 'the state lock is stuck on apply', 'skills': ['terraform']},
    {'request': 'why does plan want to destroy the bucket', 'skills': ['terraform']},
    {'request': 'import an existing bucket into state', 'skills': ['terraform']},
    {'request': 'write a haiku about autumn', 'skills': []},
    {'request': 'what time is it in tokyo', 'skills': []},
]


@dataclass(slots=True, kw_only=True, frozen=True)
class SkillLibrary:
    skills_dir: Path
    triggers_file: Path

    def skill_file(self, name: str) -> Path:
        return self.skills_dir.joinpath(name, 'SKILL.md')

    def rename_skill(self, name: str, new_name: str) -> None:
        path = self.skill_file(name)
        text = path.read_text(encoding='utf-8')
        path.write_text(text.replace(f'name: {name}\n', f'name: {new_name}\n'), encoding='utf-8')


@dataclass(slots=True, kw_only=True, frozen=True)
class MemoryRun:
    store: MemoryLoopStore
    packets: MemoryPacketPublisher
    routers: OverlapRouterFactory
    tuning: TuningService
    routing: RoutingService
    publishing: PublishingService

    @property
    def state(self) -> LoopState:
        return self.store.read()


def write_skill(root: Path, name: str, description: str) -> None:
    folder = root.joinpath(name)
    folder.mkdir(parents=True)
    frontmatter = f'name: {name}\ndescription: {description}\nlicense: MIT\n'
    folder.joinpath('SKILL.md').write_text(f'---\n{frontmatter}---\n# {name}\n', encoding='utf-8')


def write_launcher(folder: Path) -> Path:
    launcher = folder.joinpath('claude')
    launcher.write_text(
        f'#!/bin/sh\nexec "{sys.executable}" "{FAKE_CLAUDE}" "$0" "$@"\n', encoding='utf-8'
    )
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
    return launcher


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    root = tmp_path.joinpath('skills')
    for name, description in SKILLS.items():
        write_skill(root, name, description)
    return root


@pytest.fixture
def triggers_file(tmp_path: Path) -> Path:
    path = tmp_path.joinpath('triggers.json')
    path.write_bytes(msgspec.json.encode(TRIGGERS))
    return path


@pytest.fixture
def library(skills_dir: Path, triggers_file: Path) -> SkillLibrary:
    return SkillLibrary(skills_dir=skills_dir, triggers_file=triggers_file)


@pytest.fixture
def loop_options() -> LoopOptions:
    return LoopOptions(judge=Judge.SUBAGENT, batch_size=5, max_rounds=6, patience=3, seed=7)


@pytest.fixture
def start_request(library: SkillLibrary, loop_options: LoopOptions) -> StartRequest:
    return StartRequest(
        skills=(library.skills_dir,), triggers=library.triggers_file, options=loop_options
    )


@pytest.fixture
def memory_run() -> MemoryRun:
    store = MemoryLoopStore()
    packets = MemoryPacketPublisher()
    routers = OverlapRouterFactory()
    return MemoryRun(
        store=store,
        packets=packets,
        routers=routers,
        tuning=TuningService(store=store, packets=packets, run_ids=SequentialRunIds()),
        routing=RoutingService(store=store, routers={Judge.CLAUDE_CODE: routers}),
        publishing=PublishingService(store=store),
    )


@pytest.fixture
def started(memory_run: MemoryRun, start_request: StartRequest) -> MemoryRun:
    memory_run.tuning.start(start_request)
    return memory_run


@pytest.fixture
def scripted_agent() -> ScriptedAgent:
    return ScriptedAgent()


@pytest.fixture
def fake_claude(tmp_path: Path) -> Path:
    folder = tmp_path.joinpath('bin')
    folder.mkdir()
    return write_launcher(folder)


@pytest.fixture
def router(skills_dir: Path, fake_claude: Path) -> ClaudeCodeRouter:
    return ClaudeCodeRouter(
        executable=str(fake_claude),
        skills=FileSkillRepository().discover([skills_dir]),
        options=RoutingOptions(concurrency=4),
    )
