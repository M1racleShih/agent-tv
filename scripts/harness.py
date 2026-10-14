#!/usr/bin/env python3
"""Repository checks. Product tests are invoked only when their manifests exist."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import tomllib
from urllib.parse import unquote, urlsplit
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}
PLAN_SECTIONS = {"purpose", "progress", "decisions", "validation", "recovery", "outcomes"}


@dataclass
class Check:
    name: str
    status: str
    detail: str
    log: str | None = None
    command: list[str] | None = None
    duration_seconds: float | None = None


class Document(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.links: list[str] = []
        self.stack: list[str] = []
        self.errors: list[str] = []
        self.plan_status: str | None = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.append(values["id"])
        if "href" in values:
            self.links.append(values["href"])
        if "src" in values:
            self.links.append(values["src"])
        if tag == "meta" and values.get("name") == "agenttv:plan-status":
            self.plan_status = values.get("content")
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"Unexpected closing tag </{tag}>; check nesting.")
        else:
            self.stack.pop()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def local_link_error(root: Path, source: Path, href: str,
                     documents: dict[Path, Document]) -> str | None:
    parts = urlsplit(href)
    if parts.scheme in {"http", "https", "mailto"}:
        return None
    if parts.scheme or parts.netloc:
        return f"{source.relative_to(root)}: unsupported link {href!r}"
    target = (source.parent / unquote(parts.path)).resolve() if parts.path else source
    if not target.is_relative_to(root.resolve()):
        return f"{source.relative_to(root)}: local link leaves the project: {href!r}"
    if not target.is_file():
        return f"{source.relative_to(root)}: missing link target {href!r}"
    if parts.fragment and target in documents:
        if unquote(parts.fragment) not in documents[target].ids:
            return f"{source.relative_to(root)}: missing anchor {href!r}"
    return None


def documentation_errors(root: Path, policy: dict) -> list[str]:
    errors = []
    for name in policy["required_documents"]:
        if not (root / name).is_file():
            errors.append(f"Missing {name}; restore the entry or update policy and links together.")
    documents = {}
    for path in sorted((root / "docs").rglob("*.html")):
        path = path.resolve()
        doc = Document()
        doc.feed(path.read_text(encoding="utf-8"))
        doc.close()
        documents[path] = doc
        errors.extend(f"{path.relative_to(root)}: {item}" for item in doc.errors)
        if doc.stack:
            errors.append(f"{path.relative_to(root)}: unclosed tags {doc.stack}")
        duplicates = [key for key, count in Counter(doc.ids).items() if count > 1]
        if duplicates:
            errors.append(f"{path.relative_to(root)}: duplicate anchors {duplicates}")
        if path.parent == root / "docs/plans":
            if doc.plan_status not in {"template", "planned", "active", "complete", "blocked"}:
                errors.append(f"{path.relative_to(root)}: add a valid agenttv:plan-status meta tag.")
            missing = PLAN_SECTIONS - set(doc.ids)
            if missing:
                errors.append(f"{path.relative_to(root)}: missing plan sections {sorted(missing)}")
    for path, doc in documents.items():
        for href in doc.links:
            problem = local_link_error(root, path, href, documents)
            if problem:
                errors.append(problem)
    for filename in ("README.md", "AGENTS.md", "CLAUDE.md"):
        path = root / filename
        if path.exists():
            for href in re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                problem = local_link_error(root, path, href, documents)
                if problem:
                    errors.append(problem)
    bridge = root / "CLAUDE.md"
    if bridge.exists() and bridge.read_text(encoding="utf-8").strip() != "@AGENTS.md":
        errors.append("Keep CLAUDE.md as @AGENTS.md so project instructions have one source.")
    ignore_file = root / ".gitignore"
    ignored = set(ignore_file.read_text().splitlines()) if ignore_file.exists() else set()
    for name in policy["ignored_directories"]:
        if name not in ignored:
            errors.append(f"Add {name} to .gitignore; skills and run data stay local.")
    return errors


def catalog_errors(root: Path, policy: dict, catalog: dict) -> list[str]:
    errors = []
    cases = catalog.get("cases", [])
    if catalog.get("schema_version") != 1 or not isinstance(cases, list) or not cases:
        return ["harness/cases.json needs schema_version 1 and a nonempty cases array."]
    ids = [case.get("id") for case in cases]
    if len(ids) != len(set(ids)):
        errors.append("Case IDs must be unique; retain existing IDs when updating tests.")
    documents = {}
    for path in (root / "docs").rglob("*.html"):
        doc = Document()
        doc.feed(path.read_text(encoding="utf-8"))
        documents[path.resolve()] = doc
    for case in cases:
        case_id = case.get("id", "<missing>")
        if not isinstance(case_id, str) or not re.fullmatch(r"[a-z]+-\d{2}", case_id):
            errors.append(f"Invalid case ID: {case_id!r}")
        for key in ("area", "scenario", "expected", "spec"):
            if not isinstance(case.get(key), str) or not case[key].strip():
                errors.append(f"{case_id}: supply {key}.")
        if isinstance(case.get("spec"), str):
            problem = local_link_error(root, root / "case-reference", case["spec"], documents)
            if problem:
                errors.append(f"{case_id}: {problem}")
        command = case.get("automated_command")
        if command is not None and (not isinstance(command, list) or not command
                                    or any(not isinstance(arg, str) or not arg.strip() for arg in command)):
            errors.append(f"{case_id}: automated_command must be null or a nonempty argument array.")
    areas = {case.get("area") for case in cases}
    missing = set(policy["required_case_areas"]) - areas
    if missing:
        errors.append(f"Missing acceptance areas: {sorted(missing)}")
    return errors


def architecture_errors(root: Path, policy: dict, metadata: dict) -> list[str]:
    errors = []
    members = set(metadata.get("workspace_members", []))
    packages = [p for p in metadata.get("packages", []) if p["id"] in members]
    rules = policy["rust_packages"]
    for package in packages:
        name = package["name"]
        if name not in rules:
            errors.append(f"Register workspace package {name} and its dependency direction in harness/policy.json.")
            continue
        rule = rules[name]
        manifest = Path(package["manifest_path"]).resolve()
        if manifest != (root / rule["path"] / "Cargo.toml").resolve():
            errors.append(f"{name}: place its manifest under {rule['path']} or update the design and policy.")
        for dependency in package.get("dependencies", []):
            target = dependency["name"]
            if dependency.get("path"):
                if target not in rule["local_dependencies"]:
                    errors.append(f"{name} -> {target}: local dependency is outside its layer; pass domain observations through the server.")
                target_rule = rules.get(target)
                if not target_rule or Path(dependency["path"]).resolve() != (root / target_rule["path"]).resolve():
                    errors.append(f"{name} -> {target}: use the registered package path inside this project.")
            if target in rule.get("forbidden_dependencies", []):
                errors.append(f"{name} -> {target}: move runtime, HTTP or database work to the appropriate outer package.")
    return errors


def product_setup_errors(root: Path, policy: dict) -> list[str]:
    required = ["Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "web/package.json",
                "web/package-lock.json", "web/.node-version"]
    errors = [f"Missing {name}; product verification requires reproducible Rust and web projects."
              for name in required if not (root / name).is_file()]
    for name, rule in policy["rust_packages"].items():
        if not (root / rule["path"] / "Cargo.toml").is_file():
            errors.append(f"Missing {name} at {rule['path']}; this product layer is not implemented.")
    return errors


def skill_error(envelope: dict) -> str | None:
    data = envelope.get("data", {})
    if not envelope.get("ok") or not data.get("healthy"):
        return "dskills reports an unhealthy project; inspect dskills --json status and repair selection."
    if data.get("track") is not False:
        return "Set project skills to no-track with dskills; skill files stay outside version control."
    if not {"claude", "codex", "kimi", "pi"}.issubset(data.get("agents", [])):
        return "Select all four agent families in dskills."
    if "plain-docs" not in data.get("skills", []):
        return "Activate plain-docs through dskills before authoring documents."
    dirs = data.get("project_dirs", {})
    if any(dirs.get(name) != ".agents/skills" for name in ("codex", "kimi", "pi")):
        return "Codex, Kimi and pi share .agents/skills; adjust the dskills project selection."
    if dirs.get("claude") != ".claude/skills":
        return "Use the project's .claude/skills output for Claude."
    return None


def command_check(root: Path, run_dir: Path, name: str, command: list[str], *, json_output=False) -> Check:
    label = re.sub(r"[^a-zA-Z0-9_-]", "-", name)
    log = run_dir / (label + ".log")
    data_dir = run_dir / "data" / label
    data_dir.mkdir(parents=True, exist_ok=True)
    print(f"RUN  {name}: {json.dumps(command)}", flush=True)
    env = os.environ.copy()
    env.update({"AGENTTV_DATA_DIR": str(data_dir), "AGENTTV_SOURCE_MODE": "fixture",
                "AGENTTV_FIXTURES_DIR": str(root / "tests/fixtures"), "CI": "true"})
    started = time.monotonic()
    try:
        with log.open("w", encoding="utf-8") as output, log.with_suffix(".stderr.log").open("w", encoding="utf-8") as errors:
            process = subprocess.run(command, cwd=root, env=env, stdout=output,
                                     stderr=errors if json_output else subprocess.STDOUT, timeout=600, check=False)
        status = "passed" if process.returncode == 0 else "failed"
        detail = f"exit={process.returncode}"
    except (OSError, subprocess.TimeoutExpired) as error:
        status, detail = "failed", f"{type(error).__name__}: {error}"
    if status == "failed" and log.exists():
        print(log.read_text(encoding="utf-8", errors="replace")[-2500:], flush=True)
        if json_output:
            print(log.with_suffix(".stderr.log").read_text(encoding="utf-8", errors="replace")[-2500:], flush=True)
    return Check(name, status, detail, str(log.relative_to(root)), command, round(time.monotonic() - started, 3))


def checked_errors(name: str, errors: list[str], success: str) -> Check:
    return Check(name, "failed" if errors else "passed", "\n".join(errors) if errors else success)


def unittest_result_error(output: str) -> str | None:
    match = re.search(r"\bRan (\d+) tests?\b", output)
    if not match or int(match.group(1)) == 0:
        return "No harness tests ran; restore tests/harness and confirm unittest discovery."
    return None


def doctor(root: Path) -> list[Check]:
    checks = [Check("python", "passed" if sys.version_info >= (3, 11) else "failed", sys.version.split()[0])]
    for tool in ("git", "cargo", "rustc", "node", "npm"):
        path = shutil.which(tool)
        if not path:
            checks.append(Check(tool, "failed", f"{tool} is missing from PATH."))
            continue
        try:
            result = subprocess.run([path, "--version"], cwd=root, capture_output=True, text=True, timeout=15)
            version = (result.stdout or result.stderr).strip().splitlines()
            checks.append(Check(tool, "passed" if result.returncode == 0 else "failed", version[0] if version else "No version output."))
        except (OSError, subprocess.TimeoutExpired) as error:
            checks.append(Check(tool, "failed", str(error)))
    if shutil.which("git"):
        result = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=root, capture_output=True, text=True)
        checks.append(Check("git-checkout", "passed" if result.returncode == 0 else "not_applicable",
                            result.stdout.strip() or "No Git checkout yet; local checks work, CI awaits repository publication."))
    if not shutil.which("dskills"):
        checks.append(Check("dskills", "failed", "Install or locate dskills; this command does not change global configuration."))
    else:
        try:
            result = subprocess.run(["dskills", "--json", "status"], cwd=root, capture_output=True, text=True, timeout=20)
            problem = skill_error(json.loads(result.stdout))
            checks.append(Check("dskills", "failed" if problem or result.returncode else "passed", problem or "Healthy no-track project; plain-docs and all four agent families are configured."))
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            checks.append(Check("dskills", "failed", f"Cannot read dskills status: {error}"))
    return checks


def run_checks(root: Path, run_dir: Path, scope: str, policy: dict, catalog: dict) -> list[Check]:
    checks = [checked_errors("documents", documentation_errors(root, policy), "HTML structure, local links, plan sections, instruction bridge and ignore rules pass."),
              checked_errors("acceptance-catalog", catalog_errors(root, policy, catalog), "Acceptance case identities, areas and specification links pass.")]
    if scope == "docs":
        return checks
    test_result = command_check(root, run_dir, "harness-tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests/harness", "-p", "test_*.py"])
    if test_result.status == "passed":
        problem = unittest_result_error((root / test_result.log).read_text())
        if problem:
            test_result.status, test_result.detail = "failed", problem
    checks.append(test_result)
    if scope == "harness":
        return checks
    rust = (root / "Cargo.toml").is_file()
    web = (root / "web/package.json").is_file()
    if scope == "product":
        checks.append(checked_errors("product-setup", product_setup_errors(root, policy), "Both product projects and reproducibility files exist."))
    if rust:
        try:
            tomllib.loads((root / "Cargo.toml").read_text())
            result = command_check(root, run_dir, "rust-architecture", ["cargo", "metadata", "--locked", "--no-deps", "--format-version", "1"], json_output=True)
            checks.append(result)
            if result.status == "passed":
                metadata = load_json(root / result.log)
                checks.append(checked_errors("rust-layers", architecture_errors(root, policy, metadata), "Workspace package paths and dependency directions pass."))
        except (OSError, ValueError) as error:
            checks.append(Check("rust-layers", "failed", str(error)))
        for name, command in [
            ("rust-format", ["cargo", "fmt", "--all", "--", "--check"]),
            ("rust-clippy", ["cargo", "clippy", "--locked", "--workspace", "--all-targets", "--", "-D", "warnings"]),
            ("rust-tests", ["cargo", "test", "--locked", "--workspace", "--all-targets"]),
        ]:
            checks.append(command_check(root, run_dir, name, command))
    else:
        checks.append(Check("rust-product", "not_applicable", "Cargo.toml is absent; Rust product behavior has not been verified."))
    if web:
        try:
            package = load_json(root / "web/package.json")
            scripts = package.get("scripts", {})
            for script in policy["web_scripts"]:
                if not scripts.get(script):
                    checks.append(Check(f"web-{script}", "failed", f"Define the noninteractive {script} script in web/package.json."))
                    continue
                command = ["npm", "--prefix", "web", "run", script]
                if script == "test":
                    command += ["--", "--run"]
                checks.append(command_check(root, run_dir, f"web-{script}", command))
        except (OSError, ValueError) as error:
            checks.append(Check("web-manifest", "failed", str(error)))
    else:
        checks.append(Check("web-product", "not_applicable", "web/package.json is absent; browser product behavior has not been verified."))
    pending = [case["id"] for case in catalog["cases"] if not case.get("automated_command")]
    checks.append(Check("critical-case-coverage", "failed" if pending and scope == "product" else "not_applicable" if pending else "passed",
                        f"{len(pending)} cases await executable fixture tests: {', '.join(pending)}" if pending else "Every critical case has an executable command."))
    if scope == "product" and not catalog_errors(root, policy, catalog):
        for case in catalog["cases"]:
            if case.get("automated_command"):
                checks.append(command_check(root, run_dir, case["id"], case["automated_command"]))
    return checks


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="Inspect local tool versions and dskills without changing configuration.")
    subparsers.add_parser("cases", help="List required acceptance cases and test registration status.")
    check = subparsers.add_parser("check", help="Run checks and save a local JSON report.")
    check.add_argument("--scope", choices=("docs", "harness", "all", "product"), default="all")
    args = parser.parse_args(argv)
    try:
        policy = load_json(ROOT / "harness/policy.json")
        catalog = load_json(ROOT / "harness/cases.json")
        if policy.get("schema_version") != 1:
            raise ValueError("Unsupported harness policy schema; update the reader and policy together.")
    except (OSError, ValueError) as error:
        print(f"FAIL configuration: {error}", file=sys.stderr)
        return 1
    if args.command == "cases":
        errors = catalog_errors(ROOT, policy, catalog)
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        for case in catalog["cases"]:
            status = "registered" if case.get("automated_command") else "planned"
            print(f"{case['id']:<16} {status:<12} {case['scenario']}")
        print("Registration describes intended coverage; execution evidence comes from check --scope product. Live-source and visual checks are separate.")
        return 0
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    run_dir = ROOT / ".harness/runs" / run_id
    run_dir.mkdir(parents=True)
    scope = args.scope if args.command == "check" else "doctor"
    try:
        checks = doctor(ROOT) if args.command == "doctor" else run_checks(ROOT, run_dir, scope, policy, catalog)
    except (OSError, ValueError, KeyError, TypeError) as error:
        checks = [Check("configuration", "failed", f"{type(error).__name__}: {error}")]
    ok = all(item.status != "failed" for item in checks)
    report = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
              "scope": scope, "ok": ok, "product_verification_requested": scope == "product",
              "critical_cases_registered": sum(bool(case.get("automated_command")) for case in catalog["cases"]),
              "critical_cases_total": len(catalog["cases"]), "checks": [asdict(item) for item in checks]}
    report_path = run_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for item in checks:
        print(f"{item.status.upper():<15} {item.name}: {item.detail}")
    print(f"REPORT {report_path}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
