"""Every test here pins a failure reproduced in a real skill-creator install.

A measurement harness with no tests of its own is the root cause of every other
problem in that tool, so these run first and this file is the one to read before
changing anything in skilleng/.

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from skilleng.aggregate import NoDataError, build
from skilleng.events import normalize, prompt_mentions_skill, skill_invoked
from skilleng.package import package, scan
from skilleng.report import safe_json_for_script, to_html, to_markdown
from skilleng.schema import (Arm, Assertion, AssertionKind, AssertionResult, EvalCase,
                             EvalSet, Outcome, Provenance, RunRecord, SchemaError, Tier)
from skilleng.skillmd import errors, lint
from skilleng.workspace import Workspace


def _run(eval_id: str, arm: Arm, idx: int, score: float, **kw) -> RunRecord:
    """One run whose assertions produce the requested score."""
    n = 4
    passed = round(score * n)
    asserts = [
        AssertionResult(f"a{i}", f"assertion {i}", AssertionKind.MECHANICAL,
                        Outcome.PASS if i < passed else Outcome.FAIL, "evidence")
        for i in range(n)
    ]
    return RunRecord(eval_id=eval_id, arm=arm, run_index=idx, outcome=Outcome.PASS,
                     assertions=asserts, **kw)


def _prov(**kw) -> Provenance:
    base = dict(host="copilot-cli", model="test-model", tier=Tier.STANDARD.value,
                skill_name="demo", skill_content_hash="abc", assertion_set_hash="h1")
    base.update(kw)
    return Provenance(**base)


class DeltaSign(unittest.TestCase):
    """F-01. skill-creator computes configs[0] - configs[1] over a *sorted* directory
    listing, so naming the baseline `old_skill` inverts the sign: a skill that went
    0% -> 100% is reported as -1.00."""

    def test_delta_is_treatment_minus_control_regardless_of_name_order(self):
        runs = [_run("e1", Arm.BASELINE, 1, 0.0, skill_invoked=None),
                _run("e1", Arm.FORCED, 1, 1.0, skill_invoked=True),
                _run("e2", Arm.BASELINE, 1, 0.0, skill_invoked=None),
                _run("e2", Arm.FORCED, 1, 1.0, skill_invoked=True)]
        bench = build(runs, _prov())
        lift = next(d for d in bench.deltas if d["name"] == "lift")
        self.assertEqual(lift["treatment"], "forced")
        self.assertEqual(lift["control"], "baseline")
        self.assertAlmostEqual(lift["point"], 1.0)
        self.assertGreater(lift["point"], 0, "a perfect improvement must not report a negative delta")

    def test_arm_roles_are_fixed_not_alphabetical(self):
        self.assertEqual(Arm.BASELINE.role, "control")
        self.assertEqual(Arm.FORCED.role, "treatment")
        self.assertLess("available", "baseline", "alphabetical order does NOT match role order")


class ZeroRuns(unittest.TestCase):
    """F-02. The documented layout yields no runs; skill-creator prints a table of
    zeros with placeholder labels and exits 0."""

    def test_no_runs_raises_instead_of_reporting_zeros(self):
        with self.assertRaises(NoDataError):
            build([], _prov())

    def test_writer_and_reader_agree_on_layout(self):
        d = Path(tempfile.mkdtemp())
        ws = Workspace.create(d)
        ws.prepare_run(1, "e1", Arm.FORCED, 1)
        ws.save_run(1, _run("e1", Arm.FORCED, 1, 0.5))
        self.assertEqual(len(ws.load_runs(1)), 1,
                         "the path the runner writes must be the path the aggregator reads")
        shutil.rmtree(d, ignore_errors=True)


class ScriptEscaping(unittest.TestCase):
    """F-11. json.dumps does not escape </script>; one HTML output file with an
    inline script blanks the viewer and opens an injection sink."""

    def test_closing_script_tag_is_neutralised(self):
        payload = {"content": "<html><script>x</script><img src=x onerror=alert(1)></html>"}
        blob = safe_json_for_script(payload)
        self.assertNotIn("</script", blob)
        self.assertNotIn("</", blob)
        self.assertEqual(json.loads(blob.replace("<\\/", "</"))["content"], payload["content"])

    def test_report_escapes_hostile_eval_ids(self):
        runs = [_run("</h2><script>alert(1)</script>", Arm.FORCED, 1, 1.0),
                _run("</h2><script>alert(1)</script>", Arm.BASELINE, 1, 0.0)]
        html = to_html(build(runs, _prov()).__dict__ | {"provenance": _prov().__dict__})
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)


class Validator(unittest.TestCase):
    """F-15. skill-creator prints "Skill is valid!" for an empty name and an empty
    description, never checks name-vs-directory, and rejects real host frontmatter."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _skill(self, dirname: str, fm: str, body: str = "\n# x\n") -> Path:
        d = self.tmp / dirname
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\n{fm}\n---\n{body}")
        return d

    def test_empty_name_and_description_are_errors(self):
        d = self._skill("empty", 'name: ""\ndescription: ""')
        codes = {f.code for f in errors(lint(d))}
        self.assertIn("name.empty", codes)
        self.assertIn("description.empty", codes)

    def test_name_must_match_directory(self):
        d = self._skill("wrongdir", "name: other-name\ndescription: Does x. Use when x.")
        self.assertIn("name.dirmatch", {f.code for f in errors(lint(d))})

    def test_host_frontmatter_does_not_block_packaging(self):
        d = self._skill("host-keys", "name: host-keys\ndescription: Does x. Use when x.\n"
                                     "model: opus\ndisable-model-invocation: false\ntarget: vscode")
        self.assertEqual(errors(lint(d)), [], "host-specific keys must warn, never block")

    def test_dangling_reference_is_an_error(self):
        d = self._skill("dangly", "name: dangly\ndescription: Does x. Use when x.",
                        "\nRead `references/missing.md` first.\n")
        self.assertIn("reference.dangling", {f.code for f in errors(lint(d))})


