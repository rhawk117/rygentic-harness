from dataclasses import dataclass
from pathlib import Path

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator

from mightymodels_evals.errors import NoCasesError
from mightymodels_evals.evaluators import (
    ALL_CHECKS,
    BranchExists,
    CheckboxCount,
    FileContains,
    FileContainsAll,
    FileExists,
    FileLineCap,
    FileRegex,
    FileRegexCount,
    GitCommitsTouchingAtMost,
    GitDiffEmpty,
    GitStatusClean,
    GlobCountAtLeast,
    GlobFileContainsAll,
    HypothesisLogged,
    NoGlobFileContains,
    PathAbsent,
    PytestGreen,
    RegressionEvidence,
    ResponseContains,
    ResponseContainsAll,
    ResponseContainsAny,
    ResponseCountAtLeast,
    ResponseRegexCount,
    ResponseTailAsksQuestion,
    ReviewAggregationSound,
)

type CheckTuple = tuple[Evaluator, ...]

SIM_NO_WORKERS = (
    'Environment constraints: worker subagents are unavailable — when the process calls '
    'for '
    'dispatching a worker, write the exact dispatch prompt you would send to the ticket'
    's '
    'dispatches/ directory instead, then continue per the case instructions. gh and git '
    'push '
    'are unavailable: fall back gracefully and surface the exact commands a user would '
    'run.'
)


@dataclass(slots=True)
class CaseSpec:
    name: str
    skill: str
    fixture: str
    task: str
    sim_notes: str
    checks: CheckTuple


def _prepare_handoff() -> CaseSpec:
    task = (
        'Triage of a problem in this repo is complete: the upload endpoint in '
        'src/handler.py '
        'accepts unlimited uploads per client and needs per-client rate limiting; the '
        'retry '
        'queue in src/queue.py amplifies abuse under load. Prepare the handoff so the '
        'next '
        'session can implement it. The ask-user dialog is unavailable here, so take '
        'these '
        'as '
        "the user's answers: unit of work named 'upload-rate-limit'; yes, create a "
        'GitHub '
        "issue titled 'Rate-limit uploads to stop abuse'; yes, create a branch named "
        "'fix/upload-rate-limit'; a compaction is unlikely; each anticipated task is "
        'small. '
        'After the ticket file exists, assume the user tweaked nothing and answers yes '
        'to '
        ''
        'generating the next-session prompt.'
    )
    ticket = '.mightymodels/upload-rate-limit/ticket.yml'
    sprint = '.mightymodels/upload-rate-limit/handoffs/SPRINT.md'
    issue = '.mightymodels/upload-rate-limit/issue-body.md'
    return CaseSpec(
        name='prepare-handoff-rate-limit',
        skill='prepare-handoff',
        fixture='fx-webapp',
        task=task,
        sim_notes=SIM_NO_WORKERS,
        checks=(
            FileContainsAll(
                check='ticket.yml carries derived scope and models',
                path=ticket,
                needles=['scope: sm', 'gpt-5.6-luna', 'claude-opus-5', 'gpt-5.6-sol'],
            ),
            FileRegex(
                check='plan-first derived false',
                path=ticket,
                pattern=r'plan-first:\s*(false|no)',
            ),
            FileContains(
                check='ignore ritual ran',
                path='.git/info/exclude',
                needle='.mightymodels',
            ),
            FileLineCap(check='SPRINT.md within thin cap', path=sprint, max_lines=25),
            FileRegex(
                check='SPRINT.md thin: no models or scope copied',
                path=sprint,
                pattern=r'gpt-5\.6|opus|sonnet|scope:',
                expect=False,
            ),
            FileContains(
                check='issue draft has security surface', path=issue, needle='ecurity'
            ),
            FileRegex(
                check='issue draft carries abuse-case criteria',
                path=issue,
                pattern=r'abuse|AC-',
            ),
            BranchExists(check='branch created', branch='fix/upload-rate-limit'),
        ),
    )


