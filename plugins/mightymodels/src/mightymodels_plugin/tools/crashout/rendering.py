"""The two texts of the crashout journal: its recurring patterns, and one crashout in full.

The patterns count the journal by severity and by verdict, most frequent first, list every
failure under the day, verdict and severity of its crashout, and end with the corrective actions,
each once. Two actions are the same when they differ only in whitespace: grouping by meaning is
the reader's work.

One crashout reads as a line per field in the journal's field order, the rant and the failures
indented under their names.
"""

from collections import Counter
from collections.abc import Iterable, Sequence

from mightymodels_plugin.tools.crashout.schema import JournaledCrashout

DAY_LENGTH = 10
ABSENT = 'none'


def counted(names: Iterable[str]) -> str:
    return ' '.join(f'{name}={count}' for name, count in Counter(names).most_common())


def failure_lines(crashout: JournaledCrashout) -> list[str]:
    tag = f'[{crashout.at[:DAY_LENGTH]} | {crashout.verdict} | {crashout.severity}]'
    return [f'  {tag} {failure}' for failure in crashout.failures]


def standing_actions(journal: Sequence[JournaledCrashout]) -> list[str]:
    actions = dict.fromkeys(' '.join(crashout.corrective_action.split()) for crashout in journal)
    return [f'  - {action}' for action in actions]


def patterns_text(journal: Sequence[JournaledCrashout]) -> str:
    barked = sum(crashout.barked_back for crashout in journal)
    lines = [
        f'entries: {len(journal)}',
        f'severity: {counted(crashout.severity for crashout in journal)}',
        f'verdicts: {counted(crashout.verdict for crashout in journal)}',
        f'barked_back: {barked}/{len(journal)}',
        f'first: {journal[0].at}  last: {journal[-1].at}',
        '',
        'failures:',
        *(line for crashout in journal for line in failure_lines(crashout)),
        '',
        'standing corrective actions:',
        *standing_actions(journal),
    ]
    return '\n'.join(lines) + '\n'


def crashout_text(crashout: JournaledCrashout) -> str:
    lines = [
        f'at: {crashout.at}',
        f'ticket: {ABSENT if crashout.ticket is None else crashout.ticket}',
        f'branch: {ABSENT if crashout.branch is None else crashout.branch}',
        f'severity: {crashout.severity}',
        f'verdict: {crashout.verdict}',
        'rant:',
        *(f'  {line}' for line in crashout.rant.split('\n')),
        'failures:',
        *(f'  - {failure}' for failure in crashout.failures),
        f'root_cause: {crashout.root_cause}',
        f'corrective_action: {crashout.corrective_action}',
        f'barked_back: {str(crashout.barked_back).lower()}',
    ]
    return '\n'.join(lines) + '\n'
