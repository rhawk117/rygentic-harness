"""The contract. Every artifact in the pipeline is defined here and nowhere else.

skill-creator's worst failures came from having no single source of truth: two YAML
parsers for one file, three names for one concept (assertions/expectations), and a
directory layout described in prose to a model while being globbed differently in
code. Everything here exists to make that class of drift impossible.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION, __version__


class SchemaError(ValueError):
    """Raised when an artifact cannot be trusted. Never downgraded to a warning."""


# --------------------------------------------------------------------------
# Arms
# --------------------------------------------------------------------------

class Arm(str, Enum):
    """Three arms, because "with skill" is two different questions.

    skill-creator collapses `available` and `forced` into one `with_skill` arm, so a
    run where the skill never fired is graded as though the skill were tested. A low
    score then has two indistinguishable causes: bad triggering, or bad instructions.
    Splitting them gives every regression an address.
    """

    BASELINE = "baseline"    # skill absent — would the model have done this anyway?
    AVAILABLE = "available"  # installed, unmentioned — does it fire when it should?
    FORCED = "forced"        # explicitly invoked — given that it fires, does it help?

    @property
    def role(self) -> str:
        return {"baseline": "control", "available": "treatment", "forced": "treatment"}[self.value]


#: Named deltas. The key is the report label; the value is (treatment, control).
#: Deltas are looked up by role, never by sorted position — that positional
#: assumption is what inverts skill-creator's sign whenever the baseline arm is
#: named `old_skill` (which sorts before `with_skill`).
DELTAS: dict[str, tuple[Arm, Arm]] = {
    "lift": (Arm.FORCED, Arm.BASELINE),      # execution quality, trigger variance removed
    "realized": (Arm.AVAILABLE, Arm.BASELINE),  # what a user actually gets end to end
}


class Outcome(str, Enum):
    """pass / fail / ERROR.

    An error is the absence of a measurement, not a negative measurement. Folding
    timeouts into "fail" is how skill-creator converts infrastructure failure into
    passing scores on the negative half of a trigger eval set.
    """

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"


class AssertionKind(str, Enum):
    """The epistemic status of an assertion, made machine-readable.

    Only MECHANICAL results are trustworthy at small n. JUDGED results require a
    blinded grader and carry a reliability estimate. HUMAN results are surfaced for
    review and never scored automatically.
    """

    MECHANICAL = "mechanical"
    JUDGED = "judged"
    HUMAN = "human"


class Tier(str, Enum):
    QUICK = "quick"
    STANDARD = "standard"
    RIGOROUS = "rigorous"

    @property
    def runs_per_eval(self) -> int:
        return {"quick": 1, "standard": 3, "rigorous": 8}[self.value]

    @property
    def may_claim_intervals(self) -> bool:
        """Whether the report is allowed to render a confidence interval.

        Honest-by-construction rather than honest-by-discipline: skill-creator prints
        `± 0.06` off n=3 because nothing stops it.
        """
        return self.value in ("standard", "rigorous")

    @property
    def may_claim_significance(self) -> bool:
        return self.value == "rigorous"

    @property
    def requires_blinding(self) -> bool:
        return self.value in ("standard", "rigorous")

    @property
    def requires_confirmation_run(self) -> bool:
        return self.value == "rigorous"


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------

@dataclass
class Provenance:
    """Attached to every artifact. A benchmark without it is an anecdote with a table.

    `assertion_set_hash` is what makes cross-iteration comparison honest: change an
    assertion and the hash changes, and the report refuses to plot a trend through it.
    """

    harness_version: str = __version__
    schema_version: int = SCHEMA_VERSION
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    host: str | None = None            # "claude-code" | "copilot-cli"
    host_version: str | None = None
    model: str | None = None
    surface: str | None = None         # cli | vscode | cloud-agent | code-review
    tier: str = Tier.STANDARD.value
    skill_name: str | None = None
    skill_content_hash: str | None = None
    assertion_set_hash: str | None = None
    eval_set_hash: str | None = None
    platform: str = field(default_factory=lambda: f"{platform.system()}-{platform.machine()}")
    python: str = field(default_factory=lambda: sys.version.split()[0])
    git_sha: str | None = None
    notes: list[str] = field(default_factory=list)

    def comparable_with(self, other: "Provenance") -> tuple[bool, list[str]]:
        """Whether two artifacts may be compared, and why not if not."""
        blockers: list[str] = []
        if self.schema_version != other.schema_version:
            blockers.append(f"schema_version {self.schema_version} vs {other.schema_version}")
        if self.model != other.model:
            blockers.append(f"model {self.model!r} vs {other.model!r}")
        if self.assertion_set_hash != other.assertion_set_hash:
            blockers.append("assertion set changed — the ruler moved between measurements")
        if self.host != other.host:
            blockers.append(f"host {self.host!r} vs {other.host!r}")
        return (not blockers), blockers


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def dir_hash(root: Path, ignore: set[str] | None = None) -> str:
    """Stable hash of a directory's contents. Used for skill_content_hash."""
    ignore = ignore or {".git", "__pycache__", ".DS_Store", "evals", "node_modules"}
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if any(part in ignore for part in p.relative_to(root).parts):
            continue
        if not p.is_file():
            continue
        h.update(str(p.relative_to(root)).encode("utf-8"))
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def git_sha(cwd: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or None if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


# --------------------------------------------------------------------------
# Eval definitions
# --------------------------------------------------------------------------

@dataclass
class Assertion:
    """One checkable claim. `kind` decides how much the statistics layer trusts it."""

    id: str
    text: str
    kind: AssertionKind = AssertionKind.JUDGED
    check: str | None = None      # mechanical only: shell command, cwd = outputs dir
    weight: float = 1.0

    def __post_init__(self) -> None:
        self.kind = AssertionKind(self.kind)
        if self.kind is AssertionKind.MECHANICAL and not self.check:
            raise SchemaError(
                f"assertion {self.id!r} is mechanical but has no `check` command. "
                "A mechanical assertion must be executable, or it is a judged one wearing a badge."
            )
        if self.kind is not AssertionKind.MECHANICAL and self.check:
            raise SchemaError(f"assertion {self.id!r} has a `check` but kind={self.kind.value}; use kind=mechanical")


@dataclass
class EvalCase:
    id: str
    prompt: str
    expected_output: str = ""
    files: list[str] = field(default_factory=list)
    assertions: list[Assertion] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.assertions = [a if isinstance(a, Assertion) else Assertion(**a) for a in self.assertions]
        if not self.id or not str(self.id).strip():
            raise SchemaError("eval case needs a non-empty id")
        if not self.prompt.strip():
            raise SchemaError(f"eval case {self.id!r} has an empty prompt")


@dataclass
class EvalSet:
    skill_name: str
    cases: list[EvalCase] = field(default_factory=list)
    trigger_queries: list[dict] = field(default_factory=list)  # {query, should_trigger}

    def __post_init__(self) -> None:
        self.cases = [c if isinstance(c, EvalCase) else EvalCase(**c) for c in self.cases]
        seen: set[str] = set()
        for c in self.cases:
            if c.id in seen:
                raise SchemaError(f"duplicate eval id {c.id!r} — results would silently merge")
            seen.add(c.id)
        for i, q in enumerate(self.trigger_queries):
            if "query" not in q or "should_trigger" not in q:
                raise SchemaError(f"trigger_queries[{i}] needs both `query` and `should_trigger`")

    def assertion_set_hash(self) -> str:
        payload = [
            [c.id] + sorted(f"{a.id}:{a.kind.value}:{a.text}:{a.check or ''}" for a in c.assertions)
            for c in sorted(self.cases, key=lambda c: c.id)
        ]
        return content_hash(json.dumps(payload, sort_keys=True))

    def eval_set_hash(self) -> str:
        payload = [[c.id, c.prompt] for c in sorted(self.cases, key=lambda c: c.id)]
        payload += [[q["query"], bool(q["should_trigger"])] for q in self.trigger_queries]
        return content_hash(json.dumps(payload, sort_keys=True))

    @staticmethod
    def load(path: Path) -> "EvalSet":
        raw = json.loads(Path(path).read_text())
        v = raw.get("schema_version")
        if v is not None and v != SCHEMA_VERSION:
            raise SchemaError(
                f"{path} has schema_version {v}, this harness speaks {SCHEMA_VERSION}. "
                "Refusing to guess at the difference."
            )
        return EvalSet(
            skill_name=raw["skill_name"],
            cases=raw.get("cases", raw.get("evals", [])),
            trigger_queries=raw.get("trigger_queries", []),
        )

    def save(self, path: Path) -> None:
        body = {"schema_version": SCHEMA_VERSION, "skill_name": self.skill_name,
                "cases": [asdict(c) for c in self.cases], "trigger_queries": self.trigger_queries}
        Path(path).write_text(json.dumps(body, indent=2, default=_enc) + "\n")


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------

@dataclass
class AssertionResult:
    id: str
    text: str
    kind: AssertionKind
    outcome: Outcome
    evidence: str = ""
    weight: float = 1.0

    def __post_init__(self) -> None:
        self.kind = AssertionKind(self.kind)
        self.outcome = Outcome(self.outcome)


@dataclass
class RunRecord:
    """One execution of one eval case in one arm.

    `tokens` is None when the host did not report a token count. It is never a
    character count wearing the label "tokens", and never silently zero.
    """

    eval_id: str
    arm: Arm
    run_index: int
    outcome: Outcome
    assertions: list[AssertionResult] = field(default_factory=list)
    skill_invoked: bool | None = None     # from the hook event log; None = not instrumented
    duration_seconds: float | None = None
    tokens: int | None = None
    tool_calls: int | None = None
    error: str | None = None
    output_files: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.arm = Arm(self.arm)
        self.outcome = Outcome(self.outcome)
        self.assertions = [a if isinstance(a, AssertionResult) else AssertionResult(**a) for a in self.assertions]
        if self.outcome is Outcome.ERROR and not self.error:
            raise SchemaError(f"{self.eval_id}/{self.arm.value}#{self.run_index}: error outcome needs a reason")

    def score(self, kinds: set[AssertionKind] | None = None) -> float | None:
        """Weighted pass fraction over scorable assertions. None when unscorable.

        Returns None for an errored run so callers must handle absence explicitly
        rather than averaging a zero into the result.
        """
        if self.outcome is Outcome.ERROR:
            return None
        kinds = kinds or {AssertionKind.MECHANICAL, AssertionKind.JUDGED}
        scorable = [a for a in self.assertions if a.kind in kinds and a.outcome is not Outcome.ERROR]
        if not scorable:
            return None
        total = sum(a.weight for a in scorable)
        got = sum(a.weight for a in scorable if a.outcome is Outcome.PASS)
        return got / total if total else None


def _enc(o: Any) -> Any:
    if isinstance(o, Enum):
        return o.value
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")


def dump(obj: Any, path: Path) -> None:
    Path(path).write_text(json.dumps(obj, indent=2, default=_enc) + "\n")
