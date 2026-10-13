import os
import re
import sys
import time
from pathlib import Path

import msgspec

REQUIRED_ARGS = frozenset(
    {
        '-p',
        '--setting-sources',
        'project',
        '--strict-mcp-config',
        '--no-session-persistence',
        '--permission-prompts',
        'none',
        '--max-turns',
        '1',
        '--tools',
        'Skill',
        '--output-format',
        'stream-json',
        '--verbose',
    }
)
BUILTIN_SKILLS = ('code-review', 'debug')
STOPWORDS = frozenset({'a', 'an', 'and', 'for', 'i', 'is', 'my', 'the', 'this', 'to', 'use'})
WORD = re.compile(r'[a-z_]+')
CRASH_ENV = 'FAKE_CLAUDE_CRASH_ON'
AUTH_ERROR_ENV = 'FAKE_CLAUDE_AUTH_ERROR'
UNLISTED_ENV = 'FAKE_CLAUDE_UNLISTED'
PID_DIR_ENV = 'FAKE_CLAUDE_PID_DIR'
PROMPT_LOG_ENV = 'FAKE_CLAUDE_PROMPT_LOG'
HANG_ENV = 'FAKE_CLAUDE_HANG_ON'
HANG_SECONDS = 30
EXIT_FAILED = 1
EXIT_REFUSED = 3
AUTH_ERROR = 'Invalid API key · Please run /login'


class StubFrontmatter(msgspec.Struct):
    description: str


def words(text: str) -> frozenset[str]:
    found = (match.group() for match in WORD.finditer(text.lower()))
    return frozenset(found) - STOPWORDS


def staged_skills(project: Path) -> dict[str, str]:
    found = {}
    for skill_file in sorted(project.glob('.claude/skills/*/SKILL.md')):
        header = skill_file.read_text(encoding='utf-8').split('---')[1]
        found[skill_file.parent.name] = msgspec.yaml.decode(
            header, type=StubFrontmatter
        ).description
    return found


def emit(event: dict[str, object]) -> None:
    sys.stdout.write(msgspec.json.encode(event).decode() + '\n')


def record(env_name: str, content: str) -> None:
    if folder := os.getenv(env_name):
        Path(folder).joinpath(str(os.getpid())).write_text(content, encoding='utf-8')


def tool_use(skill: str) -> dict[str, object]:
    block = {'type': 'tool_use', 'name': 'Skill', 'input': {'skill': skill}}
    return {'type': 'assistant', 'message': {'content': [block]}}


def failure_exit(request: str) -> int | None:
    if os.getenv(AUTH_ERROR_ENV):
        emit({'type': 'result', 'subtype': 'success', 'is_error': True, 'result': AUTH_ERROR})
        return EXIT_FAILED
    marker = os.getenv(CRASH_ENV)
    if marker and marker in request:
        sys.stderr.write('Error: simulated crash\n')
        return EXIT_FAILED
    return None


def route_request(request: str, project: Path) -> int:
    marker = os.getenv(HANG_ENV)
    if marker and marker in request:
        time.sleep(HANG_SECONDS)
    staged = staged_skills(project)
    listed = list(BUILTIN_SKILLS)
    if not os.getenv(UNLISTED_ENV):
        listed.extend(staged)
    emit({'type': 'system', 'subtype': 'init', 'skills': listed, 'tools': ['Skill']})
    chosen = [name for name, text in staged.items() if words(text) & words(request)]
    for name in chosen:
        emit(tool_use(name))
    subtype = 'success'
    if chosen:
        subtype = 'error_max_turns'
    emit({'type': 'result', 'subtype': subtype, 'is_error': bool(chosen), 'result': ''})
    return int(bool(chosen))


def main(argv: list[str]) -> int:
    if not set(argv) >= REQUIRED_ARGS:
        return EXIT_REFUSED
    request = sys.stdin.read()
    record(PID_DIR_ENV, '')
    record(PROMPT_LOG_ENV, request)
    if (code := failure_exit(request)) is not None:
        return code
    return route_request(request, Path.cwd())


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
