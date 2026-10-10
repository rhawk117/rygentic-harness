import string
from collections.abc import Iterable

import msgspec
from hypothesis import strategies as st

from vibe_code_cli.tune.domain.state import RunSetup
from vibe_code_cli.tune.domain.values import Judge, LoopOptions, Skill
from vibe_code_cli.tune.repository import StratifiedSplitter, TriggerEntry
from vibe_code_cli.tune.schemas import JudgePacket, ProposePacket

type JudgeAnswer = dict[str, list[str]]

SKILL_NAMES = ('alpha', 'beta', 'gamma', 'delta')
UNKNOWN_SKILLS = ('ghost', 'Alpha', '', 'alpha ')
STRAY_KEYS = ('q0', 'q01', 'Q1', '1', 'q')
VOCABULARY = (
    'ticket',
    'sprint',
    'backlog',
    'module',
    'function',
    'callers',
    'bucket',
    'state',
    'plan',
    'haiku',
)
BLANK = st.text(alphabet=' \t\n', max_size=4)

phrases = st.lists(st.sampled_from(VOCABULARY), min_size=1, max_size=4).map(' '.join)

loop_options = st.builds(
    LoopOptions,
    judge=st.just(Judge.SUBAGENT),
    validation_fraction=st.floats(min_value=0.3, max_value=0.7),
    batch_size=st.integers(min_value=2, max_value=5),
    max_rounds=st.integers(min_value=1, max_value=3),
    patience=st.integers(min_value=1, max_value=3),
    min_gain=st.sampled_from((0.0, 0.05)),
    max_description_chars=st.integers(min_value=40, max_value=80),
    seed=st.integers(min_value=0, max_value=1000),
)


def skill_for(name: str, phrase: str) -> Skill:
    return Skill(name=name, path=f'/{name}/SKILL.md', description=f'Use for {phrase}.')


@st.composite
def skill_libraries(draw: st.DrawFn) -> tuple[Skill, ...]:
    names = draw(st.lists(st.sampled_from(SKILL_NAMES), min_size=1, max_size=3, unique=True))
    return tuple(skill_for(name, draw(phrases)) for name in names)


@st.composite
def trigger_entries(draw: st.DrawFn, skills: tuple[Skill, ...]) -> list[TriggerEntry]:
    names = [skill.name for skill in skills]
    strata = st.lists(st.sampled_from(names), unique=True).map(tuple)
    first, second, *rest = draw(st.lists(phrases, min_size=2, max_size=5, unique=True))
    shared = draw(strata)
    others = [TriggerEntry(request=request, skills=draw(strata)) for request in rest]
    return [
        TriggerEntry(request=first, skills=shared),
        TriggerEntry(request=second, skills=shared),
        *others,
    ]


@st.composite
def run_setups(draw: st.DrawFn) -> RunSetup:
    skills = draw(skill_libraries())
    options = draw(loop_options)
    entries = draw(trigger_entries(skills))
    return RunSetup(
        run_id='h0',
        skills=skills,
        examples=StratifiedSplitter(options=options).assign(entries),
        options=options,
    )


def verdicts_for(setup: RunSetup) -> st.SearchStrategy[dict[str, frozenset[str]]]:
    chosen = st.frozensets(st.sampled_from(sorted(setup.skill_names)))
    return st.fixed_dictionaries({example.request_id: chosen for example in setup.examples})


def answer_keys(size: int) -> frozenset[str]:
    return frozenset(f'q{index}' for index in range(1, size + 1))


def wrong_answer_keys(size: int) -> st.SearchStrategy[frozenset[str]]:
    expected = answer_keys(size)
    strays = st.sampled_from((*STRAY_KEYS, f'q{size + 1}'))
    kept = st.frozensets(st.sampled_from(sorted(expected)), max_size=size - 1)
    short = st.builds(frozenset.union, kept, st.frozensets(strays))
    padded = st.builds(frozenset.union, st.just(expected), st.frozensets(strays, min_size=1))
    return short | padded


def empty_answer(keys: Iterable[str]) -> bytes:
    return msgspec.json.encode({key: [] for key in sorted(keys)})


def judge_answers(packet: JudgePacket) -> st.SearchStrategy[JudgeAnswer]:
    chosen = st.lists(st.sampled_from(sorted(packet.skills)), unique=True)
    return st.fixed_dictionaries(dict.fromkeys(packet.requests, chosen))


def with_unknown_skill(answer: JudgeAnswer) -> st.SearchStrategy[bytes]:
    tampered = [
        {**answer, key: [*answer[key], stray]} for key in sorted(answer) for stray in UNKNOWN_SKILLS
    ]
    return st.sampled_from([msgspec.json.encode(variant) for variant in tampered])


def broken_json(answer: JudgeAnswer) -> st.SearchStrategy[bytes]:
    encoded = msgspec.json.encode(answer)
    truncated = st.sampled_from([encoded[:end] for end in range(len(encoded))])
    not_a_mapping = st.one_of(
        st.integers(), st.text(max_size=5), st.lists(st.integers(), max_size=3)
    )
    unlisted = st.fixed_dictionaries(dict.fromkeys(answer, st.text(max_size=5)))
    return truncated | (not_a_mapping | unlisted).map(msgspec.json.encode)


def malformed_judge_answers(packet: JudgePacket) -> st.SearchStrategy[bytes]:
    answers = judge_answers(packet)
    return st.one_of(
        wrong_answer_keys(len(packet.requests)).map(empty_answer),
        answers.flatmap(with_unknown_skill),
        answers.flatmap(broken_json),
    )


def invalid_proposals(packet: ProposePacket) -> st.SearchStrategy[str]:
    too_long = st.text(
        alphabet=string.ascii_letters,
        min_size=packet.max_chars + 1,
        max_size=packet.max_chars + 8,
    )
    tried = st.sampled_from((packet.current, *packet.rejected))
    padded = st.tuples(BLANK, tried, BLANK).map(''.join)
    return st.one_of(BLANK, too_long, padded)
