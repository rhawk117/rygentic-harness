"""Claude Code entry point for the Bash PostToolUse hook; the work lives in mightymcp."""

from mightymcp.hookkit import run_hook
from mightymcp.hooks.post_bash import post_bash

if __name__ == '__main__':
    run_hook(post_bash)
