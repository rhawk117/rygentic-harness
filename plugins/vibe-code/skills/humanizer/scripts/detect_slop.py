#!/usr/bin/env python3
"""Report the regex-detectable AI-writing tells in Markdown or plain text as JSON.

Pattern IDs (P01 to P33) match the headings in the skill's references/ files. Only
mechanical patterns are scanned; judgment patterns are listed in SKILL.md. Fenced
code, frontmatter, blockquotes, inline code, link targets and double-quoted spans
count as secondhand text and are never scanned. The report never says whether text
is AI-written: it lists hits, density, and paragraphs where several rules cluster.
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass
from enum import Enum, IntEnum, StrEnum, auto
from operator import attrgetter
from pathlib import Path
from typing import TextIO

if sys.version_info < (3, 12):  # noqa: UP036 bare python3 on PATH may predate 3.12
    sys.stderr.write(
        'detect_slop.py requires Python 3.12 or newer '
        'see if `uv` is available in your workspace or tell the user\n'
    )
    raise SystemExit(3)


STDIN_MARKER = '-'
FENCE_MARKERS = ('```', '~~~')
EXCERPT_LIMIT = 80
SECONDHAND_SPANS = re.compile(r'`[^`\n]*`|\]\([^)\n]*\)|"[^"\n]*"|\u201c[^\u201d\n]*\u201d')


class ExitCode(IntEnum):
    CLEAN = 0
    OVER_THRESHOLD = 1
    UNREADABLE_INPUT = 2


class Region(Enum):
    PROSE = auto()
    FRONTMATTER = auto()
    FENCE = auto()


class Reference(StrEnum):
    CONTENT = 'references/content-patterns.md'
    LANGUAGE = 'references/language-patterns.md'
    STYLE = 'references/style-patterns.md'
    COMMUNICATION = 'references/communication-patterns.md'
    FILLER = 'references/filler-hedging.md'


@dataclass(slots=True, kw_only=True, frozen=True)
class Rule:
    rule_id: str
    name: str
    reference: Reference
    pattern: re.Pattern[str]


@dataclass(slots=True, kw_only=True, frozen=True)
class ProseLine:
    number: int
    paragraph: int
    text: str


@dataclass(slots=True, kw_only=True, frozen=True)
class Hit:
    rule_id: str
    name: str
    reference: Reference
    line: int
    column: int
    paragraph: int
    excerpt: str


@dataclass(slots=True, kw_only=True, frozen=True)
class Cluster:
    paragraph_line: int
    rule_ids: tuple[str, ...]


@dataclass(slots=True, kw_only=True, frozen=True)
class SourceText:
    name: str
    text: str


@dataclass(slots=True, kw_only=True, frozen=True)
class DocumentReport:
    source: str
    words: int
    hits_per_1000_words: float
    clusters: tuple[Cluster, ...]
    hits: tuple[Hit, ...]


def compile_phrase_rule(
    *,
    rule_id: str,
    name: str,
    reference: Reference,
    phrases: Sequence[str],
) -> Rule:
    alternatives = '|'.join(map(re.escape, phrases))
    pattern = re.compile(rf'(?<!\w)(?:{alternatives})(?!\w)', re.IGNORECASE)
    return Rule(rule_id=rule_id, name=name, reference=reference, pattern=pattern)


def compile_pattern_rule(
    *,
    rule_id: str,
    name: str,
    reference: Reference,
    expression: str,
) -> Rule:
    pattern = re.compile(expression, re.MULTILINE)
    return Rule(rule_id=rule_id, name=name, reference=reference, pattern=pattern)


DEFAULT_RULES: tuple[Rule, ...] = (
    compile_phrase_rule(
        rule_id='P01',
        name='significance inflation',
        reference=Reference.CONTENT,
        phrases=(
            'a testament to',
            'is a reminder of',
            'pivotal moment',
            'pivotal role',
            'vital role',
            'key role',
            'significant role',
            'highlights the importance',
            'reflects broader',
            'enduring legacy',
            'lasting legacy',
            'setting the stage for',
            'marks a shift',
            'marking a shift',
            'key turning point',
            'evolving landscape',
            'focal point',
            'indelible mark',
            'deeply rooted',
        ),
    ),
    compile_phrase_rule(
        rule_id='P02',
        name='notability claims',
        reference=Reference.CONTENT,
        phrases=(
            'independent coverage',
            'active social media presence',
            'leading expert',
            'media outlets',
        ),
    ),
    compile_pattern_rule(
        rule_id='P03',
        name='trailing -ing analysis',
        reference=Reference.CONTENT,
        expression=(
            r'(?i),\s+(?:highlighting|underscoring|emphasizing|ensuring|reflecting'
            r'|symbolizing|contributing to|cultivating|fostering|encompassing'
            r'|showcasing)\b'
        ),
    ),
    compile_phrase_rule(
        rule_id='P04',
        name='promotional language',
        reference=Reference.CONTENT,
        phrases=(
            'vibrant',
            'nestled',
            'in the heart of',
            'at the heart of',
            'breathtaking',
            'must-visit',
            'stunning',
            'renowned',
            'groundbreaking',
            'rich cultural heritage',
            'natural beauty',
            'commitment to excellence',
        ),
    ),
    compile_phrase_rule(
        rule_id='P05',
        name='vague attribution',
        reference=Reference.CONTENT,
        phrases=(
            'experts argue',
            'experts believe',
            'experts say',
            'industry reports',
            'observers have',
            'critics argue',
            'studies show',
        ),
    ),
    compile_phrase_rule(
        rule_id='P06',
        name='challenges and prospects formula',
        reference=Reference.CONTENT,
        phrases=(
            'despite these challenges',
            'faces several challenges',
            'challenges and legacy',
            'future outlook',
            'future prospects',
        ),
    ),
    compile_phrase_rule(
        rule_id='P07',
        name='AI vocabulary',
        reference=Reference.LANGUAGE,
        phrases=(
            'delve',
            'delves',
            'delving',
            'tapestry',
            'intricate',
            'intricacies',
            'interplay',
            'garner',
            'garnered',
            'underscore',
            'underscores',
            'underscored',
            'showcase',
            'showcases',
            'showcased',
            'foster',
            'fosters',
            'enhance',
            'enhances',
            'crucial',
            'enduring',
            'additionally',
            'align with',
            'aligns with',
        ),
    ),
    compile_phrase_rule(
        rule_id='P08',
        name='copula avoidance',
        reference=Reference.LANGUAGE,
        phrases=('serves as', 'stands as', 'boasts', 'boasting'),
    ),
    compile_pattern_rule(
        rule_id='P09',
        name='negative parallelism or tailing negation',
        reference=Reference.LANGUAGE,
        expression=(
            r"(?i)\bnot (?:just|only|merely)\b[^.!?\n]{0,80}?\b(?:but|it'?s|it is)\b"
            r"|\bit'?s not (?:just |merely )?about\b"
            r'|,\s+no\s+[a-z]+ing\b'
        ),
    ),
    compile_pattern_rule(
        rule_id='P13',
        name='subjectless fragment',
        reference=Reference.LANGUAGE,
        expression=(
            r'(?i)(?:^|(?<=[.!?] ))No [a-z-]+(?: [a-z-]+)? '
            r'(?:needed|required|necessary)\b'
        ),
    ),
    compile_pattern_rule(
        rule_id='P14',
        name='em or en dash',
        reference=Reference.STYLE,
        expression=r'[\u2014\u2013]|(?<=\s)--(?=\s)',
    ),
    compile_pattern_rule(
        rule_id='P15',
        name='boldface overuse',
        reference=Reference.STYLE,
        expression=r'(?:\*\*[^*\n]+\*\*[^*\n]*){3,}',
    ),
    compile_pattern_rule(
        rule_id='P16',
        name='inline-header list item',
        reference=Reference.STYLE,
        expression=r'^\s*(?:[-*+]|\d+\.)\s+\*\*[^*\n]+?(?::\*\*|\*\*:)',
    ),
    compile_pattern_rule(
        rule_id='P17',
        name='title case heading',
        reference=Reference.STYLE,
        expression=(
            r'^#{1,6}\s+\S.*?\s(?:And|Or|Of|The|In|On|For|To|With|An?)\s+\S.*$'
            r"|^#{1,6}\s+(?:[A-Z][\w'-]*\s+){3,}[A-Z][\w'-]*\s*$"
        ),
    ),
    compile_pattern_rule(
        rule_id='P18',
        name='emoji',
        reference=Reference.STYLE,
        expression=r'[\U0001f300-\U0001faff\u2600-\u27bf\u2b50\u2b55]',
    ),
    compile_pattern_rule(
        rule_id='P19',
        name='curly double quotes',
        reference=Reference.STYLE,
        expression=r'[\u201c\u201d]',
    ),
    compile_phrase_rule(
        rule_id='P20',
        name='chatbot correspondence',
        reference=Reference.COMMUNICATION,
        phrases=(
            'I hope this helps',
            'of course!',
            'certainly!',
            'would you like me to',
            'want me to',
            'let me know if',
            'should I continue',
            'feel free to ask',
            'here is an overview',
            'here is a summary',
            "here's a breakdown",
        ),
    ),
    compile_phrase_rule(
        rule_id='P21',
        name='cutoff disclaimer or speculative gap-fill',
        reference=Reference.COMMUNICATION,
        phrases=(
            'as of my last',
            'my last training',
            'my knowledge cutoff',
            'while specific details are',
            'based on available information',
            'not publicly available',
            'maintains a low profile',
            'keeps personal details private',
            'stay out of the spotlight',
            'it is believed that',
            'likely grew up',
            'not extensively documented',
        ),
    ),
    compile_phrase_rule(
        rule_id='P22',
        name='sycophantic tone',
        reference=Reference.COMMUNICATION,
        phrases=(
            'great question',
            'absolutely right',
            'excellent point',
            'what a great',
        ),
    ),
    compile_phrase_rule(
        rule_id='P23',
        name='filler phrase',
        reference=Reference.FILLER,
        phrases=(
            'in order to',
            'due to the fact that',
            'at this point in time',
            'in the event that',
            'has the ability to',
            'it is important to note',
            "it's important to note",
            'it is worth noting',
            "it's worth noting",
        ),
    ),
    compile_pattern_rule(
        rule_id='P24',
        name='stacked hedging',
        reference=Reference.FILLER,
        expression=(
            r'(?i)\b(?:could|might|may)\s+(?:potentially|possibly|perhaps)\b'
            r'|\bpotentially\s+possibly\b|\bit could be argued\b'
        ),
    ),
    compile_phrase_rule(
        rule_id='P25',
        name='generic positive conclusion',
        reference=Reference.FILLER,
        phrases=(
            'the future looks bright',
            'exciting times',
            'step in the right direction',
            'journey toward excellence',
            'the possibilities are endless',
        ),
    ),
    compile_phrase_rule(
        rule_id='P27',
        name='persuasive authority trope',
        reference=Reference.COMMUNICATION,
        phrases=(
            'the real question is',
            'at its core',
            'what really matters',
            'the deeper issue',
            'the heart of the matter',
            'in reality',
        ),
    ),
    compile_phrase_rule(
        rule_id='P28',
        name='signposting',
        reference=Reference.COMMUNICATION,
        phrases=(
            "let's dive in",
            "let's dive into",
            "let's explore",
            "let's break this down",
            "let's break it down",
            "here's what you need to know",
            "now let's look at",
            'without further ado',
            "let's take a closer look",
        ),
    ),
    compile_pattern_rule(
        rule_id='P33',
        name='rhetorical opener',
        reference=Reference.COMMUNICATION,
        expression=(
            r"(?:^|(?<=[.!?] ))(?:Honestly\?|Look,|Real talk[.:,]|Let's be honest[.,]"
            r"|Here's the thing[.:,]|The thing is,)"
        ),
    ),
)


@dataclass(slots=True, kw_only=True, frozen=True)
class ScanOptions:
    rules: tuple[Rule, ...] = DEFAULT_RULES
    cluster_threshold: int = 3


def blank_span_interior(match: re.Match[str]) -> str:
    span = match.group()
    return span[0] + ' ' * (len(span) - 2) + span[-1]


def mask_secondhand(text: str) -> str:
    masked = SECONDHAND_SPANS.sub(blank_span_interior, text)
    return masked.replace('\u2019', "'").replace('\u2018', "'")


def is_blockquote(text: str) -> bool:
    return text.lstrip().startswith('>')


def advance_region(region: Region, text: str, number: int) -> tuple[Region, bool]:
    marker = text.strip()
    if number == 1 and marker == '---':
        return Region.FRONTMATTER, False

    if region is Region.FRONTMATTER:
        return (Region.PROSE if marker == '---' else Region.FRONTMATTER), False

    if marker.startswith(FENCE_MARKERS):
        return (Region.PROSE if region is Region.FENCE else Region.FENCE), False

    return region, region is Region.PROSE


def select_prose_lines(lines: Sequence[str]) -> Iterator[ProseLine]:
    region = Region.PROSE
    paragraph = 1
    for number, text in enumerate(lines, start=1):
        region, in_prose = advance_region(region, text, number)
        if not text.strip():
            paragraph = number + 1

        if in_prose and text.strip() and not is_blockquote(text):
            yield ProseLine(
                number=number,
                paragraph=paragraph,
                text=mask_secondhand(text),
            )


def find_rule_hits(rule: Rule, line: ProseLine) -> Iterator[Hit]:
    for match in rule.pattern.finditer(line.text):
        yield Hit(
            rule_id=rule.rule_id,
            name=rule.name,
            reference=rule.reference,
            line=line.number,
            column=match.start() + 1,
            paragraph=line.paragraph,
            excerpt=match.group().strip()[:EXCERPT_LIMIT],
        )


def find_hits(prose: Sequence[ProseLine], rules: Sequence[Rule]) -> Iterator[Hit]:
    for line in prose:
        for rule in rules:
            yield from find_rule_hits(rule, line)


def find_clusters(hits: Sequence[Hit], threshold: int) -> tuple[Cluster, ...]:
    rules_by_paragraph: defaultdict[int, set[str]] = defaultdict(set)
    for hit in hits:
        rules_by_paragraph[hit.paragraph].add(hit.rule_id)

    return tuple(
        Cluster(paragraph_line=paragraph, rule_ids=tuple(sorted(rule_ids)))
        for paragraph, rule_ids in sorted(rules_by_paragraph.items())
        if len(rule_ids) >= threshold
    )


def measure_density(hit_count: int, words: int) -> float:
    return round(hit_count * 1000 / words, 1) if words else 0.0


def scan_document(document: SourceText, options: ScanOptions) -> DocumentReport:
    prose = tuple(select_prose_lines(document.text.splitlines()))
    hits = tuple(
        sorted(
            find_hits(prose, options.rules),
            key=attrgetter('line', 'column'),
        )
    )

    words = sum(len(line.text.split()) for line in prose)
    return DocumentReport(
        source=document.name,
        words=words,
        hits=hits,
        hits_per_1000_words=measure_density(len(hits), words),
        clusters=find_clusters(hits, options.cluster_threshold),
    )


def encode_report(report: DocumentReport) -> dict[str, object]:
    return {
        'source': report.source,
        'words': report.words,
        'hits_per_1000_words': report.hits_per_1000_words,
        'rule_counts': dict(sorted(Counter(hit.rule_id for hit in report.hits).items())),
        'clusters': list(map(asdict, report.clusters)),
        'hits': list(map(asdict, report.hits)),
    }


def load_document(path: str) -> SourceText:
    if path == STDIN_MARKER:
        input_text = sys.stdin.read()
        return SourceText(name='<stdin>', text=input_text)

    file_text = Path(path).read_text(encoding='utf-8')
    return SourceText(name=path, text=file_text)


def select_exit_code(
    reports: Sequence[DocumentReport],
    fail_over: int | None,
) -> ExitCode:
    clustered = sum(len(report.clusters) for report in reports)
    exceeded = fail_over is not None and clustered > fail_over
    return ExitCode.OVER_THRESHOLD if exceeded else ExitCode.CLEAN


def parse_count(value: str) -> int:
    count = int(value)
    if count < 0:
        message = f'expected a non-negative integer, got {value}'
        raise argparse.ArgumentTypeError(message)

    return count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=__file__,
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        'paths',
        nargs='*',
        help='files to scan; omit or pass - for stdin',
    )
    parser.add_argument(
        '--cluster-threshold',
        type=parse_count,
        default=ScanOptions().cluster_threshold,
        metavar='N',
        help='distinct rules in one paragraph that make it a cluster (default: 3)',
    )
    parser.add_argument(
        '--fail-over',
        type=parse_count,
        default=None,
        metavar='N',
        help='exit 1 when clustered paragraphs across all inputs exceed N',
    )
    return parser


def write_json(payload: object, stream: TextIO) -> None:
    json.dump(payload, stream, indent=2, ensure_ascii=False)
    stream.write('\n')


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    options = ScanOptions(
        cluster_threshold=arguments.cluster_threshold,
    )

    lazy_documents = map(load_document, arguments.paths or (STDIN_MARKER,))

    try:
        documents = tuple(lazy_documents)
    except (OSError, UnicodeDecodeError) as error:
        write_json({'error': str(error)}, sys.stderr)
        return ExitCode.UNREADABLE_INPUT

    reports = tuple(scan_document(document, options) for document in documents)

    encoded_documents = map(encode_report, reports)
    write_json({'documents': list(encoded_documents)}, sys.stdout)
    return select_exit_code(reports, arguments.fail_over)


if __name__ == '__main__':
    raise SystemExit(main())
