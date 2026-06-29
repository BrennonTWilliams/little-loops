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
.ll/decisions.yaml # Decisions and rules log (opt-in; managed by `ll-issues decisions`)
thoughts/       # Plans and research documents
docs/           # Architecture, API, troubleshooting
```

## Commands & Skills

Run `/ll:help` for full list. Both commands (`commands/*.md`) and skills (`skills/*/SKILL.md`) are invoked via `/ll:<name>`. Skills are marked with ^.

- **Issue Discovery**: `capture-issue`^, `scan-codebase`, `scan-product`, `audit-architecture`, `product-analyzer`^, `scope-epic`^, `create-epics-from-unparented`^
- **Issue Refinement**: `normalize-issues`, `prioritize-issues`, `align-issues`, `format-issue`^ (template structure), `refine-issue` (codebase research), `wire-issue`^ (integration wiring), `verify-issues`, `tradeoff-review-issues`, `ready-issue`, `issue-workflow`^, `issue-size-review`^, `map-dependencies`^, `audit-issue-conflicts`^, `link-epics`^
- **Planning & Implementation**: `create-sprint`, `review-sprint`, `review-epic`^, `manage-issue`^, `iterate-plan`, `confidence-check`^, `go-no-go`^, `create-eval-from-issues`^
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

## Code Style

- Python 3.11+, type hints required
- PEP 8 with 100 char line limit
- Use dataclasses for data structures
- Docstrings for classes and public methods
- Conventional commits: `type(scope): description`

## Development Preferences

- **Prefer Skills over Agents**: When adding new functionality, create a Skill instead of a new Agent. Skills are simpler, more composable, and can be invoked directly by users or other components. Reserve Agents for complex, autonomous multi-step tasks that require specialized capabilities.

## Loop Authoring

Loops that modify other harness artifacts (loop YAMLs, skill files, agent
definitions, commands, or `.claude/CLAUDE.md` itself) are **meta-loops** and
follow stricter design rules than data-operating loops:

1. **Diagnosis-first scaffolding.** Meta-loops should follow a
   `diagnose → propose → apply → measure-externally` shape, not the generic
   harness 5-phase pipeline. The `create-loop` wizard's "Optimize a harness"
   branch generates this template; do not adapt the standard "Harness a skill"
   template for meta-loops.
2. **Non-LLM evaluator required.** Every `check_semantic` (`llm_structured`)
   state in a meta-loop MUST be paired with at least one non-LLM evaluator
   in the routing chain: `exit_code`, `output_numeric`, `convergence`,
   `diff_stall`, or `mcp_result`. LLM self-grades on harness updates are
   ~33–55% accurate (SHOR Table 1; Sonnet 4.6 = 33.4%) — pair with
   measurable external evidence or the loop will optimize for what the
   judge prompt rewards, not what users observe.
3. **Per-run artifact isolation.** Loops MUST write intermediate artifacts
   (queues, checkpoints, generated files) under `${context.run_dir}/`, not
   bare `.loops/tmp/`. The runner injects `run_dir` as
   `.loops/runs/<loop>-<timestamp>/` and creates the folder before
   execution. Writing to shared `.loops/tmp/` causes state corruption when
   two instances of the same loop run concurrently (e.g., under
   `ll-parallel`, retries that re-enter the loop, or a user re-running it
   in a worktree while another instance is mid-flight). Legitimate
   cross-instance artifacts (`.issues/`, `.loops/diagnostics/`,
   `thoughts/`) are exempt — only `.loops/tmp/` is flagged.

`ll-loop validate` enforces rule 2 as ERROR severity (rule MR-1). Use
`meta_self_eval_ok: true` at the loop top-level to suppress the check in
the rare case where you have a justified reason. See ENH-1665.

`ll-loop validate` enforces rule MR-2 as WARNING severity. A meta-loop that
captures a baseline value but never references it in a later evaluator lacks
the measure→propose→apply→re-measure spine — without that comparison the loop
cannot tell whether an edit helped or hurt. Use `meta_self_eval_ok: true` at
the loop top-level to suppress when baseline comparison is intentionally absent.

`ll-loop validate` enforces rule 3 as WARNING severity (rule MR-3). Use
`shared_state_ok: true` at the loop top-level to suppress the check when
cross-run sharing is intentional.

`ll-loop validate` enforces rule 4 as WARNING severity (rule MR-4). An
LLM-judged state (action_type: prompt/slash_command, or an explicit
check_semantic/llm_structured evaluator) that sets `on_yes` but omits
`on_no` or `on_partial` — with no `next:` or full `route:` table — silently
dead-ends when the judge returns `no` or `partial`. Use
`partial_route_ok: true` at the loop top-level to suppress the check when
dead-ending on a non-yes verdict is intentional. See ENH-1917.

`ll-loop validate` enforces rule 5 as WARNING severity (rule MR-5). A
harness-category loop that writes artifact files to a flat path in an
iterative generate→evaluate→generate cycle overwrites every iteration's
output — only the final version survives. Add per-iteration snapshots and
declare `artifact_versioning: true`, or set `artifact_versioning_ok: true`
to suppress when intentional overwrite is the desired behavior. See ENH-1957.

`ll-loop validate` enforces rule 6 as WARNING severity (rule MR-6). A
meta-loop where a `shell`-type state writes to the same file path as an
LLM-generator state (`prompt`/`slash_command` with `yaml_state_editor` or
`replace_action` markers) is flagged as the hand-patching anti-pattern.
Hand-patching creates fragile output that diverges from the generator on the
next run; the stable fix is to update the generator action so every subsequent
run produces correct output automatically. Set `generator_fix_ok: true` to
suppress for intentional post-processing cases. See ENH-2079.

`ll-loop validate` enforces rule 7 as ERROR severity (rule MR-7). Any FSM
action string containing an unescaped `${namespace.path:-default}` (bash
parameter-expansion default syntax) is flagged. The FSM interpolation engine
does not support this form and will crash at runtime with
`Path 'ns.path:-default' not found in context`. Use
`${namespace.path:default=value}` (engine-native) or `$${VAR:-value}`
(escaped, handled by the shell) instead. Set `bash_default_ok: true` to
suppress. See ENH-2348.

`ll-loop validate` enforces rule 8 as WARNING severity (rule MR-8). A
`check_semantic`/`llm_structured` state whose `evaluate.prompt` omits
evidence-contract keywords (`verbatim`, `quote`, `evidence`) may default to
optimism — LLM self-grades are 33–55% accurate without verbatim citation
requirements (SHOR Table 1). States with no `evaluate.prompt` (using
`DEFAULT_LLM_PROMPT`) are not flagged; the evidence contract is injected
automatically. Set `evidence_contract_ok: true` to suppress. See ENH-2342.

`ll-loop validate` enforces rule 9 as ERROR severity (rule MR-9). A shell
action containing `$$(` or `$$VAR` over-escapes bash. The FSM interpolator only
rewrites the brace form `$${...}` → `${...}`; bare `$(...)` command substitution
and `$VAR` references are passed to `bash -c` untouched. Doubling them is NOT an
escape — the leading `$$` expands to the runner's PID, so `echo "$$(pwd)/$$DIR"`
captures `<pid>(pwd)/<pid>DIR` instead of an absolute path, silently corrupting
every downstream `${captured…}` reference. Use single `$` (`$(pwd)`, `$DIR`) for
command substitution and variables; reserve `$$` exclusively for the `$${VAR}`
brace escape that collides with `${ns.path}` interpolation. Set `shell_pid_ok:
true` to suppress in the rare case where a literal PID is intended.

`ll-loop validate` enforces rule 10 as WARNING severity (rule MR-10). A shell
state whose inline Python calls `json.loads`/`json.load`, catches
`JSONDecodeError`/`ValueError`/bare `Exception`, and explicitly exits 0
(`sys.exit(0)` or `exit(0)`) — without an `on_error:` route — silently discards
parse failures: the FSM receives exit 0 and treats the state as successful,
producing zero results with no log, no stderr, and no non-zero exit code (as
observed in BUG-2383 across three loops). Add `on_error:` to the state to route
parse failures explicitly. Set `parse_swallow_ok: true` to suppress in the rare
case where treating a parse failure as an empty result is intentional and the
absence of an error route is deliberate.

The `loop-specialist` agent diagnoses violations post-hoc as
`self-evaluation bias` / `feature-stubbing` failure modes
(`agents/loop-specialist.md`); this section shifts the gate left.

Rationale for these rules, plus the optimizer error taxonomy and the canonical
`diagnose → propose → apply → measure-externally` shape, lives in
[docs/guides/HARNESS_OPTIMIZATION_GUIDE.md](../docs/guides/HARNESS_OPTIMIZATION_GUIDE.md).

Use `ll-loop diagnose-evaluators <loop>` to validate discriminator health after
MR-1 passes: a state can have a non-LLM evaluator paired correctly (MR-1
satisfied) but still be toothless if its verdict never varies across runs.
Bernoulli variance `p*(1-p)` below 0.05 across ≥10 runs flags an evaluator that
isn't measuring anything useful.

Use `ll-loop calibrate-budget <loop>` to decide whether increasing `max_steps`
will actually improve outcomes. Additional iterations amplify a sound strategy but
produce near-zero returns when the underlying evaluator is unhealthy. Example:

```
Evaluator: check_quality (llm_structured)
  Variance p*(1-p): 0.02   ⚠ WARN: below 0.05 threshold — fix evaluator before increasing max_steps
Evaluator: check_exit (exit_code)
  Variance p*(1-p): 0.23   ✓ OK
```

`check_quality` has `p*(1-p) = 0.02` — it nearly always returns the same verdict, so
the loop cannot learn from its signal regardless of how many iterations you allow.
`check_exit` has `p*(1-p) = 0.23` — it discriminates well; more iterations here earn
their token cost.  Fix toothless evaluators (broaden the judge prompt, tighten the
exit-code command) *before* raising `max_iterations`, or the extra budget is wasted.

Use `ll-loop run --baseline` to empirically validate that a meta-loop harness
improves output quality over an unguided LLM call. See
[docs/guides/AUTOMATIC_HARNESSING_GUIDE.md § Validating Your Harness](../docs/guides/AUTOMATIC_HARNESSING_GUIDE.md).

## Issue File Format

Files in `.issues/` follow: `P[0-5]-[TYPE]-[NNN]-description.md`
- Types: `BUG`, `FEAT`, `ENH`, `EPIC`
- Priorities: P0 (critical) to P5 (low)
- **Status values**: `open` (default), `in_progress`, `blocked`, `deferred`, `done`, `cancelled`. Do not use synonyms (`complete`, `completed`, `finished`, `wip`). `done` is the terminal-success value; the event-bus uses `"completed"` for the *event* payload, which is a different namespace. Synonyms are coerced to canonical values on read, but writing canonical values avoids ambiguity.

## Important Files

- `CONTRIBUTING.md` - Development setup and guidelines
- `docs/ARCHITECTURE.md` - System design
- `docs/reference/API.md` - Python module reference
- `docs/development/TROUBLESHOOTING.md` - Common issues

## CLI Tools

The `scripts/` directory contains Python CLI tools:
- `ll-init` - Initialize little-loops for a project (headless core; `--yes`, `--dry-run`, `--plan`/`apply`, `--hosts` multi-select; always writes `loops.run_defaults` into generated config; detects existing install and version drift)
- `ll-auto` - Process all backlog issues sequentially in priority order (`--skip-learning-gate` bypasses the per-issue learning-test gate)
- `ll-parallel` - Process issues concurrently using isolated git worktrees
- `ll-sprint` - Define and execute curated issue sets with dependency-aware ordering
- `ll-action` - Invoke any ll skill as a one-shot command with JSON-structured output
- `ll-harness` - One-shot runner evaluation (skill, cmd, mcp, prompt, dsl) with exit-code and semantic criteria
- `ll-loop` - Execute FSM-based automation loops (`promote-baseline` promotes latest run output as comparator baseline; `edit-routes` renders routing as an editable decision table)
- `ll-workflows` - Identify multi-step workflow patterns from user message history
- `ll-logs` - Discover, extract, sequence, and tail Claude Code session logs (`discover` / `extract` / `sequences` / `stats` / `tail` / `dead-skills` / `scan-failures` / `diff` / `eval-export` subcommands; writes `logs/index.md`)
- `ll-messages` - Extract user messages from Claude Code logs
- `ll-session` - Query the unified SQLite session store (`search --fts` / `recent --kind` / `recent --issue <ID>` / `backfill [--host claude-code|codex|opencode|pi] [--max-sessions N]` / `export [--tables TYPE…] [--since DATE] [-o FILE]` / `path <session_id>` / `grep <pattern>` / `expand <id>` / `describe <id>` / `prune [--dry-run]` subcommands; default DB `.ll/history.db`)
- `ll-history-context` - Render a `## Historical Context` block for an issue from `.ll/history.db` (corrections + FTS5 matches, capped at 5 rows, stale-filtered). Use `--effort` to output per-issue effort context (session count, cycle time). Use `--for-skill NAME` to gate the call on `history.planning_skills` config (exits 0 with no output if NAME is not in the configured list)
- `ll-history` - View completed issue statistics, analysis, export topic-filtered excerpts from history, and list sessions per issue (`sessions <ID>`)
- `ll-deps` - Cross-issue dependency analysis and validation
- `ll-sync` - Sync local issues with GitHub Issues
- `ll-verify-docs` - Verify documented counts match actual file counts
- `ll-verify-package-data` - Lint `__file__` escapes that break non-editable installs + verify manifest assets are in-wheel (exit 1 on any violation)
- `ll-verify-design-tokens` - Structural lint for half-flipped design-token themes: a theme that inverts `surface`+`text` but leaves `border`/`action` at light-tuned `semantic.json` defaults (exit 1 on any violation; flags bundled `editorial-mono` pending its follow-on)
- `ll-verify-skill-budget` - Check skill description token footprint against listing budget (exit 1 if over)
- `ll-verify-skills` - Check that no SKILL.md exceeds 500 lines (exit 1 if any violations)
- `ll-verify-triggers` - Validate skill description trigger accuracy against should-fire/should-not-fire phrasings (exit 1 if below threshold or collisions)
- `ll-check-links` - Check markdown documentation for broken links
- `ll-issues` - Issue management and visualization (next-id, list, show, path, sequence, impact-effort, refine-status, set-status, sections, anchor-sweep, fingerprint, epic-progress, epic-consistency, decisions (list, add, outcome, generate, sync, suggest-rules, promote))
- `ll-learning-tests` - Query and manage the learning test registry (check/list/mark-stale); record creation is owned by `/ll:explore-api`
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

- **For test/lint runs and other large command output**, pipe to scratch and tail the summary: `Bash "python -m pytest ... > .loops/tmp/scratch/test-results.txt 2>&1; tail -20 .loops/tmp/scratch/test-results.txt"`. Bash output is uncapped, so this is the real source of context bloat. The `scratch-pad-redirect` hook does this automatically for allowlisted commands.
- **To read a file**, use the `Read` tool — including large files. Read is self-capping (defaults to 2000 lines; use `offset`/`limit` to page). Do NOT `cat` a file to scratch as a substitute for reading it: that strips the content you need and leaves the file edit-locked because `Edit`/`Write` require a prior successful `Read` (BUG-2357).
- **Reference scratch paths** when reasoning about command output. Use `Read` on the scratch file when you need specific lines later.
- Small command output (< 200 lines) should still be inlined normally.