class ErrorsAreNotFailures(unittest.TestCase):
    """F-04 / F-06. Folding infrastructure failure into "fail" is how a dead harness
    scores like a mediocre one."""

    def test_errored_run_is_unscorable_not_zero(self):
        r = RunRecord(eval_id="e", arm=Arm.FORCED, run_index=1, outcome=Outcome.ERROR,
                      error="timed out after 30s")
        self.assertIsNone(r.score())

    def test_error_outcome_requires_a_reason(self):
        with self.assertRaises(SchemaError):
            RunRecord(eval_id="e", arm=Arm.FORCED, run_index=1, outcome=Outcome.ERROR)

    def test_errors_are_reported_and_excluded(self):
        runs = [_run("e1", Arm.FORCED, 1, 1.0),
                RunRecord(eval_id="e1", arm=Arm.FORCED, run_index=2, outcome=Outcome.ERROR, error="boom"),
                _run("e1", Arm.BASELINE, 1, 0.0)]
        bench = build(runs, _prov())
        forced = next(a for a in bench.arms if a["arm"] == "forced")
        self.assertEqual(forced["errors"], 1)
        self.assertAlmostEqual(forced["error_rate"], 0.5)
        self.assertAlmostEqual(forced["mean_score"], 1.0, msg="the error must not drag the mean toward zero")
        self.assertTrue(any("errored" in d for d in bench.diagnostics))

    def test_uninstrumented_run_is_unknown_not_false(self):
        self.assertIsNone(skill_invoked([], "missing-run", "demo"))


class TokensAreTokens(unittest.TestCase):
    """F-09. grader.md documents output_chars as a "proxy for tokens" and the
    aggregator files it under a column labelled Tokens."""

    def test_absent_token_counts_are_absent_not_zero(self):
        runs = [_run("e1", Arm.FORCED, 1, 1.0), _run("e1", Arm.BASELINE, 1, 0.0)]
        bench = build(runs, _prov())
        for arm in bench.arms:
            self.assertIsNone(arm["mean_tokens"])
            self.assertFalse(arm["tokens_available"])
        self.assertTrue(any("token counts unavailable" in d for d in bench.diagnostics))
        self.assertNotIn("Tokens", to_markdown(bench.__dict__ | {"provenance": _prov().__dict__}))


