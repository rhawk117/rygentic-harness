"""Claude Code entry point for the SubagentStop gate; the work lives in mightymcp."""

from mightymcp.hookkit import run_hook
from mightymcp.hooks.subagent_stop import subagent_stop

if __name__ == '__main__':
    run_hook(subagent_stop)
