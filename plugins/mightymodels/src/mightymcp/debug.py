from pydantic import BaseModel, Field

from mightymcp.artifacts import missing_refusals, ticket_directory

WHATS_BROKEN = 'whats-broken.md'
FIRST_ATTEMPT = 1
LAST_ATTEMPT = 3


class Hypothesis(BaseModel):
    """One whats-broken attempt: the symptom, the claim, and the check for it."""

    symptom: str = Field(description='The slug or symptom the debug is named for')
    attempt: int = Field(description=f'Attempt {FIRST_ATTEMPT}-{LAST_ATTEMPT}')
    reproduce: str = Field(description='The failing command and its output, one line')
    hypothesis: str = Field(
        description='I believe <X> is the cause because <evidence>. If true, <Z> shows it'
    )
    test: str = Field(description='The minimal check that could falsify this')


class WhatsBrokenWrite(BaseModel):
    """whats-broken.md as regenerated, or why nothing was written."""

    path: str | None = Field(default=None, description='Absolute path of the file')
    text: str = Field(default='', description='The hypothesis as written')
    refusals: list[str] = Field(
        default_factory=list, description='Why nothing was written'
    )


class WhatsBrokenClose(BaseModel):
    """The closed debug, or why there was nothing to close."""

    path: str | None = Field(default=None, description='The file that was deleted')
    refusals: list[str] = Field(
        default_factory=list, description='Why nothing was deleted'
    )


def whats_broken_write(slug: str, hypothesis: Hypothesis) -> WhatsBrokenWrite:
    """Regenerate whats-broken.md with this attempt's single falsifiable hypothesis."""
    directory, refusals = ticket_directory(slug)
    refusals.extend(
        missing_refusals({
            'symptom': hypothesis.symptom,
            'reproduce': hypothesis.reproduce,
            'hypothesis': hypothesis.hypothesis,
            'test': hypothesis.test,
        })
    )
    if not FIRST_ATTEMPT <= hypothesis.attempt <= LAST_ATTEMPT:
        refusals.append(
            f'attempt {hypothesis.attempt} is outside {FIRST_ATTEMPT}-{LAST_ATTEMPT}; '
            'the third failed fix stops the debug'
        )
    if directory is None or refusals:
        return WhatsBrokenWrite(refusals=refusals)

    text = (
        f'# whats-broken: {hypothesis.symptom}\n'
        f'attempt: {hypothesis.attempt}\n'
        f'reproduce: {hypothesis.reproduce}\n'
        f'hypothesis: {hypothesis.hypothesis}\n'
        f'test: {hypothesis.test}\n'
    )
    path = directory.joinpath(WHATS_BROKEN)
    path.write_text(text, encoding='utf-8')
    return WhatsBrokenWrite(path=str(path), text=text)


def whats_broken_close(slug: str) -> WhatsBrokenClose:
    """Delete whats-broken.md now the debug has closed."""
    directory, refusals = ticket_directory(slug)
    if directory is None:
        return WhatsBrokenClose(refusals=refusals)

    path = directory.joinpath(WHATS_BROKEN)
    if not path.is_file():
        return WhatsBrokenClose(refusals=[f'no debug is live: {path} does not exist'])
    path.unlink()
    return WhatsBrokenClose(path=str(path))
