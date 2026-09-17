"""Claude Code entry point for the Agent dispatch guard; the work lives in mightymcp."""

from mightymcp.hookkit import run_hook
from mightymcp.hooks.pre_agent import pre_agent

if __name__ == '__main__':
    run_hook(pre_agent)
