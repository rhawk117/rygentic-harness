"""Claude Code entry point for the Write and Edit guard; the work lives in mightymcp."""

from mightymcp.hookkit import run_hook
from mightymcp.hooks.pre_write_edit import pre_write_edit

if __name__ == '__main__':
    run_hook(pre_write_edit)
