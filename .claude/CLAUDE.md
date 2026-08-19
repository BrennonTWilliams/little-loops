<!-- Last updated: 2026-07-27 -->
# little-loops (ll) - Claude Code Plugin

Development workflow toolkit for Claude Code with issue management, code quality commands, and automated processing.

## Distribution

little-loops ships two ways into a consuming project:

- **pip package** — `pip install little-loops` (PyPI), providing the `ll-*` CLI entry points
- **Claude Code plugin** — via the marketplace, providing `/ll:*` commands, skills, agents, and hooks

`ll-init` sets both up and records which one is in play as `install_source` in the
project's `.ll/ll-config.json` (`pypi`, `local-editable`, `global-claude-code`,
`project-claude-code`).

**This repo is the source, not a consumer.** Everything below describes developing
little-loops itself; install here with `pip install -e "./scripts[dev]"`.

**All little-loops projects on this machine are `local-editable` against this
checkout** — they exist to exercise and inform little-loops development. Consequence:
uncommitted changes here are immediately live in every one of them, with no reinstall
step. A broken `main` breaks those projects' tooling silently, and a defect that shows
up "in another project" is usually a working-tree change here, not a released bug.

## Project Configuration

- **Plugin manifest**: `.claude-plugin/plugin.json`
- **Config schema**: `scripts/little_loops/config-schema.json`
- **Project config**: `.ll/ll-config.json` (read this for project-specific settings)
- **Local overrides**: `.ll/ll.local.md` (user-specific, gitignored)
- **Hooks**: `hooks/hooks.json`

### Local Settings Override

Create `.ll/ll.local.md` to override settings for your local environment without modifying shared config:

```markdown
---
project:
  test_cmd: "python -m pytest scripts/tests/ -v --tb=short"
scan:
  focus_dirs: ["scripts/", "my-experimental-dir/"]
---

# Local Settings Notes

Personal development preferences.
```

**Merge behavior**: Nested objects are deep merged, arrays replace (not append), explicit `null` removes a setting.

**Note**: The `## Active Rules` section in the body of `ll.local.md` is machine-written by `sync_to_local_md` (via `ll-issues decisions sync`) and contains active required decision rules. Do not hand-edit this section; it will be overwritten on the next sync.

## Key Directories

```
commands/       # Slash commands (/ll:*)
agents/         # Subagent definitions
skills/         # Skill definitions
hooks/          # Lifecycle hooks (subdivided below)
  adapters/     # Host translation layer; one subdir per host (claude-code/, opencode/, codex/) that envelopes the host event into LLHookEvent
                # Note: hooks/adapters/codex/hooks.json moved to scripts/little_loops/hooks/adapters/codex/ (FEAT-2274)
  prompts/      # Prompt-text files referenced from hooks/hooks.json entries (continuation-prompt-template.md stays here)
                # Note: optimize-prompt-hook.md moved to scripts/little_loops/hooks/prompts/ (FEAT-2274)
                # Host-agnostic Python handlers live under scripts/little_loops/hooks/ (session_start, pre_compact, ...) and are invoked by main_hooks()
scripts/        # Python package (little_loops)
                # Package data (consumed by CLI code) lives inside scripts/little_loops/:
                #   templates/    — project-type configs, section templates, design tokens
                #   assets/       — ll-cli-logo.txt
                #   hooks/prompts/optimize-prompt-hook.md
                #   hooks/adapters/codex/hooks.json
.issues/        # Issue tracking (bugs/, features/, enhancements/, epics/)
.ll/decisions.yaml # Decisions and rules log — legacy flat file (opt-in; managed by `ll-issues decisions`)
.ll/decisions.d/   # Append-only per-entry decision fragments (`<uuid4>.json`); folded into decisions.yaml on compaction. A fresh install has only this dir. Presence gates must accept either.
postmortems/    # Loop-run postmortems and ad-hoc run forensics. Gitignored,
                # source-repo-only — NEVER carried into consuming projects.
                # Run analyses go here, not the repo root. Quotes traces and
                # paths from private codebases; `ll-verify-private-refs` exempts it.
thoughts/       # Plans and research documents
docs/           # Architecture, API, troubleshooting
```

## Commands & Skills

Run `/ll:help` for full list. Both commands (`commands/*.md`) and skills (`skills/*/SKILL.md`) are invoked via `/ll:<name>`. Skills are marked with ^.

