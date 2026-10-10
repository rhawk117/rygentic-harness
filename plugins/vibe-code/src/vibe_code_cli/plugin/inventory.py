from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import msgspec

from vibe_code_cli.frontmatter import parse_skill_text
from vibe_code_cli.jsondoc import JsonObject, as_object
from vibe_code_cli.plugin.layout import MANIFEST_PATH
from vibe_code_cli.plugin.record import Component, Plan, decode_plan

HOOKS_FILE = 'hooks/hooks.json'
MCP_FILE = '.mcp.json'
LSP_FILE = '.lsp.json'
IDENTITY_KEYS = (
    'name',
    'version',
    'description',
    'keywords',
    'license',
    'author',
    'homepage',
    'repository',
    'userConfig',
    'dependencies',
)


@dataclass(slots=True, kw_only=True, frozen=True)
class Plugin:
    directory: Path
    manifest: JsonObject

    def relative(self, path: Path) -> str:
        return path.relative_to(self.directory).as_posix()

    def inside(self, path: Path) -> bool:
        return path.resolve().is_relative_to(self.directory.resolve())

    def override_paths(self, key: str) -> list[Path]:
        value = self.manifest.get(key)
        entries = value if isinstance(value, list) else [value]
        paths = [
            self.directory.joinpath(entry)
            for entry in entries
            if isinstance(entry, str)
        ]
        return [path for path in paths if self.inside(path)]

    def config_documents(self, key: str, default: str) -> list[tuple[str, JsonObject]]:
        documents = [(default, json_document(self.directory / default))]
        value = self.manifest.get(key)
        for entry in value if isinstance(value, list) else [value]:
            inline = as_object(entry)
            if inline is not None:
                documents.append((MANIFEST_PATH, inline))
                continue

            if isinstance(entry, str) and self.inside(self.directory / entry):
                documents.append((entry.removeprefix('./'), json_document(self.directory / entry)))

        return [(source, document) for source, document in documents if document]


def json_document(path: Path) -> JsonObject:
    if not path.is_file():
        return {}
    return as_object(msgspec.json.decode(path.read_bytes())) or {}


def frontmatter_fields(path: Path) -> dict[str, object]:
    return parse_skill_text(path.read_text(encoding='utf-8', errors='replace')).fields or {}


def existing(kind: str, name: str, *, purpose: str, files: list[str]) -> Component:
    return Component(
        kind=kind,
        name=name,
        purpose=purpose or f'existing {kind} {name}',
        status='built',
        files=files,
    )


def markdown_component(
    plugin: Plugin, kind: str, path: Path, *, name: str | None = None
) -> Component:
    description = frontmatter_fields(path).get('description')
    purpose = description.strip() if isinstance(description, str) else ''
    return existing(kind, name or path.stem, purpose=purpose, files=[plugin.relative(path)])


def skill_components(plugin: Plugin) -> list[Component]:
    roots = [plugin.directory / 'skills', *plugin.override_paths('skills')]
    found = [
        skill
        for root in roots
        for skill in [root / 'SKILL.md', *sorted(root.glob('*/SKILL.md'))]
        if skill.is_file()
    ]
    return [
        markdown_component(plugin, 'skill', path, name=path.parent.name)
        for path in dict.fromkeys(found)
    ]


def markdown_in(path: Path, *, recursive: bool) -> Iterator[Path]:
    if path.is_file():
        yield path
        return
    if path.is_dir():
        yield from sorted(path.rglob('*.md') if recursive else path.glob('*.md'))


def replaceable_files(plugin: Plugin, key: str, default: str, *, recursive: bool) -> list[Path]:
    paths = plugin.override_paths(key) or [plugin.directory / default]
    files = (file for path in paths for file in markdown_in(path, recursive=recursive))
    return list(dict.fromkeys(files))


def command_components(plugin: Plugin) -> list[Component]:
    files = replaceable_files(plugin, 'commands', 'commands', recursive=False)
    return [markdown_component(plugin, 'command', path) for path in files]


def agent_components(plugin: Plugin) -> list[Component]:
    files = replaceable_files(plugin, 'agents', 'agents', recursive=True)
    names = [frontmatter_fields(path).get('name') for path in files]
    return [
        markdown_component(plugin, 'agent', path, name=name if isinstance(name, str) else None)
        for path, name in zip(files, names, strict=True)
    ]


def output_style_components(plugin: Plugin) -> list[Component]:
    files = replaceable_files(plugin, 'outputStyles', 'output-styles', recursive=True)
    return [markdown_component(plugin, 'output-style', path) for path in files]


def executable_components(plugin: Plugin) -> list[Component]:
    return [
        existing('executable', path.name, purpose='', files=[plugin.relative(path)])
        for path in sorted((plugin.directory / 'bin').glob('*'))
        if path.is_file()
    ]


def hook_components(plugin: Plugin) -> list[Component]:
    components = []
    for source, document in plugin.config_documents('hooks', HOOKS_FILE):
        events = as_object(document.get('hooks', document)) or {}
        purpose = f'hooks with events: {", ".join(sorted(events))}'
        components.append(existing('hook', 'hooks', purpose=purpose, files=[source]))
    return components


def server_components(plugin: Plugin, kind: str, *, key: str, default: str) -> list[Component]:
    components = []
    for source, document in plugin.config_documents(key, default):
        servers = as_object(document.get(key, document)) or {}
        for name, entry in servers.items():
            purpose = server_purpose(kind, as_object(entry) or {})
            components.append(existing(kind, name, purpose=purpose, files=[source]))
    return components


def server_purpose(kind: str, server: JsonObject) -> str:
    if kind == 'lsp':
        extensions = as_object(server.get('extensionToLanguage')) or {}
        return f'language server for {", ".join(extensions)}'
    return f'{server.get("type", "stdio")} server: {server.get("command") or server.get("url", "")}'


def mcp_components(plugin: Plugin) -> list[Component]:
    return server_components(plugin, 'mcp', key='mcpServers', default=MCP_FILE)


def lsp_components(plugin: Plugin) -> list[Component]:
    return server_components(plugin, 'lsp', key='lspServers', default=LSP_FILE)


INVENTORIES: tuple[Callable[[Plugin], list[Component]], ...] = (
    hook_components,
    output_style_components,
    mcp_components,
    lsp_components,
    executable_components,
    skill_components,
    command_components,
    agent_components,
)


def inventory(plugin_dir: Path) -> Plan:
    plugin = Plugin(directory=plugin_dir, manifest=json_document(plugin_dir / MANIFEST_PATH))
    fallback = plugin_dir.resolve().name
    placeholders = {
        'name': fallback,
        'description': f'Existing plugin {fallback}.',
        'keywords': [fallback],
        'problem': 'Existing plugin; the problem it solves is not recorded.',
        'audience': {'who': 'the existing users of the plugin', 'how': 'team'},
        'kinds': ['domain'],
        'distribution': {
            'channel': 'local',
            'install': f'claude --plugin-dir {plugin_dir.resolve()}',
        },
    }
    identity = {key: plugin.manifest[key] for key in IDENTITY_KEYS if key in plugin.manifest}
    plan = decode_plan({**placeholders, **identity})
    components = [component for find in INVENTORIES for component in find(plugin)]
    return msgspec.structs.replace(plan, components=components)
