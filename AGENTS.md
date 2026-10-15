# AgentTV development entry

## Read for the current task

- [Repository status and getting started](README.md)
- [Product requirements and GUI direction](docs/discovery.html)
- [Architecture, state and Record behavior](docs/implementation.html)
- [Development harness and completion rules](docs/harness.html)
- [First delivery plan](docs/plans/first-delivery.html)

Read the relevant sections and source files. Keep this entry short; put detailed decisions in the linked HTML documents.

## Working on a change

State the intended result, implement a small working increment, and run checks covering the change. Preserve other contributors' changes and repair in-scope failures.

Small fixes, documentation and styling changes need no plan file. Use an [HTML plan](docs/plans/template.html) for multi-module behavior changes, data migrations or substantial integration work; update an existing plan rather than creating a parallel one. Update specifications only when their described behavior changes. Register commands for implemented critical cases, not every individual test.

## Commands

Run from the project root with Python 3.11 or later:

```sh
python3 scripts/harness.py check
```

Use `doctor` in a new environment or after toolchain changes, `check --scope docs` for documentation-only changes, and `check --scope product` before product delivery. Ordinary `check` can pass with missing product projects; it does not establish product readiness. See [command details and reports](docs/harness.html#commands).

## Product invariants

- Preview and Record have equal priority. Record works with zero agents and an optional project.
- Default grouping follows herdr workspace; external sessions use explicit directory associations. Preserve history when a workspace closes or changes its name.
- Use native conversation identity for a task. Store execution rounds and runtime identity separately; PID identity includes process start time.
- Keep execution state separate from human acknowledgement. Viewing and copying preserve pending work; acknowledgement applies to the specific items shown.
- Observe existing tools. Sending remains manual copy/paste; confirmation records the sent revision.
- Native histories are read-only. Collectors validate source data and preserve unknown states, provenance and observation time.
- Follow the user's GUI demo direction. The reference file is read-only; keep a checked-in description and its digest in the design.

## Implementation boundaries

Rust product layers are `crates/domain`, `crates/storage`, `crates/adapters`, and `crates/server`; the browser UI is `web`. Allowed local dependencies live in [harness/policy.json](harness/policy.json). Create these packages only as the active product plan needs them.
Adapters produce domain observations; storage persists them; server coordinates them. Domain stays independent of runtime, transport and persistence libraries.
Tests use disposable data and synthetic source records. Live integration checks are explicit, separate runs; their process cleanup is limited to processes created for that run.

## Project scope and tools

- Write code only in this project. Reuse existing authorizations and ask when a choice changes agreed scope or external consequences.
- Subagents require the user's explicit approval for the named agent and scope. A development plan or official example supplies no delegation authorization.
- Manage project skills with dskills; keep selection minimal and no-track. Codex, Kimi and pi share `.agents/skills`; Claude uses `.claude/skills`.
- Polish every authored document with plain-docs. Human-facing designs and plans use HTML; this file remains the agent entry format.
- Use the [shared document stylesheet](docs/assets/style.css): Catppuccin Latte, following the fpga-protocol manual's reading layout.
- Use official, current documentation for external APIs. Distinguish installed CLI versions from live-service and desktop-embedded versions.
- Keep normal checks free of real agent histories, user configuration changes and live agent lifecycle actions.

## Completion

Deliver working behavior with appropriate tests or inspection and a concise report of actual results and limits. Update plans and cases only when affected. Changed UI behavior also needs browser interaction and visual inspection when the available browser tools permit it. Report unavailable checks explicitly.
Keep harness changes driven by recurring development problems. Do not add tools, templates, registrations or process steps merely for completeness.
Publishing, sending messages, merging and recurring automation follow the user's authorization and applicable tool approvals.