- **Issue Discovery**: `capture-issue`^, `scan-codebase`, `scan-product`, `audit-architecture`, `product-analyzer`^, `scope-epic`^
- **Issue Refinement**: `normalize-issues`, `prioritize-issues`, `align-issues`, `format-issue`^ (template structure), `refine-issue` (codebase research), `reconcile-issue` (rewrite directive sections from own findings), `wire-issue`^ (integration wiring), `verify-issues`, `tradeoff-review-issues`, `ready-issue`, `issue-workflow`^, `issue-size-review`^, `map-dependencies`^, `audit-issue-conflicts`^, `link-epics`^ (`--mode assign|synthesize`)
- **Planning & Implementation**: `create-sprint`, `review-sprint`, `review-epic`^, `manage-issue`^, `iterate-plan`, `confidence-check`^, `go-no-go`^, `create-eval-from-issues`^, `spike`^
- **Code Quality**: `check-code`, `run-tests`, `audit-docs`^, `update-docs`^, `find-dead-code`
- **Git & Release**: `commit`, `open-pr`, `describe-pr`, `manage-release`, `sync-issues`, `cleanup-worktrees`
- **Automation & Loops**: `create-loop`^, `loop-suggester`, `review-loop`^, `simplify-loop`^, `debug-loop-run`^, `audit-loop-run`^, `rename-loop`^, `cleanup-loops`^, `workflow-automation-proposer`^, `verify-issue-loop`^ (`--mode criteria|adversarial`), `distill-traces`^
- **Meta-Analysis**: `audit-claude-config`^, `analyze-workflows`, `analyze-history`^, `improve-claude-md`^
- **Session & Config**: `init`^, `configure`^, `update`^, `help`, `handoff`, `resume`, `toggle-autoprompt`

## Development

```bash
# Tests
python -m pytest scripts/tests/

# Type checking
python -m mypy scripts/little_loops/

# Linting
ruff check scripts/

# Format
ruff format scripts/
```

### Testing & CI Policy

The authoritative gate is the local test suite — "Ensure CI passes" throughout
the docs means `python -m pytest scripts/tests/` exits 0:

```bash
python -m pytest scripts/tests/
```

A **self-hosted GitHub Actions runner on Thinky** (cost-free, see
`.github/workflows/ci.yml`) automates this on every push to `main`. It runs the
unit suite (`-m "not integration and not conformance"`); integration and
conformance tests stay local/manual for now. It is deliberately **not** triggered
on `pull_request`: the repo is public and a self-hosted runner executes untrusted
fork code, so PR runs would be a remote-code-execution surface on Thinky. If PR
coverage is added later, it must gate on approval / trusted branches.

On **every CI run** (success, failure, or cancellation), each job uploads
its pytest log + junit XML as a scoped artifact with 7-day retention.
The **unit-tests** job uploads `pytest.log` / `pytest-junit.xml` as
`pytest-unit-failures-*`; the **conformance** job uploads
`/tmp/conformance.log` / `pytest-conformance-junit.xml` as
`pytest-conformance-failures-*`. Both artifact names include
`run_id + run_attempt` so retries don't clobber. These are the paper
trail for every CI outcome — download from the Actions run page to
triage a failure *or verify a clean green finish*. (Originally landed
as `if: failure()` only; flipped to `if: always()` so the clean-finish
signal stays downloadable after the BUG-3208 wedge fix.)

Do not add **paid/hosted** CI. When an issue asks for a "CI-gated" check, satisfy
it **inside this suite**, not with a workflow file:

- Pure-Python gates are ordinary pytest tests / `ll-verify-*` CLIs invoked from a
  test.
- **Gates in another language/toolchain are wrapped as a pytest test that shells
  out** and asserts exit 0, so they run under the same `python -m pytest
  scripts/tests/` command. Skip gracefully when the external tool is absent so
  contributors without it aren't hard-blocked; the gate is still enforced
  wherever the tool exists. Example: the policy-builder JS conformance suite
  (`node --test scripts/tests/js/*.test.mjs`, Node ≥ 22) is enforced via
  `scripts/tests/test_policy_builder_node_gate.py` (FEAT-2390).

## Code Style

- Python 3.11+, type hints required
- PEP 8 with 100 char line limit
- Use dataclasses for data structures
- Docstrings for classes and public methods
- Conventional commits: `type(scope): description`
- **Minimize third-party dependencies**: Prefer stdlib or an existing dependency in `scripts/pyproject.toml` over adding a new one. If a new dependency is genuinely needed, justify it with a comment next to the pin (see the `anthropic` pin for the pattern) explaining why it's necessary and any bounds on its version.

## Development Preferences