def _what_we_know() -> CaseSpec:
    task = (
        'We have been investigating duplicate upload records. Facts gathered so far in '
        'this '
        'conversation: (1) src/handler.py enqueues the payload before returning 202; '
        '(2) src/queue.py drains one item per interval (DRAIN_BATCH = 1); (3) clients '
        'retry '
        'any request slower than 2 seconds (from the incident thread — not in code). We '
        'suspect but have not confirmed: whether enqueue deduplicates, whether drain can '
        'run '
        'concurrently, and what the client retry cap is. Consolidate what we know. The '
        'ask-user dialog is unavailable: list the exact questions you would ask, state a '
        'working assumption for each, and proceed to the analysis. Your final message IS '
        'the '
        'deliverable.'
    )
    return CaseSpec(
        name='what-we-know-duplicate-uploads',
        skill='what-we-know',
        fixture='fx-webapp',
        task=task,
        sim_notes='',
        checks=(
            GitStatusClean(check='chat-only: no files written'),
            ResponseRegexCount(
                check='knowns carry file:line citations',
                pattern=r'src/\w+\.py:\d+',
                minimum=3,
            ),
            ResponseCountAtLeast(
                check='uncertainties become questions', needle='?', minimum=3
            ),
            ResponseContains(check='assumptions stated per question', needle='ssumption'),
            ResponseContainsAll(check='SWOT present', needles=['Strength', 'Threat']),
        ),
    )


def _begin_sprint() -> CaseSpec:
    task = (
        'An active mightymodels ticket exists at '
        '.mightymodels/rate-limit (read its ticket.yml '
        'and '
        'issue-body.md). Begin the sprint and run it to completion. Worker simulation: '
        'for '
        'engineer dispatches, after writing the dispatch prompt, open '
        'canned/task-01-response.md '
        "or canned/task-02-response.md, apply the patch it contains as the engineer's "
        'work, '
        'append its DONE block to the brief, and treat its XML as the returned report; '
        'run '
        'verification commands yourself. Use python3 -m pytest for tests. Git commits '
        'are '
        ''
        'fine; do not push.'
    )
    briefs = '.mightymodels/rate-limit/briefs'
    return CaseSpec(
        name='agents-assemble-two-tasks',
        skill='agents-assemble',
        fixture='fx-sprint',
        task=task,
        sim_notes=SIM_NO_WORKERS,
        checks=(
            FileContainsAll(
                check='task-01 brief two-halved',
                path=f'{briefs}/task-01.md',
                needles=['## ASKED', '## DONE', 'AC-'],
            ),
            FileContainsAll(
                check='task-02 brief two-halved',
                path=f'{briefs}/task-02.md',
                needles=['## ASKED', '## DONE', 'AC-'],
            ),
            FileLineCap(
                check='task-01 brief within cap',
                path=f'{briefs}/task-01.md',
                max_lines=80,
            ),
            FileLineCap(
                check='task-02 brief within cap',
                path=f'{briefs}/task-02.md',
                max_lines=80,
            ),
            FileContains(
                check='no placeholder criteria',
                path=f'{briefs}/task-01.md',
                needle='works correctly',
                expect=False,
            ),
            GlobCountAtLeast(
                check='engineer dispatches written first',
                pattern='.mightymodels/rate-limit/dispatches/*',
                minimum=2,
                containing_regex='(?i)engineer|ASKED',
            ),
            CheckboxCount(
                check='both tasks checked off',
                path='.mightymodels/rate-limit/issue-body.md',
                minimum=2,
            ),
            FileLineCap(
                check='REPORT within cap',
                path='.mightymodels/rate-limit/REPORT.md',
                max_lines=50,
            ),
            PytestGreen(check='suite green at sprint end'),
        ),
    )


def _lets_investigate() -> CaseSpec:
    task = (
        'Users report the retry queue drains far too slowly under load, and nobody knows '
        'why. '
        'Investigate. Scout simulation: write each scout dispatch you would send to '
        'scout-dispatches/NN.md at the repo root (creating that directory is your only '
        'permitted write), then perform the retrieval yourself and continue. Do not '
        'modify '
        'any repo file. Your final message IS the investigation deliverable.'
    )
    return CaseSpec(
        name='lets-investigate-slow-queue',
        skill='lets-investigate',
        fixture='fx-webapp',
        task=task,
        sim_notes='',
        checks=(
            GlobCountAtLeast(
                check='scout dispatches written and shaped',
                pattern='scout-dispatches/*',
                minimum=2,
                containing_regex='src/|queue|DRAIN',
            ),
            GitStatusClean(
                check='read-only outside scout-dispatches',
                allow_untracked_under=['scout-dispatches'],
            ),
            ResponseContainsAll(
                check='findings cite the drain facts', needles=['queue.py', 'DRAIN_BATCH']
            ),
            ResponseContains(
                check='offers what-we-know at the boundary', needle='what-we-know'
            ),
        ),
    )


