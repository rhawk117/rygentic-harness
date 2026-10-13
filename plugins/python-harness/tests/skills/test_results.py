"""Validation and publication of data-engineering's results.py."""

import hashlib
import json
import math
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import results
from pytest_mock import MockerFixture

CREATED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
NAIVE = datetime.fromisoformat('2026-01-01T00:00:00')


class FakeFigure:
    def __init__(self) -> None:
        self.saved: list[tuple[Path, dict[str, object]]] = []

    def savefig(self, fname: Path, **kwargs: object) -> None:
        self.saved.append((fname, kwargs))
        fname.write_text('<svg/>', encoding='utf-8')


def make_metric(**overrides: object) -> results.Metric:
    fields = {'name': 'mean', 'value': 1.5, 'unit': 'ms', 'n': 10, **overrides}
    return results.Metric(**fields)


def make_interval(**overrides: object) -> results.Interval:
    fields = {'lower': 1.0, 'upper': 2.0, 'level': 0.95, 'method': 'bootstrap', **overrides}
    return results.Interval(**fields)


def make_report(**overrides: object) -> results.AnalysisReport:
    fields = {
        'run_id': 'run-1',
        'created_at': CREATED_AT,
        'data_kind': results.DataKind.SYNTHETIC,
        'inputs': (results.InputRef(name='data.csv', sha256='abc'),),
        'parameters': {'seed': 7, 'label': 'x', 'ratio': 0.5, 'flag': True, 'none': None},
        'metrics': (make_metric(interval=make_interval()),),
        'checks': ('finite',),
        **overrides,
    }
    return results.AnalysisReport(**fields)


def make_bundle(**overrides: object) -> results.Bundle:
    fields = {
        'report': make_report(),
        'table': pa.table({'value': [1, 2, 3]}),
        'narrative': '# Report\n',
        **overrides,
    }
    return results.Bundle(**fields)


class TestFindMetricViolation:
    def test_a_complete_metric_has_no_violation(self) -> None:
        assert results.find_metric_violation(make_metric(interval=make_interval())) is None

    @pytest.mark.parametrize(
        'metric',
        [
            make_metric(value=math.nan),
            make_metric(value=math.inf),
            make_metric(interval=make_interval(lower=-math.inf)),
            make_metric(interval=make_interval(upper=math.nan)),
        ],
    )
    def test_nonfinite_values_and_bounds_are_reported(self, metric: results.Metric) -> None:
        violation = results.find_metric_violation(metric)

        assert isinstance(violation, results.NonFiniteMetricError)
        assert "metric 'mean' has a nonfinite value or interval bound" in str(violation)

    @pytest.mark.parametrize(
        'metric',
        [make_metric(name=''), make_metric(unit=''), make_metric(n=-1)],
    )
    def test_incomplete_metrics_are_reported(self, metric: results.Metric) -> None:
        assert isinstance(results.find_metric_violation(metric), results.IncompleteMetricError)

    def test_a_missing_count_is_allowed(self) -> None:
        assert results.find_metric_violation(make_metric(n=None)) is None

    @pytest.mark.parametrize(
        'interval',
        [
            make_interval(lower=3.0, upper=2.0),
            make_interval(level=0.0),
            make_interval(level=1.0),
        ],
    )
    def test_invalid_intervals_are_reported(self, interval: results.Interval) -> None:
        violation = results.find_metric_violation(make_metric(interval=interval))

        assert isinstance(violation, results.InvalidIntervalError)

    def test_nonfinite_is_reported_before_incomplete(self) -> None:
        violation = results.find_metric_violation(make_metric(name='', value=math.nan))

        assert isinstance(violation, results.NonFiniteMetricError)


