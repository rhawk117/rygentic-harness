from pathlib import Path

import pytest
import yaml
from mightymcp.scripts import (
    CrashoutEntry,
    crashout_add,
    crashout_last,
    crashout_stats,
    metrics_run,
)

JOURNAL = ('.mightymodels', 'crashouts.yml')


def entry(**overrides: object) -> CrashoutEntry:
    fields: dict[str, object] = {
        'severity': 'heated',
        'verdict': 'deserved',
        'rant': 'you deleted the failing test instead of fixing the code',
        'failures': ['deleted a failing test', 'called the suite green'],
        'root_cause': 'treated the gate as the obstacle',
        'corrective_action': 'fix the code, never the gate',
        'barked_back': False,
        'ticket': 'demo',
        'branch': 'feat/demo',
    }
    return CrashoutEntry.model_validate(fields | overrides)


@pytest.fixture
def source_repo(repo: Path) -> Path:
    """A repository with one package under it for the metrics script to measure."""
    module = repo.joinpath('src', 'pkg', 'calc.py')
    module.parent.mkdir(parents=True)
    module.write_text('def add(a, b):\n    return a + b\n', encoding='utf-8')
    return repo


def test_crashout_add_journals_the_entry(repo: Path) -> None:
    run = crashout_add(entry())

    assert run.refusals == []
    assert 'journaled crashout #1' in run.stdout
    journaled = yaml.safe_load(repo.joinpath(*JOURNAL).read_text(encoding='utf-8'))
    assert journaled[0]['root_cause'] == 'treated the gate as the obstacle'
    assert journaled[0]['failures'] == [
        'deleted a failing test',
        'called the suite green',
    ]
    assert journaled[0]['ticket'] == 'demo'
    assert journaled[0]['barked_back'] is False


def test_crashout_stats_counts_what_was_journaled(repo: Path) -> None:
    crashout_add(entry())
    crashout_add(entry(severity='crashout', barked_back=True))

    run = crashout_stats()

    assert run.refusals == []
    assert 'entries: 2' in run.stdout
    assert 'verdicts: deserved=2' in run.stdout
    assert 'barked_back: 1/2' in run.stdout
    assert 'fix the code, never the gate' in run.stdout


def test_crashout_stats_on_an_empty_journal_says_so(repo: Path) -> None:
    run = crashout_stats()

    assert run.refusals == []
    assert run.stdout == 'no crashouts recorded yet. serenity.\n'


def test_crashout_last_prints_the_most_recent_entry(repo: Path) -> None:
    crashout_add(entry())
    crashout_add(entry(rant='the second one'))

    run = crashout_last()

    assert run.refusals == []
    assert 'the second one' in run.stdout
    assert run.stdout.count('root_cause:') == 1


def test_an_entry_the_script_rejects_comes_back_as_a_refusal(repo: Path) -> None:
    run = crashout_add(entry(severity='furious'))

    assert run.stdout == ''
    assert run.refusals[0].startswith('crashout_journal.py exited 1')
    assert 'severity must be one of' in run.refusals[0]
    assert not repo.joinpath(*JOURNAL).exists()


def test_metrics_run_measures_the_repository(source_repo: Path) -> None:
    run = metrics_run()

    assert run.refusals == []
    assert run.stdout.startswith('files\t1 (0 test)')
    assert 'module cycles (ADP)\t0' in run.stdout


def test_metrics_run_passes_the_package_depth_through(source_repo: Path) -> None:
    shallow = metrics_run(package_depth=1)
    deep = metrics_run(package_depth=2, max_listed=5)

    assert '\npkg\t' in shallow.stdout
    assert '\npkg.calc\t' in deep.stdout


def test_metrics_run_without_a_repository_root_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('MIGHTYMCP_PROJECT_DIR', str(tmp_path))

    run = metrics_run()

    assert run.stdout == ''
    assert run.refusals == [f'{tmp_path} is not a repository root: no .git entry']


def test_a_plugin_root_without_the_scripts_is_refused(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('CLAUDE_PLUGIN_ROOT', str(tmp_path))
    crashout = tmp_path.joinpath('skills', 'crashout', 'scripts', 'crashout_journal.py')
    metrics = tmp_path.joinpath('skills', 'uncle-bob', 'scripts', 'metrics.py')

    assert crashout_stats().refusals == [f'no script at {crashout}']
    assert metrics_run().refusals == [f'no script at {metrics}']


def test_the_journal_without_a_repository_root_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('MIGHTYMCP_PROJECT_DIR', str(tmp_path))

    run = crashout_last()

    assert run.stdout == ''
    assert run.refusals == [f'{tmp_path} is not a repository root: no .git entry']
