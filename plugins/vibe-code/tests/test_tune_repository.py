from collections import Counter
from operator import attrgetter
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from vibe_code_cli.tune.domain.values import LoopOptions, Skill, Split
from vibe_code_cli.tune.errors import (
    DuplicateSkillError,
    MalformedTriggerSetError,
    MissingFrontmatterError,
    RewriteMismatchError,
    StaleSkillError,
)
from vibe_code_cli.tune.policy import Rewrite, SkillFilePolicy
from vibe_code_cli.tune.repository import (
    FileSkillRepository,
    PlannedWrite,
    StratifiedSplitter,
    TriggerEntry,
    YamlTriggerSetReader,
    parse_skill_document,
    read_skill,
)

REPOSITORY = FileSkillRepository()


def plan_description_write(skill: Skill, description: str) -> PlannedWrite:
    return REPOSITORY.plan_write(skill, description)


class TestReplaceDescription:
    body = '# Title\n\nBody keeps its --- separators.\n'

    @pytest.mark.parametrize(
        'frontmatter',
        [
            pytest.param('name: s\ndescription: plain text\nlicense: MIT\n', id='plain'),
            pytest.param('name: s\ndescription: "quoted: yes"\nlicense: MIT\n', id='quoted'),
            pytest.param(
                'name: s\ndescription: >-\n  folded one\n  folded two\nlicense: MIT\n',
                id='folded',
            ),
            pytest.param('name: s\ndescription: |\n  literal\nlicense: MIT\n', id='literal'),
        ],
    )
    def test_only_the_description_changes(self, tmp_path: Path, frontmatter: str) -> None:
        path = tmp_path.joinpath('SKILL.md')
        path.write_text(f'---\n{frontmatter}---\n{self.body}', encoding='utf-8')
        original = read_skill(path)
        plan_description_write(original, 'New text: with a colon & "quotes"').commit()
        rewritten = read_skill(path)
        assert rewritten.description == 'New text: with a colon & "quotes"'
        assert rewritten.name == original.name
        assert path.read_text(encoding='utf-8').endswith(self.body)
        assert 'license: MIT' in path.read_text(encoding='utf-8')

    def test_document_without_frontmatter_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path.joinpath('SKILL.md')
        with pytest.raises(MissingFrontmatterError):
            parse_skill_document(path, '# no frontmatter\n')

    def test_rendering_round_trips(self, tmp_path: Path) -> None:
        text = f'---\nname: s\ndescription: d\n---\n{self.body}'
        document = parse_skill_document(tmp_path, text)
        assert document.with_description(tmp_path, 'd').render() == text.replace(
            'description: d', 'description: "d"'
        )


class TestReadSkillWhenToUse:
    def test_when_to_use_is_filled_and_stripped(self, tmp_path: Path) -> None:
        path = tmp_path.joinpath('SKILL.md')
        path.write_text(
            '---\nname: s\ndescription: d\nwhen_to_use: |\n  use it now\n---\nbody\n',
            encoding='utf-8',
        )
        assert read_skill(path).when_to_use == 'use it now'

    def test_missing_when_to_use_defaults_to_empty(self, tmp_path: Path) -> None:
        path = tmp_path.joinpath('SKILL.md')
        path.write_text('---\nname: s\ndescription: d\n---\nbody\n', encoding='utf-8')
        assert read_skill(path).when_to_use == ''


class TestPlannedWriteSafety:
    def write_skill(self, tmp_path: Path, text: str) -> Path:
        path = tmp_path.joinpath('SKILL.md')
        path.write_bytes(text.encode('utf-8'))
        return path

    def test_crlf_line_endings_are_kept(self, tmp_path: Path) -> None:
        path = self.write_skill(tmp_path, '---\r\nname: s\r\ndescription: old\r\n---\r\nbody\r\n')
        plan_description_write(read_skill(path), 'new').commit()
        assert path.read_bytes() == (b'---\r\nname: s\r\ndescription: "new"\r\n---\r\nbody\r\n')

    def test_file_edited_since_init_is_refused(self, tmp_path: Path) -> None:
        path = self.write_skill(tmp_path, '---\nname: s\ndescription: old\n---\n')
        recorded = read_skill(path)
        path.write_text('---\nname: s\ndescription: edited\n---\n', encoding='utf-8')
        with pytest.raises(StaleSkillError):
            plan_description_write(recorded, 'new')

    def test_rewrite_breaking_an_alias_is_refused(self, tmp_path: Path) -> None:
        path = self.write_skill(
            tmp_path, '---\nname: s\ndescription: &shared old\nwhen_to_use: *shared\n---\n'
        )
        with pytest.raises(RewriteMismatchError):
            plan_description_write(read_skill(path), 'new')

    def test_missing_description_key_is_a_clean_error(self, tmp_path: Path) -> None:
        path = self.write_skill(tmp_path, '---\nname: s\nlicense: MIT\n---\n')
        document = parse_skill_document(path, path.read_text(encoding='utf-8'))
        with pytest.raises(MissingFrontmatterError):
            document.with_description(path, 'new')


class TestDiscoverSkills:
    def test_directories_are_scanned_for_skill_files(self, skills_dir: Path) -> None:
        names = {skill.name for skill in REPOSITORY.discover([skills_dir])}
        assert names == {'jira', 'pysymbols', 'terraform'}

    def test_duplicate_names_are_refused(self, skills_dir: Path) -> None:
        with pytest.raises(DuplicateSkillError):
            REPOSITORY.discover([skills_dir, skills_dir.joinpath('jira', 'SKILL.md')])


