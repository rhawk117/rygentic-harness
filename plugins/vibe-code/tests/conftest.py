import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest
from vibe_code_cli.builtin import BuiltinUnavailableError, Services
from vibe_code_cli.findings import Finding

type ServicesFactory = Callable[[Sequence[Finding]], Services]
type FindingAssertion = Callable[[Sequence[Finding], str], None]
type SectionWriter = Callable[[Sequence[str]], str]
type TemplateFill = Callable[[str, Mapping[str, str], re.Pattern[str]], str]

CONCEPTS = ('skill', 'hook', 'subagent', 'instruction', 'mcp', 'plugin', 'tune')


def pytest_configure(config: pytest.Config) -> None:
    for concept in CONCEPTS:
        config.pluginmanager.import_plugin(f'vibe_code_cli.{concept}.tests.support')


@dataclass(slots=True, kw_only=True, frozen=True)
class FakeBuiltin:
    findings: Sequence[Finding] = ()
    problem: BuiltinUnavailableError | None = None

    def __call__(self, _target: Path, /, **_options: bool) -> list[Finding]:
        if self.problem is not None:
            raise self.problem
        return list(self.findings)


@dataclass(slots=True, kw_only=True, frozen=True)
class OneFinding:
    level: str

    def __call__(self, findings: Sequence[Finding], fragment: str) -> None:
        levels = [finding.level for finding in findings if fragment in finding.message]
        assert levels == [self.level], findings


def services_reporting(findings: Sequence[Finding]) -> Services:
    return Services(run_builtin=FakeBuiltin(findings=findings))


def tagged_sections(names: Sequence[str]) -> str:
    return ''.join(f'<{name}>\nText.\n</{name}>\n\n' for name in names)


def filled_template(template: str, fills: Mapping[str, str], placeholder: re.Pattern[str]) -> str:
    def replacement(token: re.Match[str]) -> str:
        return fills.get(token[0], token[0])

    return placeholder.sub(replacement, template)


@pytest.fixture
def fake_services() -> ServicesFactory:
    return services_reporting


@pytest.fixture
def unavailable_services() -> Services:
    problem = BuiltinUnavailableError('claude plugin validate printed no JSON report')
    return Services(run_builtin=FakeBuiltin(problem=problem))


@pytest.fixture
def assert_error() -> FindingAssertion:
    return OneFinding(level='error')


@pytest.fixture
def assert_warning() -> FindingAssertion:
    return OneFinding(level='warning')


@pytest.fixture
def sections() -> SectionWriter:
    return tagged_sections


@pytest.fixture
def fill() -> TemplateFill:
    return filled_template
