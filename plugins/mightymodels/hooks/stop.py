"""Claude Code entry point for the Stop reminder; the work lives in mightymcp."""

from mightymcp.hookkit import run_hook
from mightymcp.hooks.stop import stop

if __name__ == '__main__':
    run_hook(stop)