class TierGating(unittest.TestCase):
    """F-07. skill-creator prints mean +/- stddev off n=3 with no gate at all."""

    def test_quick_tier_may_not_show_intervals(self):
        runs = [_run("e1", Arm.FORCED, 1, 1.0), _run("e1", Arm.BASELINE, 1, 0.0)]
        bench = build(runs, _prov(tier=Tier.QUICK.value))
        self.assertFalse(bench.claims_permitted["intervals"])
        self.assertIsNone(next(a for a in bench.arms if a["arm"] == "forced")["score_interval"])
        self.assertIn("cannot tell you whether a difference is real", bench.claims_permitted["note"])

    def test_standard_tier_shows_intervals(self):
        runs = [_run(f"e{i}", arm, 1, 1.0 if arm is Arm.FORCED else 0.0)
                for i in range(3) for arm in (Arm.FORCED, Arm.BASELINE)]
        bench = build(runs, _prov(tier=Tier.STANDARD.value))
        self.assertTrue(bench.claims_permitted["intervals"])
        self.assertIsNotNone(next(a for a in bench.arms if a["arm"] == "forced")["score_interval"])

    def test_resolving_power_is_reported(self):
        runs = [_run(f"e{i}", arm, 1, 1.0 if arm is Arm.FORCED else 0.0)
                for i in range(3) for arm in (Arm.FORCED, Arm.BASELINE)]
        bench = build(runs, _prov())
        self.assertTrue(any("resolving power" in d for d in bench.diagnostics))


class RulerStaysFixed(unittest.TestCase):
    """F-10. skill-creator invites the grader to improve assertions between
    iterations and then plots pass rate across them."""

    def test_changing_an_assertion_changes_the_hash(self):
        a = EvalSet("demo", [EvalCase(id="e1", prompt="p", assertions=[
            Assertion(id="a1", text="output mentions X", kind=AssertionKind.JUDGED)])])
        b = EvalSet("demo", [EvalCase(id="e1", prompt="p", assertions=[
            Assertion(id="a1", text="output mentions X and Y", kind=AssertionKind.JUDGED)])])
        self.assertNotEqual(a.assertion_set_hash(), b.assertion_set_hash())

    def test_comparison_is_refused_when_the_ruler_moved(self):
        ok, blockers = _prov(assertion_set_hash="h1").comparable_with(_prov(assertion_set_hash="h2"))
        self.assertFalse(ok)
        self.assertTrue(any("assertion set changed" in b for b in blockers))

    def test_comparison_is_refused_across_models(self):
        ok, blockers = _prov(model="a").comparable_with(_prov(model="b"))
        self.assertFalse(ok)


class SchemaDiscipline(unittest.TestCase):
    """F-17. Two YAML parsers, three names for one concept, one dead schema."""

    def test_duplicate_eval_ids_are_rejected(self):
        with self.assertRaises(SchemaError):
            EvalSet("demo", [EvalCase(id="e1", prompt="a"), EvalCase(id="e1", prompt="b")])

    def test_mechanical_assertion_must_be_executable(self):
        with self.assertRaises(SchemaError):
            Assertion(id="a", text="t", kind=AssertionKind.MECHANICAL)

    def test_eval_set_round_trips(self):
        d = Path(tempfile.mkdtemp())
        es = EvalSet("demo", [EvalCase(id="e1", prompt="do a thing", assertions=[
            Assertion(id="a1", text="made a file", kind=AssertionKind.MECHANICAL, check="test -f out.csv")])])
        es.save(d / "evals.json")
        self.assertEqual(EvalSet.load(d / "evals.json").assertion_set_hash(), es.assertion_set_hash())
        shutil.rmtree(d, ignore_errors=True)

    def test_future_schema_version_is_refused(self):
        d = Path(tempfile.mkdtemp())
        (d / "evals.json").write_text(json.dumps({"schema_version": 999, "skill_name": "x", "cases": []}))
        with self.assertRaises(SchemaError):
            EvalSet.load(d / "evals.json")
        shutil.rmtree(d, ignore_errors=True)


