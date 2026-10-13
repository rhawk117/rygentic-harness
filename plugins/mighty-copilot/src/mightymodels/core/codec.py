"""JSON encoding and decoding for the package, on msgspec alone.

`encode_compact` and `encode_indented` take any value msgspec encodes (a `Struct`, a dataclass, a
mapping, a sequence, a scalar or `None`) and return the document as UTF-8 bytes with no trailing
newline: the first with nothing between its tokens, the second indented by `INDENT` spaces. Keys
keep the order the value holds them in, and a character outside ASCII is written as itself, never
as an escape.

`decode_text` reads one JSON document from text into plain values. Whatever msgspec refuses is
raised as `UnreadableJsonError`: text that is not JSON, `NaN` and the infinities, a number out of
a float's range, a surrogate with no pair (escaped or raw), and anything after the document.
"""

import msgspec

from mightymodels.core.errors import StateError

INDENT = 2


class UnreadableJsonError(StateError):
    def __init__(self, detail: str) -> None:
        super().__init__(f'the text is not JSON the codec reads: {detail}')


def encode_compact(value: object) -> bytes:
    return msgspec.json.encode(value)


def encode_indented(value: object) -> bytes:
    return msgspec.json.format(msgspec.json.encode(value), indent=INDENT)


def decode_text(text: str) -> object:
    try:
        return msgspec.json.decode(text)
    except (msgspec.DecodeError, UnicodeEncodeError) as error:
        raise UnreadableJsonError(str(error)) from error
