from dataclasses import dataclass
from pathlib import Path

from mightymodels_plugin.tools.tests.slug_calls import SLUG

PASSED, REJECTED = 0, 2
VERIFY_RUN = ('verify', 'run', '--slug', SLUG, '--all')
NOT_SET = 'is not set, so there is no plugin data directory'


@dataclass(slots=True, kw_only=True, frozen=True)
class KeptFile:
    file: Path
    content: bytes

    def is_as_it_was(self) -> bool:
        return self.file.read_bytes() == self.content

    def has_nothing_beside_it(self) -> bool:
        return list(self.file.parent.iterdir()) == [self.file]


def kept(file: Path) -> KeptFile:
    return KeptFile(file=file, content=file.read_bytes())
