"""Claude Code entry point for the SessionStart hook; the work lives in mightymcp."""

from mightymcp.hookkit import run_hook
from mightymcp.hooks.session_start import session_start

if __name__ == '__main__':
    run_hook(session_start)
