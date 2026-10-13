"""The source files under a root and what each one measures.

The walk takes Python, JavaScript and TypeScript files in sorted order and leaves out hidden and
vendored directories, minified and bundled scripts and type declaration files. Python is parsed
with `ast`, so its numbers are exact. JavaScript and TypeScript are read with patterns: the
imports are reliable, the function numbers are approximate and each one says so.
"""

import ast
import logging
import re
from dataclasses import replace
from pathlib import Path

from mightymodels.review_metrics.shapes import LINE_LIMIT, FileMetric, FunctionMetric

IGNORED_DIRS = frozenset(
    {
        '.git',
        '.hg',
        '.svn',
        'node_modules',
        '__pycache__',
        '.venv',
        'venv',
        'env',
        '.tox',
        '.mypy_cache',
        '.ruff_cache',
        '.pytest_cache',
        'dist',
        'build',
        '.next',
        '.nuxt',
        'coverage',
        'vendor',
        'target',
        '.idea',
        '.vscode',
        'site-packages',
        '.eggs',
    }
)
PY_SUFFIXES = frozenset({'.py'})
JS_SUFFIXES = frozenset({'.js', '.jsx', '.mjs', '.cjs'})
TS_SUFFIXES = frozenset({'.ts', '.tsx', '.mts', '.cts'})
MIN_CAPTURE_GROUPS = 2
TEST_DIR_NAMES = frozenset({'test', 'tests', '__tests__', 'spec', 'specs'})
OPENING_BRACKETS = '([{<'
CLOSING_BRACKETS = ')]}>'
LOGGER = logging.getLogger(__name__)

