from dataclasses import dataclass
from typing import get_args

import msgspec
from msgspec import UnsetType

from vibe_code_cli.findings import Finding, error, warning
from vibe_code_cli.hook.schema import EventName, HookHandler, MatcherGroup
from vibe_code_cli.jsondoc import JsonObject


@dataclass(slots=True, kw_only=True, frozen=True)
class SchemaFinding:
    where: str
    finding: Finding


@dataclass(slots=True, kw_only=True, frozen=True)
class Handler:
    event: str
    where: str
    hook: HookHandler


@dataclass(slots=True, kw_only=True, frozen=True)
class Group:
    event: str
    where: str
    matcher: str | UnsetType
    handlers: tuple[Handler, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class Event:
    name: str
    empty: bool
    groups: tuple[Group, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class DecodedHooks:
    events: tuple[Event, ...] | None
    findings: tuple[SchemaFinding, ...]


def decode_hooks(config: JsonObject | None) -> DecodedHooks:
    if config is None or 'hooks' not in config:
        return DecodedHooks(events=None, findings=())

    try:
        entries_by_event = msgspec.convert(config['hooks'], dict[str, object])
    except msgspec.ValidationError as problem:
        findings = (schema_finding('hooks', problem),)
        return DecodedHooks(events=None, findings=findings)

    events = []
    findings = []
    for name, entries in entries_by_event.items():
        event, event_findings = decode_event(name, entries)
        events.append(event)
        findings.extend(event_findings)

    return DecodedHooks(events=tuple(events), findings=tuple(findings))


def schema_finding(where: str, problem: msgspec.ValidationError) -> SchemaFinding:
    return SchemaFinding(
        where=where,
        finding=error(f'{where}: {problem}'),
    )


def decode_event(name: str, entries: object) -> tuple[Event, list[SchemaFinding]]:
    where = f'hooks.{name}'
    findings = event_name_findings(name, where)
    try:
        raw_groups = msgspec.convert(entries, list[object])
    except msgspec.ValidationError as problem:
        return Event(name=name, empty=False, groups=()), [
            *findings,
            schema_finding(where, problem),
        ]

    groups = []
    for index, raw_group in enumerate(raw_groups):
        group, group_findings = decode_group(name, f'{where}.{index}', raw_group)
        findings.extend(group_findings)
        if group is not None:
            groups.append(group)

    return Event(name=name, empty=not raw_groups, groups=tuple(groups)), findings


def event_name_findings(name: str, where: str) -> list[SchemaFinding]:
    try:
        msgspec.convert(name, EventName)
    except msgspec.ValidationError as problem:
        pascal_case = name[:1].upper() + name[1:]
        if pascal_case not in get_args(EventName):
            return [SchemaFinding(where=where, finding=warning(f'{where}: {problem}'))]

        message = f'{where}: event names are PascalCase; spell it {pascal_case}'
        return [SchemaFinding(where=where, finding=error(message))]

    return []


def decode_group(
    event: str,
    where: str,
    raw_group: object,
) -> tuple[Group | None, list[SchemaFinding]]:
    try:
        group = msgspec.convert(raw_group, MatcherGroup)
    except msgspec.ValidationError as problem:
        return None, [schema_finding(where, problem)]

    handlers = []
    findings = []
    for index, raw_handler in enumerate(group.hooks):
        handler_where = f'{where}.hooks.{index}'

        try:
            hook = msgspec.convert(raw_handler, HookHandler)
        except msgspec.ValidationError as problem:
            findings.append(schema_finding(handler_where, problem))
            continue

        handlers.append(
            Handler(
                event=event,
                where=handler_where,
                hook=hook,
            )
        )

    group = Group(
        event=event,
        where=where,
        matcher=group.matcher,
        handlers=tuple(handlers),
    )

    return group, findings