class TestFindReportViolation:
    def test_a_complete_report_has_no_violation(self) -> None:
        assert results.find_report_violation(make_report()) is None

    def test_a_naive_timestamp_is_reported(self) -> None:
        violation = results.find_report_violation(make_report(created_at=NAIVE))

        assert isinstance(violation, results.NonUtcTimestampError)

    def test_an_aware_timestamp_that_is_not_utc_is_reported(self) -> None:
        created_at = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=1)))

        violation = results.find_report_violation(make_report(created_at=created_at))

        assert isinstance(violation, results.NonUtcTimestampError)

    def test_a_report_without_inputs_is_reported(self) -> None:
        violation = results.find_report_violation(make_report(inputs=()))

        assert isinstance(violation, results.MissingInputsError)

    def test_a_repeated_metric_name_is_reported(self) -> None:
        metrics = (make_metric(), make_metric(value=2.0))

        violation = results.find_report_violation(make_report(metrics=metrics))

        assert isinstance(violation, results.DuplicateMetricError)

    def test_the_first_metric_violation_is_returned(self) -> None:
        metrics = (make_metric(name='a'), make_metric(name='b', value=math.nan))

        violation = results.find_report_violation(make_report(metrics=metrics))

        assert isinstance(violation, results.NonFiniteMetricError)
        assert "'b'" in str(violation)


class TestErrorMessages:
    @pytest.mark.parametrize(
        ('error', 'fragment'),
        [
            (results.InvalidIntervalError, 'lower <= upper'),
            (results.IncompleteMetricError, 'nonnegative n'),
            (results.NonUtcTimestampError, 'UTC-aware created_at'),
            (results.MissingInputsError, 'no inputs'),
            (results.DuplicateMetricError, 'repeats a metric name'),
        ],
    )
    def test_each_error_names_its_subject_and_rule(self, error: type, fragment: str) -> None:
        assert fragment in str(error('subject'))
        assert "'subject'" in str(error('subject'))
        assert issubclass(error, ValueError)


class TestEnvironment:
    def test_file_sha256_matches_hashlib(self, tmp_path: Path) -> None:
        path = tmp_path / 'data.bin'
        path.write_bytes(b'payload')

        assert results.file_sha256(path) == hashlib.sha256(b'payload').hexdigest()

    def test_an_installed_package_reports_its_version(self) -> None:
        assert results.installed_version('msgspec') not in {'', 'not installed'}

    def test_an_unknown_package_reports_not_installed(self) -> None:
        assert results.installed_version('no-such-package-here') == 'not installed'

    def test_the_environment_lists_python_and_the_requested_packages(self) -> None:
        options = results.PublicationOptions(packages=('msgspec', 'no-such-package-here'))

        environment = results.describe_environment(options)

        assert environment.python.count('.') == 2
        assert set(environment.packages) == {'msgspec', 'no-such-package-here'}
        assert environment.packages['no-such-package-here'] == 'not installed'


