"""Failure-path tests for the development checks, independent of product code."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import harness


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agenttv-harness-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "docs/plans").mkdir(parents=True)
        self.page = self.root / "docs/spec.html"
        self.page.write_text('<!doctype html><html><body><h1 id="record">Record</h1></body></html>')
        (self.root / "AGENTS.md").write_text('[Spec](docs/spec.html#record)\n')
        (self.root / "CLAUDE.md").write_text('@AGENTS.md\n')
        (self.root / ".gitignore").write_text('.harness/\n.agents/skills/\n')
        self.policy = {
            "required_documents": ["AGENTS.md", "CLAUDE.md", "docs/spec.html"],
            "ignored_directories": [".harness/", ".agents/skills/"],
            "required_case_areas": ["record"],
            "rust_packages": {
                "agenttv-domain": {"path": "crates/domain", "local_dependencies": [], "forbidden_dependencies": ["rusqlite"]},
                "agenttv-storage": {"path": "crates/storage", "local_dependencies": ["agenttv-domain"]},
            },
        }
        self.catalog = {"schema_version": 1, "cases": [{"id": "record-01", "area": "record",
            "scenario": "Copy", "expected": "Keep Ready", "spec": "docs/spec.html#record", "automated_command": None}]}

    def test_valid_documents_and_catalog(self):
        self.assertEqual(harness.documentation_errors(self.root, self.policy), [])
        self.assertEqual(harness.catalog_errors(self.root, self.policy, self.catalog), [])

    def test_broken_anchor_is_actionable(self):
        (self.root / "AGENTS.md").write_text('[Spec](docs/spec.html#missing)')
        self.assertIn("missing anchor", " ".join(harness.documentation_errors(self.root, self.policy)))

    def test_readme_link_is_checked(self):
        (self.root / "README.md").write_text('[Start](docs/spec.html#missing)')
        self.assertIn("README.md: missing anchor", " ".join(harness.documentation_errors(self.root, self.policy)))

    def test_local_link_cannot_escape_project(self):
        (self.root / "AGENTS.md").write_text('[Outside](../private.html)')
        self.assertIn("leaves the project", " ".join(harness.documentation_errors(self.root, self.policy)))

    def test_duplicate_anchor_and_unbalanced_html_fail(self):
        self.page.write_text('<html><body><p id="same"><b></p><p id="same">x</body></html>')
        errors = " ".join(harness.documentation_errors(self.root, self.policy))
        self.assertIn("duplicate anchors", errors)
        self.assertIn("closing tag", errors)

    def test_plan_requires_progress_decisions_and_validation(self):
        (self.root / "docs/plans/work.html").write_text('<html><head><meta name="agenttv:plan-status" content="active"></head><body><h1 id="purpose">Work</h1></body></html>')
        errors = " ".join(harness.documentation_errors(self.root, self.policy))
        self.assertIn("missing plan sections", errors)
        self.assertIn("progress", errors)

    def test_duplicate_case_and_invalid_command_fail(self):
        self.catalog["cases"].append(copy.deepcopy(self.catalog["cases"][0]))
        self.catalog["cases"][1]["automated_command"] = "echo success"
        errors = " ".join(harness.catalog_errors(self.root, self.policy, self.catalog))
        self.assertIn("unique", errors)
        self.assertIn("argument array", errors)

    def test_missing_acceptance_area_fails(self):
        self.policy["required_case_areas"].append("preview")
        self.assertIn("preview", " ".join(harness.catalog_errors(self.root, self.policy, self.catalog)))

    def test_domain_dependency_inversion_fails(self):
        metadata = {"workspace_members": ["domain"], "packages": [{"id": "domain", "name": "agenttv-domain",
            "manifest_path": str(self.root / "crates/domain/Cargo.toml"),
            "dependencies": [{"name": "agenttv-storage", "path": str(self.root / "crates/storage")}, {"name": "rusqlite"}]}]}
        errors = " ".join(harness.architecture_errors(self.root, self.policy, metadata))
        self.assertIn("outside its layer", errors)
        self.assertIn("rusqlite", errors)

    def test_allowed_storage_dependency_passes(self):
        metadata = {"workspace_members": ["storage"], "packages": [{"id": "storage", "name": "agenttv-storage",
            "manifest_path": str(self.root / "crates/storage/Cargo.toml"),
            "dependencies": [{"name": "agenttv-domain", "path": str(self.root / "crates/domain")}]}]}
        self.assertEqual(harness.architecture_errors(self.root, self.policy, metadata), [])

    def test_known_dependency_cannot_point_at_another_checkout(self):
        metadata = {"workspace_members": ["storage"], "packages": [{"id": "storage", "name": "agenttv-storage",
            "manifest_path": str(self.root / "crates/storage/Cargo.toml"),
            "dependencies": [{"name": "agenttv-domain", "path": str(self.root.parent / "other-repo")}]}]}
        self.assertIn("inside this project", " ".join(harness.architecture_errors(self.root, self.policy, metadata)))

    def test_strict_product_mode_rejects_absent_app(self):
        errors = " ".join(harness.product_setup_errors(self.root, self.policy))
        self.assertIn("Cargo.toml", errors)
        self.assertIn("web/package.json", errors)
        self.assertIn("not implemented", errors)

    def test_empty_unittest_run_cannot_pass(self):
        self.assertIsNotNone(harness.unittest_result_error("Ran 0 tests in 0.000s\nOK"))
        self.assertIsNotNone(harness.unittest_result_error("No result"))
        self.assertIsNone(harness.unittest_result_error("Ran 1 test in 0.100s\nOK"))

    def test_command_failure_is_reported_and_output_retained(self):
        run = self.root / ".harness/run"
        run.mkdir(parents=True)
        result = harness.command_check(self.root, run, "expected-failure", [sys.executable, "-c", "print('fixture failure'); raise SystemExit(7)"])
        self.assertEqual(result.status, "failed")
        self.assertIn("7", result.detail)
        self.assertIn("fixture failure", (self.root / result.log).read_text())

    def test_command_receives_disposable_data_and_fixture_mode(self):
        run = self.root / ".harness/run"
        run.mkdir(parents=True)
        command = [sys.executable, "-c", "import os,json;print(json.dumps([os.environ['AGENTTV_SOURCE_MODE'],os.environ['AGENTTV_DATA_DIR']]))"]
        result = harness.command_check(self.root, run, "fixture-env", command)
        self.assertEqual(result.status, "passed")
        mode, data_dir = json.loads((self.root / result.log).read_text())
        self.assertEqual(mode, "fixture")
        self.assertTrue(Path(data_dir).is_relative_to(run / "data"))
        self.assertTrue(Path(data_dir).is_dir())

    def test_json_output_stays_parseable_with_stderr_warning(self):
        run = self.root / ".harness/run"
        run.mkdir(parents=True)
        result = harness.command_check(self.root, run, "metadata", [sys.executable, "-c", "import sys;print('{}');print('warning',file=sys.stderr)"], json_output=True)
        self.assertEqual(json.loads((self.root / result.log).read_text()), {})

    def test_skill_selection_preserves_four_agents_and_no_track(self):
        envelope = {"ok": True, "data": {"healthy": True, "track": False,
            "agents": ["claude", "codex", "kimi", "pi"], "skills": ["plain-docs"],
            "project_dirs": {"claude": ".claude/skills", "codex": ".agents/skills", "kimi": ".agents/skills", "pi": ".agents/skills"}}}
        self.assertIsNone(harness.skill_error(envelope))
        envelope["data"]["track"] = True
        self.assertIn("no-track", harness.skill_error(envelope))


if __name__ == "__main__":
    unittest.main()