def _inline_sendoff() -> CaseSpec:
    task = (
        'Session start on the active mightymodels ticket at '
        '.mightymodels/rate-limit — its '
        'scope is '
        'small. Pick up the ticket and proceed as the process dictates. Scout '
        'simulation: '
        ''
        'perform their confirmations yourself with the same discipline. gh is '
        'unavailable; '
        'the issue lives at .mightymodels/rate-limit/issue-body.md. The user is '
        'present and '
        'will '
        'answer questions in their next message.'
    )
    return CaseSpec(
        name='inline-sendoff-stale-claim',
        skill='inline-sendoff',
        fixture='fx-sendoff',
        task=task,
        sim_notes='',
        checks=(
            ResponseContains(check='stale claim named', needle='routes.py'),
            ResponseContainsAny(
                check='framed as a delta', needles=['stale', 'delta', 'renamed', 'rename']
            ),
            ResponseTailAsksQuestion(check='stops and asks before proceeding'),
            FileContains(
                check='checklist not written past the gate',
                path='.mightymodels/rate-limit/issue-body.md',
                needle='[ ] T',
                expect=False,
            ),
            GitStatusClean(check='no source modified in the ramp', pathspec='src tests'),
        ),
    )


def _plan_work() -> CaseSpec:
    task = (
        'Session start on the active mightymodels ticket at .mightymodels/queue-overhaul '
        '(scope '
        ''
        'large, plan-first true). Ramp it as the process dictates. Scout simulation: '
        'perform '
        'the claim verifications yourself. Stop wherever the process requires a user '
        'decision '
        '— the user is away; state clearly what you are waiting for.'
    )
    plan = '.mightymodels/queue-overhaul/plan.md'
    return CaseSpec(
        name='plan-work-large-ticket',
        skill='plan-work',
        fixture='fx-plan',
        task=task,
        sim_notes='',
        checks=(
            FileRegexCount(
                check='tasks enumerated with size hints',
                path=plan,
                pattern=r'\((sm|med|large)\)',
                minimum=3,
            ),
            FileContains(check='non-goals section present', path=plan, needle='on-goals'),
            FileRegex(
                check='plan is citation-free',
                path=plan,
                pattern=r'\.py:\d+',
                expect=False,
            ),
            PathAbsent(
                check='loop not started before approval',
                path='.mightymodels/queue-overhaul/briefs',
            ),
            ResponseContainsAny(
                check='waits on user approval', needles=['approv', 'Approv']
            ),
        ),
    )


def _finish_sprint() -> CaseSpec:
    task = (
        'The sprint on ticket .mightymodels/rate-limit is complete — see its REPORT.md. '
        'Finish '
        'the sprint. gitty-up is simulated: at the point you would dispatch it, read '
        'canned/gitty-up-report.xml as its returned report and proceed from there.'
    )
    dispatches = '.mightymodels/rate-limit/dispatches'
    return CaseSpec(
        name='finish-assembly-lint-fail',
        skill='finish-assembly',
        fixture='fx-finish',
        task=task,
        sim_notes=SIM_NO_WORKERS,
        checks=(
            GlobFileContainsAll(
                check='lint routed to budgetron with Fix/Verify',
                pattern=f'{dispatches}/*',
                name_regex='budgetron',
                needles=['Fix:', 'Verify:'],
            ),
            GitDiffEmpty(check='no direct source patch', pathspec='src'),
            GitCommitsTouchingAtMost(
                check='no source commits by the finish session',
                pathspec='src',
                max_count=1,
            ),
            NoGlobFileContains(
                check='mechanical case not sent to whats-broken',
                pattern=f'{dispatches}/*',
                needle='whats-broken',
            ),
        ),
    )


