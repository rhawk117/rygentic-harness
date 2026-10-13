from collections.abc import Mapping
from types import MappingProxyType

from mightymodels.core.run_id import RunId
from mightymodels.core.slug import Slug
from mightymodels.tools.close.schema import Closing
from mightymodels.tools.contract.schema import ContractCommand
from mightymodels.tools.crashout.schema import CrashoutEntry
from mightymodels.tools.failed_fix.schema import FailedFixPayload, TaskFailedFix
from mightymodels.tools.investigation.schema import (
    InvestigationStart,
    InvestigationStartRequest,
    LedgerEntry,
)
from mightymodels.tools.request import RequestModel
from mightymodels.tools.review.schema import (
    DisposePayload,
    DisposeRequest,
    Disposition,
    Evidence,
    FindingInput,
    ResolvePayload,
    StartPayload,
    StartRequest,
)
from mightymodels.tools.similarity.schema import SimilarityRequest, SpooledReport
from mightymodels.tools.task.schema import (
    MarkTaskPayload,
    StartTaskPayload,
    TaskMark,
    TaskStart,
    TaskVerification,
    TooLargeTaskStart,
    VerifyTaskPayload,
)
from mightymodels.tools.ticket.schema import TicketAnswers, TicketContext, TicketInterview

SLUG = 'retry-queue'
TICKET = Slug(SLUG)
RUN = RunId('20260928-120000')
VALID: Mapping[type[RequestModel], dict[str, object]] = MappingProxyType(
    {
        Closing: {'shipped': 'the drain runs in one pass'},
        ContractCommand: {'id': 'T1.AC-1', 'argv': ['true'], 'approved_by': 'user'},
        CrashoutEntry: {
            'severity': 'heated',
            'verdict': 'deserved',
            'rant': 'why did you skip the tests',
            'failures': ['skipped the tests'],
            'root_cause': 'optimised for speed',
            'corrective_action': 'run the gate before reporting',
            'barked_back': False,
        },
        LedgerEntry: {'kind': 'open', 'text': 'why is the drain slow', 'source': 'user'},
        InvestigationStart: {'target': 'the drain loop', 'kind': 'behavior'},
        InvestigationStartRequest: {'target': 'the drain loop', 'kind': 'behavior'},
        Evidence: {'kind': 'metric', 'cite': 'cyclomatic complexity 14'},
        FindingInput: {
            'sources': ['MV-1'],
            'severity': 'High',
            'title': 'the drain loop sleeps between batches',
            'location': 'src/queue.py:12',
            'fix': 'drain in one pass',
            'verify': 'run the drain test',
        },
        SimilarityRequest: {'action': 'search', 'query': 'the drain loop'},
        SpooledReport: {
            'repository_key': 'acme/widgets',
            'scout': 'code-scout',
            'target': 'the drain loop',
            'report': 'the drain loop sleeps between batches',
        },
        StartPayload: {'scope': 'codebase', 'depth': 'deep', 'emphasis': 'balanced'},
        StartRequest: {'scope': 'codebase', 'depth': 'deep', 'emphasis': 'balanced'},
        Disposition: {'decision': 'fix'},
        DisposePayload: {'by': 'user', 'decisions': {'F1': {'decision': 'fix'}}},
        DisposeRequest: {'by': 'user', 'decisions': {'F1': {'decision': 'fix'}}},
        ResolvePayload: {'finding': 'F1', 'result': 'fixed'},
        TaskStart: {'by': 'engineer', 'owned': ['src/queue.py'], 'acceptance': ['AC-1']},
        TooLargeTaskStart: {
            'by': 'engineer',
            'owned': ['src/queue.py'],
            'acceptance': ['AC-1'],
            'too_large_approved_by': 'user',
        },
        TaskVerification: {'commit': 'abc1234'},
        TaskMark: {'to': 'failed', 'reason': 'the drain test fails'},
        FailedFixPayload: {'task_id': 'T1', 'change': {'hypothesis': 'the drain loop sleeps'}},
        TaskFailedFix: {'hypothesis': 'the drain loop sleeps between batches'},
        StartTaskPayload: {
            'task_id': 'T1',
            'change': {'by': 'engineer', 'owned': ['src/queue.py'], 'acceptance': ['AC-1']},
        },
        VerifyTaskPayload: {'task_id': 'T1', 'change': {'commit': 'abc1234'}},
        MarkTaskPayload: {
            'task_id': 'T1',
            'change': {'to': 'failed', 'reason': 'the drain test fails'},
        },
        TicketAnswers: {
            'summary': 'Retry queue drains slowly',
            'scope': 'large',
            'compaction': True,
            'branch': 'fix/retry-queue',
            'context': ['drain loop sleeps between batches'],
        },
        TicketInterview: {
            'summary': 'Retry queue drains slowly',
            'scope': 'large',
            'compaction': True,
            'branch': 'fix/retry-queue',
            'context': ['drain loop sleeps between batches'],
        },
        TicketContext: {'context': ['drain loop sleeps between batches']},
    }
)


def plain(length: int) -> str:
    return 'x' * length


def finding_id(length: int) -> str:
    return 'F' + '1' * (length - 1)
