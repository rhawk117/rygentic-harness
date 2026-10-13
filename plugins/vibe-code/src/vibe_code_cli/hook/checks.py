from urllib.parse import urlparse

from msgspec import UNSET

from vibe_code_cli.findings import CannotCheckError, Finding, error, warning
from vibe_code_cli.hook.events import (
    DEFAULT_TIMEOUT_SECONDS,
    ENFORCEMENT_EVENTS,
    SLOW_ENFORCEMENT_SECONDS,
    TimeoutDefaults,
)
from vibe_code_cli.hook.file import HooksFile
from vibe_code_cli.hook.matchers import matcher_findings
from vibe_code_cli.hook.nodes import DecodedHooks, Event, Handler
from vibe_code_cli.hook.schema import CommandHook, HttpHook
from vibe_code_cli.hook.scripts import script_findings
from vibe_code_cli.jsondoc import JsonObject

PLUGIN_TOP_LEVEL_KEYS = frozenset({'hooks', 'description'})

WEB_SCHEMES = frozenset({'http', 'https'})


def check_hooks(
    hooks_file: HooksFile, decoded: DecodedHooks, *, builtin_errored: bool
) -> list[Finding]:
    config = hooks_file.config
    if config is None:
        if builtin_errored:
            return []
        message = (
            f'{hooks_file.path} is not a JSON object the built-in let pass; '
            'the checks could not run'
        )
        raise CannotCheckError(message)
    findings: list[Finding] = []
    if hooks_file.plugin_shape:
        findings.extend(top_level_findings(config))
    if decoded.events is not None:
        findings.extend(hooks_findings(decoded.events, hooks_file))
    return findings


def top_level_findings(config: JsonObject) -> list[Finding]:
    return [
        error(
            f'unknown top-level field {key!r}; a plugin hooks file holds only hooks and description'
        )
        for key in sorted(config.keys() - PLUGIN_TOP_LEVEL_KEYS)
    ]


def hooks_findings(events: tuple[Event, ...], hooks_file: HooksFile) -> list[Finding]:
    if not events:
        return [error('hooks: must not be an empty object')]
    findings = [finding for event in events for finding in event_findings(event)]
    for event in events:
        for group in event.groups:
            findings.extend(matcher_findings(group))
            for handler in group.handlers:
                findings.extend(handler_findings(handler, hooks_file))
    return findings


def event_findings(event: Event) -> list[Finding]:
    if event.empty:
        return [error(f'hooks.{event.name}: must not be an empty array')]
    return []


def handler_findings(handler: Handler, hooks_file: HooksFile) -> list[Finding]:
    findings = timeout_findings(handler)
    findings.extend(script_findings(handler, hooks_file))
    hook = handler.hook
    if isinstance(hook, CommandHook):
        findings.extend(command_findings(handler.where, hook))

    if isinstance(hook, HttpHook):
        findings.extend(http_findings(handler.where, hook))

    return findings


def command_findings(where: str, hook: CommandHook) -> list[Finding]:
    if not hook.command.strip():
        return [error(f'{where}: command must not be empty')]

    return []


def http_findings(where: str, hook: HttpHook) -> list[Finding]:
    findings = []
    if hook.url.strip() and urlparse(hook.url).scheme.lower() not in WEB_SCHEMES:
        findings.append(error(f'{where}: url must use http:// or https://'))

    findings.extend(
        error(f'{where}: allowedEnvVars[{index}] must be a non-empty string')
        for index, name in enumerate(hook.allowed_env_vars)
        if not name.strip()
    )

    return findings


def timeout_findings(handler: Handler) -> list[Finding]:
    hook = handler.hook
    if not isinstance(hook, CommandHook | HttpHook) or runs_in_background(hook):
        return []

    if hook.timeout is UNSET:
        default = TimeoutDefaults().lowered.get(handler.event, DEFAULT_TIMEOUT_SECONDS)
        message = f'no timeout set; Claude Code applies its default of {default:g} s'
        return [warning(f'{handler.where}: {message}')]

    return slow_timeout_findings(handler, hook.timeout)


def runs_in_background(hook: CommandHook | HttpHook) -> bool:
    return isinstance(hook, CommandHook) and hook.async_


def slow_timeout_findings(handler: Handler, seconds: float) -> list[Finding]:
    if handler.event not in ENFORCEMENT_EVENTS or seconds <= SLOW_ENFORCEMENT_SECONDS:
        return []
    return [
        warning(
            f'{handler.where}: timeout is {seconds:g} s on {handler.event}; a timed-out hook '
            'does not block the call, so keep policy checks tight'
        )
    ]