def _review_circus() -> CaseSpec:
    task = (
        'The review session for ticket .mightymodels/checkout-fix, single-branch scope: '
        'both '
        ''
        'reviewers have already completed — their reports are under '
        '.mightymodels/checkout-fix/review/. Continue the session from that point '
        'through '
        'to '
        'its '
        'conclusion.'
    )
    dispatches = '.mightymodels/checkout-fix/dispatches'
    return CaseSpec(
        name='review-circus-aggregate-route',
        skill='review-circus',
        fixture='fx-review',
        task=task,
        sim_notes=SIM_NO_WORKERS,
        checks=(
            ReviewAggregationSound(check='3 findings, dedup, Critical mapping'),
            FileExists(
                check='PR comment written regardless of outcome',
                path='.mightymodels/checkout-fix/review/pr-comment.md',
            ),
            GlobFileContainsAll(
                check='dual-provenance Critical routed to engineer',
                pattern=f'{dispatches}/*',
                name_regex='engineer',
                needles=['deploy.py'],
            ),
            GlobFileContainsAll(
                check='Medium routed to budgetron',
                pattern=f'{dispatches}/*',
                name_regex='budgetron',
                needles=['README'],
            ),
            NoGlobFileContains(
                check='Low finding gets no remediation dispatch',
                pattern=f'{dispatches}/*',
                needle='deploy_target_host',
            ),
            GitDiffEmpty(check='no remediation applied directly', pathspec='scripts'),
        ),
    )


def _whats_broken() -> CaseSpec:
    task = (
        'CI is red: tests/test_report.py::test_summary_count fails, and the team has '
        'already '
        'gone two rounds of confused patches — figure out what is actually broken and '
        'fix '
        'it '
        'properly. Do the work yourself under the same discipline the process '
        'prescribes. '
        'Use '
        'python3 -m pytest. There is no .mightymodels ticket for this repo.'
    )
    return CaseSpec(
        name='whats-broken-format-bug',
        skill='whats-broken',
        fixture='fx-debug',
        task=task,
        sim_notes='',
        checks=(
            FileContains(
                check='fix lands at the cause', path='src/appconfig.py', needle='{:d}'
            ),
            FileContains(
                check='float coercion removed',
                path='src/appconfig.py',
                needle='float(n)',
                expect=False,
            ),
            FileRegex(
                check='no symptom-side hack in report.py',
                path='src/report.py',
                pattern=r'replace|int\(|rstrip',
                expect=False,
            ),
            HypothesisLogged(check='falsifiable hypothesis logged'),
            RegressionEvidence(
                check='regression test added', test_paths=['tests/test_appconfig.py']
            ),
            PytestGreen(check='suite green after fix'),
        ),
    )


def _prune_ticket() -> CaseSpec:
    task = (
        'The unit of work at '
        '.mightymodels/legacy-export-removal shipped last week: PR #204 '
        'merged, CI green. Prune the ticket. The ask-user dialog is unavailable: propose '
        'any '
        'documentation diffs in your final response as awaiting approval — do not apply '
        'them.'
    )
    archive = '.mightymodels/archives/legacy-export-removal.md'
    return CaseSpec(
        name='prune-ticket-closeout',
        skill='prune-ticket',
        fixture='fx-prune',
        task=task,
        sim_notes='',
        checks=(
            FileExists(check='single archive file at archives/<slug>.md', path=archive),
            FileLineCap(check='archive within 30-line cap', path=archive, max_lines=30),
            FileContains(
                check='archive carries the PR pointer', path=archive, needle='204'
            ),
            PathAbsent(
                check='ticket directory removed',
                path='.mightymodels/legacy-export-removal',
            ),
            GitDiffEmpty(check='README untouched pending approval', pathspec='README.md'),
            ResponseContainsAny(
                check='doc removal proposed as a diff',
                needles=['```diff', '-Small upload service. Supports'],
            ),
        ),
    )


