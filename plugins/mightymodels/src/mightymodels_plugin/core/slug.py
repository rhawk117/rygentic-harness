"""The one name type that may become a path component under `.mightymodels/`.

`ARCHIVES_DIRECTORY` is the one well-formed name the type refuses. `.mightymodels/archives/`
holds every ticket's archive, so a ticket of that name would keep its files in the archive
directory itself.
"""

from typing import Annotated, override

from pydantic import AfterValidator, ConfigDict, RootModel, StringConstraints, ValidationError

from mightymodels_plugin.core.errors import StateError

SLUG_PATTERN = r'^[A-Za-z0-9][A-Za-z0-9_-]*$'
SLUG_LIMIT = 64
ARCHIVES_DIRECTORY = 'archives'


class InvalidSlugError(StateError):
    def __init__(self, raw: str) -> None:
        super().__init__(
            f'{raw!r} is not a slug: letters, digits, dashes and underscores only, '
            f'starting with a letter or digit, at most {SLUG_LIMIT} characters, and never '
            f'{ARCHIVES_DIRECTORY!r}, the name reserved for the archive directory'
        )
        self.raw = raw


class ReservedSlugError(ValueError):
    def __init__(self) -> None:
        super().__init__(f'{ARCHIVES_DIRECTORY!r} is reserved for the archive directory')


def unreserved(text: str) -> str:
    if text == ARCHIVES_DIRECTORY:
        raise ReservedSlugError
    return text


type SlugText = Annotated[
    str,
    StringConstraints(pattern=SLUG_PATTERN, max_length=SLUG_LIMIT),
    AfterValidator(unreserved),
]


class Slug(RootModel[SlugText]):
    model_config = ConfigDict(frozen=True)

    @override
    def __str__(self) -> str:
        return self.root


def parsed_slug(raw: str) -> Slug | InvalidSlugError:
    try:
        return Slug(raw)
    except ValidationError:
        return InvalidSlugError(raw)
