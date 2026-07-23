<!-- Last updated: 2026-03-15 -->
# little-loops (ll) - Claude Code Plugin

Development workflow toolkit for Claude Code with issue management, code quality commands, and automated processing.

## Project Configuration

- **Plugin manifest**: `.claude-plugin/plugin.json`
- **Config schema**: `config-schema.json`
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
thoughts/       # Plans and research documents
docs/           # Architecture, API, troubleshooting
```

## Commands & Skills

Run `/ll:help` for full list. Both commands (`commands/*.md`) and skills (`skills/*/SKILL.md`) are invoked via `/ll:<name>`. Skills are marked with ^.

- **Issue Discovery**: `capture-issue`^, `scan-codebase`, `scan-product`, `audit-architecture`, `product-analyzer`^, `scope-epic`^, `create-epics-from-unparented`^
- **Issue Refinement**: `normalize-issues`, `prioritize-issues`, `align-issues`, `format-issue`^ (template structure), `refine-issue` (codebase research), `reconcile-issue` (rewrite directive sections from own findings), `wire-issue`^ (integration wiring), `verify-issues`, `tradeoff-review-issues`, `ready-issue`, `issue-workflow`^, `issue-size-review`^, `map-dependencies`^, `audit-issue-conflicts`^, `link-epics`^
- **Planning & Implementation**: `create-sprint`, `review-sprint`, `review-epic`^, `manage-issue`^, `iterate-plan`, `confidence-check`^, `go-no-go`^, `create-eval-from-issues`^, `spike`^
- **Code Quality**: `check-code`, `run-tests`, `audit-docs`^, `update-docs`^, `find-dead-code`
- **Git & Release**: `commit`, `open-pr`, `describe-pr`, `manage-release`, `sync-issues`, `cleanup-worktrees`
- **Automation & Loops**: `create-loop`^, `loop-suggester`, `review-loop`^, `simplify-loop`^, `debug-loop-run`^, `audit-loop-run`^, `rename-loop`^, `cleanup-loops`^, `workflow-automation-proposer`^, `verify-issue-loop`^, `adversarial-verify-loop`^, `distill-traces`^
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

**There is no hosted/paid CI in this project — do not add GitHub Actions (or any
paid CI runner).** The single enforced, cost-free gate is the local test suite:

```bash
python -m pytest scripts/tests/
```

This suite *is* our CI. "Ensure CI passes" / "will fail CI" throughout the docs
means this command must exit 0 — not that a hosted pipeline runs.

When an issue asks for a "CI-gated" check, satisfy it **inside this suite**, not
with a workflow file:

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

Loops that modify other harness artifacts (loop YAMLs, skill files, agent
definitions, commands, or `.claude/CLAUDE.md` itself) are **meta-loops** and
follow stricter design rules than data-operating loops. Three shape rules govern
them: **(1) diagnosis-first scaffolding** — follow a
`diagnose → propose → apply → measure-externally` shape, not the generic 5-phase
pipeline (use the `create-loop` wizard's "Optimize a harness" branch, never the
"Harness a skill" template); **(2) non-LLM evaluator required** — every
`check_semantic`/`llm_structured` state pairs with a measurable external signal
(LLM self-grades on harness edits are ~33–55% accurate, SHOR Table 1); **(3)
per-run artifact isolation** — write intermediate artifacts under
`${context.run_dir}/`, never bare `.loops/tmp/`.

`ll-loop validate` enforces the rules below. Each row: severity, what it catches,
and the top-level flag that suppresses it. **Full rationale, the optimizer error
taxonomy, and the canonical shape live in
[docs/guides/HARNESS_OPTIMIZATION_GUIDE.md](../docs/guides/HARNESS_OPTIMIZATION_GUIDE.md)**
(the source of truth this table summarizes).

| Rule | Sev | Catches | Suppress with |
|------|-----|---------|---------------|
| MR-1 | ERROR | `check_semantic`/`llm_structured` state with no non-LLM evaluator (`exit_code`, `output_numeric`, `convergence`, `diff_stall`, `score_stall`, `mcp_result`) in its routing chain | `meta_self_eval_ok` |
| MR-2 | WARN | baseline value captured but never referenced by a later evaluator (no measure→propose→apply→re-measure spine) | `meta_self_eval_ok` |
| MR-3 | WARN | intermediate artifacts written to bare `.loops/tmp/` instead of `${context.run_dir}/` (`.issues/`, `.loops/diagnostics/`, `thoughts/` exempt) | `shared_state_ok` |
| MR-4 | WARN | LLM-judged state sets `on_yes` but dead-ends on `no`/`partial` (no `on_no`/`on_partial`/`next`/full `route`) | `partial_route_ok` |
| MR-5 | WARN | harness loop writes iteration artifacts to a flat path (overwrites); needs per-iteration snapshots + `artifact_versioning: true` | `artifact_versioning_ok` |
| MR-6 | WARN | `shell` state writes to the same path as an LLM-generator state (hand-patching); fix the generator instead | `generator_fix_ok` |
| MR-7 | ERROR | unescaped `${ns.path:-default}` (bash `:-` syntax the engine can't parse); use `${ns.path:default=value}` or `$${VAR:-value}` | `bash_default_ok` |
| MR-8 | WARN | `check_semantic` `evaluate.prompt` omits evidence-contract keywords (`verbatim`, `quote`, `evidence`); default-`DEFAULT_LLM_PROMPT` states exempt | `evidence_contract_ok` |
| MR-9 | ERROR | `$$(` or `$$VAR` over-escapes bash — `$$` expands to the runner PID; use single `$` for subst/vars, `$$` only for `$${VAR}` braces | `shell_pid_ok` |
| MR-10 | WARN | inline Python `json.load*` catches parse errors and `exit(0)` with no `on_error:` route (swallows failures as empty success) | `parse_swallow_ok` |
| MR-11 | WARN | user-controlled `${context.input\|goal\|description\|task\|prompt\|query\|topic}` pasted raw into a `shell` body outside a safe position (single-quoted string, quoted heredoc, `:shell` suffix); shell metacharacters (`"`, `$`, `` ` ``, `\`, `!`) break bash tokenizing or inject commands | `unsafe_context_interpolation_ok` |
| policy-table | WARN | `context.policy_rules` predicate references a dimension never scored (`rubric_dimensions` / `rubric-dim-<name>.txt`) — silently inert | `policy_dims_scored_ok` |
| static `loop:` ref | ERROR | a state's static (non-`${...}`) `loop:` name resolves to no `.yaml`; blocks load. Use the full relative path (`loop: oracles/foo`) | — |
| haiku-gen | WARN | a state's `model:` names a haiku variant but the state is a generator (not an evaluator/verdict state) — no MR-1 non-LLM-evaluator backstop for the cheaper model's output | `haiku_generator_ok` |
| capture-reachability | WARN/ERROR | a `${captured.*}` reference whose capturing state doesn't dominate it (may run on a path that bypasses the capture), or references a never-captured var | `capture_reachability_ok` |

The `loop-specialist` agent (`agents/loop-specialist.md`) diagnoses violations
post-hoc as `self-evaluation bias` / `feature-stubbing`; these gates shift the
check left.

After MR-1 passes, validate discriminator health and budget before raising `max_steps`:
- `ll-loop diagnose-evaluators <loop>` — flags a paired-but-toothless evaluator
  whose verdict never varies (Bernoulli variance `p*(1-p)` < 0.05 across ≥10 runs).
- `ll-loop calibrate-budget <loop>` — extra iterations against a toothless
  evaluator earn nothing; fix the evaluator before spending more budget.
- `ll-loop run <loop> --baseline` — confirm the harness beats an unguided single
  call. See [docs/guides/AUTOMATIC_HARNESSING_GUIDE.md § Validating Your Harness](../docs/guides/AUTOMATIC_HARNESSING_GUIDE.md).

## Issue File Format

Files in `.issues/` follow: `P[0-5]-[TYPE]-[NNN]-description.md`
- Types: `BUG`, `FEAT`, `ENH`, `EPIC`
- Priorities: P0 (critical) to P5 (low)
- **Status values**: `open` (default), `in_progress`, `blocked`, `deferred`, `done`, `cancelled`. Do not use synonyms (`complete`, `completed`, `finished`, `wip`). `done` is the terminal-success value; the event-bus uses `"completed"` for the *event* payload, which is a different namespace. Synonyms are coerced to canonical values on read, but writing canonical values avoids ambiguity.
- **Deferral discriminator** (ENH-2664): a `deferred` transition via `ll-issues set-status <ID> deferred` stamps `deferred_by` (`human` default, or `automation`), `deferred_reason`, and `deferred_date`. `deferred_reason`/`deferred_date` are the same keys ENH-2535 introduced for closure-context display (`show.py`); under `deferred_by: automation` the value is a machine enum code, not free-text prose. Automation reason codes (`rn-implement.yaml`'s `mark_deferred` state): `blocked_by_unmet` (unmet `blocked_by` dep — recoverable), `remediation_stalled` (stalled remediation, decomposition declined — needs human attention). Set both via `--by`/`--reason` on `set-status`. **Unified not-ready policy** (ENH-2666): `autodev.yaml` uses the same `deferred` transition for its not-ready exits — `mark_gate_blocked` (`gate_blocked`), `record_decision_unresolved` (`decision_unresolved`), `recheck_after_size_review`'s low-readiness skip (`low_readiness`) — instead of leaving the issue `open` for retry. Visibility is provided by `ll-issues deferred-triage`, not by re-evaluating the issue every run. `decomposed` exits (child issues enqueued) are unaffected — those already close the parent via `finalize-decomposition` → `status: done`. **Ready-but-atomic remediation** (BUG-2734): when `issue-size-review --auto` scores an issue Very Large (8-11) but *deliberately declines to decompose it* (strictly sequential / shared-infra children) and readiness already passes, autodev no longer defers it as `low_readiness` — `check_guard2_verdict` routes it through a one-shot earn-the-pass remediation (`remediate_oversized_atomic` → re-run `/ll:confidence-check`) before falling back to an honest `oversized_atomic` deferral if outcome risk still fails. A per-issue `outcome_gate_waived: true` frontmatter flag (stamped manually or by `/ll:go-no-go`) bypasses the outcome half of the gate on the next pass.

## Important Files

- `CONTRIBUTING.md` - Development setup and guidelines
- `docs/ARCHITECTURE.md` - System design
- `docs/reference/API.md` - Python module reference
- `docs/development/TROUBLESHOOTING.md` - Common issues

## CLI Tools

The `scripts/` directory contains Python CLI tools:
- `ll-init` - Initialize little-loops for a project (headless core; `--yes`, `--dry-run`, `--plan`/`apply`, `--hosts` multi-select; always writes `loops.run_defaults` into generated config; detects existing install and version drift; `init/introspect.py` derives `project.src_dir`/`{test,lint,format,type}_cmd`/`scan.focus_dirs` from declared repo manifests instead of template literals, tagging each with `declared`/`inferred`/`default` provenance — existing config always wins on re-init, FEAT-2703)
- `ll-auto` - Process all backlog issues sequentially in priority order (`--skip-learning-gate` bypasses the per-issue learning-test gate)
- `ll-parallel` - Process issues concurrently using isolated git worktrees. Canonical parallel substrate (used by `ll-sprint` multi-issue waves); intentionally kept as Python with no FSM equivalent — the FSM engine has no concurrency primitive (see `docs/ARCHITECTURE.md` § Orchestration Layers)
- `ll-sprint` - Define and execute curated issue sets with dependency-aware ordering
- `ll-action` - Invoke any ll skill as a one-shot command with JSON-structured output
- `ll-artifact` - Generate self-contained human-facing HTML artifacts; `policy-builder` emits a `file://`-safe visual builder for policy-router / rubric loop YAML (stamps design-token CSS vars + grammar spec + skill catalog at generation time)
- `ll-harness` - One-shot runner evaluation (skill, cmd, mcp, prompt, dsl) with exit-code and semantic criteria
- `ll-loop` - Execute FSM-based automation loops (`promote-baseline` promotes latest run output as comparator baseline; `edit-routes` renders routing as an editable decision table; `queue list` lists pending run-queue entries and prunes dead-PID files as a side effect; `queue remove <id>` cancels a queued waiter — SIGTERMs its process (psutil identity-checked unless `--force`) and deletes its `.queue/<uuid>.json` entry)
- `ll-workflows` - Identify multi-step workflow patterns from user message history
- `ll-logs` - Discover, extract, sequence, and tail Claude Code session logs (`discover` / `extract` / `sequences` / `stats` / `tail` / `dead-skills` / `scan-failures` / `diff` / `eval-export` / `loop-fleet` subcommands; writes `logs/index.md`)
- `ll-messages` - Extract user messages from Claude Code logs
- `ll-session` - Query the unified SQLite session store (`search --fts` / `recent --kind` / `recent --issue <ID>` / `backfill [--host claude-code|codex|opencode|pi] [--max-sessions N] [--rebuild]` / `rebuild [--config PATH]` / `compact [--and-prune] [--config PATH]` / `export [--tables TYPE…] [--since DATE] [-o FILE]` / `path <session_id>` / `grep <pattern>` / `expand <id>` / `describe <id>` / `prune [--dry-run]` / `recompress [--batch N]` subcommands; default DB `.ll/history.db`. `backfill` ingests JSONL into `raw_events`, plus issues/loops/commits/Learning-Test-Registry direct-write mirrors (`learning_test_events`, ENH-2466) from on-disk sources in the same call — `rebuild` materializes the JSONL-derived cache tables from `raw_events`, `compact`/`prune` handle the retention lifecycle (ENH-2581). Session-lifecycle/handoff transitions (`handoff_needed`/`compaction`/`stale_ref_sweep`) are fire-time writes to `session_lifecycle_events`, queryable via `--kind session_lifecycle` (ENH-2495). `raw_events` payloads (`raw_line`/`parsed_json`) are stored zlib-compressed; `recompress` batch-converts legacy uncompressed rows and VACUUMs). The DB path resolves `LL_HISTORY_DB` env → `history.db_path` config → default `.ll/history.db` (ENH-2623)
- `ll-compact-session` - Manually trigger LCM session-memory compaction for one session (`ll-compact-session SESSION_ID [--db PATH] [--json]`), printing the resulting `CompactResult` (summary text, covered message count, token estimate). Distinct from `ll-session compact`'s retention sweep — this operates on the `summary_nodes` LCM axis, the same path the soft-threshold (7,500 token) background 6-section summarizer uses automatically (FEAT-2598)
- `ll-history-context` - Render a `## Historical Context` block for an issue from `.ll/history.db` (corrections + FTS5 matches, capped at 5 rows, stale-filtered). Use `--effort` to output per-issue effort context (session count, cycle time). Use `--for-skill NAME` to gate the call on `history.planning_skills` config (exits 0 with no output if NAME is not in the configured list)
- `ll-history` - View completed issue statistics, analysis, export topic-filtered excerpts from history, and list sessions per issue (`sessions <ID>`)
- `ll-deps` - Cross-issue dependency analysis and validation
- `ll-code` - Structural code queries (callers, callees, imports, impact) via a pluggable provider protocol; grep/AST fallback provider ships day-one, no index required (`status`/`callers-of`/`callees-of`/`importers-of`/`defines`/`references`/`impact-of`, `--provider`, `--json`)
- `ll-sync` - Sync local issues with GitHub Issues
- `ll-verify-docs` - Verify documented counts match actual file counts
- `ll-verify-package-data` - Lint `__file__` escapes that break non-editable installs + verify manifest assets are in-wheel (exit 1 on any violation)
- `ll-verify-design-tokens` - Structural lint for half-flipped design-token themes: a theme that inverts `surface`+`text` but leaves `border`/`action` at light-tuned `semantic.json` defaults (exit 1 on any violation; flags bundled `editorial-mono` pending its follow-on)
- `ll-verify-des-audit` - Walk the source tree and verify every event-emit site maps to a registered DES variant (exit 1 on uncovered event types — the F5 adoption gate, ENH-2475)
- `ll-verify-skill-budget` - Check skill description token footprint against listing budget (exit 1 if over)
- `ll-verify-skills` - Check that no SKILL.md exceeds 500 lines (exit 1 if any violations)
- `ll-verify-triggers` - Validate skill description trigger accuracy against should-fire/should-not-fire phrasings (exit 1 if below threshold or collisions)
- `ll-verify-decisions` - Validate the decisions log — both the legacy `.ll/decisions.yaml` flat file (via `load_decisions()`) and each `.ll/decisions.d/*.json` fragment (via a strict second-pass re-glob that bypasses the read path's silent skip) — failing on YAML/JSON parse errors, missing required fields, or unknown entry-type discriminators (exit 1 on any caught corruption; ENH-2589, gates the pre-commit hook ENH-2590, pytest CI gate ENH-2591, and Claude Code PreToolUse hook ENH-2592)
- `ll-verify-kinds` - Assert every `CREATE TABLE` in `session_store._MIGRATIONS` is registered in `_KIND_TABLE` or explicitly listed as kindless (exit 1 on any unregistered table; ENH-2581)
- `ll-check-links` - Check markdown documentation for broken links
- `ll-issues` - Issue management and visualization (next-id, list, show, path, sequence, impact-effort, refine-status, set-status, sections, anchor-sweep, fingerprint, format-check, epic-progress, epic-consistency, deferred-triage, decisions (list, add, outcome, generate, sync, suggest-rules, promote))
- `ll-learning-tests` - Query and manage the learning test registry (check/list/mark-stale/orphans; `prove <target>` triggers proving directly via `ready-to-implement-gate`); record creation is owned by `/ll:explore-api`
- `ll-gitignore` - Suggest and apply `.gitignore` patterns based on untracked files
- `ll-migrate` - One-time migration of completed/deferred issues to type-based directories (ENH-1390)
- `ll-migrate-relationships` - One-time migration that renames `parent_issue:` → `parent:` and `related:` → `relates_to:` across all issue files (ENH-1434)
- `ll-migrate-labels` - One-time migration that moves freeform `## Labels` body sections to `labels:` frontmatter across all issue files (ENH-1392)
- `ll-migrate-status` - One-time migration that normalizes non-canonical `status:` values (e.g. `completed` → `done`) across all issue files (ENH-1551)
- `ll-create-extension` - Scaffold a new extension repo with entry-point, skeleton handler, and LLTestBus example
- `ll-generate-schemas` - Regenerate JSON Schema files for all `LLEvent` types into `docs/reference/schemas/` (maintainer tool)
- `ll-generate-skill-descriptions` - Auto-generate ≤100-char skill descriptions via Claude CLI; skips `disable-model-invocation: true` skills (release utility)
- `ll-adapt` - Generate host-specific artefacts for a given host (e.g. `--host codex`); run `ll-adapt --host codex --apply` to regenerate skills, commands, and agent TOML files for Codex
- `ll-doctor` - Check host CLI capability support for little-loops features
- `ll-ctx-stats` - Show context-window analytics for the current project (per-tool byte vs. context savings from `.ll/history.db`; JSONL-based session cache hit rate; skill-health signals)
- `ll-config` - Resolve and print a single dot-path config value (`ll-config get <key>`, e.g. `ll-config get history.go_no_go.correction_penalty`); wraps `BRConfig.resolve_variable()` with a never-raise, config-or-default contract — the CLI a markdown skill shells out to instead of referencing `{{config...}}` template tokens directly (those only expand under `ll-auto`'s `skill_expander.py` pre-expansion pass)
- `ll-queue` - Persisted work-item queue backed by `.ll/queue.db` (`add`/`list`/`status`/`remove`/`run` subcommands; FEAT-2682, FEAT-2683). `add <target>` classifies a bare string into an FSM loop name, a skill/command name, or a raw CLI invocation (override with `--runner`); distinct from `ll-loop queue`'s PID-liveness marker mechanism, which FEAT-2684 preserves unchanged as a compat shim rather than migrating. `run` serially dequeues `pending` entries in priority/FIFO order and dispatches each through ENH-2668's `run_action()`, writing back real `status`/`result` (`SKILL`/`CMD`/`MCP`/`PROMPT` kinds only — `RunnerType.LOOP` stays on `PersistentExecutor`)

Install: `pip install -e "./scripts[dev]"`

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