class TestPublishBundle:
    def test_the_artifacts_and_manifest_are_written(self, tmp_path: Path) -> None:
        directory = tmp_path / 'run'

        manifest_path = results.publish_bundle(directory, make_bundle())

        assert manifest_path == directory / 'manifest.json'
        assert sorted(path.name for path in directory.iterdir()) == [
            'manifest.json',
            'metrics.json',
            'report.md',
            'table.parquet',
        ]

    def test_the_table_is_a_real_parquet_file(self, tmp_path: Path) -> None:
        directory = tmp_path / 'run'

        results.publish_bundle(directory, make_bundle())

        assert pq.read_table(directory / 'table.parquet').to_pydict() == {'value': [1, 2, 3]}

    def test_the_manifest_describes_every_artifact(self, tmp_path: Path) -> None:
        directory = tmp_path / 'run'

        manifest_path = results.publish_bundle(directory, make_bundle())

        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        assert manifest['schema_version'] == results.SCHEMA_VERSION
        assert manifest['run_id'] == 'run-1'
        assert manifest['publication_status'] == 'complete'
        assert [artifact['name'] for artifact in manifest['artifacts']] == [
            'metrics.json',
            'table.parquet',
            'report.md',
        ]
        for artifact in manifest['artifacts']:
            written = (directory / artifact['name']).read_bytes()
            assert artifact['size_bytes'] == len(written)
            assert artifact['sha256'] == hashlib.sha256(written).hexdigest()

    def test_the_metrics_file_holds_the_report_and_environment(self, tmp_path: Path) -> None:
        directory = tmp_path / 'run'

        results.publish_bundle(directory, make_bundle())

        published = json.loads((directory / 'metrics.json').read_text(encoding='utf-8'))
        assert published['schema_version'] == results.SCHEMA_VERSION
        assert published['report']['run_id'] == 'run-1'
        assert published['report']['data_kind'] == 'synthetic'
        assert set(published['environment']['packages']) == {'msgspec', 'pyarrow'}

    def test_the_narrative_is_written_as_given(self, tmp_path: Path) -> None:
        directory = tmp_path / 'run'

        results.publish_bundle(directory, make_bundle(narrative='hello\n'))

        assert (directory / 'report.md').read_text(encoding='utf-8') == 'hello\n'

    def test_a_figure_is_saved_and_listed(self, tmp_path: Path) -> None:
        directory = tmp_path / 'run'
        figure = FakeFigure()

        manifest_path = results.publish_bundle(directory, make_bundle(figure=figure))

        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        assert figure.saved == [(directory / 'figure.svg', {'bbox_inches': 'tight'})]
        assert manifest['artifacts'][-1]['name'] == 'figure.svg'

    def test_custom_names_are_honoured(self, tmp_path: Path) -> None:
        directory = tmp_path / 'run'
        options = results.PublicationOptions(
            metrics_name='m.json',
            table_name='t.parquet',
            narrative_name='n.md',
            manifest_name='done.json',
        )

        manifest_path = results.publish_bundle(directory, make_bundle(), options)

        assert manifest_path.name == 'done.json'
        assert (directory / 'm.json').is_file()
        assert (directory / 't.parquet').is_file()
        assert (directory / 'n.md').is_file()
        assert not (directory / '.done.json.tmp').exists()


class TestPublishOrderAndFailures:
    def test_the_manifest_is_written_after_every_artifact(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        directory = tmp_path / 'run'
        seen: list[tuple[str, ...]] = []
        original = results.write_manifest

        def spy(
            target: Path, manifest: results.Manifest, options: results.PublicationOptions
        ) -> Path:
            seen.append(tuple(sorted(path.name for path in target.iterdir())))
            return original(target, manifest, options)

        mocker.patch.object(results, 'write_manifest', side_effect=spy)

        results.publish_bundle(directory, make_bundle(figure=FakeFigure()))

        assert seen == [('figure.svg', 'metrics.json', 'report.md', 'table.parquet')]

    def test_a_failed_artifact_write_leaves_no_manifest(
        self, tmp_path: Path, mocker: MockerFixture
    ) -> None:
        directory = tmp_path / 'run'
        mocker.patch.object(results.pq, 'write_table', side_effect=OSError('disk full'))

        with pytest.raises(OSError, match='disk full'):
            results.publish_bundle(directory, make_bundle())

        assert not (directory / 'manifest.json').exists()

    def test_an_existing_directory_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(FileExistsError):
            results.publish_bundle(tmp_path, make_bundle())

    @pytest.mark.parametrize(
        ('changes', 'error'),
        [
            ({'metrics': (make_metric(value=math.nan),)}, 'NonFiniteMetricError'),
            ({'metrics': (make_metric(name=''),)}, 'IncompleteMetricError'),
            (
                {'metrics': (make_metric(interval=make_interval(level=2.0)),)},
                'InvalidIntervalError',
            ),
            ({'created_at': NAIVE}, 'NonUtcTimestampError'),
            ({'inputs': ()}, 'MissingInputsError'),
            ({'metrics': (make_metric(), make_metric())}, 'DuplicateMetricError'),
        ],
    )
    def test_an_invalid_report_raises_before_anything_is_written(
        self, tmp_path: Path, changes: dict[str, Any], error: str
    ) -> None:
        directory = tmp_path / 'run'

        with pytest.raises(getattr(results, error)):
            results.publish_bundle(directory, make_bundle(report=make_report(**changes)))

        assert not directory.exists()
