from mcp.server import MCPServer

from mightymcp.fleet import Fleet, load_fleet, render_fleet

server = MCPServer(
    name='mightymodels',
    version='0.9.0',
    instructions=(
        'Read-only view of the mightymodels plugin. Use fleet_roster to see which '
        'agents the plugin ships and what each one is for before dispatching work.'
    ),
)


@server.tool()
def fleet_roster() -> Fleet:
    """List every agent the mightymodels plugin ships, with its job and model."""
    return load_fleet()


@server.resource('mm://fleet', name='fleet', mime_type='text/plain')
def fleet_resource() -> str:
    """The agent fleet as one line per worker: name (model): job."""
    return render_fleet(load_fleet())


def main() -> None:
    server.run()
