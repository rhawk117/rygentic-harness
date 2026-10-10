from collections.abc import Sequence
from dataclasses import dataclass

from vibe_code_cli.tune.collisions import Collision
from vibe_code_cli.tune.domain.scoring import Scorecard, score_verdicts
from vibe_code_cli.tune.domain.state import LoopState
from vibe_code_cli.tune.domain.values import RoundResult, Skill

SCORE_HEADER = ('| | Train | Validation |', '|---|---|---|')
ROUND_HEADER = ('| Round | Skill | Train | Validation | Result |', '|---|---|---|---|---|')


def score_row(label: str, card: Scorecard) -> str:
    return f'| {label} | {card.train:.3f} | {card.validation:.3f} |'


def round_row(result: RoundResult) -> str:
    outcome = 'accepted' if result.accepted else 'rejected'
    scores = f'{result.train:.3f} | {result.validation:.3f}'
    return f'| {result.number} | {result.skill} | {scores} | {outcome} |'


def change_lines(skill: Skill, after: str) -> tuple[str, ...]:
    return (f'### {skill.name}', '', f'Before: {skill.description}', '', f'After: {after}', '')


@dataclass(slots=True, kw_only=True, frozen=True)
class MarkdownReport:
    state: LoopState
    collisions: Sequence[Collision]

    def scores(self) -> list[str]:
        history = self.state.history
        examples = self.state.setup.examples
        if history.baseline is None or history.accepted is None:
            return ['Baseline judging has not finished yet.']
        baseline = score_verdicts(examples, history.baseline.verdicts)
        final = score_verdicts(examples, history.accepted.verdicts)
        return [*SCORE_HEADER, score_row('Baseline', baseline), score_row('Final', final)]

    def rounds(self) -> list[str]:
        rows = [round_row(result) for result in self.state.history.rounds]
        if not rows:
            return ['No rewrite rounds ran.']
        return [*ROUND_HEADER, *rows]

    def changes(self) -> list[str]:
        final = self.state.accepted.descriptions
        changed = self.state.setup.changed(final)
        lines = [line for skill in changed for line in change_lines(skill, final[skill.name])]
        return lines or ['No descriptions changed.']

    def competitors(self) -> list[str]:
        names = self.state.competitors
        if not names:
            return ['None recorded; the subagent judge sees only the tuned skills.']
        listed = ', '.join(names)
        return [f'Claude Code also listed these skills in the routed sessions: {listed}.']

    def remaining_collisions(self) -> list[str]:
        lines = [f'- {collision.describe()}' for collision in self.collisions]
        return lines or ['None above the threshold.']

    def render(self) -> str:
        sections = (
            ('Scores', self.scores()),
            ('Rounds', self.rounds()),
            ('Changed descriptions', self.changes()),
            ('Competing skills', self.competitors()),
            ('Remaining collisions', self.remaining_collisions()),
        )
        judge = self.state.setup.options.judge.value
        lines = ['# Skill description tuning report', '', f'Judge: {judge}', '']
        for title, body in sections:
            lines.extend([f'## {title}', '', *body, ''])
        return '\n'.join(lines)
