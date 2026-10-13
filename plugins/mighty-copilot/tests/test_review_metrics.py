"""`mightymodels review-metrics` against a fixed tree and its recorded output."""

import json
from pathlib import Path

import pytest
from mightymodels.cli import main

COMMAND = 'review-metrics'
GOLDEN = Path(__file__).resolve().parent.joinpath('fixtures')
LONG = 'x = "' + 'a' * 130 + '"'
FAILED_ROOT = 2
CORE_PY = [
    'from abc import ABC, abstractmethod',
    'from . import io',
    '',
    '',
    'class Store(ABC):',
    '    @abstractmethod',
    '    def load(self): ...',
    '',
    '',
    'class Plain:',
    '    pass',
    '',
    '',
    'def busy(a, b, c, d, flag: bool = False, *rest, **extra):',
    '    for item in a:',
    '        if item:',
    '            while b:',
    '                b -= 1',
    '        elif c:',
    '            pass',
    *[f'    step_{n} = {n}' for n in range(20)],
    '    return io.write(a)',
    '',
    LONG,
]
IO_PY = [
    'from billing.core import Plain',
    'import os',
    '',
    '',
    'def write(value, verbose=True):',
    '    return Plain, os, value, verbose',
]
INDEX_TS = [
    "import { helper } from './util';",
    "export * from './shapes/index';",
    'export interface Shape { area(): number }',
    'export abstract class Base implements Shape {',
    '  abstract area(): number;',
    '}',
    'export class Square extends Base {',
    '  area(): number { return 4; }',
    '}',
    'export function draw(shape: Shape, fill: boolean, scale = 1, dry = false) {',
    '  if (fill) {',
    '    return helper(shape, scale, dry);',
    '  }',
    '  return null;',
    '}',
]
UTIL_JS = [
    "const lodash = require('lodash');",
    'const helper = (shape, scale, dry) => {',
    '  return lodash.identity([shape, scale, dry]);',
    '};',
    'async function load(url, { retries = 3, verbose = false } = {}) {',
    '  return fetch(url);',
    '}',
    'module.exports = { helper, load };',
]
SPEC_PY = ['from billing import core', '', '', 'def check():', '    return core']
CLI_PY = ['from billing.io import write', '', '', 'def run():', '    return write(1)']
UTIL_TEST_JS = ["const { helper } = require('./util');", "test('x', () => helper());"]
IGNORED_JS = ['function ignored(a,b,c,d,e){}']
SAMPLE: dict[str, list[str]] = {
    'src/billing/__init__.py': [],
    'src/billing/core.py': CORE_PY,
    'src/billing/io.py': IO_PY,
    'src/billing/spec/core_spec.py': SPEC_PY,
    'lib/tools/cli.py': CLI_PY,
    'web/index.ts': INDEX_TS,
    'web/shapes/index.ts': ["import { draw } from '../index';", 'export const unit = 1;'],
    'web/util.js': UTIL_JS,
    'web/util.test.js': UTIL_TEST_JS,
    'web/vendor.min.js': IGNORED_JS,
    'node_modules/dep/index.js': IGNORED_JS,
    '.hidden/skip.py': ['def ignored(a, b, c, d, e): ...'],
}


@pytest.fixture
def sample(tmp_path: Path) -> Path:
    root = tmp_path.joinpath('sample')
    for name, lines in SAMPLE.items():
        path = root.joinpath(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return root


@pytest.mark.parametrize('depth', [1, 2])
def test_output_matches_the_recorded_report(
    sample: Path, capsys: pytest.CaptureFixture[str], depth: int
) -> None:
    out = sample.parent.joinpath('metrics.json')
    code = main([COMMAND, str(sample), '--out', str(out), '--package-depth', str(depth)])
    printed = capsys.readouterr().out
    report = json.loads(out.read_text(encoding='utf-8'))
    golden = GOLDEN.joinpath(f'metrics-depth-{depth}')
    assert code == 0
    expected = json.loads(golden.with_suffix('.json').read_text(encoding='utf-8'))
    assert report == expected
    summary = printed.split('\n', 1)[1]
    assert summary == golden.with_suffix('.txt').read_text(encoding='utf-8')


def test_a_missing_root_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    absent = tmp_path.joinpath('absent')
    code = main([COMMAND, str(absent)])
    assert code == FAILED_ROOT
    assert capsys.readouterr().err == f'error: {absent.resolve()} is not a directory\n'