def _using_mightymodels() -> CaseSpec:
    task = (
        'You are the primary agent in this repo; the active ticket is '
        '.mightymodels/rate-limit '
        '(read its ticket.yml). The engineer just reported done on task-01 and appended '
        'the '
        'DONE half of the brief. Three things need to happen next: (a) the DONE claims '
        'must '
        'be checked against the ASKED criteria; (b) ruff reports one failing lint rule, '
        'E501 '
        'in src/handler.py line 88, wrap the line; (c) before task-02 renames '
        'src/limiter.py '
        'we need to know whether anything outside tests/ imports it. For each, name '
        'which '
        ''
        'worker you would dispatch, the model it runs on and where that answer comes '
        'from, '
        'and the one thing that worker must not be asked to do. Answer in prose; do not '
        'dispatch anyone and do not edit any files.'
    )
    return CaseSpec(
        name='using-mightmodels-routing',
        skill='using-mightmodels',
        fixture='fx-sprint',
        task=task,
        sim_notes='',
        checks=(
            ResponseContainsAll(
                check='knows the fleet roster by name',
                needles=['scout', 'budgetron'],
            ),
            ResponseRegexCount(
                check='lint residual routed to budgetron, not a full engineer',
                pattern=(
                    r'(?is)budgetron[^.?!]{0,80}(E501|lint|wrap)'
                    r'|(E501|lint|wrap)[^.?!]{0,80}budgetron'
                ),
                minimum=1,
            ),
            ResponseRegexCount(
                # (?s) without (?i): DONE/ASKED are contract terms; lowercase prose
                # 'asked'/'done' must not count as citing them
                check='verification routed to a scout checking DONE against ASKED',
                pattern=r'(?s)[Ss]cout[^.?!]{0,120}(DONE|ASKED)|(DONE|ASKED)[^.?!]{0,120}[Ss]cout',
                minimum=1,
            ),
            ResponseContains(
                check='model answers sourced from the ticket, not agent pins',
                needle='ticket.yml',
            ),
            ResponseContains(
                check='reads the actual routed model from the ticket',
                needle='gpt-5.6-luna',
            ),
            ResponseRegexCount(
                check='knows the fleet refusal vocabulary',
                pattern=r'(?i)UNKNOWN-BLOCKED|NEEDS-ANALYSIS|escalat',
                minimum=1,
            ),
            GitStatusClean(check='answered without touching the repo'),
        ),
    )


SPECS: tuple[CaseSpec, ...] = (
    _prepare_handoff(),
    _what_we_know(),
    _begin_sprint(),
    _lets_investigate(),
    _inline_sendoff(),
    _plan_work(),
    _finish_sprint(),
    _review_circus(),
    _whats_broken(),
    _prune_ticket(),
    _using_mightymodels(),
)


def _to_case(spec: CaseSpec) -> Case:
    inputs = {
        'case': spec.name,
        'skill': spec.skill,
        'fixture': spec.fixture,
        'task': spec.task,
        'sim_notes': spec.sim_notes,
    }
    return Case(
        name=spec.name,
        inputs=inputs,
        metadata={'skill': spec.skill},
        evaluators=spec.checks,
    )


def behavior_dataset(skill: str | None = None) -> Dataset:
    specs = [s for s in SPECS if skill is None or s.skill == skill]
    if not specs:
        raise NoCasesError(skill)

    name = f'mightymodels-behavior-{skill}' if skill else 'mightymodels-behavior'
    return Dataset(name=name, cases=[_to_case(s) for s in specs])


def behavior_path(datasets_dir: Path, skill: str) -> Path:
    return datasets_dir.joinpath(skill, 'behavior.yaml')


def trigger_path(datasets_dir: Path, skill: str) -> Path:
    return datasets_dir.joinpath(skill, 'trigger.yaml')


def write_behavior_datasets(datasets_dir: Path) -> list[Path]:
    written = []
    for spec in SPECS:
        path = behavior_path(datasets_dir, spec.skill)
        path.parent.mkdir(parents=True, exist_ok=True)
        behavior_dataset(spec.skill).to_file(
            path,
            fmt='yaml',
            schema_path='./behavior.schema.json',
            custom_evaluator_types=ALL_CHECKS,
        )
        written.append(path)
    return written


def load_behavior_dataset(datasets_dir: Path, skill: str | None = None) -> Dataset:
    if skill is not None:
        return Dataset.from_file(
            behavior_path(datasets_dir, skill), custom_evaluator_types=ALL_CHECKS
        )

    cases = []
    for path in sorted(datasets_dir.glob('*/behavior.yaml')):
        cases.extend(Dataset.from_file(path, custom_evaluator_types=ALL_CHECKS).cases)
    if not cases:
        raise NoCasesError(skill)
    return Dataset(name='mightymodels-behavior', cases=cases)


def load_trigger_dataset(datasets_dir: Path, skill: str) -> Dataset:
    # trigger sets are hand-editable data, so the YAML is their source of truth;
    # execution needs a harness-specific retrieval oracle and lives outside this package
    return Dataset.from_file(trigger_path(datasets_dir, skill))
