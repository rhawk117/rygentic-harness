from skilleng.runners import (  # noqa: F401  (registration side effect)
    claude_code,
    copilot_cli,
)
from skilleng.runners.base import (
    HostAdapter,
    RunRequest,
    RunResult,
    get_adapter,
    list_adapters,
    register,
)

__all__ = [
    'HostAdapter',
    'RunRequest',
    'RunResult',
    'get_adapter',
    'list_adapters',
    'register',
]
