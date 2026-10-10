import shutil
import sys
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import IO

if sys.platform == 'win32':
    import msvcrt

    def lock_handle(handle: IO[bytes]) -> None:
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)  # ty: ignore[possibly-missing-attribute]  # this branch only runs on its own platform

    def unlock_handle(handle: IO[bytes]) -> None:
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)  # ty: ignore[possibly-missing-attribute]  # this branch only runs on its own platform

else:
    import fcntl

    def lock_handle(handle: IO[bytes]) -> None:
        fcntl.flock(handle, fcntl.LOCK_EX)  # ty: ignore[possibly-missing-attribute]  # this branch only runs on its own platform

    def unlock_handle(handle: IO[bytes]) -> None:
        fcntl.flock(handle, fcntl.LOCK_UN)  # ty: ignore[possibly-missing-attribute]  # this branch only runs on its own platform


@contextmanager
def exclusive_lock(path: Path) -> Generator[None, None, None]:
    with path.open('a+b') as handle:
        lock_handle(handle)
        try:
            yield
        finally:
            unlock_handle(handle)


def write_atomically(path: Path, data: bytes) -> None:
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f'.{path.name}.',
        suffix='.tmp',
        delete=True,
        delete_on_close=False,
    ) as staging:
        staging.write(data)
        staging.close()
        if path.exists():
            shutil.copymode(path, staging.name)
        Path(staging.name).replace(path)
