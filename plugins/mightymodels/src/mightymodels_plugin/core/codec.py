"""JSON encoding for the package, on msgspec alone.

`encode_indented` takes any value msgspec encodes (a `Struct`, a dataclass, a mapping, a
sequence, a scalar or `None`) and returns the document as UTF-8 bytes, indented by `INDENT`
spaces with no trailing newline. Keys keep the order the value holds them in, and a character
outside ASCII is written as itself, never as an escape.
"""

import msgspec

INDENT = 2


def encode_indented(value: object) -> bytes:
    return msgspec.json.format(msgspec.json.encode(value), indent=INDENT)