class TestSkillFilePolicyStaleness:
    skill = Skill(name='s', path='/s/SKILL.md', description='new')

    def test_unchanged_description_has_no_problem(self) -> None:
        policy = SkillFilePolicy()
        assert policy.get_stale_skill_problem(self.skill, {'description': 'new'}) is None

    def test_changed_description_is_stale(self) -> None:
        policy = SkillFilePolicy()
        problem = policy.get_stale_skill_problem(self.skill, {'description': 'old'})
        assert isinstance(problem, StaleSkillError)


class TestSkillFilePolicyRewrite:
    path = Path('/s/SKILL.md')
    policy = SkillFilePolicy()

    def test_matching_rewrite_has_no_problem(self) -> None:
        rewrite = Rewrite(
            path=self.path,
            description='new',
            original={'description': 'old', 'license': 'MIT'},
            rewritten={'description': 'new', 'license': 'MIT'},
        )
        assert self.policy.get_rewrite_problem(rewrite) is None

    def test_unparseable_rewrite_is_a_problem(self) -> None:
        rewrite = Rewrite(
            path=self.path, description='new', original={'description': 'old'}, rewritten=None
        )
        assert isinstance(self.policy.get_rewrite_problem(rewrite), RewriteMismatchError)

    def test_rewrite_changing_other_keys_is_a_problem(self) -> None:
        rewrite = Rewrite(
            path=self.path,
            description='new',
            original={'description': 'old', 'license': 'MIT'},
            rewritten={'description': 'new', 'license': 'Apache'},
        )
        assert isinstance(self.policy.get_rewrite_problem(rewrite), RewriteMismatchError)

    def test_rewrite_not_matching_description_is_a_problem(self) -> None:
        rewrite = Rewrite(
            path=self.path,
            description='new',
            original={'description': 'old'},
            rewritten={'description': 'different'},
        )
        assert isinstance(self.policy.get_rewrite_problem(rewrite), RewriteMismatchError)


class TestAssignSplits:
    entries = st.lists(
        st.builds(
            TriggerEntry,
            request=st.text(min_size=1, max_size=20),
            skills=st.lists(st.sampled_from(['a', 'b', 'c']), max_size=2, unique=True).map(tuple),
        ),
        min_size=1,
        max_size=40,
        unique_by=attrgetter('request'),
    )
    options = st.builds(
        LoopOptions,
        validation_fraction=st.floats(min_value=0.05, max_value=0.95),
        seed=st.integers(min_value=0, max_value=1000),
    )

    @given(entries, options)
    def test_every_request_appears_exactly_once(
        self, entries: list[TriggerEntry], options: LoopOptions
    ) -> None:
        examples = StratifiedSplitter(options=options).assign(entries)
        assert [e.request for e in examples] == [e.request for e in entries]
        assert len({e.request_id for e in examples}) == len(entries)

    @given(entries, options, st.data())
    def test_split_is_deterministic_in_any_order(
        self, entries: list[TriggerEntry], options: LoopOptions, data: st.DataObject
    ) -> None:
        splitter = StratifiedSplitter(options=options)
        shuffled = data.draw(st.permutations(entries))
        by_request = {e.request: e.split for e in splitter.assign(shuffled)}
        assert all(by_request[e.request] is e.split for e in splitter.assign(entries))

    @given(entries, options)
    def test_large_enough_strata_reach_validation(
        self, entries: list[TriggerEntry], options: LoopOptions
    ) -> None:
        sizes = Counter(entry.stratum for entry in entries)
        fraction = options.validation_fraction
        large = {stratum for stratum, size in sizes.items() if size * fraction >= 1}
        validated = {
            tuple(sorted(e.expected))
            for e in StratifiedSplitter(options=options).assign(entries)
            if e.split is Split.VALIDATION
        }
        assert large <= validated


class TestTriggerTextViolation:
    @pytest.mark.parametrize(
        ('text', 'truncated'),
        [
            pytest.param(
                '- request: give PR #214 a review\n  skills: [pr-review]\n',
                True,
                id='plain-with-hash',
            ),
            pytest.param(
                '- request: "give PR #214 a review"\n  skills: [pr-review]\n',
                False,
                id='quoted-with-hash',
            ),
            pytest.param(
                '- request: plain request  # a real comment\n  skills: []\n',
                True,
                id='trailing-comment',
            ),
            pytest.param('[{"request": "json #1", "skills": []}]', False, id='json'),
        ],
    )
    def test_comment_truncation_is_detected(self, text: str, truncated: bool) -> None:
        problem = YamlTriggerSetReader().get_text_problem(Path('triggers.yaml'), text)
        assert (problem is not None) is truncated


class TestMalformedTriggerSet:
    def test_wrongly_shaped_entry_raises_malformed_trigger_set(self, tmp_path: Path) -> None:
        path = tmp_path.joinpath('triggers.yaml')
        path.write_text('- request: [not, a, string]\n  skills: []\n', encoding='utf-8')
        with pytest.raises(MalformedTriggerSetError):
            YamlTriggerSetReader().read(path, LoopOptions())