JS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[\w*{},\s$]+\s+from\s+)?|export\s+[\w*{},\s$]+\s+from\s+|"""
    r"""require\(\s*|import\(\s*)['"]([^'"]+)['"]"""
)
JS_FUNC_RES = (
    re.compile(
        r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([\w$]+)?\s*\(([^)]*)\)'
    ),
    re.compile(
        r'^\s*(?:export\s+)?(?:const|let|var)\s+([\w$]+)\s*=\s*(?:async\s+)?(?:function\s*\*?\s*)?\(([^)]*)\)\s*(?:=>|\{)'
    ),
    re.compile(r'^\s*(?:const|let|var)\s+([\w$]+)\s*=\s*(?:async\s+)?([\w$]+)\s*=>'),
)
TS_ABSTRACT_RE = re.compile(
    r'^\s*(?:export\s+)?(?:declare\s+)?(?:abstract\s+class|interface)\s+[\w$]+',
    re.MULTILINE,
)
TS_CLASS_RE = re.compile(
    r'^\s*(?:export\s+)?(?:declare\s+)?(?:abstract\s+)?class\s+[\w$]+', re.MULTILINE
)


def language_of(path: Path) -> str | None:
    if path.suffix in PY_SUFFIXES:
        return 'python'
    if path.suffix in JS_SUFFIXES:
        return 'javascript'
    if path.suffix in TS_SUFFIXES:
        return 'typescript'
    return None


def is_test_path(rel: Path) -> bool:
    parts = {p.lower() for p in rel.parts[:-1]}
    if parts & TEST_DIR_NAMES:
        return True
    stem = rel.stem.lower()
    if stem.startswith('test_') or stem.endswith('_test') or stem == 'conftest':
        return True
    return any(marker in rel.name.lower() for marker in ('.spec.', '.test.'))


def iter_source_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in sorted(root.rglob('*')):
        if not path.is_file() or language_of(path) is None:
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in IGNORED_DIRS or part.startswith('.') for part in rel_parts[:-1]):
            continue
        if path.name.endswith(('.min.js', '.bundle.js', '.d.ts')):
            continue
        found.append(path)
    return found


def count_loc(text: str) -> tuple[int, int]:
    loc = 0
    long_lines = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        loc += 1
        if len(line) > LINE_LIMIT:
            long_lines += 1
    return loc, long_lines


def module_name_for(rel: Path) -> str:
    parts = list(rel.parts)
    parts[-1] = rel.stem
    if parts[-1] in ('__init__', 'index'):
        parts = parts[:-1]
    return '.'.join(parts) if parts else rel.stem


def python_param_stats(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[int, int]:
    args = node.args
    params = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    named = [a for a in params if a.arg not in ('self', 'cls')]
    bool_count = 0
    defaults = [*args.defaults, *args.kw_defaults]
    for default in defaults:
        if isinstance(default, ast.Constant) and isinstance(default.value, bool):
            bool_count += 1
    for arg in named:
        annotation = getattr(arg, 'annotation', None)
        if isinstance(annotation, ast.Name) and annotation.id == 'bool':
            bool_count += 1
    extra = (1 if args.vararg else 0) + (1 if args.kwarg else 0)
    return len(named) + extra, min(bool_count, len(named))


SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
NESTING_NODES = (
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Match,
)


def dispatch_depth(child: ast.AST, depth: int) -> int:
    if isinstance(child, SCOPE_NODES):
        return depth
    if isinstance(child, ast.If):
        return if_chain_depth(child, depth + 1)
    if isinstance(child, NESTING_NODES):
        return python_max_depth(child, depth + 1)
    return python_max_depth(child, depth)


def python_max_depth(node: ast.AST, depth: int = 0) -> int:
    deepest = depth
    for child in ast.iter_child_nodes(node):
        deepest = max(deepest, dispatch_depth(child, depth))
    return deepest


def if_chain_depth(node: ast.If, depth: int) -> int:
    deepest = depth
    for stmt in node.body:
        deepest = max(deepest, dispatch_depth(stmt, depth))
    if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
        return max(deepest, if_chain_depth(node.orelse[0], depth))
    for stmt in node.orelse:
        deepest = max(deepest, dispatch_depth(stmt, depth))
    return deepest


def ast_name(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ''


def is_abstract_method(item: ast.stmt) -> bool:
    if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    return any(
        ast_name(decorator) in ('abstractmethod', 'abstractproperty')
        for decorator in item.decorator_list
    )


def class_is_abstract(node: ast.ClassDef) -> bool:
    if any(ast_name(base) in ('ABC', 'Protocol', 'ABCMeta') for base in node.bases):
        return True
    if any(keyword.arg == 'metaclass' for keyword in node.keywords):
        return True
    return any(map(is_abstract_method, node.body))


def import_names(node: ast.AST, package_parts: list[str]) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        return from_import_names(node, package_parts)
    return []


def python_imports(tree: ast.Module, module: str) -> list[str]:
    package_parts = module.split('.')[:-1]
    return [name for node in ast.walk(tree) for name in import_names(node, package_parts)]


def from_import_base(node: ast.ImportFrom, package_parts: list[str]) -> str:
    if node.level == 0:
        return node.module or ''
    prefix = '.'.join(package_parts[: len(package_parts) - node.level + 1])
    return '.'.join(filter(None, (prefix, node.module)))


def from_import_names(node: ast.ImportFrom, package_parts: list[str]) -> list[str]:
    base = from_import_base(node, package_parts)
    names = [alias.name for alias in node.names if alias.name != '*']
    if not names:
        return [base] if base else []
    return ['.'.join(filter(None, (base, name))) for name in names]


def analyze_python(_path: Path, rel: Path, text: str) -> FileMetric:
    loc, long_lines = count_loc(text)
    metric = FileMetric(
        path=str(rel),
        language='python',
        loc=loc,
        long_lines=long_lines,
        is_test=is_test_path(rel),
    )
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return metric
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    return replace(
        metric,
        classes=len(classes),
        abstract_classes=sum(1 for node in classes if class_is_abstract(node)),
        functions=tuple(
            python_function(node, rel)
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ),
        imports=tuple(python_imports(tree, module_name_for(rel))),
    )


def python_function(node: ast.FunctionDef | ast.AsyncFunctionDef, rel: Path) -> FunctionMetric:
    params, bool_params = python_param_stats(node)
    end = getattr(node, 'end_lineno', node.lineno)
    return FunctionMetric(
        file=str(rel),
        name=node.name,
        line=node.lineno,
        loc=end - node.lineno + 1,
        params=params,
        bool_params=bool_params,
        max_depth=python_max_depth(node),
    )


def js_function_end(lines: list[str], start: int) -> int:
    end = min(start + 1, len(lines) - 1)
    depth = 0
    opened = False
    for idx in range(start, len(lines)):
        line = lines[idx]
        depth += line.count('{') - line.count('}')
        opened = opened or '{' in line
        closed = opened and depth <= 0
        terminated = not opened and line.rstrip().endswith((';', ',')) and idx > start
        if closed or terminated:
            end = idx
            break
    return end


def bracket_step(char: str) -> int:
    if char in OPENING_BRACKETS:
        return 1
    if char in CLOSING_BRACKETS:
        return -1
    return 0


def js_param_stats(raw: str) -> tuple[int, int]:
    raw = raw.strip()
    if not raw:
        return 0, 0
    depth = 0
    count = 1
    for char in raw:
        depth += bracket_step(char)
        if char == ',' and depth == 0:
            count += 1
    bools = len(re.findall(r'(?:=\s*(?:true|false)\b|:\s*boolean\b)', raw))
    return count, min(bools, count)


def typescript_classes(text: str) -> int:
    return len(TS_CLASS_RE.findall(text)) + len(
        re.findall(r'^\s*(?:export\s+)?interface\s+[\w$]+', text, re.MULTILINE)
    )


def analyze_js(_path: Path, rel: Path, text: str, language: str) -> FileMetric:
    loc, long_lines = count_loc(text)
    typed = language == 'typescript'
    lines = text.splitlines()
    found = (js_function(lines, idx, rel) for idx in range(len(lines)))
    return FileMetric(
        path=str(rel),
        language=language,
        loc=loc,
        long_lines=long_lines,
        classes=typescript_classes(text) if typed else 0,
        abstract_classes=len(TS_ABSTRACT_RE.findall(text)) if typed else 0,
        is_test=is_test_path(rel),
        functions=tuple(function for function in found if function is not None),
        imports=tuple(JS_IMPORT_RE.findall(text)),
    )


def js_signature(line: str) -> re.Match[str] | None:
    return next(filter(None, (pattern.match(line) for pattern in JS_FUNC_RES)), None)


def js_function(lines: list[str], idx: int, rel: Path) -> FunctionMetric | None:
    match = js_signature(lines[idx])
    if match is None:
        return None
    captured = match.lastindex and match.lastindex >= MIN_CAPTURE_GROUPS
    params, bool_params = js_param_stats((match.group(2) if captured else '') or '')
    end = js_function_end(lines, idx)
    return FunctionMetric(
        file=str(rel),
        name=match.group(1) or '<anonymous>',
        line=idx + 1,
        loc=end - idx + 1,
        params=params,
        bool_params=bool_params,
        max_depth=-1,
        approximate=True,
    )


def read_source(path: Path) -> str | None:
    try:
        return path.read_text(encoding='utf-8', errors='replace')
    except OSError as error:
        LOGGER.debug('Unable to read source file %s', path, exc_info=error)
        return None


def analyze_source(path: Path, root: Path) -> FileMetric | None:
    language = language_of(path)
    text = read_source(path)
    if text is None or language is None:
        return None
    rel = path.relative_to(root)
    if language == 'python':
        return analyze_python(path, rel, text)
    return analyze_js(path, rel, text, language)


def collect_metrics(root: Path) -> list[FileMetric]:
    analyzed = (analyze_source(path, root) for path in iter_source_files(root))
    return [metric for metric in analyzed if metric is not None]
