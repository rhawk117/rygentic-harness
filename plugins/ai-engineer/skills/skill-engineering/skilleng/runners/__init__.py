from .base import HostAdapter, RunRequest, RunResult, get_adapter, list_adapters, register
from . import claude_code, copilot_cli  # noqa: F401  (registration side effect)

__all__ = ["HostAdapter", "RunRequest", "RunResult", "get_adapter", "list_adapters", "register"]
