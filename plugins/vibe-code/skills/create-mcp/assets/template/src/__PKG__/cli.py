"""Command-line entrypoint: `uv run __NAME__ [--transport ...] [--root DIR]`."""

import argparse
import logging
import os
import sys
from pathlib import Path

from __PKG__ import DESCRIPTION
from __PKG__.server import REQUIRED_BINARIES, build_server
from __PKG__.workspace import WorkspaceTool

TRANSPORTS: tuple[str, ...] = __TRANSPORTS__
DEFAULT_TRANSPORT = TRANSPORTS[0]
DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 8000
ROOT_VARIABLE: str | None = __ROOT_VARIABLE__


def default_root() -> Path:
    if ROOT_VARIABLE and (value := os.environ.get(ROOT_VARIABLE)):
        return Path(value)
    return Path.cwd()


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog='__NAME__', description=DESCRIPTION)
    parser.add_argument(
        '--root',
        type=Path,
        default=default_root(),
        help='directory the server may read and run commands in',
    )
    parser.add_argument(
        '--log-level', default='INFO', choices=('DEBUG', 'INFO', 'WARNING', 'ERROR')
    )
    if len(TRANSPORTS) > 1:
        parser.add_argument('--transport', choices=TRANSPORTS, default=DEFAULT_TRANSPORT)
    if 'streamable-http' in TRANSPORTS:
        parser.add_argument('--host', default=DEFAULT_HOST)
        parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    logging.basicConfig(
        level=arguments.log_level, stream=sys.stderr, format='%(name)s %(levelname)s %(message)s'
    )
    root = arguments.root.resolve()
    if not root.is_dir():
        logging.getLogger('__NAME__').error('root %s is not a directory', root)
        return 2
    missing = [
        binary for binary in REQUIRED_BINARIES if not WorkspaceTool(binary=binary).available()
    ]
    if missing:
        logging.getLogger('__NAME__').warning(
            'binaries not on PATH: %s; tools that need them will report failure', ', '.join(missing)
        )
    mcp = build_server(root)
    transport = getattr(arguments, 'transport', DEFAULT_TRANSPORT)
    logging.getLogger('__NAME__').info('serving over %s with root %s', transport, root)
    if transport == 'streamable-http':
        mcp.run(transport='streamable-http', host=arguments.host, port=arguments.port)
    if transport == 'stdio':
        mcp.run(transport='stdio')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
