"""Claude Code entry point for the SubagentStart hook; the work lives in mightymcp."""

from mightymcp.hookkit import run_hook
from mightymcp.hooks.subagent_start import subagent_start

if __name__ == '__main__':
    run_hook(subagent_start)
