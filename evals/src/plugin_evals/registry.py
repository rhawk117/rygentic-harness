from collections.abc import Sequence
from types import ModuleType

from plugin_evals.case_modules import ai_engineer, mightymodels
from plugin_evals.cases import CaseSpec
from plugin_evals.errors import HarnessError, NoCasesError

# every plugin that ships behavior cases registers its module here; a module is a
# plugin's whole contribution to the harness and exposes its specs as SPECS
CASE_MODULES: tuple[ModuleType, ...] = (mightymodels, ai_engineer)


class DuplicateSkillError(HarnessError):
    def __init__(self, skill: str, plugins: tuple[str, str]) -> None:
        super().__init__(
            f'skill {skill!r} has case specs in both {plugins[0]!r} and {plugins[1]!r}; '
            f'skill names key the datasets harness-wide and must be unique'
        )
        self.skill = skill
        self.plugins = plugins


class UnknownPluginError(HarnessError):
    def __init__(self, plugin: str, registered: tuple[str, ...]) -> None:
        super().__init__(
            f'no case module registered for plugin {plugin!r}; '
            f'registered plugins: {", ".join(registered)}'
        )
        self.plugin = plugin
        self.registered = registered


def collect_specs(modules: Sequence[ModuleType]) -> tuple[CaseSpec, ...]:
    specs: list[CaseSpec] = []
    owner: dict[str, str] = {}
    for module in modules:
        for spec in module.SPECS:
            if spec.skill in owner:
                raise DuplicateSkillError(spec.skill, (owner[spec.skill], spec.plugin))
            owner[spec.skill] = spec.plugin
            specs.append(spec)
    return tuple(specs)


def all_specs() -> tuple[CaseSpec, ...]:
    return collect_specs(CASE_MODULES)


def plugin_names() -> tuple[str, ...]:
    return tuple(dict.fromkeys(spec.plugin for spec in all_specs()))


def select_specs(
    plugin: str | None = None, skill: str | None = None
) -> tuple[CaseSpec, ...]:
    if plugin is not None and plugin not in plugin_names():
        raise UnknownPluginError(plugin, plugin_names())

    specs = tuple(
        spec
        for spec in all_specs()
        if (plugin is None or spec.plugin == plugin)
        and (skill is None or spec.skill == skill)
    )
    if not specs:
        raise NoCasesError(skill)
    return specs


def plugin_for_skill(skill: str) -> str:
    return select_specs(skill=skill)[0].plugin