class Portability(unittest.TestCase):
    """One event schema, two hosts. The detector must not care which host it is."""

    def test_both_host_payload_shapes_normalise_identically(self):
        cc = normalize({"hook_event_name": "PreToolUse", "tool_name": "Skill",
                        "tool_input": {"skill": "demo"}}, "r", "available")
        cop = normalize({"event": "preToolUse", "toolName": "skill",
                         "toolArgs": {"name": "demo"}}, "r", "available")
        self.assertEqual((cc.event, cc.skill), (cop.event, cop.skill))
        self.assertEqual(cc.event, "pre_tool_use")

    def test_unrecognised_payload_is_flagged_not_dropped(self):
        ev = normalize({"totally": "unknown"}, "r", "available")
        self.assertTrue(ev.unmapped)
        self.assertEqual(ev.raw_keys, ["totally"])

    def test_skill_detected_from_a_read_of_its_skill_md(self):
        ev = normalize({"hookEventName": "preToolUse", "toolName": "read",
                        "arguments": {"path": "/w/.claude/skills/demo/SKILL.md"}}, "r", "available")
        self.assertEqual(ev.skill, "demo")

    def test_available_arm_hygiene(self):
        self.assertTrue(prompt_mentions_skill("run /demo on this", "demo"))
        self.assertTrue(prompt_mentions_skill("use the demo skill", "demo"))
        self.assertFalse(prompt_mentions_skill("merge these csv files", "demo"))


class SupplyChain(unittest.TestCase):
    """F-14. skill-creator packages .git, packages .env, scans for nothing, and
    strips the evals the recipient would need to re-verify the skill."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.d = self.tmp / "demo-skill"
        (self.d / "scripts").mkdir(parents=True)
        (self.d / "evals").mkdir()
        (self.d / ".git").mkdir()
        (self.d / "SKILL.md").write_text(
            "---\nname: demo-skill\ndescription: Does a thing. Use when a thing is needed.\n---\n\n"
            "Run `scripts/go.py`.\n")
        (self.d / "scripts" / "go.py").write_text(
            "import subprocess, requests\nrequests.get('https://api.example.com/x')\n")
        (self.d / "evals" / "evals.json").write_text('{"skill_name": "demo-skill", "cases": []}')
        (self.d / ".git" / "config").write_text("[remote]\n")
        (self.d / ".env").write_text("SECRET=hunter2\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_git_and_env_never_enter_the_archive(self):
        archive, rep, _ = package(self.d, self.tmp / "out")
        self.assertIsNotNone(archive)
        import zipfile
        names = zipfile.ZipFile(archive).namelist()
        self.assertFalse([n for n in names if ".git/" in n or n.endswith(".env")])

    def test_evals_ship_with_the_skill(self):
        archive, _, _ = package(self.d, self.tmp / "out")
        import zipfile
        self.assertIn("demo-skill/evals/evals.json", zipfile.ZipFile(archive).namelist())

    def test_a_leaked_credential_blocks_packaging(self):
        # Built at runtime so this fixture is not itself a scanner hit in this file.
        (self.d / "notes.md").write_text("ghp_" + "a" * 36 + "\n")
        archive, rep, _ = package(self.d, self.tmp / "out")
        self.assertIsNone(archive)
        self.assertTrue(rep.blocking)

    def test_a_suppressed_match_is_reported_but_does_not_block(self):
        (self.d / "docs.md").write_text(
            "Example only, do not use:  # skilleng:allow-secret\nghp_" + "b" * 36 + "\n")
        archive, rep, _ = package(self.d, self.tmp / "out")
        self.assertIsNotNone(archive, "a suppressed match must not block packaging")
        self.assertTrue(rep.suppressed, "a suppression must still be listed in the report")
        self.assertIn("Suppressed secret matches", rep.to_markdown())

    def test_script_behaviour_and_endpoints_are_inventoried(self):
        rep = scan(self.d)
        self.assertIn("api.example.com", rep.endpoints)
        behaviours = rep.scripts[0]["behaviours"]
        self.assertIn("makes network requests", behaviours)
        self.assertIn("Bash", rep.proposed_allowed_tools)

    def test_security_report_travels_inside_the_archive(self):
        archive, _, _ = package(self.d, self.tmp / "out")
        import zipfile
        self.assertIn("demo-skill/SECURITY.md", zipfile.ZipFile(archive).namelist())


class Gates(unittest.TestCase):
    """F-19. skill-creator enforces its review step with capital letters."""

    def test_phase_cannot_advance_until_gates_pass(self):
        d = Path(tempfile.mkdtemp())
        ws = Workspace.create(d)
        self.assertFalse(ws.gate("controls"))
        ws.set_gate("controls", True, "separation 0.83")
        ws.set_gate("review", False, "no human feedback yet")
        self.assertTrue(ws.gate("controls"))
        self.assertFalse(ws.gate("review"))
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
