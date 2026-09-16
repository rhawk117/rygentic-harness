"""Claude Code entry point for the PreCompact snapshot; the work lives in mightymcp."""

from mightymcp.hookkit import run_hook
from mightymcp.hooks.pre_compact import pre_compact

if __name__ == '__main__':
    run_hook(pre_compact)
