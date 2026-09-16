from collections.abc import Callable
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ResourceNotFoundError
from mcp.server.mcpserver.resources import FileResource

from mightymcp.brief import brief_read, render_asked
from mightymcp.fleet import plugin_root
from mightymcp.paths import (
    MIGHTYMODELS_DIR,
    TICKET_FILE,
    TicketPathError,
    active_ticket,
    safe_name,
    ticket_dir,
)
from mightymcp.status import ASKED_HEADING, render_status, sprint_status

URI_SCHEME = 'mm://'
MARKDOWN = 'text/markdown'
YAML = 'text/yaml'
PLAIN = 'text/plain'
ENGINEER_URI = f'{URI_SCHEME}template/engineer/{{task}}'
TICKET_URI = f'{URI_SCHEME}ticket/{{slug}}'
BRIEF_URI = f'{URI_SCHEME}ticket/{{slug}}/brief/{{task}}'
STATUS_URI = f'{URI_SCHEME}ticket/{{slug}}/status'
# One level of *.md, so the templates/ subdirectory is left to TEMPLATE_GLOB.
REF_GLOB = 'skills/*/references/*.md'
AGENT_GLOB = 'agents/*.md'
TEMPLATE_GLOB = 'skills/promptlint/references/templates/*.md'
ENGINEER_TEMPLATE = 'skills/promptlint/references/templates/engineer.md'
# The slots the engineer template leaves for the dispatch to fill.
BRIEF_PATH_SLOT = f'{MIGHTYMODELS_DIR}/<slug>/briefs/task-NN.md'
STANZA_FENCE = '````'


def register_resources(server: MCPServer) -> None:
    """Register every mm:// resource: the plugin's own markdown, then the ticket state."""
    for resource in bundled_resources():
        server.add_resource(resource)
    _add_template(server, ENGINEER_URI, MARKDOWN, engineer_dispatch)
    _add_template(server, TICKET_URI, YAML, ticket_yaml)
    _add_template(server, BRIEF_URI, MARKDOWN, ticket_brief)
    _add_template(server, STATUS_URI, PLAIN, ticket_status)


def bundled_resources() -> list[FileResource]:
    """The markdown the plugin ships: skill references, agents, and role templates."""
    base = plugin_root()
    return [
        *(
            _markdown(
                f'ref/{path.parents[1].name}/{path.stem}',
                path,
                f'The {path.stem} reference of the {path.parents[1].name} skill',
            )
            for path in sorted(base.glob(REF_GLOB))
        ),
        *(
            _markdown(
                f'agent/{path.stem}',
                path,
                f'The {path.stem} agent contract, frontmatter included',
            )
            for path in sorted(base.glob(AGENT_GLOB))
        ),
        *(
            _markdown(
                f'template/{path.stem}',
                path,
                f'The promptlint dispatch template for the {path.stem} role',
            )
            for path in sorted(base.glob(TEMPLATE_GLOB))
        ),
    ]


def engineer_dispatch(task: str) -> str:
    """The engineer template, carrying the ASKED half of this task's brief."""
    try:
        slug = active_ticket()
    except TicketPathError as err:
        raise ResourceError(str(err)) from err

    brief = brief_read(slug, task)
    if brief.asked is None:
        raise ResourceNotFoundError('; '.join(brief.refusals))
    template = plugin_root().joinpath(ENGINEER_TEMPLATE).read_text(encoding='utf-8')
    return _fill_engineer(
        template,
        render_asked(brief.asked),
        f'{MIGHTYMODELS_DIR}/{slug}/briefs/{task}.md',
    )


def ticket_yaml(slug: str) -> str:
    """The ticket.yml of one ticket, as written."""
    return _read(_ticket_path(slug, TICKET_FILE))


def ticket_brief(slug: str, task: str) -> str:
    """One task brief of a ticket, as written: every half it carries."""
    path = _ticket_path(slug, 'briefs', task)
    return _read(path.with_name(f'{path.name}.md'))


def ticket_status(slug: str) -> str:
    """Where a sprint stands: one line per task, then the ticket-wide counters."""
    status = sprint_status(slug)
    if status.refusals:
        raise ResourceNotFoundError('; '.join(status.refusals))
    return render_status(status)


def _add_template(
    server: MCPServer, uri: str, mime_type: str, fn: Callable[..., str]
) -> None:
    server.resource(uri, name=uri.removeprefix(URI_SCHEME), mime_type=mime_type)(fn)


def _markdown(name: str, path: Path, description: str) -> FileResource:
    return FileResource(
        uri=f'{URI_SCHEME}{name}',
        name=name,
        description=description,
        mime_type=MARKDOWN,
        path=path,
    )


def _ticket_path(slug: str, *names: str) -> Path:
    """A path inside .mightymodels/<slug>/, with every name vetted as one segment."""
    try:
        return ticket_dir(slug).joinpath(*(safe_name(name) for name in names))
    except TicketPathError as err:
        raise ResourceError(str(err)) from err


def _read(path: Path) -> str:
    if not path.is_file():
        raise ResourceNotFoundError(f'no file at {path}')
    return path.read_text(encoding='utf-8')


def _fill_engineer(template: str, stanza: str, brief_path: str) -> str:
    lines = template.splitlines()
    start = lines.index(ASKED_HEADING)
    end = lines.index(STANZA_FENCE, start)
    filled = '\n'.join([*lines[:start], *stanza.splitlines(), *lines[end:]])
    return filled.replace(BRIEF_PATH_SLOT, brief_path) + '\n'
