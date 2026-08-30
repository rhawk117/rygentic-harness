import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit_rules import audit, main

FIXTURES = Path(__file__).resolve().joinpath("fixtures")


class DirtyFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.findings, cls.layout = audit(FIXTURES / "dirty")
        cls.smells = {finding.smell for finding in cls.findings}

    def smells_in(self, path):
        return {finding.smell for finding in self.findings if finding.path == path}

    def test_detects_lint_leakage(self):
        self.assertIn("Lint Leakage", self.smells_in("AGENTS.md"))

    def test_detects_blind_reference(self):
        blind = [f for f in self.findings if f.smell == "Blind Reference"]
        self.assertTrue(any("plugin-reorg" in f.message for f in blind))

    def test_detects_conflicting_test_commands(self):
        conflicts = [f for f in self.findings if f.smell == "Conflicting Instructions"]
        self.assertTrue(any("npm test" in f.message and "pnpm test" in f.message
                            for f in conflicts))

    def test_detects_missing_apply_to(self):
        self.assertIn("Scoping", self.smells_in(".github/instructions/frontend.instructions.md"))

    def test_missing_apply_to_is_an_error(self):
        scoping = [f for f in self.findings
                   if f.smell == "Scoping" and f.path.endswith("frontend.instructions.md")]
        self.assertEqual(["error"], [f.severity for f in scoping])

    def test_flags_rule_without_paths_as_info_only(self):
        scoping = [f for f in self.findings
                   if f.smell == "Scoping" and f.path == ".claude/rules/api.md"]
        self.assertEqual(["info"], [f.severity for f in scoping])

    def test_detects_agents_md_invisible_to_claude_code(self):
        self.assertIn("Invisible AGENTS.md", self.smells)

    def test_detects_duplication_across_tools(self):
        self.assertIn("Duplication", self.smells)

    def test_layout_reports_readers_per_file(self):
        by_path = {entry["path"]: entry for entry in self.layout["files"]}
        self.assertEqual(["GitHub Copilot"], by_path["AGENTS.md"]["read_by"])
        self.assertEqual(["Claude Code"], by_path["CLAUDE.md"]["read_by"])

    def test_ignores_smells_inside_code_fences(self):
        fenced = FIXTURES / "dirty" / "FENCED.md"
        fenced.write_text("# X\n\n```md\n- Indentation: 2 spaces\n```\n", encoding="utf-8")
        try:
            findings, _ = audit(FIXTURES / "dirty")
            self.assertFalse([f for f in findings
                              if f.path == "FENCED.md" and f.smell == "Lint Leakage"])
        finally:
            fenced.unlink()


class CleanFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.findings, cls.layout = audit(FIXTURES / "clean")

    def test_no_errors_or_warnings(self):
        blocking = [f for f in self.findings if f.severity in ("error", "warn")]
        self.assertEqual([], [f"{f.path}:{f.line} {f.smell}: {f.message}" for f in blocking])

    def test_import_cost_is_info_only(self):
        imports = [f for f in self.findings if f.smell == "Import Cost"]
        self.assertEqual(["info"], sorted({f.severity for f in imports}))

    def test_skill_paths_are_reported_as_shared(self):
        skill_dir = FIXTURES / "clean" / ".claude" / "skills" / "demo"
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text("---\nname: demo\ndescription: d\n---\n", encoding="utf-8")
        try:
            _, layout = audit(FIXTURES / "clean")
            entry = next(e for e in layout["files"] if e["path"].endswith("demo/SKILL.md"))
            self.assertEqual(["Claude Code", "GitHub Copilot"], entry["read_by"])
        finally:
            (skill_dir / "SKILL.md").unlink()
            skill_dir.rmdir()
            skill_dir.parent.rmdir()


class ExitCodes(unittest.TestCase):
    def test_dirty_fixture_exits_nonzero(self):
        self.assertEqual(1, main([str(FIXTURES / "dirty")]))

    def test_no_fail_suppresses_exit_code(self):
        self.assertEqual(0, main([str(FIXTURES / "dirty"), "--no-fail"]))

    def test_clean_fixture_exits_zero(self):
        self.assertEqual(0, main([str(FIXTURES / "clean")]))

    def test_missing_directory_exits_two(self):
        self.assertEqual(2, main([str(FIXTURES / "does-not-exist")]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
