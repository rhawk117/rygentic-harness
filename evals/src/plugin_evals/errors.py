class HarnessError(Exception):
    pass


class RepoCommandError(HarnessError):
    def __init__(self, git_args: tuple[str, ...], output: str) -> None:
        super().__init__(f'git {" ".join(git_args)} failed: {output[-300:]}')
        self.git_args = git_args
        self.output = output


class UnknownFixtureError(HarnessError):
    def __init__(self, name: str) -> None:
        super().__init__(f'unknown fixture {name!r}')
        self.name = name


class ReplayRunMissingError(HarnessError):
    def __init__(self, workdir: str) -> None:
        super().__init__(f'no replay run at {workdir}')
        self.workdir = workdir


class TemplateDriftError(HarnessError):
    def __init__(self, rel: str, needle: str) -> None:
        super().__init__(
            f'{rel} no longer contains {needle!r}; template and builder drifted apart'
        )
        self.rel = rel
        self.needle = needle


class NoCasesError(HarnessError):
    def __init__(self, skill: str | None) -> None:
        super().__init__(f'no behavior cases for skill {skill!r}')
        self.skill = skill
