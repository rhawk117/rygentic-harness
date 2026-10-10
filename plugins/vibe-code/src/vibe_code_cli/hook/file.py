from dataclasses import dataclass
from pathlib import Path

import msgspec

from vibe_code_cli.findings import CannotCheckError
from vibe_code_cli.jsondoc import JsonObject, as_object


@dataclass(slots=True, kw_only=True, frozen=True)
class HooksFile:
    path: Path
    text: str
    config: JsonObject | None

    @property
    def plugin_shape(self) -> bool:
        return self.path.name == "hooks.json"

    @property
    def plugin_root(self) -> Path | None:
        directory = self.path.resolve().parent
        return directory.parent if directory.name == "hooks" else None

    @property
    def project_dir(self) -> Path | None:
        directory = self.path.resolve().parent
        return directory.parent if directory.name == ".claude" else None

    def hooks_text_for_builtin(self) -> str:
        if self.plugin_shape:
            return self.text

        if self.config is None:
            message = f"{self.path} is not a JSON object, so its hooks cannot be handed to claude"
            raise CannotCheckError(message)

        if "hooks" not in self.config:
            message = f'{self.path} has no top-level "hooks" key, so there is nothing to validate'
            raise CannotCheckError(message)

        return msgspec.json.encode({"hooks": self.config["hooks"]}).decode()


def load_hooks_file(path: Path) -> HooksFile:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as problem:
        message = f"could not read {path}: {problem}"
        raise CannotCheckError(message) from problem

    try:
        value = msgspec.json.decode(text)
    except msgspec.DecodeError:
        return HooksFile(path=path, text=text, config=None)

    return HooksFile(
        path=path,
        text=text,
        config=as_object(value),
    )
