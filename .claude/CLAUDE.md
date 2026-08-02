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
| MR-12 | WARN/ERROR | automation-context `pruning_profile:` consistency (ENH-2714/ENH-2805), three checks under one flag: (1) ERROR — a state's own `tools:` allowlist excludes a `/ll:<skill>` it invokes; (2) WARN — a resolved profile sets `suppress_catalog: true` on a skill-invoking state (catalog removal may block host slash-command resolution); (3) WARN — a skill/command-invoking state has no resolvable `pruning_profile` at all (state override or loop default), paying the full static prefix on every call; `request_path: sdk`/`batch` no longer exempts a skill-invoking state (BUG-2831) — the executor force-downgrades those to `cli` at runtime (a bare tool-less sdk/batch call can't run a `/ll:` skill), so they genuinely reach `action_runner` and need pruning guidance | `pruning_profile_ok` |
| policy-table | WARN | `context.policy_rules` predicate references a dimension never scored (`rubric_dimensions` / `rubric-dim-<name>.txt`) — silently inert | `policy_dims_scored_ok` |
| static `loop:` ref | ERROR | a state's static (non-`${...}`) `loop:` name resolves to no `.yaml`; blocks load. Use the full relative path (`loop: oracles/foo`) | — |
| haiku-gen | WARN | a state's `model:` names a haiku variant but the state is a generator (not an evaluator/verdict state) — no MR-1 non-LLM-evaluator backstop for the cheaper model's output | `haiku_generator_ok` |
| capture-reachability | WARN/ERROR | a `${captured.*}` reference whose capturing state doesn't dominate it (may run on a path that bypasses the capture), or references a never-captured var; nested-path-aware (BUG-2812) — distinguishes the correct `${captured.<sub_loop_state_name>.<var>...}` form (child captures namespace under the delegating state's own name) from an ERROR-worthy reference to a sub-loop-delegating state's own `capture:` name plus a nested field beyond `.output`/`.exit_code` (that name only ever resolves to the child's event-stream dict) | `capture_reachability_ok` |
| session-mode-eval | WARN | a `check_semantic`/`llm_structured` (or default-LLM-judged) state resolves to `session_mode: continue` (state override or loop default), breaking independent evaluator judgment (FEAT-2711) | `session_mode_ok` |
| terminal-action-ok | WARN | a non-empty `action` on a `terminal: true` state — the executor finishes the run the instant a terminal is entered, before its `action` would run, so it's dead code; move it into a new penultimate non-terminal state with `next: <terminal>` and `on_error:` routing (the `rn-implement::report` shape). Exempts a terminal doubling as the loop's `on_max_steps`/`on_max_iterations` handler (BUG-158) (BUG-2813) | `terminal_action_ok` |
| MR-13 | WARN | abandonment must reach summary.json and downgrade the verdict: a loop with an abandonment mechanism (checkbox rewrite to `[!]`/`[x]`+"abandoned" annotation, or a `max_step_attempts`-style attempt cap) but no state emitting an `"abandoned"` key into its summary JSON; or a shell action hardcoding `"verdict":"success"`/`verdict=success` with no conditional branch on an abandonment/failure counter and no `"abandoned"` key in that state (ENH-2860) | `abandonment_verdict_ok` |
| MR-14 | WARN | a state's raw `evaluate:` mapping has a key outside `EvaluateConfig`'s dataclass fields — silently dropped by `EvaluateConfig.from_dict` with no diagnostic (root cause of BUG-2893/BUG-2894); suggests the nearest known field via `difflib.get_close_matches`. WARN-now/ERROR-later: the JSON schema's `additionalProperties: false` on `evaluateConfig` already takes the ERROR stance, but the Python loader stays WARN until built-in+user-loop telemetry shows the population is clean (ENH-2896) | `evaluate_unknown_keys_ok` |

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
- **Status values**: `open` (default), `in_progress`, `blocked`, `deferred`, `done`, `cancelled`. Do not use synonyms (`complete`, `completed`, `finished`, `wip`). `done` is the terminal-success value; the event-bus uses `"completed"` for the *event* payload, which is a different namespace. Synonyms are coerced to canonical values on read, but writing canonical values avoids ambiguity. **`deferred` is non-terminal for dependency purposes** (BUG-2897): only `done`/`cancelled` resolve a `blocked_by`/`depends_on` edge. A dependent of a `deferred` blocker must still be reported as blocked — `DependencyGraph` construction needs the non-terminal superset (`issue_parser.find_issues_for_graph()`), not `find_issues()`'s default work-selection filter, or the edge is silently dropped.
- **Supersession** (ENH-2829): there is no `superseded` status value. A superseded issue is marked `cancelled` (optionally with `cancelled_reason`); the replacement relationship is a graph edge — declare `supersedes: [ID, ...]` on the replacement issue, and `ll-issues show` derives the reverse `Superseded by` row on the superseded issue via `issue_parser.superseded_by()`. Do not hand-maintain a `superseded_by` frontmatter field — it is always derived, never written.
- **Deferral discriminator** (ENH-2664): a `deferred` transition via `ll-issues set-status <ID> deferred` stamps `deferred_by` (`human` default, or `automation`), `deferred_reason`, and `deferred_date`. `deferred_reason`/`deferred_date` are the same keys ENH-2535 introduced for closure-context display (`show.py`); under `deferred_by: automation` the value is a machine enum code, not free-text prose. Automation reason codes (`rn-implement.yaml`'s `mark_deferred` state): `blocked_by_unmet` (unmet `blocked_by` dep — recoverable), `remediation_stalled` (stalled remediation, decomposition declined — needs human attention). Set both via `--by`/`--reason` on `set-status`. **Unified not-ready policy** (ENH-2666): `autodev.yaml` uses the same `deferred` transition for its not-ready exits — `mark_gate_blocked` (`gate_blocked`), `record_decision_unresolved` (`decision_unresolved`), `recheck_after_size_review`'s low-readiness skip (`low_readiness`) — instead of leaving the issue `open` for retry. Visibility is provided by `ll-issues deferred-triage`, not by re-evaluating the issue every run. `decomposed` exits (child issues enqueued) are unaffected — those already close the parent via `finalize-decomposition` → `status: done`. **Ready-but-atomic remediation** (BUG-2734): when `issue-size-review --auto` scores an issue Very Large (8-11) but *deliberately declines to decompose it* (strictly sequential / shared-infra children) and readiness already passes, autodev no longer defers it as `low_readiness` — `check_guard2_verdict` routes it through a one-shot earn-the-pass remediation (`remediate_oversized_atomic` → re-run `/ll:confidence-check`) before falling back to an honest `oversized_atomic` deferral if outcome risk still fails. A per-issue `outcome_gate_waived: true` frontmatter flag (stamped manually or by `/ll:go-no-go`) bypasses the outcome half of the gate on the next pass. **Generalized reconcile plateau gate + stagnation backstop** (FEAT-2751): `check_reconcile_needed`'s plateau predicate (ENH-2689) was gated on `autodev-pre-spike-readiness.txt`, written only on the spike-armed branches, so a non-spike issue whose Readiness score never moved after refine/wire/size-review never reached the `/ll:reconcile-issue` remedy. `dequeue_next` now snapshots every dequeued issue's pre-refine confidence to `autodev-pre-readiness.txt`; `check_reconcile_needed` prefers the spike snapshot when present, else falls back to this one. `recheck_after_size_review` also gained a stagnation backstop: when ≥2 repair-class attempts ran this cycle (`autodev-repair-cycle-count.txt`, incremented by dedicated `count_repair_cycle_*` states after `refine_current`/`run_wire`/`run_size_review`/`run_spike`/`reconcile_current`) and Readiness is still no better than the dequeue-time snapshot, the deferral reason is `readiness_stagnated` instead of `low_readiness` — a distinct code meaning "every remedy including reconcile was attempted." **Pre-deferral remedy guarantee** (BUG-2803): a `low_readiness` deferral is never written for an issue that got no non-refine remedy attempt. Fresh issues (empty dequeue-time snapshot) below the readiness threshold are now reconcile-eligible in `check_reconcile_needed` (which backfills the snapshot so the stagnation discriminator can apply later), and `recheck_after_size_review` arms a one-shot remedy (spike when the issue body contains an unresolved measurement/proof-gate marker — e.g. "do not start otherwise", "measurement (gate)", "pre-implementation measurement" — else spike when `score_ambiguity` is the strictly weakest subscore, else reconcile; bounded by a per-issue run-dir fired marker) via `check_pre_deferral_remedy` → `dispatch_pre_deferral_remedy` before any `low_readiness` write. The measurement-gate check (ENH-2978) takes precedence over the ambiguity-subscore fallback since an unresolved empirical precondition is a proof-of-mechanism problem, not an ambiguity problem. Repeat failures after an attempted remedy defer as `readiness_stagnated`.

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
- `ll-loop` - Execute FSM-based automation loops (`promote-baseline` promotes latest run output as comparator baseline; `edit-routes` renders routing as an editable decision table; `queue list` lists pending run-queue entries and prunes dead-PID files as a side effect; `queue remove <id>` cancels a queued waiter — SIGTERMs its process (psutil identity-checked unless `--force`) and deletes its `.queue/<uuid>.json` entry; `audit <run>|--latest LOOP [--json]` computes deterministic run counters — event tallies, per-state stats, auxiliary-mutation scan, budget utilization — that `/ll:audit-loop-run` Steps 5.5/5.6 consume instead of hand-counting, ENH-2949; `scaffold-eval --issues ID[,ID...] [--dsl] [--out PATH|--stdout] [--json]` and `scaffold-verify <id> [--adversarial] [--out PATH|--stdout] [--json]` generate FSM eval-harness/verification loop YAML in Python instead of `/ll:create-eval-from-issues`/`/ll:verify-issue-loop` hand-assembling it in prose, validating via `fsm.validation.validate_fsm()` in-process, FEAT-2948)
- `ll-workflows` - Identify multi-step workflow patterns from user message history
- `ll-logs` - Discover, extract, sequence, and tail Claude Code session logs (`discover` / `extract` / `sequences` / `stats` / `tail` / `dead-skills` / `scan-failures` / `diff` / `eval-export` / `loop-fleet` subcommands; writes `logs/index.md`). `--project`/`--all` and the window flags (`--window-days`/`--since`/`--until`, `--since` mutually exclusive with `--window-days`, `--until` composes with either for a closed range) come from shared `cli_args.py` helpers (`add_corpus_target_args`/`add_window_args`) across `sequences`/`stats`/`scan-failures`/`dead-skills`/`loop-fleet`. `dead-skills --sort {tier,name}` defaults to tier-then-count (worst first); `loop-fleet --sort {success,name}` defaults to success-ascending (worst first); `scan-failures --limit N` caps top clusters by count and `loop-fleet --json --limit N` caps per-run rows (ENH-2925)
- `ll-messages` - Extract user messages from Claude Code logs
- `ll-session` - Query the unified SQLite session store (`search --fts` / `recent --kind` / `recent --issue <ID>` / `backfill [--host claude-code|codex|opencode|pi] [--max-sessions N] [--rebuild]` / `rebuild [--config PATH]` / `compact [--and-prune] [--config PATH]` / `export [--tables TYPE…] [--since DATE] [-o FILE]` / `path <session_id>` / `grep <pattern>` / `expand <id>` / `describe <id>` / `prune [--dry-run]` / `recompress [--batch N]` subcommands; default DB `.ll/history.db`. `backfill` ingests JSONL into `raw_events`, plus issues/loops/commits/Learning-Test-Registry direct-write mirrors (`learning_test_events`, ENH-2466) from on-disk sources in the same call — `rebuild` materializes the JSONL-derived cache tables from `raw_events`, `compact`/`prune` handle the retention lifecycle (ENH-2581). Session-lifecycle/handoff transitions (`handoff_needed`/`compaction`/`stale_ref_sweep`) are fire-time writes to `session_lifecycle_events`, queryable via `--kind session_lifecycle` (ENH-2495). `raw_events` payloads (`raw_line`/`parsed_json`) are stored zlib-compressed; `recompress` batch-converts legacy uncompressed rows and VACUUMs). The DB path resolves `LL_HISTORY_DB` env → `history.db_path` config → default `.ll/history.db` (ENH-2623)
- `ll-compact-session` - Manually trigger LCM session-memory compaction for one session (`ll-compact-session SESSION_ID [--db PATH] [--json]`), printing the resulting `CompactResult` (summary text, covered message count, token estimate). Distinct from `ll-session compact`'s retention sweep — this operates on the `summary_nodes` LCM axis, the same path the soft-threshold (7,500 token) background 6-section summarizer uses automatically (FEAT-2598)
- `ll-history-context` - Render a `## Historical Context` block for an issue from `.ll/history.db` (corrections + FTS5 matches, capped at 5 rows, stale-filtered). Use `--effort` to output per-issue effort context (session count, cycle time). Use `--for-skill NAME` to gate the call on `history.planning_skills` config (exits 0 with no output if NAME is not in the configured list)
- `ll-history` - View completed issue statistics, analysis, rework-rate signals, export topic-filtered excerpts from history, and list sessions per issue (`sessions <ID>`). `rework` subcommand reports reopen/follow-up/touch-back/revert rates and quality-adjusted throughput as a time series across (month, orchestrator) windows (FEAT-2867)
- `ll-help` - List every `/ll:` command and skill, grouped by area (`--json`/`--format {md,json}`/`--area AREA`/`-C DIRECTORY`)
- `ll-deps` - Cross-issue dependency analysis and validation
- `ll-code` - Structural code queries (callers, callees, imports, impact) via a pluggable provider protocol; grep/AST fallback provider ships day-one, no index required (`status`/`callers-of`/`callees-of`/`importers-of`/`defines`/`references`/`impact-of`, `--provider`, `--json`)
- `ll-sync` - Sync local issues with GitHub Issues
- `ll-verify-docs` - Verify documented counts match actual file counts
- `ll-verify-package-data` - Lint `__file__` escapes that break non-editable installs + verify manifest assets are in-wheel (exit 1 on any violation)
- `ll-verify-skill-prose` - Scan `skills/*/SKILL.md` + `commands/*.md` for prose reimplementations of algorithms that exist in `scripts/little_loops/`; curated marker table (Jaccard/word-overlap, stop-word list, session-JSONL scan, inline `python3 -c`, `git mv` glob loops, union-find/cluster-merge), `<!-- ll-prose-ok: reason -->` suppression comment (exit 1 on any unsuppressed finding, ENH-2951)
- `ll-verify-design-tokens` - Structural lint for half-flipped design-token themes: a theme that inverts `surface`+`text` but leaves `border`/`action` at light-tuned `semantic.json` defaults (exit 1 on any violation)
- `ll-verify-des-audit` - Walk the source tree and verify every event-emit site maps to a registered DES variant (exit 1 on uncovered event types — the F5 adoption gate, ENH-2475)
- `ll-verify-skill-budget` - Check skill description token footprint against listing budget (exit 1 if over)
- `ll-verify-skills` - Check that no SKILL.md exceeds 500 lines (exit 1 if any violations)
- `ll-verify-triggers` - Validate skill description trigger accuracy against should-fire/should-not-fire phrasings (exit 1 if below threshold or collisions)
- `ll-verify-decisions` - Validate the decisions log — both the legacy `.ll/decisions.yaml` flat file (via `load_decisions()`) and each `.ll/decisions.d/*.json` fragment (via a strict second-pass re-glob that bypasses the read path's silent skip) — failing on YAML/JSON parse errors, missing required fields, or unknown entry-type discriminators (exit 1 on any caught corruption; ENH-2589, gates the pre-commit hook ENH-2590, pytest CI gate ENH-2591, and Claude Code PreToolUse hook ENH-2592)
- `ll-verify-kinds` - Assert every `CREATE TABLE` in `session_store._MIGRATIONS` is registered in `_KIND_TABLE` or explicitly listed as kindless (exit 1 on any unregistered table; ENH-2581)
- `ll-verify-private-refs` - Scan for private-codebase references in files this public repo publishes (absolute home paths, `~/.claude/projects/` host-session paths, plus opt-in project-name regexes from the gitignored `.ll/private-refs.local.txt` — a *tracked* name list would publish what the check withholds). Two modes: `FILE...` gates changed files with all rules and no baseline (the forward-only pre-commit / PreToolUse gate), `--all` scans every tracked file with structural rules only against the tracked `.ll/private-refs-baseline.json` and fails on counts beyond it (`--update-baseline` re-records). Report excerpts are redacted, so findings never reproduce the path. Suppress with `ll-private-ok: <reason>` on the line or the one above. `gitleaks` does not cover this — the leak is paths and names, not credentials
- `ll-verify-cli-allowlist` - Assert `skills/configure/areas.md`'s "All ll- commands" preset and `writers._LL_PERMISSIONS` cover every `ll-` entry point in `scripts/pyproject.toml` (exit 1 on drift; BUG-2764)
- `ll-verify-cli-docs` - Assert this § CLI Tools section matches the real CLI surface, both directions: every documented subcommand/flag resolves against `--help` output, and every `pyproject.toml` entry point has a bullet here (exit 1 on documented-but-absent commands/flags; undocumented entry points are reported as a warning only, ENH-2970)
- `ll-verify-host-map` - Assert the adapter host-capability map agrees with `HOST_COMPATIBILITY.md`, `host_runner.HostCapabilities`, and the emitters' actual behavior (exit 1 on drift, ENH-2873)
- `ll-check-links` - Check markdown documentation for broken links (exit code gated on genuinely broken links only; unreachable/timeout links are reported but don't fail unless `--strict-network` is set, ENH-2836)
- `ll-issues` - Issue management and visualization (next-id, list, show, path, sequence, impact-effort, refine-status, set-status, link, sections, anchor-sweep, research-triage (`<ISSUE_ID> [--json]`; reports which of `/ll:refine-issue`'s three research axes — `locator`/`analyzer`/`pattern_finder` — the issue already covers, so Step 3 spawns only the unmet ones. An axis is covered when ≥80% of its qualified path refs resolve via `classify_file_ref()` (analyzer/pattern_finder additionally need a co-located backtick symbol) **and** no resolved path's `max(git commit time, mtime)` is newer than the issue's latest `/ll:refine-issue` Session Log entry. Exits 0 on any readable issue including all-unmet, ENH-2971), fingerprint, find-similar (alias `fs`; title word-overlap Jaccard scoring against the issue corpus, single-text or `--batch` pairwise, `--against open|all`, ENH-2941), format-check (`--all`/`--next`/`--format json`/`--fix`/`--apply`; `--next` targets the highest-priority active issue with no type filter, mutually exclusive with a positional `issue_id`/`--all`, exits 1 with a message on an empty backlog; gap classes missing/renamed/empty/boilerplate/malformed_id/prose_dep_drift/stale_prose_dep/program_design_nonspecific/deprecated_key/multi_frontmatter/testable/stale_file_ref — the `testable` class is a doc-only keyword inference, ENH-2946; `stale_file_ref` classifies file-path references in the body via `text_utils.classify_file_ref()`/`RefIndex` (basename-keyed `git ls-files` index built once per invocation) into resolved/stale/unresolvable_form/planned_new, reporting only the `stale` ones, ENH-2983), set-flags (`<issue_id> [--from-notes <file|->] [--dry-run] [--json]`; writes `decision_needed`/`missing_artifacts`/`implementation_order_risk`/`spike_needed` from the phrase-list + numeric-gate rules in `FLAG_RULES` (`cli/issues/set_flags.py`) — set-only, never clears a flag; `--from-notes` defaults to reading the issue's own `## Confidence Check Notes` section, ENH-2946), epic-progress, epic-consistency, deferred-triage, decisions (list, add, outcome, generate, sync, suggest-rules, promote), normalize (`[ISSUE_ID...]`/`--check`/`--auto`/`--strict`/`--json`; filename/ID mechanics — missing_id/malformed_filename/duplicate_id auto-fixed via `git mv` + frontmatter/edge sync, legacy_dir/type_mismatch report-only, ENH-2944), prioritize (`--all`/`--check`/`--apply <file|->`/`--json`; priority-rename mechanics — discovers unprioritized (or, with `--all`, every) active issue via a `^P[0-5]-` filename match against `config.issues.priorities`, and applies a `{issue_id: priority}` map via `git_mv_with_fallback()` (prepend if unprioritized, replace `P[X]-` otherwise; already-at-target is a no-op, not an error), ENH-2953))
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
- `ll-adapt-agents-for-codex` - Thin alias for `ll-adapt --host codex`: emit `.codex/agents/<name>.toml` files from `agents/*.md` for Codex subagent discovery (`--apply`/`--only NAME`/`--quiet`; dry-run by default)
- `ll-adapt-skills-for-codex` - Thin alias for `ll-adapt --host codex`: add Codex Skills API frontmatter to `SKILL.md` files and bridge `commands/*.md` into `skills/ll-<name>/` entries (`--apply`/`--quiet`; dry-run by default)
- `ll-doctor` - Check host CLI capability support and little-loops install surface (default checks: entry points, skills/commands discoverability, decisions store, history DB, loop validity; `--full` aggregates the `ll-verify-*`/`ll-check-links` family). Exit code is not tied solely to host capabilities — any default or `--full` check can independently fail exit 0 at error-tier severity, folded in via the check-registry protocol's error/warn severity split (FEAT-2793/FEAT-2795). `--trim` adds a context-residency report — per-section `CLAUDE.md` cost and per-entry catalog cost scored against `skill_events` usage over `--trim-window-days` (default 90), verdicted `trim` (0 uses in window) / `review` / `keep`. Advisory only: never affects the exit code, since an unused skill is a cost signal, not a broken install. Memory sections are never auto-verdicted `trim` — "would the model work this out unaided?" is not computable, so the CLI reports cost and defers
- `ll-ctx-stats` - Show context-window analytics for the current project (per-tool byte vs. context savings from `.ll/history.db`; JSONL-based session cache hit rate; skill-health signals)
- `ll-config` - Resolve and print a single dot-path config value (`ll-config get <key>`, e.g. `ll-config get history.go_no_go.correction_penalty`); wraps `BRConfig.resolve_variable()` with a never-raise, config-or-default contract — the CLI a markdown skill shells out to instead of referencing `{{config...}}` template tokens directly (those only expand under `ll-auto`'s `skill_expander.py` pre-expansion pass)
- `ll-queue` - Persisted work-item queue backed by `.ll/queue.db` (`add`/`list`/`status`/`remove`/`run`/`requeue` subcommands; FEAT-2682, FEAT-2683, FEAT-2906, FEAT-2930). `add <target>` classifies a bare string into an FSM loop name, a skill/command name, or a raw CLI invocation (override with `--runner`); `--input` carries loop input for a `LOOP`-runner target, same semantics as `ll-loop run <loop> [input]` (interpreted at dequeue time, not re-parsed at enqueue time). Distinct from `ll-loop queue`'s PID-liveness marker mechanism, which FEAT-2684 preserves unchanged as a compat shim rather than migrating. `run` serially dequeues `pending` entries in priority/FIFO order: `SKILL`/`CMD`/`MCP`/`PROMPT` kinds dispatch through ENH-2668's `run_action()`; `LOOP` entries are intercepted before `run_action()` (whose contract still refuses `RunnerType.LOOP`) and driven via a subprocess `ll-loop run` shell-out per entry — not `PersistentExecutor` in-process — writing back real `status`/`result` either way. `--timeout` defaults per-runner: unbounded for `--runner loop` (the FSM enforces its own budget), `120` for every other runner kind (BUG-2928). `list` renders each entry's `loop_input`/timeout/elapsed-time summary truncated to 40 chars; `--wide` shows it untruncated (ENH-2931). `run --watch` (FEAT-2930) turns the one-shot drainer into a long-lived one: after draining, it sleep-polls (`--poll-interval`, default 3s) for new entries instead of exiting; `--json` under `--watch` emits NDJSON (one object per processed entry, flushed immediately) rather than the one-shot's single array. Shutdown is two-stage: a first `SIGINT`/`SIGTERM` finishes the in-flight entry and exits 0 without claiming more work; a second forwards `SIGTERM` to an in-flight `LOOP` child's process group (`start_new_session=True`), marks that entry `failed` with `error: "interrupted by operator"`, and exits 0. `claim_entry` stamps `claimed_at`/`owner_pid`; a `--watch` drainer sweeps stranded `running` entries with a dead owner back to `pending` on startup and each idle poll (psutil identity-checked liveness, mirroring `ll-loop queue`'s FEAT-2684 pattern but parameterized for `ll-queue`'s own process markers). `ll-queue requeue <id> [--force]` is the manual escape hatch when the sweep can't decide (owner alive but wedged)

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
