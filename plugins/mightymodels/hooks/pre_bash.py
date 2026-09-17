"""Claude Code entry point for the Bash guard; the work lives in mightymcp."""

from mightymcp.hookkit import run_hook
from mightymcp.hooks.pre_bash import pre_bash

if __name__ == '__main__':
    run_hook(pre_bash)