- **Prefer Skills over Agents**: When adding new functionality, create a Skill instead of a new Agent. Skills are simpler, more composable, and can be invoked directly by users or other components. Reserve Agents for complex, autonomous multi-step tasks that require specialized capabilities.

## Loop Authoring

Loops that modify other harness artifacts (loop YAMLs, skills, agents,
commands, or `.claude/CLAUDE.md` itself) are **meta-loops** with three shape
rules: **(1) diagnosis-first** — `diagnose → propose → apply →
measure-externally`, not the generic pipeline (`create-loop` wizard's
"Optimize a harness" branch); **(2) non-LLM evaluator required** — every
`check_semantic`/`llm_structured` state pairs with a measurable external
signal; **(3) per-run artifact isolation** — write under
`${context.run_dir}/`, never bare `.loops/tmp/`.

`ll-loop validate` enforces these plus MR-1..MR-14. **Full rule table,
severities, and rationale:
[docs/guides/HARNESS_OPTIMIZATION_GUIDE.md § The Design Rules](../docs/guides/HARNESS_OPTIMIZATION_GUIDE.md#the-design-rules-mr-1mr-14).**

## Issue File Format

Files in `.issues/` follow: `P[0-5]-[TYPE]-[NNN]-description.md`
- Types: `BUG`, `FEAT`, `ENH`, `EPIC`
- Priorities: P0 (critical) to P5 (low)
- **Status values**: `open` (default), `in_progress`, `blocked`, `deferred`, `done`, `cancelled`. Do not use synonyms (`complete`, `completed`, `finished`, `wip`).
- **Supersession**: no `superseded` status value — mark `cancelled` and declare `supersedes: [ID, ...]` on the replacement; `ll-issues show` derives the reverse `Superseded by` row. Never hand-write `superseded_by`.
- **Deferral discriminator**: `deferred` is non-terminal for dependency edges (only `done`/`cancelled` resolve `blocked_by`/`depends_on`); automation `deferred_reason` codes are in [docs/reference/DEFERRAL_CODES.md](../docs/reference/DEFERRAL_CODES.md).

## Important Files

- `CONTRIBUTING.md` - Development setup and guidelines
- `docs/ARCHITECTURE.md` - System design
- `docs/reference/API.md` - Python module reference
- `docs/reference/CLI.md` - Full CLI tool reference (all `ll-*` entry points); `<cmd> --help` is authoritative over any prose
- `docs/development/TROUBLESHOOTING.md` - Common issues

## Host CLI Abstraction

All host CLI invocations (`claude`, `codex`, `opencode`, `pi`) must go
through `resolve_host()` in `scripts/little_loops/host_runner.py`. Never
add new `"claude"` literals to automation code — call
`resolve_host().build_streaming(...)` (or `build_blocking_json`,
`build_detached`, `build_version_check`) and use
`HostInvocation.binary` + `HostInvocation.args` instead. Set
`LL_HOST_CLI=<host>` (or `orchestration.host_cli` in `.ll/ll-config.json`)
to override host selection. See
[docs/reference/API.md#little_loopshost_runner](../docs/reference/API.md#little_loopshost_runner)
and
[docs/reference/HOST_COMPATIBILITY.md#orchestration-cli](../docs/reference/HOST_COMPATIBILITY.md#orchestration-cli).

## Automation: Scratch Pad

When running in automation contexts (ll-auto, ll-parallel, ll-sprint), use scratch pad files to keep large **command output** out of conversation context:

- **For test/lint runs and other large command output**, pipe to scratch and tail the summary: `Bash "mkdir -p .loops/tmp/scratch && python -m pytest ... > .loops/tmp/scratch/test-results.txt 2>&1; tail -20 .loops/tmp/scratch/test-results.txt"`. Bash output is uncapped, so this is the real source of context bloat. The `scratch-pad-redirect` hook does this automatically for allowlisted commands; `SessionEnd` `scratch-cleanup.sh` only prunes files this hook created (those with the `-<pid>` suffix), so user-typed scratch files like `test-results.txt` survive cleanup (BUG-2525).
- **To read a file**, use the `Read` tool — including large files. Read is self-capping (defaults to 2000 lines; use `offset`/`limit` to page). Do NOT `cat` a file to scratch as a substitute for reading it: that strips the content you need and leaves the file edit-locked because `Edit`/`Write` require a prior successful `Read` (BUG-2357).
- **Reference scratch paths** when reasoning about command output. Use `Read` on the scratch file when you need specific lines later.
- Small command output (< 200 lines) should still be inlined normally.
