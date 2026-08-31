# CLI Tools Reference

Complete reference for `ll-` command-line tools and related utilities (including `mcp-call`). Install from PyPI:

```bash
pip install little-loops
```

See [COMMANDS.md](COMMANDS.md) for `/ll:` slash commands and [README](../../README.md) for overview.

## Common Flags

These flags appear across multiple tools:

| Flag | Short | Behavior | Used by |
|------|-------|----------|---------|
| `--dry-run` | `-n` | Show what would happen without making changes | `ll-auto`, `ll-parallel`, `ll-sprint run`, `ll-deps fix`, `ll-sync` |
| `--resume` | `-r` | Resume from previous checkpoint | `ll-auto`, `ll-parallel`, `ll-sprint run` |
| `--max-issues` | `-m` | Limit number of issues to process (0 = unlimited) | `ll-auto`, `ll-parallel` |
| `--quiet` | `-q` | Suppress non-essential output | `ll-auto`, `ll-parallel`, `ll-sprint run`, `ll-sync` |
| `--only` | | Comma-separated issue IDs to process exclusively | `ll-auto`, `ll-parallel`, `ll-sprint run` |
| `--skip` | | Comma-separated issue IDs to exclude | `ll-auto`, `ll-parallel`, `ll-sprint` |
| `--type` | | Comma-separated issue types: `BUG`, `FEAT`, `ENH`, `EPIC` | `ll-auto`, `ll-parallel`, `ll-sprint` |
| `--config` | | Path to project root (default: current directory) | `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-sync` |
| `--timeout` | `-t` | Timeout in seconds per issue | `ll-parallel`, `ll-sprint run` |
| `--handoff-threshold` | | Override auto-handoff context threshold (1-100, default: from config) | `ll-auto`, `ll-parallel`, `ll-sprint run`, `ll-loop run`, `ll-loop resume` |
| `--context-limit` | | Override context window token estimate (default: from config or model-detected) | `ll-auto`, `ll-parallel`, `ll-sprint run`, `ll-loop run`, `ll-loop resume` |
| `--json` | `-j` | Output as JSON (structured, machine-readable) | Most `ll-*` CLIs — see individual tool sections |
| `--format` | `-f` | Output format: `text`, `json`, `markdown` | `ll-history`, `ll-deps`, `ll-verify-docs`, `ll-check-links`, `ll-issues epic-progress`, `ll-issues deferred-triage` |

---

## Project Setup

### ll-init

Initialize little-loops for a project. Detects the project root, selects host adapters, generates a `.ll/ll-config.json`, and optionally installs hook adapters for supported host CLIs. Which hosts accept `--hosts`, which get an adapter installed, and which are orchestration-only are defined by the canonical tier table in [HOST_COMPATIBILITY.md § Host tiers](HOST_COMPATIBILITY.md#host-tiers).

When run on a project that already has a `.ll/ll-config.json`, the interactive wizard pre-populates every field with the existing values so you can review and update without losing previous settings. The headless `--yes` path preserves existing feature toggles and project fields, applying only the overrides supplied via `--enable`/`--disable`.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--yes` | `-y` | Accept all defaults; run non-interactively. Merges existing config values when a config is present, printing a stderr drift warning (unconditional — applies whether or not `--upgrade` is also passed) when a `declared`-provenance introspected value diverges from the stored config; the stored value is always kept (ENH-2704). Loop run defaults: `clear: true`, `show_diagrams: "clean"`. |
| `--force` | `-f` | Reset to template defaults rather than pre-populating from existing config |
| `--dry-run` | `-n` | Preview actions without writing files |
| `--plan` | | Emit a JSON plan `{detected, proposed_config, requested_upgrade, host_options, warnings, provenance, ambiguities}` without writing anything. `provenance` is a list of `{field, value, provenance, evidence}` for each manifest-introspected `project.*`/`scan.focus_dirs` field (`declared`/`inferred`/`default`); `ambiguities` lists any field where multiple equally-valid candidates were found and the template default was kept (FEAT-2703). `requested_upgrade` echoes whether `--upgrade` was also passed — plan mode never executes it (no writes happen in plan mode), it's surfaced purely so the flag isn't silently dropped (BUG-2755). On a re-init (existing `.ll/ll-config.json`), a `declared`-provenance value that diverges from the stored config prints a `Warning: config has ... but ... declares ...` line to stderr — the existing value is always kept; stdout stays pure JSON (ENH-2704) |
| `--hosts HOST [HOST ...]` | | Host harnesses to install adapters for: `claude-code`, `codex`, `kimi-code`, `qwen` (adapter-wired); `opencode`, `pi`, `omp` (recognized, adapter pending — for `omp` this is an info-only branch, no writer). Defaults to auto-detected hosts. Unknown values produce a warning and are skipped — note `gemini` is orchestration-only and is **not** valid here. See [HOST_COMPATIBILITY.md § Host tiers](HOST_COMPATIBILITY.md#host-tiers). |
| `--enable FEATURE` | | Enable a feature in the headless config (repeatable). Requires `--yes`/`--dry-run`/`--plan`. Valid: `decisions`, `scratch_pad`, `session_capture`, `product`, `analytics`, `context_monitor`, `learning_tests`, `session_digest`, `prompt_optimization`. |
| `--disable FEATURE` | | Disable a feature in the headless config (repeatable). Same valid names as `--enable`. Use `--enable prompt_optimization` to opt in to the default-off prompt optimizer. |
| `--upgrade` | | Act on version drift automatically, then run a **host-parameterized surface refresh** for every active host: upgrade the pip package, force-regenerate adapter files (e.g. `.codex/hooks.json`, re-stamping the embedded gen-version), and scope-aware-update the claude-code plugin (auto for project-scoped installs, advise-only for user-scoped). Without this flag, headless mode only warns — including a hint when a generated adapter's gen-version stamp diverges from the installed package. Passing `--upgrade` alone (no `--yes`/`--dry-run`/`--plan`) implies `--yes` and runs headlessly, rather than silently dropping the flag and launching the interactive wizard (BUG-2755). |
| `--root ROOT` | `-C` | Project root directory (default: current directory) |

Richer features (`parallel`, `sync`, `documents`, `design_tokens`, `confidence_gate`, `tdd`) carry sub-config and remain interactive-only; they are not accepted by `--enable`/`--disable`. Unknown feature names exit `2`.

**Subcommands:**

| Subcommand | Description |
|------------|-------------|
| `apply --config PLAN` | Apply writes from a `--plan` JSON output. `--config` accepts a file path or raw JSON string. Produces the same artifacts as `--yes` (config, issue dirs, design tokens, issue templates, CLAUDE.md, host adapters, etc.). Accepts `--force` to overwrite existing configuration keys and overwrite existing host adapter files (e.g. `.codex/hooks.json`). |

**Exit codes:** `0` = success, `1` = error (template missing, stdin not a TTY, etc.), `2` = usage error

**Interactive TUI screens** (omitted when `--yes` is passed):

The detected project type is shown as a banner line (not a questionary prompt) before Screen 2 starts.

| Screen | Prompt | Notes |
|--------|--------|-------|
| 1 / 7  | Plugin Install | Shown only when install/upgrade is needed: missing package, outdated package/plugin, or stale Codex adapter. Reports what it checks and prompts `questionary.confirm("Proceed with wizard? (install/upgrade separately after)")` (default Yes); declining aborts with no changes. Skipped entirely when the install is already current |
| 2 / 7  | Project Basics | Project name, src dir, test/lint/format/type-check commands. Pre-filled from existing config when present, otherwise from project-type detection; command fields offer curated-menu select with "Custom…" fallthrough |
| 3 / 7  | Scan | `focus_dirs` text entry; confirm/override exclude patterns |
| 4 / 7  | Features | Opt-in checkboxes including `github_sync`, `confidence_gate`, `tdd`, `decisions` (rules log), `scratch_pad` (automation context masking), `session_capture` (PreCompact handoff); profile picker for `design_tokens`; worktree copy-files toggle; session-digest confirm; prompt-optimization opt-out confirm (default on); **loop defaults**: "Enable --clear by default?" (default Yes) and "Default diagram mode for ll-loop run?" (default `clean`) |
| 5 / 7  | Hosts | Defaults to detected hosts |
| 6 / 7  | Settings target | Third "Skip" option skips `merge_settings` entirely |
| 7 / 7  | CLAUDE.md update | Offers to create `.claude/CLAUDE.md` (or append to an existing one) with ll CLI command stubs; skipped if a `## little-loops` section is already present (ENH-2043, ENH-2092) |

**Examples:**
```bash
ll-init --yes                      # Non-interactive full init with defaults
ll-init --yes --dry-run            # Preview without writing files
ll-init --yes --force              # Overwrite existing configuration
ll-init --yes --upgrade            # Upgrade stale package/plugin automatically
ll-init --plan                     # Emit JSON plan without writing
ll-init --hosts claude-code codex  # Install adapters for specific hosts
ll-init --yes --enable decisions --enable session_capture  # Opt in to extra features
ll-init --yes --enable prompt_optimization                 # Opt in to prompt optimizer
ll-init apply --config plan.json   # Apply writes from a --plan output
```

<!-- TODO: update-docs stub — ENH-2434 — drafted 2026-07-02 -->

> **Defaults source** (ENH-2434): All `ll-init` defaults — TUI field values, `--enable`/`--disable` valid feature names, host detection heuristics, default project commands — are read from `config-schema.json` at the package root, which is also the validation schema for `.ll/ll-config.json`. Edit defaults there; they're not duplicated between the wizard and the schema. To audit a default, search `config-schema.json` for the field name; the matching `default` value is what `ll-init --yes` will produce.

<!-- END TODO stub -->

---

## Skill Invocation

### ll-action

Thin CLI wrapper for invoking ll skills as one-shot commands with JSON-structured output. Useful for dashboard integrations, shell scripts, and cron jobs that need a single skill result without running a full FSM loop.

**Subcommands:**

#### `invoke`

Invokes a skill and streams output as newline-delimited JSON (NDJSON) events by default.

| Flag | Description |
|------|-------------|
| `skill` | Skill name (e.g. `refine-issue`, `confidence-check`) |
| `--args ARG [ARG ...]` | Arguments to pass to the skill |
| `--timeout SECONDS` | Timeout in seconds (default: 300) |
| `--output FORMAT` | `stream-json` (default) or `json` |

**stream-json event shapes:**
```json
{"event":"action_start","ts":"...","skill":"refine-issue","args":["ENH-353"]}
{"event":"action_output","ts":"...","line":"Analyzing ENH-353..."}
{"event":"action_complete","ts":"...","exit_code":0,"duration_ms":45230}
```

**json output shape (`--output json`):**
```json
{"exit_code":0,"duration_ms":45230,"output":"...","error":null}
```

#### `capabilities`

Returns the full `CapabilityReport` for the configured host. Does not invoke Claude.

```json
{
  "host": "claude-code",
  "binary": "claude",
  "version": "1.0.3",
  "capabilities": [
    {"name": "streaming", "status": "full", "note": ""},
    {"name": "permission_skip", "status": "full", "note": ""},
    {"name": "agent_select", "status": "full", "note": ""},
    {"name": "tool_allowlist", "status": "full", "note": ""},
    {"name": "json_schema", "status": "full", "note": "..."},
    {"name": "structured_output", "status": "full", "note": "..."}
  ]
}
```

The payload has exactly four keys — `host`, `binary`, `version`, `capabilities`. A never-populated `hooks` key was removed by BUG-2760.

#### `list`

Returns all skills with names, descriptions, and argument hints from the plugin manifest. Does not invoke Claude.

```json
[
  {"name":"refine-issue","description":"...","args":"ISSUE_ID [--auto] [--dry-run]"},
  {"name":"old-skill","description":"...","args":null}
]
```

The `args` field is sourced from the `args:` frontmatter field in `skills/<name>/SKILL.md` (with `argument-hint:` as a fallback alias). It is `null` when neither field is present.

**Exit codes:** `0` = success, `1` = error, `124` = timeout

**Examples:**
```bash
ll-action invoke refine-issue --args P2-ENH-1229
ll-action invoke confidence-check --args FEAT-042 --timeout 120
ll-action invoke refine-issue --args P2-ENH-1229 --output json
ll-action invoke link-epics --args --auto      # Link all HIGH-confidence orphans to epics non-interactively
ll-action capabilities
ll-action list
```

### ll-advise

One-shot, signal-cited second-model consult (FEAT-3120). Resolves the configured advisor host **independently of** `orchestration.host_cli` / `LL_HOST_CLI`, issues one blocking call, and prints a structured verdict as JSON on stdout.

`--signal` is required — every consult records what prompted it (`user_requested` is a valid, explicit value); there is no unsignalled consult path. Before issuing the consult, the advisor/main model pairing is gated through the FEAT-3108 capability floor (`check_floor`): a same-host `violation` (advisor ranks below main) refuses the consult; a cross-host `advisory` or an unrankable `unknown` proceeds with a warning on stderr. A consult against an unwired host (`opencode`, `pi`) or an unauthenticated host fails soft — non-zero exit with a clear reason, never a traceback.

**Flags:**

| Flag | Description |
|------|-------------|
| `--signal` | Required. What prompted this consult (e.g. `score_stall`, `user_requested`). |
| `--question` | Required. The consult prompt. |
| `--context-file` | Path to a caller-authored context file appended to the prompt. Never an auto-slurp of the working tree. |
| `--main-host` | Host running the primary session, for the capability floor check. Default: the ambient resolved host. |
| `--main-model` | Model running the primary session, for the capability floor check. Default: `fsm.schema.DEFAULT_LLM_MODEL` (`"sonnet"`). |
| `--host` | Advisor host, overriding `advisor.host` in `.ll/ll-config.json`. |
| `--model` | Advisor model, overriding `advisor.model` in `.ll/ll-config.json`. |
| `--json` / `-j` | Print the verdict as JSON. |

`ll-advise` never calls `apply_host_cli_from_config()` — the ambient `LL_HOST_CLI` / `orchestration.host_cli` is unchanged after the call. `advisor.enabled: false` (the default) does not block an explicit `ll-advise` invocation, and neither does the `advisor.triggers` allowlist — an explicit `--signal` is not an auto-trigger. It routes through `consult_for_trigger(..., manual=True)` (FEAT-3116), so it **is** budget-counted against `advisor.max_consults_per_task` (default 3) — an explicit `ll-advise` can be refused once auto-consults have already spent the task's budget, since the budget is per task, not per path.

**Exit codes:** `0` = consult succeeded, `2` = refused or failed (unconfigured advisor, capability floor violation, unwired/unauthenticated host, transport failure, or `budget_exhausted`)

**Examples:**
```bash
ll-advise --signal user_requested --question "Is this design sound?"
ll-advise --signal score_stall --question "..." --context-file notes.md
ll-advise --signal user_requested --question "..." --host codex --model gpt-5.1 --json
```

### ll-harness

One-shot runner evaluation CLI that invokes a skill, shell command, MCP tool, or raw Claude prompt, captures its output, and exits `0` (PASS) / `1` (FAIL) / `2` (error/timeout) based on optional criteria.

**Runners:**

| Runner | Description |
|--------|-------------|
| `skill` | Invoke a little-loops skill via the active host CLI |
| `cmd` | Run a shell command and capture its output |
| `mcp` | Call an MCP tool via JSON-RPC |
| `prompt` | Send a raw prompt to Claude via the active host CLI |
| `dsl` | Run a DSL task set and report pass rates with Wilson CI |

**Shared evaluator flags:**

| Flag | Description |
|------|-------------|
| `--exit-code INT` | Expected exit code (FAIL if mismatch) |
| `--semantic TEXT` | Natural-language criterion evaluated against captured output via LLM |
| `--timeout SECONDS` | Runner timeout (default: 120) |
| `--output FORMAT` | `text` (default) or `json` |
| `--verbose` | Show full captured output even on PASS |

**mcp-specific flag:**
`--args JSON` — JSON arguments forwarded to the MCP tool (default: `{}`).

**prompt-specific flag:**
`--model MODEL` — Override the Claude model used for the prompt (e.g. `claude-haiku-4-5-20251001`). Omit to use the host session default.

**dsl-specific flag:**
`--model MODEL` — Override the Claude model for all task invocations. Run `ll-harness dsl` once per model to compare pass rates across models.

`dsl` grades each task against its own `expected:` mapping when the task declares one (a
structured `json`-fenced answer contract is appended to the prompt and compared key-by-key,
no extra LLM call); `--semantic` remains available as a fallback for tasks with no
`expected`, and as an additional gate when both are present (an `expected` mismatch outranks
a `--semantic` abstention — see `docs/guides/EVALUATION_GUIDE.md`). A task with neither is
**ungraded**: excluded from the pass-rate denominator and reported on its own line, not
counted as a pass (BUG-3196).

**Exit codes:** `0` = PASS, `1` = FAIL, `2` = internal error / timeout, `3` = ABSTAIN (no
failure, but the semantic judge could not evaluate the check).

**`--output json` payload fields (`skill`/`cmd`/`mcp`/`prompt` runners):** always present:
`runner`, `exit_code`, `exit_code_check`, `semantic`, `result`, `stdout`, `stderr`. Additive,
present only when applicable:

| Field | Present when |
|-------|--------------|
| `expected` | An `expected:` grade was evaluated (DSL tasks) |
| `prepatch_evidence` | `--issue-id` was given and a persisted pre-patch check bundle exists |
| `history_pass_rate`, `history_pass_rate_runs` | `.ll/history.db` has ≥3 non-abstained prior runs for this target in the last 30 days (ENH-3223) |
| `history_abstention_rate`, `history_judged_runs` | `.ll/history.db` has ≥3 prior `--semantic`-judged runs for this target in the last 30 days (ENH-3223) |
| `history_since` | Either history field above is present — the ISO 8601 window start |

The `history_*` fields are **target-scoped, not criterion-scoped**: they answer "how often is
this target abstained on / does this target pass", pooled across every `--semantic` string
ever run against it, not "how often does this specific criterion abstain" (`semantic_prompt`,
the column that would allow criterion attribution, is not written by any caller today). They
are read before this run's own `harness_events` row is written, so they never include the
current run, and they are omitted entirely (not zero/null) below the 3-run noise floor. Not
read for the DSL per-task path.

For `ll-harness dsl` specifically, exit `2` covers four distinct "the run could not produce
a measurement" triggers: the given path does not exist, the task directory has no `.yaml`
files, every task in the set is ungraded, or ≥1 task hit a per-task infra error (host
timeout or crash). Exit `1` also covers a run where some tasks were ungraded even if no
graded task failed. Exit `3` fires only when ≥1 task abstained and nothing failed or was
ungraded.

**Examples:**
```bash
ll-harness skill check-code
ll-harness cmd "echo hello" --exit-code 0
ll-harness mcp my-server:my-tool --args '{"key": "val"}' --semantic "tool returned results"
ll-harness prompt "What is 2+2?" --semantic "response contains a number"
ll-harness skill refine-issue P2-ENH-1229 --semantic "has implementation plan" --output json
ll-harness dsl evals/dsl/my-loop/
ll-harness dsl evals/dsl/my-loop/ --model claude-haiku-4-5-20251001
```

**Trace-assertion mode (`skill` runner only, FEAT-2878):**

Opt-in via `--trace-mode`. Instead of checking captured stdout, the skill runs against a scoped temporary workspace and assertions are made against the live ordered tool-call trace and the workspace's resulting file state. The default (flag unset) run is unaffected.

| Flag | Description |
|------|-------------|
| `--trace-mode` | Run against a scoped temporary workspace and assert on the tool-call trace instead of stdout |
| `--require-order TOOL,TOOL,...` | Comma-separated tool names that must appear in this relative order |
| `--require-artifact PATH` | Path (relative to the workspace) that must have been written; repeatable |
| `--forbid-path PATH` | Path (relative to the workspace) that must NOT have been written; repeatable |
| `--keep-workspace` | Do not delete the scoped temporary workspace after the run |
| `--hosts HOST,HOST,...` | Opt-in multi-host divergence: run against multiple hosts (default: the single resolved host). Hosts that are unconfigured or unavailable are skipped with a reported reason |

```bash
ll-harness skill refine-issue P2-ENH-1229 --trace-mode \
  --require-order "Read,Edit" \
  --require-artifact ".issues/enhancements/P2-ENH-1229-*.md" \
  --forbid-path ".git/index.lock"
ll-harness skill check-code --trace-mode --hosts claude-code,codex
```

---

## Diagnostics

### ll-doctor

Probes the active host CLI and reports which little-loops features are supported, and also validates little-loops' own install surface within the current project — this is no longer host-capability-only. Produces a `CapabilityReport` with one `CapabilityEntry` per capability (streaming, permission skip, agent selection, tool allowlist, structured output). When the binary is detected, also runs the host's version check (`build_version_check()`) and reports the real version string, degrading to `(unknown)` when the binary is absent, the probe fails, or it times out (ENH-2761).

Beyond the host-capability table, `ll-doctor` always runs 7 default install-surface checks (FEAT-2793/FEAT-2794): **Entry Points** (every `[project.scripts]` entry in `pyproject.toml` is importable/callable), **Skills & Commands** (discoverability count via the tool catalog), **Decisions Store** (`.ll/decisions.yaml` + `.ll/decisions.d/*.json` presence), **History DB** (`.ll/history.db` presence/readability), **FSM Loop Validity** (aggregated `fsm.validation` results over builtin + project-local loop YAMLs), **Schema Drift** (report-only: compares `.ll/history.db`'s live structure against what its own recorded `schema_version`'s migrations should produce, catching silent drift a version stamp alone can't reveal; never migrates the database itself) (ENH-3242), and **Advisor** (reports the configured advisor host's reachability and the capability-floor result against the main host; always a warning — even a floor `violation` — never affects the exit code, because an unconfigured or cross-host advisor is a deliberate configuration, not a broken install) (FEAT-3122).

**Flags:**
- `-j`, `--json` — emit the report as JSON instead of the human-readable table. The JSON payload is a superset of the `CapabilityReport` dataclass: alongside `host`/`binary`/`version`/`capabilities` it includes `analytics_capture` (`{skills, cli_commands, corrections, file_events, correction_patterns}`), `issues` (`{auto_commit, auto_commit_prefix}`), and the install-surface keys `entry_points` (list of `{name, status, note}`), `skills_commands` (`{status, note, total}`), `decisions_store` (`{status, note}`), `history_db` (`{status, note}`), `loop_validity` (`{status, note, total, invalid}`), `schema_drift` (`{status, note}`), and `advisor` (list of `{name, status, note, severity, floor_status}`, one row for `advisor_host` and one for `advisor_floor`; `floor_status` is the raw `FloorResult.status` on the floor row and `null` on the host row — unlike every other key here, `severity` is surfaced per-row rather than hardcoded by the check) — the same config/check state the text output prints under their respective sections (ENH-2762, FEAT-2793, ENH-3242, FEAT-3122).
- `--full` — additionally run the full `ll-verify-*` / `ll-check-links` checker family (FEAT-2795) under a "Full Verification (--full)" section: `docs`, `skill_budget`, `skills`, `skill_prose`, `triggers`, `decisions`, `package_data`, `kinds`, `host_map`, `design_tokens`, `des_audit`, `check_links` (does not wrap `ll-verify-cli-allowlist`). Adds a `full` key (dict keyed by verifier name → `{status, note, findings}`) to the `--json` payload when combined with `-j`/`--json`. `check_links` reports `severity: "error"` on genuinely broken links and `severity: "informational"` when the only failures are unreachable (network timeout/DNS) links (ENH-2836), so a flaky or offline network doesn't fail this check. `docs` and `check_links` additionally populate `findings` (a list of `{label, action_severity, route_owner}`, one entry per mismatched doc category or broken/unreachable link) surfacing each finding's `auto`/`mention`/`route` action-severity (ENH-2886/ENH-2887) — a distinct axis from `severity`, which only governs `ll-doctor`'s exit code. Every other `--full` verifier's `findings` is an empty list. The text-output rendering prints a `- <label>: <action_severity>` sub-line (with `-> <route_owner>` when routed) under any verifier with findings, without changing the one-line-per-verifier summary shape for verifiers that don't.

**Exit codes:** `0` = all error-tier checks passed, `1` = an error-tier check failed. `ll-doctor` folds the host-capability report and any registered install-surface checks (FEAT-2793's `CheckResult` registry) — including the `--full` verifier family when requested — into a single severity split: `unsupported` capabilities/checks are error-tier (fail the exit code, as before); informational checks — e.g. an absent-but-optional subsystem — never affect it regardless of status.

**Example output:**
```
Host:    claude-code
Binary:  claude  2.1.0

Capabilities
────────────────────────────────────────
  ✓  streaming
  ✓  permission_skip
  ✓  agent_select
  ○  tool_allowlist  (flag accepted but not validated)

Analytics Capture
────────────────────────────────────────
  ✓  skills:        ['*']
  ✓  cli_commands:  ['*']
  ✓  corrections:   enabled
  ✗  file_events:   disabled
```

**Examples:**
```bash
ll-doctor
ll-doctor --json
```

---

### ll-ctx-stats

Show context-window analytics for the current project (FEAT-1160). Reads per-tool byte metrics that the `post_tool_use` hook persists into `.ll/history.db` (FEAT-1623) and renders a compact summary of how much data was processed by tools vs. how much actually entered the conversation context. Also surfaces skill-health signals (per-skill invocation frequency and correction rate) from `ll-logs stats` (ENH-1921). Falls back to `.ll/ll-context-state.json` (token estimates) when the SQLite store is absent so first-time users still get useful output.

When `learning_tests.enabled` is `true`, the report also includes a **Learning Test Coverage** section (ENH-2218) showing total record count, breakdown by status (proven / stale / refuted), and the number of orphaned records (targets with no matching import in the project). Use this section to spot stale coverage before a release.

When `usage_events` rows join to a `loop_runs` row on `run_id` (ENH-2721's schema/writer, live since schema v29), the report also includes a **Waste** section (ENH-2722): per-loop token totals split into `tokens_wasted` — tokens spent on runs whose terminal outcome produced no accepted artifact — and a `waste_pct`. "Wasted" is terminal-status only: any infra/step-cap exit (`error`/`max_steps`/`max_iterations_reached`/`timeout`/`system_signal`/`interrupted`), or a normal FSM completion (`terminated_by == "terminal"`) whose `final_state` is anything other than `"done"`. Operator-initiated exits (`user_stopped`/`handoff`) are not counted as waste, and per-iteration `diff_stall`/`score_stall` discards are out of scope (a follow-on). `usage_events` rows with no matching `loop_runs` row (unbackfilled historical rows) are excluded rather than misattributed.

**Flags:**
- `--db PATH` — Use a non-default session database (default `.ll/history.db`; also resolves `LL_HISTORY_DB` / `history.db_path` config when omitted, ENH-2623).
- `--json` — Emit the report as JSON instead of the human-readable summary. The JSON payload includes a `skill_health` array (`[{skill, invocations, corrections, correction_rate}]`) when skill events are present, or `null` when not. When learning tests are enabled it also includes a `learning_tests` key with `{total, proven, stale, refuted, orphans}`. A `waste` key holds a list of `{loop_name, tokens_total, tokens_wasted, waste_pct, runs_total, runs_wasted}` (empty list when the DB exists with no joinable rows, `null` when the DB is absent). A `context_pressure` key holds `{samples, peak_pct, avg_pct, crossings}` aggregated across `context_pressure_events` (`crossings` maps level string → count; `null` when the DB is absent, ENH-2507).

When `context_pressure_events` has rows (schema v34+, written by `context-monitor.sh` on every sampled `PostToolUse`), the report also includes a **Context pressure curve** section: sample count, peak/average `used_pct` across all sessions, and a per-level crossing tally (ENH-2507).

**Exit codes:** `0` = report rendered (data present or fallback used), `1` = no data found in either the SQLite store or the fallback file.

**Examples:**
```bash
ll-ctx-stats
ll-ctx-stats --db custom/history.db
ll-ctx-stats --json
```

To enable per-tool byte tracking, set `"analytics": {"enabled": true}` in `.ll/ll-config.json`.

---

### ll-config

Resolve and print a single dot-path configuration value, wrapping `BRConfig.resolve_variable()`. This is the CLI a markdown skill shells out to when it needs a resolved config value — the `{{config.path.to.value}}` template token syntax only expands under `ll-auto`'s `skill_expander.py` pre-expansion pass, so interactive/slash-command skill runs never see it substituted.

**Usage:**
```bash
ll-config get <key>
```

**Flags:**
| Flag | Description |
|------|-------------|
| `KEY` | Dot-separated config path (e.g. `history.go_no_go.correction_penalty`) |

**Exit codes:** `0` always — mirrors `resolve_variable()`'s never-raise, config-or-default contract. Unknown keys print nothing (empty stdout), not an error.

**Examples:**
```bash
ll-config get history.go_no_go.correction_penalty   # -0.2
ll-config get project.src_dir                        # scripts/
```

---

## Issue Processing

### ll-auto

Process all backlog issues sequentially in priority order. On startup, `ll-auto` prints a header showing the active LLM model name (detected from the Claude CLI `stream-json` init event).

**Context handoff and stale-inflight re-queue:** When the agent's context window nears capacity, `ll-auto` emits a `CONTEXT_HANDOFF` signal and hands off to a fresh session. On resume (`--resume`), any issue that was in-flight at handoff time is re-queued at the front of the remaining work list so it is not silently dropped. (1693649e)

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--resume` | `-r` | Resume from previous checkpoint |
| `--dry-run` | `-n` | Show what would be processed without running |
| `--max-issues` | `-m` | Limit number of issues (0 = unlimited) |
| `--quiet` | `-q` | Suppress non-essential output |
| `--only` | | Process only these issue IDs (comma-separated) |
| `--skip` | | Skip these issue IDs (comma-separated) |
| `--type` | | Process only these types: `BUG`, `FEAT`, `ENH`, `EPIC` |
| `--config` | | Path to project root |
| `--category` | `-c` | Filter to category: `bugs`, `features`, `enhancements`, `epics` |
| `--priority` | `-p` | Comma-separated priority levels to process (e.g., `P1,P2`) |
| `--label` | | Comma-separated labels to process (e.g., `fsm,cli,quick-win`); matches issues with `labels:` frontmatter containing any of the specified values |
| `--verbose` | `-v` | Show full prompt text; default shows abbreviated 5-line preview |
| `--timeout` | `-t` | Timeout in seconds for the run; `0` disables it (pair with `--idle-timeout` to still bound hung workers); negative values are rejected |
| `--idle-timeout` | | Kill worker if no output for N seconds (0 to disable) |
| `--handoff-threshold` | | Override auto-handoff context threshold (1-100) |
| `--context-limit` | | Override context window token estimate |
| `--skip-learning-gate` | | Bypass the per-issue learning-test pre-flight gate (for emergency runs when `learning_tests.enabled` is true) |
| `--force-implement` | | Bypass the pre-Phase-1 confidence gate (BUG-3004) and append `--force-implement` to the `/ll:manage-issue` invocation |

**Pre-Phase-1 confidence gate (BUG-3004, classification fixed by BUG-3252):** when `commands.confidence_gate.enabled` is `true`, `ll-auto` checks each issue's `confidence_score` against `readiness_threshold` *before* running `/ll:ready-issue` — the same comparison `manage-issue` Phase 2.5 makes, mirrored so a sub-threshold issue never burns a full ready-issue pass just to halt at Phase 2. A gated issue was never attempted, so it is skipped and reported via the `skipped` channel, not `failed`, plus a `CONFIDENCE_GATE_BLOCKED <id>` stdout marker FSM loops can route on. An issue with no `confidence_score` in frontmatter at all reports reason `no_confidence_score (never assessed)`; a scored-but-sub-threshold issue reports `below_readiness_threshold (N < M)` — the two cases are distinguished rather than both reading as a measured `confidence 0`. The warning line also names the remediation: `/ll:confidence-check <id>`. The gate is suppressed under `--dry-run` and for categories configured with `action: verify` or `action: plan` (manage-issue itself skips Phase 2.5 for those actions). This inherits into `ll-sprint`'s two `process_issue_inplace()` call sites as well (routed to `skipped_blocked_issues` there), with no bypass flag of its own today. **Accepted behavior change:** a sub-threshold issue no longer reaches `/ll:ready-issue`'s CLOSE path, so stale/invalid sub-threshold issues need `/ll:confidence-check` or `--force-implement` to unstick rather than auto-closing.

**Examples:**
```bash
ll-auto                          # Process all issues in priority order
ll-auto --max-issues 5           # Process at most 5 issues
ll-auto --resume                 # Resume from previous state
ll-auto --dry-run                # Preview what would be processed
ll-auto --category bugs          # Only process bugs
ll-auto --only BUG-001,BUG-002   # Process only specific issues
ll-auto --skip BUG-003           # Skip a specific issue
ll-auto --type BUG               # Process only bugs
ll-auto --type BUG,ENH           # Process bugs and enhancements
ll-auto --priority P1,P2         # Only process P1 and P2 issues
ll-auto --label quick-win        # Only process issues tagged quick-win
ll-auto --handoff-threshold 90   # Trigger handoff at 90% context usage
```

**Signal handling (BUG-3312):** Ctrl+C sends SIGINT, which sets a module-level shutdown `Event` polled by the read loop that streams the detached `claude` subprocess's output; the process group is killed within ~1s rather than waiting for the subprocess to finish. Phase-boundary checks in the issue-processing loop and continuation runner stop an interrupted issue from falling through to its next phase (e.g., an interrupted Phase 2 does not proceed to Phase 3). A second Ctrl+C forces immediate exit without waiting for cleanup. An issue interrupted mid-run is attributed as `skipped`, not `failed`, and is un-marked from `attempted_issues` so `--resume` picks it back up.

---

### ll-parallel

Process issues concurrently using isolated git worktrees.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--workers` | `-w` | Number of parallel workers (default: from config or 2) |
| `--priority` | `-p` | Comma-separated priorities to process (e.g., `P1,P2`) |
| `--worktree-base` | | Base directory for git worktrees |
| `--cleanup` | `-c` | Clean up all worktrees and exit |
| `--prune-merged-branches` | | Delete local `feature/*` branches already merged into the base branch; use with `--dry-run` to preview. Squash/rebase-merged branches require the `gh` CLI for detection. |
| `--merge-pending` | | Attempt to merge pending work from interrupted runs |
| `--clean-start` | | Remove all worktrees and start fresh |
| `--ignore-pending` | | Report pending work but continue without merging |
| `--stream-output` | | Stream Claude CLI subprocess output to console |
| `--show-model` | | Verify and display model on worktree setup |
| `--feature-branches` | | Enable/disable feature-branch mode (`--feature-branches` / `--no-feature-branches`); overrides `parallel.use_feature_branches` in config for this run |
| `--epic-branches` | | Enable/disable per-EPIC integration-branch mode (`--epic-branches` / `--no-epic-branches`); overrides `parallel.epic_branches.enabled` in config for this run |
| `--overlap-detection` | | Enable pre-flight overlap detection to reduce merge conflicts |
| `--warn-only` | | With `--overlap-detection`, warn instead of serializing |
| `--dry-run` | `-n` | Show what would be processed |
| `--resume` | `-r` | Resume from previous checkpoint |
| `--timeout` | `-t` | Timeout in seconds per issue; `0` disables the per-issue timeout (pair with `--idle-timeout` to still bound hung workers); negative values are rejected |
| `--quiet` | `-q` | Suppress non-essential output |
| `--only` | | Process only these issue IDs |
| `--skip` | | Skip these issue IDs |
| `--type` | | Process only these types: `BUG`, `FEAT`, `ENH`, `EPIC` |
| `--label` | | Comma-separated labels to process (e.g., `fsm,quick-win`) |
| `--max-issues` | `-m` | Limit total issues processed |
| `--config` | | Path to project root |
| `--idle-timeout` | | Kill worker if no output for N seconds (0 to disable) |
| `--handoff-threshold` | | Override auto-handoff context threshold (1-100) |
| `--context-limit` | | Override context window token estimate |
| `--verbose` | `-v` | Enable verbose output |
| `--skip-learning-gate` | | Bypass per-worktree `proof-first-task` gate (emergency runs when `learning_tests.enabled` is true) |

**Per-worktree proof-first gate (ENH-2219):** When `learning_tests.enabled` is `true`, each worktree runs a `proof-first-task` gate before handing off to the implementation loop. The gate reads `learning_tests_required` from the issue file; when that field is absent (an unrefined issue), it resolves targets just-in-time by extracting external-API dependencies from the issue text (BUG-2320), so the firewall still fires on the `capture-issue → ll-parallel` path. A populated field is proven directly — forwarded as `targets_csv` so `proof-first-task` proves exactly the registered list rather than re-extracting an independent one (ENH-2405); a JIT-resolved list still goes through the `assumption-firewall` extraction/classification path. Either way, the gate verifies that every resolved API assumption has a proven (non-stale) record in the registry. If resolution yields no targets, the gate logs "no external dependencies detected" and proceeds (an auditable decision, not a silent skip). Issues that fail the gate are retried once after `/ll:explore-api` completes; if the retry also fails the issue is skipped and marked `blocked`. Use `--skip-learning-gate` for emergency runs when the registry is unavailable.

> **Config tip:** Branch naming and merge behavior are controlled by `parallel.use_feature_branches` in `ll-config.json`. When `true`, branches are named `feature/<id>-<slug>` and auto-merge is skipped, leaving PR-ready branches for review. Set `parallel.push_feature_branches: true` to also push branches to remote after success, and `parallel.open_pr_for_feature_branches: true` to open a draft PR via `gh` and record `pr_url:` on the issue. See [Configuration reference](CONFIGURATION.md#parallel) and the [Feature-Branch / PR-Based Workflow](../guides/SPRINT_GUIDE.md#feature-branch--pr-based-workflow) guide.

> **Config tip (epic branches):** Per-EPIC integration branches are controlled by `parallel.epic_branches.enabled` in `ll-config.json` (or `--epic-branches` for one run). When `true`, children of a single EPIC coalesce their work onto a shared `epic/<EPIC-ID>-<slug>` integration branch (`parallel.epic_branches.prefix`, default `epic/`) instead of per-worker branches. On the EPIC's last child, the integration branch merges back to `base_branch` when `parallel.epic_branches.merge_to_base_on_complete` is `true` (default), and opens a PR via `gh` when `parallel.epic_branches.open_pr` is `true`. Set `parallel.epic_branches.verify_before_merge: true` to run `test_cmd`/`lint_cmd` against the branch tip before that merge/PR-open — a failure blocks it and leaves the branch open for retry, surfaced in the run summary rather than silently logged. (On the `auto-refine-and-implement` FSM loop, this check is skipped as redundant when the loop's `verify` state already produced a fresh `passed` verdict for the same tip — ENH-2630.) See [Configuration reference](CONFIGURATION.md#parallel) and the [Per-EPIC integration branch](../guides/SPRINT_GUIDE.md#per-epic-integration-branch) guide.

**Examples:**
```bash
ll-parallel                         # Process with default workers
ll-parallel --workers 3             # Use 3 parallel workers
ll-parallel --dry-run               # Preview what would be processed
ll-parallel --priority P1,P2        # Only process P1 and P2 issues
ll-parallel --cleanup               # Clean up worktrees and exit
ll-parallel --stream-output         # Stream Claude output in real-time
ll-parallel --only BUG-001,BUG-002  # Process only specific issues
ll-parallel --type BUG,ENH          # Process bugs and enhancements
ll-parallel --overlap-detection     # Reduce merge conflicts
ll-parallel --handoff-threshold 85  # Override handoff threshold for this run
```

---

### ll-sprint

Define and execute curated issue sets with dependency-aware ordering.

**Subcommands:**

#### `ll-sprint create <name>`

Create a new sprint.

| Argument/Flag | Short | Description |
|---------------|-------|-------------|
| `name` | | Sprint name (used as filename) |
| `--issues` | | **Required.** Comma-separated issue IDs |
| `--description` | `-d` | Sprint description |
| `--max-workers` | `-w` | Max parallel workers (default: 2) |
| `--timeout` | `-t` | Timeout per issue in seconds (default: 3600) |
| `--skip` | | Issue IDs to exclude |
| `--type` | | Filter by type: `BUG`, `FEAT`, `ENH`, `EPIC` |

#### `ll-sprint run <sprint|EPIC-NNN>` / `ll-sprint r <sprint|EPIC-NNN>`

Execute a sprint or resolve an EPIC's active children as a sprint.

| Argument/Flag | Short | Description |
|---------------|-------|-------------|
| `sprint` | | Sprint name **or** EPIC ID (e.g. `EPIC-1234`) to resolve and execute |
| `--dry-run` | `-n` | Show plan without running |
| `--feature-branches` | | Enable/disable feature-branch mode (`--feature-branches` / `--no-feature-branches`); overrides `parallel.use_feature_branches` in config for this run |
| `--epic-branches` | | Enable/disable per-EPIC integration-branch mode (`--epic-branches` / `--no-epic-branches`); overrides `parallel.epic_branches.enabled` in config for this run |
| `--max-workers` | `-w` | Max parallel workers |
| `--timeout` | `-t` | Timeout per issue in seconds |
| `--config` | | Path to project root |
| `--resume` | `-r` | Resume interrupted sprint |
| `--quiet` | `-q` | Suppress non-essential output |
| `--only` | | Issue IDs to process exclusively during execution |
| `--skip` | | Issue IDs to skip during execution |
| `--skip-analysis` | | Skip dependency analysis |
| `--type` | | Filter by type |
| `--save` | | Write the resolved sprint YAML to `.ll/sprints/epic-NNN.yaml` before executing (useful for inspect/edit workflows) |
| `--handoff-threshold` | | Override auto-handoff context threshold (1-100) |
| `--context-limit` | | Override context window token estimate |
| `--skip-learning-gate` | | Bypass the pre-flight learning-test batch gate (see below) |

When an EPIC ID is passed, resolution is the union of the EPIC's `relates_to:` field (forward) and any issue with `parent: EPIC-NNN` (backward), deduplicated and filtered to active statuses (`open`, `in_progress`, `blocked`). Resume works using the normalized `epic-NNN` name stored in `.sprint-state.json`.

**Pre-flight learning-test gate (ENH-2210):** When `learning_tests.enabled` is `true`, `ll-sprint run` aggregates all `learning_tests_required` targets across every issue in the sprint before the first wave runs, checks each target via `ll-learning-tests check --stale-aware`, and blocks execution if any are missing or stale. This catches assumption gaps for the entire sprint in a single pre-flight pass rather than discovering them mid-wave. Use `--skip-learning-gate` to bypass when the registry is unavailable.

> **Milestone write-back**: When `ll-sprint run` starts, it writes `milestone: <sprint-name>` to the frontmatter of every issue in the sprint. This makes the sprint assignment visible on each issue file and enables `ll-issues list --milestone` filtering and `ll-sync` milestone assignment.

#### `ll-sprint list` / `ll-sprint l`

List all sprints.

| Flag | Short | Description |
|------|-------|-------------|
| `--verbose` | `-v` | Show detailed information |
| `--json` | `-j` | Output as JSON array |

#### `ll-sprint show <sprint|EPIC-NNN>` / `ll-sprint s <sprint|EPIC-NNN>`

Show sprint details, dependency graph, and health summary. Accepts either a sprint name or an EPIC ID — when passed an EPIC ID, `SprintManager.load_or_resolve()` resolves the EPIC's active children into a virtual sprint and renders them in dependency wave order.

| Argument/Flag | Short | Description |
|---------------|-------|-------------|
| `sprint` | | Sprint name or EPIC ID (e.g., `EPIC-1773`) |
| `--json` | `-j` | Output as JSON (includes all fields) |
| `--config` | | Path to project root |
| `--skip-analysis` | | Skip dependency analysis |

#### `ll-sprint edit <sprint>` / `ll-sprint e <sprint>`

Edit a sprint's issue list.

| Argument/Flag | Description |
|---------------|-------------|
| `sprint` | Sprint name |
| `--add` | Comma-separated issue IDs to add |
| `--remove` | Comma-separated issue IDs to remove |
| `--prune` | Remove invalid/completed issue references |
| `--revalidate` | Re-run dependency analysis after edits |
| `--config` | Path to project root |

#### `ll-sprint delete <sprint>` / `ll-sprint del <sprint>`

Delete a sprint definition.

#### `ll-sprint analyze <sprint>` / `ll-sprint a <sprint>`

Analyze sprint for file conflicts between issues.

| Argument/Flag | Short | Description |
|---------------|-------|-------------|
| `sprint` | | Sprint name |
| `--format` | `-f` | Output format: `text` (default), `json` |
| `--config` | | Path to project root |

**Examples:**
```bash
ll-sprint create sprint-1 --issues BUG-001,FEAT-010 --description "Q1 fixes"
ll-sprint run sprint-1
ll-sprint run sprint-1 --dry-run
ll-sprint list
ll-sprint list --json                         # JSON array of all sprints
ll-sprint show sprint-1
ll-sprint edit sprint-1 --add BUG-045,ENH-050
ll-sprint edit sprint-1 --remove BUG-001
ll-sprint edit sprint-1 --prune
ll-sprint delete sprint-1
ll-sprint analyze sprint-1 --format json
```

---

## Loop Automation

### ll-loop

Execute FSM-based automation loops. If the first argument is a loop name (not a subcommand), `run` is inferred automatically.

**Subcommands:**

#### `ll-loop run <loop>` / `ll-loop r <loop>`

Run a loop.

| Argument/Flag | Short | Description |
|---------------|-------|-------------|
| `loop` | | Loop name or path |
| `input` | | (Optional positional) If valid JSON object with keys matching defined context variables, unpacks into those keys; otherwise stored as a string in `context[input_key]` |
| `--max-steps` | `-n` | Override step cap (individual state transitions) |
| `--max-iterations` | | Override full-pass cap (complete loop cycles) |
| `--delay` | | Sleep N seconds between iterations (useful for recording and to relieve host memory pressure between subprocess spawns). Config-defaultable via `loops.run_defaults.delay` (ENH-2556); an explicit `--delay` always overrides the configured default. |
| `--no-llm` | | Disable LLM evaluation |
| `--no-host-guard` | | Disable the adaptive host memory-pressure guard (`host_guard:` block, ENH-2452). By default the guard samples host memory before each prompt-mode state and adds an extra cooldown / routes / aborts per the loop's `host_guard:` config. |
| `--host-guard-budget-mb N` | | Override `host_guard.max_cumulative_subproc_mb`: cap on summed peak subprocess RSS (MB) across the run (ENH-2453). `0` disables the budget. |
| `--model` | | Default model for host-CLI action states (`prompt`/`slash_command`). Per-state `model:` key overrides this. |
| `--effort` | | Default reasoning-effort level (`low`/`medium`/`high`/`xhigh`/`max`) for host-CLI action states. Per-state `effort:` key overrides this. When set, shown appended to the header's `model:` value, e.g. `model: claude-sonnet-4-6 [LOW]` (ENH-2869). |
| `--llm-model` | | Override model for FSM evaluator/judge states (distinct from `--model`) |
| `--dry-run` | | Show execution plan without running. Diagram rendering is not suppressed — combine with `--show-diagrams` to preview both the FSM diagram and the execution plan. |
| `--background` | `-b` | Run as background daemon |
| `--follow` | `-f` | Stream FSM state transitions to stdout as they fire, in `ll-loop history` format. **Cannot be combined with `--background`** — passing both exits with an error; use `ll-logs tail` to watch a background loop instead. |
| `--quiet` / `--qt` | | Suppress progress output |
| `--verbose` | `-v` | Stream all action output live; default shows a short response head preview |
| `--queue` | `-q` | Wait for conflicting loops to finish; writes a queue entry to `<loops_dir>/.queue/<uuid>.json` while waiting (see [Queue entries](#queue-entries-loopsqueue)) |
| `--queue-timeout` | | Override the `--queue` scope-conflict wait budget in seconds (default: `loops.queue_wait_timeout_seconds` from config, 86400) |
| `--show-diagrams[=MODE]` | | Display FSM diagram after each step. `MODE` is a topology (`layered`\|`neighborhood`\|`inline`\|`window`) or preset (`detailed`\|`summary`\|`clean`\|`local`\|`slim`\|`oneline`). Bare flag selects `summary` (layered, main-path scope). Override individual facets with `--diagram-edge-labels=on\|off`, `--diagram-state-detail=title\|full`, `--diagram-scope=main\|full`. **Breaking (ENH-1672):** `main`→`summary`, `full`→`detailed`, `mini`→`clean`; old values error with migration hints. Viewport auto-degrades `layered→window→neighborhood→inline` for preset/default sources (the `window` rung crops the real layered diagram to ±K layers around the active state with `▲ N layers above`/`▼ M layers below` banners — ENH-2410); explicit topology values disable degradation (`window` is also selectable explicitly). |
| `--clear` | | Clear terminal before each iteration (combine with `--show-diagrams` for live in-place rendering; suppressed when stdout is not a tty). When combined with `--show-diagrams` on a tty, the screen splits into a pinned FSM diagram on top and a scrolling action-output region below; on terminals too short for the full diagram the pinned pane falls back first to a **windowed** view (the real layered diagram cropped to ±K layers around the active state, with `▲ N layers above`/`▼ M layers below` overflow banners — ENH-2410), then to a 1-hop neighborhood view (predecessors → [active] → successors), then to a single-line `fsm: ... → [...] → ...` status. The pane redraws on SIGWINCH (terminal resize). When a parent loop spawns child loops, the pinned pane shows **only the deepest active child loop** rather than all nesting levels simultaneously — keeping the pane readable regardless of loop depth. |
| `--builtin` | | Load loop from built-ins directory (bypasses project `.loops/` lookup) |
| `--context KEY=VALUE` | | Override a context variable (repeatable) |
| `--program-md PATH` | | Load steering directive from a Markdown file (default: `.ll/program.md` when present); parsed fields injected into context before `--context` overrides. See [program-md reference](program-md.md). |
| `--worktree` | | Run loop in an isolated git worktree on a new branch named `TIMESTAMP-LOOP-NAME`. On exit, if the worktree is clean (no uncommitted changes, no commits ahead of base), the branch is deleted. If pending work is detected (uncommitted changes or commits ahead), the branch is **retained** and a warning is printed with the branch name for recovery (`git checkout BRANCH-NAME`). **Cannot be combined with `--background`** — passing both exits with an error. See [WORKTREES.md](WORKTREES.md) for what does and does not copy into the worktree. |
| `--baseline` | | Run a blind A/B comparison: executes primary skill with full evaluation gates (harness arm) and creates a matching ungated invocation (baseline arm) in parallel, then feeds both outputs into a blind LLM judge. Writes `ab.json` to the run directory and prints a terminal summary with pass-rate delta, Wilson 95% CI bounds `[lo, hi]` for each arm, and token/duration ratios. **Cannot be combined with `--worktree`** — passing both exits with an error. |
| `--baseline-skill` | | Override the baseline arm skill (default: extracted from the execute state action). Accepts a full slash command such as `/ll:some-skill`. |
| `--cross-host` | | Re-run the loop on a second available host CLI and append a cross-host comparison table to the baseline report. Requires `--baseline`. The comparison runs the execute state on the alternate host, then feeds both outputs into the same blind LLM judge. (ENH-2086) |
| `--items` | | Number of compare cycles to run (default: iterate with MIMO packing heuristics) |
| `--cost-output-json PATH` | | Also write the per-state cost report to `PATH` as machine-readable JSON (same shape as `CostReport.write_json` — see [Per-State Token/Cost Summary](#per-state-tokencost-summary-enh-1797)). The human-readable table is unaffected. Forwarded through `ll-loop run --background` re-exec so detached runs honor the flag (BUG-1414). |
| `--handoff-threshold` | | Override auto-handoff context threshold (1-100) |
| `--context-limit` | | Override context window token estimate |
| `--no-lock` | | Run without acquiring the scope lock, bypassing the conflict check. **Caution:** this allows concurrent runs that may interfere with each other on shared resources. Use when you need parallel runs that operate on disjoint paths or when testing a loop that would otherwise be blocked by a stale lock you cannot clear. |
| `--serve` | | Bind a loopback-only HTTP + SSE bridge (`LocalBridgeTransport`) for this run and serve a live dashboard page — Level 3 (host-owned) per [ARTIFACT_CONTROL_LEVELS.md](ARTIFACT_CONTROL_LEVELS.md) (ENH-3351). Prints a tokenized `http://127.0.0.1:<port>/<token>/` URL on start. The page's state badge, iteration counter, and log tail update live via `hx-sse` + morph swaps without losing scroll position, open `<details>`, or in-progress query-box text; a "Send" control POSTs an `artifact_interaction` event to `/{token}/interaction`, delivered to the executor's inbound channel unchanged (record-and-re-emit only — no FSM routing semantics in this issue). Server lifetime == run lifetime: it shuts down (with a final `run_complete` SSE frame) when the loop reaches a terminal state, `ll-loop stop`, or Ctrl-C; `ll-loop run`'s exit code is unaffected. Works even when `.ll/history.db` does not exist yet (renders with an empty snapshot rather than failing). Without `--serve`, `ll-loop run` and all of `ll-artifact` are byte-identical to before this flag existed. |
| `--port N` | | TCP port on `127.0.0.1` for `--serve` (default: `0` = ephemeral, printed on start). No effect without `--serve`. |

##### Exit Codes (ENH-2814)

| Code | Meaning |
|---|---|
| `0` | The loop reached a terminal state that is **not** marked `failure: true` (a success, including `interrupted` and `handoff`). |
| `1` | The loop never reached a terminal state: `max_steps`, `max_iterations_reached`, `timeout`, `cycle_detected`, `stall_detected`, `user_stopped`, `system_signal`, or an unrecognised termination reason. |
| `2` | The loop ran to completion and reported failure — it reached a terminal state declared `failure: true` (see [Failure Terminals](../generalized-fsm-loop.md#failure-terminals-must-include-a-diagnostic-action)). |

Codes `1` and `2` are deliberately distinct: `1` means the run was cut short by
an infra/limit condition, `2` means the loop itself decided it failed. Before
ENH-2814, *any* terminal state exited `0`, so a loop landing on `failed` was
indistinguishable from success to shell scripts, cron wrappers, and
`ll-queue run`.

**Behaviour change:** scripts that treated every `ll-loop run` exit as success
will now see `2` on failure runs. A terminal's `failure` flag defaults to true
for states named `failed`, `error`, `aborted`, or `finalize_aborted`; any other
failure-shaped terminal must declare `failure: true` to exit nonzero.

##### Model Header Display (ENH-1805)

`ll-loop run` and `ll-loop monitor` print a header line showing the active LLM model name on startup, detected from the Claude CLI `stream-json` init event (same mechanism as `ll-auto`). The model name appears in the first output line after the logo banner:

```
ll-loop run general-task "fix the lint warnings"
  model: claude-sonnet-4-6
  [state transitions follow]
```

When `--llm-model` is passed, the header reflects the override model. When the detection fails (e.g., non-Claude host), the field shows `unknown`.

When an effort level is set (state override, `--effort` run override, or loop-level `llm.effort` default), it's appended directly onto the `model:` value — bracketed, upper-cased, one space after the model name, no separate label (ENH-2869):

```
ll-loop run general-task "fix the lint warnings"
  model: claude-sonnet-4-6 [LOW]
  [state transitions follow]
```

When no effort level is set anywhere in that chain, the `model:` value is unchanged (bare).

##### Per-State Token/Cost Summary (ENH-1797)

After a loop run completes, `ll-loop run` prints a per-state token and cost summary table immediately before the final completion line. The table is produced whenever at least one LLM action (`prompt` or `slash_command`) executed during the run.

```
state                    invoc    input   output    cache     est_cost
────────────────────────────────────────────────────────────────────
execute                      3   12 400    2 100    8 500      $0.042
check_semantic               3    3 200      480    2 900      $0.011
────────────────────────────────────────────────────────────────────
TOTAL                        6   15 600    2 580   11 400      $0.053
```

**Columns:**

| Column | Description |
|--------|-------------|
| `state` | FSM state name |
| `invoc` | Number of times the state ran an LLM action |
| `input` | Total input tokens (prompt + cached) |
| `output` | Total output tokens |
| `cache` | Cache read tokens (`cache_read_tokens`) |
| `est_cost` | Estimated USD cost (using `pricing.py` MODEL_PRICING constants; shown as `~$X.XXX (model unknown)` when the model is not in the pricing table) |

Shell (`action_type: shell`) and MCP tool (`action_type: mcp_tool`) states are omitted from the table — they produce no token usage row in `usage.jsonl`.

The raw per-iteration data lives at `.loops/runs/<run-id>/usage.jsonl` (not archived to `.loops/.history/`). See [Output Artifacts](loops.md#output-artifacts) for the `usage.jsonl` schema.

##### Machine-Readable JSON Output (`--cost-output-json`, ENH-2477)

Pass `--cost-output-json PATH` to also write the same per-state aggregates as a stable JSON document (built by `CostReport.from_usage_jsonl().write_json()` at `fsm/cost_graph.py`). The shape is locked so downstream dashboards can parse without depending on the human-readable table layout:

```json
{
  "states": [
    {
      "state": "execute",
      "iterations": 3,
      "input_tokens": 12400,
      "output_tokens": 2100,
      "cache_read_tokens": 8500,
      "cache_creation_tokens": 0,
      "cost_usd": 0.0421,
      "wallclock_ms": 18500
    }
  ],
  "totals": {
    "iterations": 6,
    "input_tokens": 15600,
    "output_tokens": 2580,
    "cache_read_tokens": 11400,
    "cost_usd": 0.0533,
    "wallclock_ms": 24300
  }
}
```

State rows are sorted by name. Totals mirror the same metric keys. `cost_usd` is `0.0` for any state where at least one row used an unknown model (the `has_unknown_model` flag is surfaced only in the Python API, not the JSON). The flag is forwarded through `ll-loop run --background` re-exec so detached runs honor the same destination (BUG-1414 prevention).

> **Note:** `agent:`, `tools:`, `model:`, and `effort:` are per-state YAML fields, not CLI flags. See [Subprocess Agent and Tool Scoping](../guides/LOOPS_GUIDE.md#subprocess-agent-and-tool-scoping) in the Loops Guide for per-state agent, tool, model, and effort scoping options.

##### Failure Reason Display

When a loop exits a non-success terminal state, `ll-loop run` prints the failing state's output as a **Failure reason** block immediately before the completion line. This surfaces failure context that would otherwise be invisible: the alt-screen wipes on teardown, and non-verbose runs never echo per-state stdout inline.

```
Failure reason:
│ harness exit code 1: assertion failed on line 42
│ expected "done", got "failed"
```

The block is shown when the run was in alt-screen mode or in non-verbose (`--quiet`) mode. It is suppressed in `--verbose` mode, where the live renderer already echoed the output. Output is capped at 40 lines to bound scrollback.

##### Queue entries (`.loops/.queue/`)

When `ll-loop run --queue` encounters a scope conflict with a running loop, it creates `<loops_dir>/.queue/<uuid>.json` before entering the wait and removes it on lock acquisition, timeout, error, or process exit (via `atexit`). The file lets external observers (e.g. a dashboard) enumerate loops that are waiting on a scope lock without scanning process state.

**Ordering:** When multiple loops are waiting on the same lock, they acquire it in FIFO (arrival) order — the first loop to enqueue is the first to run after the current holder exits.

**Entry schema:**

```json
{
  "id": "<uuid>",
  "loopName": "<loop name>",
  "enqueuedAt": "<ISO 8601 UTC timestamp>",
  "context": {
    "waitingFor": "<name of conflicting running loop>",
    "scope": ["<scope path>", ...],
    "pid": <integer PID of the waiting process>
  }
}
```

Entries are short-lived and ephemeral — treat the directory as a live view, not a history log. Stale entries are possible if a process exits abnormally without running `atexit` handlers; `ll-loop queue list` (below) *is* that cleanup tooling — reading the queue prunes entries whose `pid` is no longer alive.

Distinct from [`ll-queue`](#ll-queue), which persists general-purpose, non-FSM `ActionSpec` work items to `.ll/queue.db` — the two queue surfaces are unrelated and do not overlap.

#### `ll-loop queue list`

List pending entries in the process-backed run queue (the `.loops/.queue/*.json` files documented under [Queue entries](#queue-entries-loopsqueue) above). This is the observability surface for loops waiting on a scope lock via `ll-loop run --queue`.

**Pruning side effect:** listing the queue calls `read_queue_entries()`, which **unlinks dead-PID entries** as a side effect — every rendered entry is `alive` by construction. Running `ll-loop queue list` is therefore also the sanctioned way to garbage-collect stale queue files left behind by a process that exited without running its `atexit` handlers.

Human-readable output prints a `Pending queue entries (N):` header followed by one line per entry, sorted ascending by enqueue time:

```
Pending queue entries (2):

  a1b2c3d4  my-loop  pid=12345  alive  2026-07-13 19:40:00
  e5f6a7b8  other-loop  pid=12346  alive  2026-07-13 19:41:12
```

Each line is `<short id (first 8 chars)>  <loopName>  pid=<pid>  alive  <YYYY-MM-DD HH:MM:SS>`. When the queue is empty, it prints `Queue is empty`.

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | `-j` | Emit the queue as a JSON array (one object per entry, using the [entry schema](#queue-entries-loopsqueue)); an empty queue emits `[]`. Exit code is `0` in all cases. |

#### `ll-loop queue remove <id>`

Cancel a queued waiter: signal its process (SIGTERM) and delete its `.loops/.queue/<uuid>.json` [entry](#queue-entries-loopsqueue). This is the way to abandon a loop that is blocked waiting on a scope lock via `ll-loop run --queue` — the counterpart to the read-only `ll-loop queue list`.

The `<id>` argument accepts either a full uuid **or** an 8+-character prefix (the short id shown by `ll-loop queue list`). Before signaling, `remove` runs a psutil identity check confirming the entry's `context.pid` is really a live `ll-loop` waiter; if the check fails, the entry file is still deleted but no signal is sent (pass `--force` to signal anyway). The entry file is **always** deleted whether or not the signal landed, because the waiter's `atexit` cleanup does not fire on SIGTERM. `remove` never touches the running lock-holder — that PID lives in a separate `.running/` namespace.

**Exit codes:** `0` on success (entry deleted); `1` when the `<id>` matches no entry **or** is an ambiguous prefix matching more than one entry.

| Flag | Short | Description |
|------|-------|-------------|
| `--force` | | Bypass the psutil identity check and signal the tracked pid unconditionally. |
| `--json` | `-j` | Emit the result as a JSON object: `{"id", "removed", "signaled", "identityVerified", "pid"}`. |

**Bare `ll-loop queue` (no subcommand):** invoking `ll-loop queue` without a subcommand prints the `queue` subparser help and exits with code `1`.

#### `ll-loop validate <loop>` / `ll-loop val <loop>`

Validate a loop definition file.

In addition to structural checks (reachability, evaluator fields, routing consistency), validation applies **meta-loop lint rules** when a loop is classified as a meta-loop (writes harness artifacts, imports `lib/benchmark.yaml`, or references `yaml_state_editor`/`replace_action`):

- **MR-1 (ERROR)**: A meta-loop must have at least one non-LLM evaluator (`exit_code`, `output_numeric`, `output_json`, `output_contains`, `convergence`, `diff_stall`, `score_stall`, `action_stall`, `harbor_scorer`, `mcp_result`). LLM self-grades on harness updates are unreliable (SHOR Table 1: 33–55% accuracy). Triggers a `ValueError` (exit code 1) that blocks the loop from running.
- **MR-2 (WARNING)**: A meta-loop should reference a captured baseline value in a later evaluator (`evaluate.previous`, `evaluate.target`, or `evaluate.source`). This ensures a measure→propose→apply→re-measure spine is present. Does not block validation.
- **MR-3 (WARNING)**: A loop writes intermediate artifacts to shared `.loops/tmp/` instead of the runner-injected `${context.run_dir}/`. Concurrent runs (e.g., under `ll-parallel`) will corrupt each other's state. Does not block validation. Suppressed by `shared_state_ok: true`.
- **MR-4 (WARNING)**: An LLM-judged state (action_type: `prompt`/`slash_command`, or an explicit `llm_structured`/`check_semantic` evaluator) maps `on_yes` but has no route for `no` or `partial` verdicts — with no `next:` or `route:` table with a default. The loop silently dead-ends when the judge returns `no`/`partial`; a parent loop reads this as failed. Does not block validation. Suppressed by `partial_route_ok: true`.
- **MR-5 (WARNING)**: A harness-category loop writes artifact files to a flat path in an iterative generate→evaluate→generate cycle without per-iteration versioning. Intermediate versions are lost; only the final output survives. Add per-iteration snapshots (see oracle `generator-evaluator` for the snapshot-state pattern) and declare `artifact_versioning: true`. Does not block validation. Suppressed by `artifact_versioning: true` (loop snapshots artifacts) or `artifact_versioning_ok: true` (intentional overwrite). (ENH-1957)
- **MR-6 (WARNING)**: A meta-loop has a `shell`-type state that writes to the same file path as an LLM-generator state (`prompt`/`slash_command` with `yaml_state_editor` or `replace_action` markers). Hand-patching creates fragile output that diverges from the generator on the next run; fix the generator action so every run produces correct output automatically. Does not block validation. Suppressed by `generator_fix_ok: true` for intentional post-processing. (ENH-2079)
- **MR-7 (ERROR)**: A FSM action string contains an unescaped `${namespace.path:-default}` (bash `:-` parameter-expansion default syntax). The FSM interpolation engine does not support this form and will crash at runtime with `Path 'ns.path:-default' not found in context`. Use `${ns.path:default=value}` (engine-native) or `$${VAR:-value}` (shell-escaped) instead. Blocks the loop from running. Suppressed by `bash_default_ok: true`. (ENH-2348)
- **MR-8 (WARNING)**: A `check_semantic`/`llm_structured` state whose `evaluate.prompt` does not contain evidence-contract keywords (`verbatim`, `quote`, `evidence`). Verdicts without verbatim citation requirements default to optimism (SHOR Table 1: 33–55% accuracy; Sonnet 4.6 = 33.4%). States with `evaluate.prompt: null` inherit `DEFAULT_LLM_PROMPT` which includes the contract automatically and are not flagged. Does not block validation. Suppressed by `evidence_contract_ok: true`. (ENH-2342)
- **MR-9 (ERROR)**: A shell action string contains `$$(` or `$$VAR` (over-escaped bash). The FSM interpolator only rewrites the brace form `$${...}` → `${...}`; bare `$(...)` and `$VAR` are passed to `bash -c` untouched. Doubling them causes the leading `$$` to expand to the runner's PID, silently corrupting every downstream `${captured.*}` reference (e.g. `echo "$$(pwd)"` captures `<pid>(pwd)` instead of a path). Use single `$` for command substitution and variables; reserve `$$` exclusively for the `$${VAR}` brace form that collides with `${ns.path}` interpolation. Blocks the loop from running. Suppressed by `shell_pid_ok: true`. (BUG-2368)
- **MR-10 (WARNING)**: A `shell`-type state whose inline Python calls `json.loads`/`json.load`, catches `JSONDecodeError`/`ValueError`/bare `Exception`, and explicitly exits 0 (`sys.exit(0)` or `exit(0)`) — without an `on_error:` route — silently discards parse failures. The FSM receives exit 0 and treats the state as successful, producing zero results with no log, no stderr, and no non-zero exit code. Add `on_error:` to the state to route parse failures explicitly. Does not block validation. Suppressed by `parse_swallow_ok: true` when treating a parse failure as an empty result is intentional. (BUG-2383)
- **MR-11 (WARNING)**: A `shell`-type state pastes an untrusted `${context.*}`/`${captured.*}`/`${prev.output|stderr}` value raw into the action body, outside a safe position — a bash token position (not single-quoted, no `:shell` suffix), or *inside a Python literal* embedded in the shell body (a quoted heredoc that is a Python body, or a `python3 -c "…"` body). ENH-3342 widened this from a fixed 7-key `context.*` allowlist: untrusted-ness now comes from `classify_site()` (`captured.*` always; `prev.output`/`prev.stderr` always; `context.*` minus `run_dir`/`promoted_artifact`/any `_`-prefixed key). `interpolate()` substitutes with a bare `str(value)` and no shell escaping; a value containing `"`, `$`, `` ` ``, `\`, or `!` breaks bash tokenizing (misrouting the loop to `on_error`/`on_no`) or, from an untrusted source, injects commands. A quoted heredoc or the `:shell` suffix are safe *only* at a bash token position — once the substituted text lands inside an embedded `python3` body, a quoted heredoc no longer protects it (bash did nothing there to begin with) and `:shell`'s shlex-quoted output breaks the Python parser instead of protecting it; that inversion is what the widening catches. Fix by wrapping the placeholder in single quotes / a quoted heredoc / `:shell` at a bash token position, or — inside a Python body — hoisting the value to an `LL_ARG_X=...` environment binding read via `os.environ`, or writing it to a file outside the body (see `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`'s MR-11 section for both idioms). Does not block validation. Suppressed loop-wide by `unsafe_context_interpolation_ok: true`, or per-site by a well-formed `# ll-lint: mr11-ok(<namespace>.<key>) <reason citing an issue>` marker (a malformed marker is an ERROR; a marker matching no finding is a stale-marker WARNING). (BUG-2622, ENH-3338, ENH-3342)

MR-1, MR-2, and the multimodal evaluator blind-spot rule are suppressed by setting `meta_self_eval_ok: true` at the loop top-level (with a justifying comment). MR-3 is suppressed by `shared_state_ok: true`. MR-4 is suppressed by `partial_route_ok: true`. MR-5 is suppressed by `artifact_versioning: true` or `artifact_versioning_ok: true`. MR-6 is suppressed by `generator_fix_ok: true`. MR-7 is suppressed by `bash_default_ok: true`. MR-8 is suppressed by `evidence_contract_ok: true`. MR-9 is suppressed by `shell_pid_ok: true`. MR-10 is suppressed by `parse_swallow_ok: true`. MR-11 is suppressed by `unsafe_context_interpolation_ok: true`. MR-14 is suppressed by `evaluate_unknown_keys_ok: true`.

- **Zero-retry counter pattern (WARNING)**: Detects states whose `retry` config sets `max_retries: 0` alongside a non-zero `retry_count` counter variable, or `retry_count` that is never incremented in any on-error transition. A zero-retry counter pattern means the state will never actually retry despite having retry infrastructure wired — this is almost always a configuration mistake. Does not block validation.
- **Multimodal evaluator blind-spot (WARNING)**: Detects harness-loop states that use an LLM multimodal prompt (screenshot/image) evaluated via `output_contains` as the sole gate routing directly to a terminal state. LLMs can silently fall back to text-only analysis when reading images, producing verdicts from incomplete information without the `output_contains` evaluator detecting the gap. Consider adding a shell-action verification state (e.g., functional smoke test) between scoring and the terminal. Does not block validation. Suppressed by `meta_self_eval_ok: true`.
- **Unresolvable static `loop:` references (ERROR)**: A state whose `loop:` key contains a non-interpolated (static) target name that cannot be resolved to a `.yaml` file at definition time will fail identically at runtime (`FileNotFoundError` in `resolve_loop_path`). Originally a WARNING (BUG-2305) on the theory that some references are intentionally optional, but this theory does not hold — dynamic names containing `${...}` are already skipped, so any remaining static name either resolves or fails. The validator now emits an ERROR and `ll-loop validate` exits 1, blocking the loop from loading via `load_and_validate`. Fix: correct the target name (sub-loops under `oracles/` require the full relative path, e.g. `loop: oracles/verify-confidence-scores`, not `loop: verify-confidence-scores`). (BUG-2400)
- **Capture reachability (WARNING/ERROR)**: Detects states that reference ``${captured.<var>.*}`` in their action or evaluator source where the capturing state may not execute on all code paths to the referencing state. Uses dominance analysis (reverse BFS) to check whether every path from ``initial`` to the referencing state passes through at least one of the capturing states. When a variable is produced by more than one state on mutually-exclusive branches (e.g. `fifo_pop` and `select_next` both capture `input`), the validator accepts the reference as safe if the set of capturing states collectively dominates the referencing state — every path must pass through at least one member of the set. Emits an **ERROR** when the referenced capture variable has no capturing state at all in the current FSM (likely a missing ``capture:`` declaration). Emits a **WARNING** when a bypassing path exists — the variable may be undefined at runtime if the bypass path is taken. **Sub-loop exception**: when the loop contains sub-loop states and the variable has no capturing state in the *parent* FSM, the validator emits a **WARNING** rather than an ERROR — the capture may legitimately live in a child namespace; the WARNING ensures typos still surface rather than going completely dark. **Nested-path awareness (BUG-2812)**: the rule is aware of two distinct sub-loop reference shapes. `${captured.<sub_loop_state_name>.<var>...}` — qualified by the delegating state's own NAME, e.g. `${captured.prove.targets.output}` — is the correct form, since `executor.py` merges a child loop's captures under the invoking state's name. Referencing a sub-loop-delegating state's own `capture:` name instead (e.g. `${captured.gate_result.extracted.output}` when `gate.capture: gate_result`) is an **ERROR**: that name resolves only to the child's event-stream dict `{output, exit_code}`, never to the child's captures, so any nested field beyond `.output`/`.exit_code` can never resolve at runtime. Suppressed entirely by `capture_reachability_ok: true` at the loop top-level for a reviewed, runtime-guarded bypass the dominance analysis can't model. Does not block validation for warnings; errors block validation. (ENH-1961, BUG-1997, ENH-1998, BUG-2812)
- **No-scope (WARNING)**: A loop declares no `scope:` at all (`fsm.scope == []`, the dataclass default). Without it, `ll-loop run` falls back to a repo-root lock (`resolve_scope(fsm.scope or ["."], fsm.context)`) that false-conflicts with every other narrowly-scoped loop running concurrently under `ll-parallel`. Fix by adding `scope: ["path/"]` naming the paths this loop writes to, or `scope: ["."]` as the explicit repo-wide opt-in — there is no other carve-out. Does not block validation. (BUG-3107)
- **Terminal-action-ok (WARNING)**: Detects a non-empty `action` on a `terminal: true` state. The executor returns `_finish("terminal")` the instant a terminal is entered, before that state's own `action:` would run — the action is dead code that never executes. Fix by moving the action to a new penultimate non-terminal state with `next: <terminal>` and an `on_error:` route, leaving the terminal bare (the `rn-implement::report` shape). Exempts a terminal doubling as the loop's `on_max_steps`/`on_max_iterations` handler (BUG-158), whose action does execute once via the BUG-158 fallthrough. Does not block validation. Suppressed by `terminal_action_ok: true`. (BUG-2813)
- **MR-13 (WARNING)**: Two compound sub-checks under one flag. (1) A loop has an abandonment mechanism — a shell action rewriting a checkbox line to the `[!]` marker, rewriting to `[x]` with an "abandoned" annotation, or consuming a `max_step_attempts`-style attempt-cap context var — but no state's action emits an `"abandoned"` key into a summary JSON printf/write, so abandoned work never reaches audit tooling. (2) A shell action hardcodes a literal `"verdict":"success"`/`verdict=success` with no conditional branch referencing an abandonment/failure counter and no `"abandoned"` key emitted in that same state, laundering abandoned work into a clean success verdict (the pre-ENH-2857 `general-task.yaml` defect: 8-of-34 abandoned steps reported as `success`). Does not block validation. Suppressed by `abandonment_verdict_ok: true`. (ENH-2860)
- **MR-14 (WARNING)**: A state's raw `evaluate:` mapping contains a key outside `EvaluateConfig`'s dataclass fields (derived from `dataclasses.fields(EvaluateConfig)`, so this can never hand-drift from the loader). `EvaluateConfig.from_dict` silently drops any unrecognized key with no exception or log line — a typo'd or aspirational evaluator field (e.g. `key` misspelled `kye`) is indistinguishable from a working one until a verdict is traced back to its source (the root cause of BUG-2893/BUG-2894). The rule suggests the nearest known field via `difflib.get_close_matches`. This is WARN-now/ERROR-later: `fsm-loop-schema.json`'s `evaluateConfig` already sets `additionalProperties: false` (an ERROR stance), but the Python loader stays WARN pending telemetry that the built-in and user-loop population is clean. Does not block validation. Suppressed by `evaluate_unknown_keys_ok: true`. (ENH-2896)
- **Tamper-guard value validity (WARNING)**: A loop-level or state-level `tamper_guard:` value outside `{"revert", "fail", "allow"}` — the dataclass layer accepts any string (like `session_mode`), so this rule catches a typo before it silently disables the guard at runtime (the executor treats an unrecognized value as no guard at all). Checks the loop-level default (once) plus each state's own override (not every state's inherited value, to avoid duplicating one bad loop-level default across the whole loop). Does not block validation. Suppressed by `tamper_guard_ok: true`. (ENH-2934)
- **Pre-patch-check value validity (WARNING)**: A loop-level or state-level `prepatch_check:` value outside `{"fail", "warn", "allow"}`, mirroring the tamper-guard rule above exactly (same loop-default-once-plus-state-overrides check, same never-guessing-an-unrecognized-value-means-no-guard executor treatment). Does not block validation. Suppressed by `prepatch_check_ok: true`. (ENH-2997)

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | `-j` | Output validation result as JSON. Both success and failure emit `{"valid": <bool>, "loop": "<name>", "violations": [{"severity": "error"\|"warning", "path": "<path>", "message": "<text>"}, ...]}` — there is no `warnings` key, and a load-time failure (e.g. bad YAML) is carried as a single `violations` entry with `severity: "error"` and `path: "<root>"` rather than a separate `error` key. Exit code is unchanged (1 for ERROR, 0 for clean/warnings-only). (ENH-2090) |

#### `ll-loop list` / `ll-loop l`

List available loops. Discovery is recursive: runnable loops nested under subdirectories of `loops/` (e.g. `oracles/oracle-capture-issue`) are included, while library fragments under `loops/lib/` are filtered out via `is_runnable_loop()`. Output is grouped by `category`, each category using its own header color via the `CATEGORY_COLOR` map. Each header carries an inline rollup badge (e.g. `2 built-in, 1 project`) and dimensions of the kind/label/description columns are computed once per render to fit `terminal_width(default=120)`. Categories with a dominant name-prefix cluster (≥3 members sharing the `apo-` prefix, etc.) get a bold subgroup subhead in the parent's category color, with leaves indented one level deeper. Visibility (`built-in` / `project` / `internal` / `example`) is a first-class column rather than a trailing marker; known label classes (`hitl`, `comparison`, `generated`, `meta`) get distinct ANSI colors. Output ends with a bold `TOTAL:` summary line that surfaces loop/category counts plus a dim hidden-tier hint when applicable. **All-caps section markers** (category headers, subgroup subheads, summary lines) use the `_all_caps` helper, while body content (name, kind, labels, description) stays mixed case. No body text is rendered with dim/faint ANSI; only the hidden-tier hint keeps dim. `CATEGORY_COLOR` no longer duplicates the FEAT green (`"32"`) across `code-quality` and `quality` — both pick distinct 256-color codes. (ENH-2539, refined in v2 polish)

For nested loops, the displayed identifier is the **relative path** without the `.yaml` suffix (e.g. `oracles/oracle-capture-issue`) — the same string `ll-loop run` and `ll-loop validate` accept. Top-level loops continue to display as their bare stem. Override suppression (a project loop hiding a built-in of the same name) keys on the full relative path, not the bare stem — so a project `oracles/foo.yaml` does **not** suppress a built-in top-level `foo.yaml`.

| Flag | Short | Description |
|------|-------|-------------|
| `--running` | | Only show loops currently executing (`running`/`starting` status allowlist — BUG-3232) |
| `--all-runs` | | Show every loop run with saved state, whatever status it ended in (`completed`, `failed`, `interrupted`, `user_stopped`, `awaiting_continuation`, etc. — this is what bare `--running` returned before BUG-3232) |
| `--status STATUS` | | Filter to loops with the given status (e.g. `interrupted`, `awaiting_continuation`); overrides the `--running` allowlist if both are given |
| `--builtin` | | Only show built-in loops (exclude project `.loops/`) |
| `--category <cat>` | `-c` | Filter to loops with the given category (e.g. `apo`, `issue-management`, `code-quality`) |
| `--label <tag>` | `-l` | Filter to loops that carry the given label tag; repeat for multiple tags (OR match) |
| `--all` / `-a` | `-a` | Show all loops including internal sub-loops and examples (hidden by default) |
| `--internal` | | Show only internal (delegated-only) sub-loops |
| `--examples` | | Show only example/template loops |
| `--visibility {public,internal,example,all}` | | Filter loops by visibility tier: `public` (routable, default view), `internal`, `example`, or `all`. Composes with `--label` and `--json`. |
| `--json` / `-j` | | Output as JSON array. Without `--running`: each entry includes `name` (relative-path identifier — e.g. `oracles/oracle-capture-issue` for nested loops, `fix-quality-and-tests` for top-level), `path`, `category`, `labels`, `visibility` (`"public"` \| `"internal"` \| `"example"`), `description`, and `built_in`. With `--running`: each entry is a `LoopState` object (`loop_name`, `status`, `current_state`, `iteration`, `updated_at`, etc.); `instance_id` is **absent** from this output — use `ll-loop status <loop> --json` to resolve per-instance details |

#### `ll-loop status <loop>` / `ll-loop st <loop>`

Show current status of a loop. Aggregates across all running instances of `<loop>`.

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | `-j` | Output loop state as JSON. Returns a single object when one instance is running; returns a JSON array of objects (each including `instance_id`, `pid`, `pid_source`, `log_file`, `events_file`) when two or more instances are running. The `pid` field is populated from the `.pid` file if present, otherwise falls back to the `.lock` file. The `pid_source` field is `"pid_file"`, `"lock_file"`, or `null`. `log_file` is a path for both foreground and background runs; `null` only for background-spawned child processes (`--foreground-internal`) or pre-ENH-1703 state files. `events_file` points to the `<instance-id>.events.jsonl` file, which exists for all run modes |

The human-readable `Log:` line uses one of three labels:
- `Log: <path>` — background run with its `.log` file present (normal case)
- `Log: (foreground run — output went to terminal)` — legacy fallback only (pre-ENH-1703 instances or `instance_id=None` runs); foreground runs after ENH-1703 always produce a `.log` file and display `Log: <path>` instead
- `Log: (expected <path>, missing)` — `.pid` file exists but `.log` was deleted (something went wrong)

An `Events:` line follows whenever an `<instance-id>.events.jsonl` file is found, showing the event count and age of the most recent event regardless of run mode.

> **Note**: `ll-loop status` is not a pure read — it may transparently rewrite orphaned state files. If a state file claims `status: running` but its PID (resolved via `.pid` → `.lock` → embedded `state.pid`) is provably dead, the file is updated in-place to `status: interrupted` with a `reconciled_at` timestamp. This is a no-op for live processes and is idempotent. When no PID is resolvable from any source, a fallback checks the state's last-write age: past a 6h threshold it is treated as not-live and flipped the same way; a fresher `updated_at` (or one that can't be judged — empty, malformed, or a naive/tz-less timestamp) is left alone (BUG-3317).

#### `ll-loop stop <loop>`

Stop a running loop. Terminates **all running instances** of the named loop (no `--instance-id` selector).

Termination is process-cohort aware (ENH BUG-2147): before sending any signal, `ll-loop stop` walks the full descendant tree of the root PID via `pgrep -P` recursion, collecting every child and grandchild process. Children are terminated first (so the root cannot respawn them), then the root receives SIGTERM. If any member of the cohort is still alive after 10 s, the entire group is escalated to SIGKILL. This ensures that loops spawning child CLIs (e.g. the `claude` binary launched with `start_new_session=True`) are reliably cleaned up rather than left as orphans.

Also handles loops in `interrupted` state that hold an orphaned lock-file PID: if `.loops/.running/<loop>.lock` exists and its PID is alive, `ll-loop stop` terminates the full process cohort as above and removes the lock file. This resolves scope conflicts that block subsequent `ll-loop run` invocations without requiring manual `kill` + `rm`. If the lock-file PID is already dead, the stale lock is cleaned up and reported.

#### `ll-loop resume <loop>` / `ll-loop res <loop>`

Resume a loop. Resumable statuses are `"running"`, `"awaiting_continuation"`, `"interrupted"` (Ctrl-C, the runner caught the signal itself), and `"user_stopped"` (clean `ll-loop stop` — ENH-2522 wrote a `user-stop.marker` so the runner can distinguish this from a kernel kill). Loops that died from a kernel/SIGKILL/OOM kill terminate with `terminated_by="system_signal"` and are **not** resumable — the runner died mid-state and there is no clean recovery point. When no `--instance-id` is given, the most recent resumable instance is auto-selected. Use `--instance-id` to disambiguate when you need a specific instance.

| Flag | Short | Description |
|------|-------|-------------|
| `--instance-id <id>` | | Select a specific instance to resume (auto-detected if omitted) |
| `--background` | `-b` | Resume as a detached background process |
| `--context KEY=VALUE` | | Override a context variable (repeatable) |
| `--show-diagrams[=MODE]` | | Display FSM diagram after each step. `MODE` is a topology (`layered`\|`neighborhood`\|`inline`\|`window`) or preset (`detailed`\|`summary`\|`clean`\|`local`\|`slim`\|`oneline`). Bare flag selects `summary` (layered, main-path scope). Override individual facets with `--diagram-edge-labels=on\|off`, `--diagram-state-detail=title\|full`, `--diagram-scope=main\|full`. **Breaking (ENH-1672):** `main`→`summary`, `full`→`detailed`, `mini`→`clean`; old values error with migration hints. Viewport auto-degrades `layered→window→neighborhood→inline` for preset/default sources (the `window` rung crops the real layered diagram to ±K layers around the active state with `▲ N layers above`/`▼ M layers below` banners — ENH-2410); explicit topology values disable degradation (`window` is also selectable explicitly). |
| `--clear` | | Clear terminal before each iteration (combine with `--show-diagrams` for live in-place rendering; suppressed when stdout is not a tty). When combined with `--show-diagrams` on a tty, the screen splits into a pinned FSM diagram on top and a scrolling action-output region below; on terminals too short for the full diagram the pinned pane falls back first to a **windowed** view (the real layered diagram cropped to ±K layers around the active state, with `▲ N layers above`/`▼ M layers below` overflow banners — ENH-2410), then to a 1-hop neighborhood view (predecessors → [active] → successors), then to a single-line `fsm: ... → [...] → ...` status. The pane redraws on SIGWINCH (terminal resize). When a parent loop spawns child loops, the pinned pane shows **only the deepest active child loop** rather than all nesting levels simultaneously — keeping the pane readable regardless of loop depth. |
| `--delay` | | Sleep N seconds between iterations (useful for recording and to relieve host memory pressure between subprocess spawns) |
| `--no-host-guard` | | Disable the adaptive host memory-pressure guard (`host_guard:` block, ENH-2452) |
| `--handoff-threshold` | | Override auto-handoff context threshold (1-100) |
| `--context-limit` | | Override context window token estimate |

#### `ll-loop monitor <loop>`

Attach to a running loop and render its FSM state in realtime. Read-only:
tails `<instance-id>.events.jsonl` and the loop's `.log` file from disk and
forwards events to the same `StateFeedRenderer` used by `ll-loop run`. Ctrl-C
detaches from the rendered stream without sending any signal to the loop
process (use `ll-loop stop` to terminate the loop). When no instance is running
(no live PID), prints the last-known state of the most recent instance and
exits 0.

```bash
ll-loop monitor fix-types               # tail events and log
ll-loop monitor fix-types --show-diagrams --clear    # pinned FSM diagram + scrolling log
ll-loop monitor fix-types --clear              # with clear-screen on redraw
```

| Flag | Short | Description |
|------|-------|-------------|
| `--show-diagrams[=MODE]` | | Display FSM diagram alongside events (same semantics as `ll-loop run`). |
| `--diagram-edge-labels` | | Override edge-label visibility (`on`\|`off`). |
| `--diagram-state-detail` | | Override state-detail level (`title`\|`full`). |
| `--diagram-scope` | | Override diagram scope (`main`\|`full`). |
| `--clear` | | Pin the FSM diagram and stream events below (TTY only). |
| `--no-clear` | | Disable terminal clearing between iterations (scroll output instead). |
| `--quiet` / `--qt` | | Suppress progress output. |
| `--verbose` | `-v` | Show full prompt at action start. |

#### `ll-loop history <loop>` / `ll-loop h <loop>`

Show execution history for a loop.

| Flag | Short | Description |
|------|-------|-------------|
| `run_id` | | (Optional positional) Archived run ID to inspect; omit to list all archived runs |
| `--tail` | `-n` | Last N events to show (default: 50) |
| `--event` | `-e` | Filter by event type (e.g. `evaluate`, `route`, `state_enter`) |
| `--state` | `-s` | Filter by state name (matches `state`, `from`, or `to` fields) |
| `--since` | | Filter to events within a time window (e.g. `1h`, `30m`, `2d`) |
| `--verbose` | `-v` | Show action output preview and LLM call details (model, latency, prompt, response) |
| `--full` | | Show untruncated prompts and output (implies `--verbose`) |
| `--json` | `-j` | Output events as JSON array |

#### `ll-loop test <loop>` / `ll-loop t <loop>`

Run a single test iteration to verify loop configuration.

#### `ll-loop simulate <loop>` / `ll-loop sim <loop>`

Trace loop execution interactively without running commands.

| Flag | Short | Description |
|------|-------|-------------|
| `--scenario` | | Auto-select results: `all-pass`, `all-fail`, `first-fail`, `alternating` |
| `--max-steps` | `-n` | Override step cap (default: min of loop config or 20) |
| `--max-iterations` | | Override full-pass cap for simulation |

Runner-injected context variables (`run_dir`, `input`, `run_timestamp`) are populated before simulation begins, matching the behaviour of `ll-loop run`. Loops that reference `${context.run_dir}` in early states can be tested with simulate without errors (BUG-2118).

#### `ll-loop install <loop>`

Copy a built-in loop to `.loops/` for customization.

#### `ll-loop show <loop>` / `ll-loop s <loop>`

Show loop details and FSM structure. The header line displays active [per-loop config overrides](../guides/LOOPS_GUIDE.md#per-loop-config-overrides) (e.g., `config: handoff_threshold=60`) when a `config:` block is present in the loop YAML.

The **Commands** section at the bottom of the output can be overridden by adding a top-level `commands:` list to the loop YAML. Each entry is a `{cmd, comment}` pair; when present, this list replaces the five generic default commands so that loops requiring `--param` or `--context` flags can surface copy-paste-ready examples. See `docs/generalized-fsm-loop.md` for the full `commands:` schema.

**State overview table columns.** When `--show-diagrams` is not in `--json` mode, the main body of `ll-loop show` prints a compact state overview table with four columns:

| Column | Meaning |
|---|---|
| `State` | State name; the `initial` state is prefixed with `→`. |
| `Type` | Action shape: `sub-loop` (state with a `loop:` field — renders magenta), `shell`, `agent`, `llm_structured`, `check_semantic`, etc.; `(terminal)` states show `—`. Lets you read at a glance which states delegate to another loop vs run inline logic. |
| `Action Preview` | First non-blank line of the state's `action:` source (or `[sub-loop: <name>]` for delegating states), truncated to fit terminal width. |
| `Transitions` | Compact routing summary: each `on_yes` / `on_no` / `on_error` / `on_partial` / `next` / `route.<verdict>` label grouped by target (e.g., `yes→done`, `no→retry`); emits `—` when the state has no explicit routing. |

This state-overview table is separate from the `--show-diagrams` ASCII diagram — the table is always rendered in `--clean` / `--summary` / default output as a quick reference; the diagram shows the graph topology when `--show-diagrams` is enabled.

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | `-j` | Output FSM config as JSON |
| `--resolved` | | Expand sub-loop states inline under `_subloop` key (requires `--json`) |
| `--show-diagrams[=MODE]` | | Display FSM diagram inline. `MODE` is a topology (`layered`\|`neighborhood`\|`inline`\|`window`) or preset (`detailed`\|`summary`\|`clean`\|`local`\|`slim`\|`oneline`). Bare flag selects `summary`. Override facets with `--diagram-edge-labels=on\|off`, `--diagram-state-detail=title\|full`, `--diagram-scope=main\|full`. Mutually exclusive with `--json`. |
| `--diagram-edge-labels` | | Override edge-label visibility for the diagram (`on`\|`off`). |
| `--diagram-state-detail` | | Override state-detail level for the diagram (`title`\|`full`). |
| `--diagram-scope` | | Override diagram scope (`main`\|`full`). |

#### `ll-loop fragments <lib>`

List fragments defined in a library file, showing each fragment's name and description. Resolves the library path relative to `.loops/`, then falls back to the built-in library directory.

```bash
ll-loop fragments lib/common.yaml         # list built-in common fragments
ll-loop fragments lib/cli.yaml            # list built-in CLI tool fragments
ll-loop fragments lib/benchmark.yaml      # list built-in benchmark runner fragment
ll-loop fragments lib/prompt-fragments.yaml  # list built-in prompt fragment library
ll-loop fragments lib/harness.yaml        # list built-in Playwright screenshot fragment
ll-loop fragments .loops/my-lib.yaml      # list project-local fragment library
```

#### `ll-loop scaffold-eval`

Generate FSM eval-harness loop YAML in Python from one or more issue IDs (FEAT-2948) — the mechanical port of `/ll:create-eval-from-issues`'s Variant A/B templates and Proof-First Gate chaining. Builds `FSMLoop`/`StateConfig` objects directly, validates via `fsm.validation.validate_fsm()` in-process, and emits YAML with `<EXECUTE_PROMPT>`/`<EVALUATION_CRITERIA_PROMPT>` placeholder slots for the skill (or caller) to fill — the state graph and chaining are never hand-assembled.

| Flag | Description |
|------|-------------|
| `--issues ID[,ID...]` | Comma-separated issue IDs (required). 1 issue → Variant A (`initial: execute`); 2+ → Variant B (`initial: discover`) |
| `--dsl` | Not implemented here; the skill's DSL fill-in-the-blank/transform/correction generator is a separate code path — errors with a pointer to `/ll:create-eval-from-issues --dsl` |
| `--out PATH` | Write the generated YAML to PATH |
| `--stdout` | Print the generated YAML to stdout |
| `-j`, `--json` | Output the `ScaffoldResult` (`yaml_path`, `yaml_text`, `placeholders`, `validated`, `errors`) as JSON |

**Examples:**
```bash
ll-loop scaffold-eval --issues FEAT-919 --stdout            # single-issue Variant A
ll-loop scaffold-eval --issues FEAT-919,ENH-950 --json       # multi-issue Variant B, JSON result
```

#### `ll-loop scaffold-verify`

Generate a single-issue FSM verification loop YAML in Python (FEAT-2948) — the mechanical port of `/ll:verify-issue-loop`'s criteria-mode linear chain and fixed adversarial 3-probe template. Extracts criteria via `IssueParser.extract_criteria()` (bullet-marker normalization: checkboxes, plain bullets, numbered lists; sub-bullets skipped), builds and validates the `FSMLoop` in-process, and selects the timeout in code (1800s criteria / 2700s adversarial). Unlike `scaffold-eval`, the output has no placeholder slots — criteria/adversarial prompt text is fully determined by the issue's own title and criterion text, so the emitted YAML is immediately runnable.

| Flag | Description |
|------|-------------|
| `issue_id` | Issue ID (positional, required) |
| `--adversarial` | Emit the fixed 3-probe adversarial template instead of criteria mode |
| `--out PATH` | Write the generated YAML to PATH |
| `--stdout` | Print the generated YAML to stdout |
| `-j`, `--json` | Output the `ScaffoldResult` as JSON |

**Examples:**
```bash
ll-loop scaffold-verify FEAT-919 --stdout                   # criteria mode
ll-loop scaffold-verify FEAT-919 --adversarial --json        # adversarial mode, JSON result
```

#### `ll-loop next-loop`

Inspect `.loops/.history/` and suggest the next loop(s) to run, with resolved input parameters where available. Useful for unattended chaining or scheduled follow-up work.

| Flag | Short | Description |
|------|-------|-------------|
| `--count N` | `-n` | Return top N suggestions instead of just one (default: 1) |
| `--json` | `-j` | Output suggestions as a JSON array |
| `--execute` | | Run the top suggestion immediately via the same code path as `ll-loop run` |
| `--exclude NAME` | | Skip the named loop from suggestions (repeatable; useful from on-completion hooks to avoid trivial self-loops) |

Each suggestion includes a scored `rationale` (run frequency, recency, success rate) and a ready-to-paste shell command. For `autodev`, the suggested input is automatically resolved to the current set of `status: open` issue IDs.

**JSON output keys:** `loop`, `input`, `context`, `score`, `rationale`, `command`

**Examples:**
```bash
ll-loop next-loop                          # Top suggestion with human-readable output
ll-loop next-loop --count 3                # Top 3 ranked candidates
ll-loop next-loop --json                   # Machine-readable suggestion
ll-loop next-loop --execute                # Run the top suggestion immediately
ll-loop next-loop --exclude autodev        # Skip autodev (e.g. from its own on-completion hook)
ll-loop next-loop --count 3 --json        # Top 3 as JSON for downstream tooling
```

#### `ll-loop audit`

Compute deterministic counters for a single archived loop run (ENH-2949) — the non-LLM evidence base that `/ll:audit-loop-run` reasons over. Distinct from [`ll-loop audit-meta`](#ll-loop-audit-meta), which aggregates LLM-vs-external-evaluator agreement across many runs of one loop.

| Flag | Short | Description |
|------|-------|-------------|
| `run` (positional) | | Run directory name under `.loops/.history/`, e.g. `<run_id>-<loop_name>`. Optional when `--latest` is given |
| `--latest LOOP` | | Resolve the most recent archived run for LOOP instead of naming a run directory |
| `--max-steps N` | | Override the loop's `max_steps` when computing budget utilization (default: read from the run's `state.json` → loop spec) |
| `--json` | `-j` | Output counters as a JSON object |

**JSON keys:** `run_id`, `loop`, `events_total`, `events_by_type`, `per_state` (each value `{entries, actions_complete, duration_s}`), `aux_mutation_count`, `tool_call_count`, `diff_stall_present`, `steps_consumed`, `max_steps`, `budget_utilization`, `terminated_by`, `failure_terminal`, `verdict_inputs`.

**Exit codes:** 0 = counters computed; 1 = run directory could not be resolved.

**Examples:**
```bash
ll-loop audit 1730000000-autodev          # Human-readable counter summary
ll-loop audit --latest autodev --json     # Most recent autodev run, as JSON
ll-loop audit --latest autodev --max-steps 40
```

#### `ll-loop audit-meta`

Read `meta-eval.jsonl` from archived runs and print a summary table of LLM vs. external-evaluator agreement statistics. Useful for diagnosing meta-loops where the LLM judge may be too lenient or agreeing on no-op iterations.

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | `-j` | Output stats as a JSON object |

**Exit codes:** 0 = no divergence flags triggered; 1 = at least one threshold crossed (`agreed: false` streak ≥ 3, or trivial-agreement streak ≥ 3).

**Examples:**
```bash
ll-loop audit-meta harness-optimize        # Human-readable summary table
ll-loop audit-meta harness-optimize --json # JSON output for scripting
```

#### `ll-loop diagnose-evaluators`

Scan `.loops/.history/*-<loop>/events.jsonl` to detect non-discriminating evaluator states whose verdict has near-zero variance across runs. Flags states below `--threshold` (default 0.05) with pattern-matched recommendations for improving discriminating power.

| Flag | Short | Description |
|------|-------|-------------|
| `--threshold` | | Variance floor below which a state is flagged (default: 0.05) |
| `--min-runs` | | Minimum runs required for meaningful variance (default: 10) |
| `--json` | `-j` | Output results as a JSON object; each evaluator entry includes `ci_lower` and `ci_upper` (Wilson 95% CI bounds on the pass-rate) |

**Exit codes:** 0 = no low-variance states found or insufficient data; 1 = at least one non-discriminating evaluator flagged.

**Examples:**
```bash
ll-loop diagnose-evaluators harness-refine-issue              # Human-readable report
ll-loop diagnose-evaluators harness-refine-issue --json        # JSON output for scripting
ll-loop diagnose-evaluators harness-refine-issue --threshold 0.1 --min-runs 5
```

#### `ll-loop calibrate-budget`

Report per-evaluator Bernoulli variance `p*(1-p)` to decide whether increasing `max_steps` will improve outcomes. Calls the same analytics engine as `diagnose-evaluators` but frames output around retry-budget ROI: evaluators below the variance threshold waste iterations and should be fixed before raising `max_steps`.

| Flag | Short | Description |
|------|-------|-------------|
| `--threshold` | | Variance floor below which a state is flagged (default: 0.05) |
| `--min-runs` | | Minimum runs required for meaningful variance (default: 10) |
| `--json` | `-j` | Output results as a JSON object; each evaluator entry includes `ci_lower` and `ci_upper` (Wilson 95% CI bounds on the pass-rate) |

**Exit codes:** 0 = all evaluators healthy or insufficient data; 1 = at least one evaluator flagged (fix before increasing `max_steps`).

**Examples:**
```bash
ll-loop calibrate-budget rn-refine                    # Human-readable variance report
ll-loop calibrate-budget rn-refine --json              # JSON output for scripting
ll-loop calibrate-budget rn-refine --threshold 0.1 --min-runs 5
```

#### `ll-loop promote-baseline`

Promote the latest run's action output as the new comparator baseline. Reads `action_output` events from the most recent `.loops/.history/*-<loop>/events.jsonl` and writes the concatenated output to `.loops/baselines/<loop>/output.txt`. Use this to manually set the baseline after inspecting a run, as an alternative to `auto_promote: true`.

**Arguments:**
| Argument | Description |
|----------|-------------|
| `loop` | Loop name |

**Exit codes:** 0 = baseline promoted successfully; 1 = no history found or no `action_output` events.

**Examples:**
```bash
ll-loop promote-baseline my-loop    # Promote latest run as new baseline
```

#### `ll-loop edit-routes`

Render a loop's routing logic as an editable decision table. Opens the table in `$EDITOR` (or prints to stdout with `--dry-run`). On save, parses the edited table and writes changes back to the loop YAML, preserving all non-route fields, comments, and YAML structure.

**Two rendering modes:**

- **State × verdict matrix** (default) — one row per state, one column per verdict. Used for standard loops.
- **Compound decision table** (auto-detected or `--decision-table`) — used for loops that import `lib/policy-router.yaml` with a `context.policy_rules` block. Renders a condition-columns × action grid where each row is one conjunctive rule, columns are scored dimensions, and the final column is the target action state.

Before opening the editor in verdict-matrix mode, prints warnings for: unreachable states, dead-end states (no outbound routes and not terminal), and missing verdict arms (e.g. `on_yes` without `on_no` or `default`). In decision-table mode, warns on shadowed rules, missing catch-all, and unknown action states.

**Arguments:**
| Argument | Default | Description |
|----------|---------|-------------|
| `loop` | | Loop name or path |
| `--format {markdown,csv}` | `markdown` | Output format for the table |
| `--dry-run` | | Print table to stdout without opening editor |
| `--no-warnings` | | Skip gap/conflict detection output |
| `--allow-delete` | | Allow deletion of state blocks that were removed from the edited table (default: removed rows are ignored) |
| `--decision-table` | | Force compound policy-router decision table instead of state × verdict matrix |

**State operations via the verdict-matrix table:**
- **Edit routes** — change any cell in the table; the corresponding `on_<verdict>` field is updated on save.
- **Add a terminal stub** — add a new row with a state name that doesn't exist yet and leave all verdict cells empty. On save the state is inserted with `terminal: true` as a placeholder you can expand later.
- **Delete a state** — remove a row entirely, then re-run with `--allow-delete`. Without `--allow-delete`, deleted rows are silently ignored.

**Compound decision table format:**

```
| #  | confidence | outcome | security | aggregate | → action     |
|----|------------|---------|----------|-----------|--------------|
| 1  | —          | —       | <65      | —         | escalate     |
| 2  | >=85       | >=75    | —        | —         | implement    |
| 3  | *          | *       | *        | *         | deep_repair  |
```

Each condition cell is an operator+value (`>=85`, `<65`, `==true`). Empty cell (`—`) means dimension unconstrained in that rule. Catch-all row uses `*` in all condition columns (first-match-wins, catch-all should be last). Edit cells or reorder rows; save to write changes back to `context.policy_rules`.

**Exit codes:** 0 = success or no changes; 1 = parse error or unknown state in edited table (when not a new stub); 2 = loop not found.

**Examples:**
```bash
ll-loop edit-routes rn-implement             # Open routing table in $EDITOR
ll-loop edit-routes rn-implement --dry-run   # Print table to stdout
ll-loop edit-routes rn-implement --format csv --dry-run   # CSV format
ll-loop edit-routes rn-implement --no-warnings            # Skip gap warnings
ll-loop edit-routes rn-implement --allow-delete           # Apply row deletions
ll-loop edit-routes policy-refine --decision-table        # Compound table (explicit)
ll-loop edit-routes policy-refine --dry-run               # Auto-detects decision-table mode
```

**Examples:**
```bash
ll-loop fix-types                     # Run loop (shorthand for run)
ll-loop run fix-types --worktree      # Run in isolated git worktree
ll-loop run fix-types --dry-run       # Show execution plan
ll-loop run fix-types --dry-run --show-diagrams          # FSM diagram + execution plan
ll-loop run fix-types --dry-run --show-diagrams=detailed # Detailed diagram + plan
ll-loop validate fix-types            # Validate loop definition
ll-loop test fix-types                # Run single test iteration
ll-loop simulate fix-types            # Interactive simulation
ll-loop simulate fix-types --scenario all-pass
ll-loop list                          # List available loops
ll-loop list --running                # List loops currently executing
ll-loop list --all-runs               # List every run with saved state, any status
ll-loop list --json                   # JSON array of available loops
ll-loop status fix-types              # Show loop status
ll-loop status fix-types --json       # Loop state as JSON
ll-loop stop fix-types                # Stop a running loop
ll-loop resume fix-types              # Resume interrupted loop
ll-loop history fix-types             # Show execution history
ll-loop history fix-types --tail 20   # Last 20 events
ll-loop history fix-types --verbose   # Include LLM call details
ll-loop history fix-types --full      # Untruncated output
ll-loop history fix-types --json      # JSON output
ll-loop history fix-types <run_id>    # Inspect a specific archived run
ll-loop install fix-types             # Install built-in loop
ll-loop show fix-types                # Show loop details
ll-loop show fix-types --json         # FSM config as JSON
ll-loop show fix-types --json --resolved  # FSM config with sub-loop states expanded
ll-loop fragments lib/common.yaml         # List built-in common fragments with descriptions
ll-loop fragments lib/cli.yaml            # List built-in CLI tool fragments with descriptions
ll-loop fragments lib/benchmark.yaml      # List built-in benchmark runner fragment
ll-loop fragments lib/prompt-fragments.yaml  # List built-in prompt fragment library
ll-loop fragments lib/harness.yaml        # List built-in Playwright screenshot fragment
ll-loop next-loop                     # Suggest next loop from history
ll-loop next-loop --count 3 --json    # Top 3 suggestions as JSON
ll-loop audit-meta fix-types          # Summarize meta-eval agreement stats
ll-loop audit-meta fix-types --json   # JSON output
```

See [LOOPS_GUIDE](../guides/LOOPS_GUIDE.md) for loop configuration details.

---

## Issue Management

### ll-issues

Issue management and visualization utilities.

**Subcommands:**

#### `ll-issues next-id` / `ll-issues ni`

Print the next globally unique issue number across all types.

| Flag | Description |
|------|-------------|
| `--count N` / `-n N` | Print N consecutive IDs starting at `max+1`, one per line (default: 1). Must be a positive integer; `0` or negative values exit with code 2. |
| `--config` | Path to project root |

#### `ll-issues list` / `ll-issues l`

List issues with optional filters.

| Flag | Description |
|------|-------------|
| `--type` | Filter by type: `BUG`, `FEAT`, `ENH`, `EPIC` |
| `--priority` | Filter by priority: `P0`–`P5`, or comma-separated e.g. `P1,P2` |
| `--label` | Filter by label from `labels:` frontmatter; repeatable for OR match |
| `--milestone` | Filter by milestone name from `milestone:` frontmatter (exact match) |
| `--group-by` | Group output by `type` (default, existing four-bucket view) or `epic` (group child issues under their parent ID, with an "Unparented" bucket for issues without a `parent:` field; each EPIC bucket header includes a `(N/M done · K blocked)` progress badge). The `(N/M done)` denominator is the EPIC's full transitive descendant set, including nested EPICs — a nested EPIC child is rendered as its own row in a `Sub-EPICs (k)` sub-section beneath the parent heading, each carrying its own `(j/m done)` rollup, so the badge and the visible list always agree (BUG-2480). |
| `--status` | Filter by status: `open` (default), `in_progress`, `blocked`, `deferred`, `done`, `cancelled`, `all`. Note: synonyms in on-disk frontmatter are normalized on read, but `--status` arguments must use canonical values (argparse validates choices before normalization runs). |
| `--parent EPIC-NNN` | Filter to the full **transitive** descendant set of the given EPIC or issue ID (e.g. `--parent EPIC-101`) — grandchildren nested under an intermediate (often `done`) FEAT/ENH are included, resolved via the same cycle-safe walker as `epic-progress`. Still `--status`-gated (default `open`), so completed descendants are not re-surfaced. |
| `--flat` | Output flat list for scripting |
| `--json` / `-j` | Output as JSON array; each entry includes `id`, `title`, `priority`, `type`, `status`, `path`, `labels`, `milestone`, and `parent` (the parent EPIC or issue ID when set) |
| `--include-summary` | When combined with `--json`, adds a `"summary"` key to each JSON object containing the plain text of the issue's `## Summary` section (empty string if absent). No-op without `--json`. |
| `--sort` / `-s` | Sort by field: `priority` (default), `id`, `type`, `title`, `created`, `completed`, `confidence`, `outcome`, `refinement` |
| `--asc` | Sort ascending |
| `--desc` | Sort descending |
| `--limit` / `-n` | Cap output at N issues (must be ≥ 1) |
| `--no-truncate` | Show full untruncated titles (default: truncate to terminal width) |
| `--config` | Path to project root |

#### `ll-issues count` / `ll-issues c`

Count issues. Outputs a single integer by default, or a JSON object with breakdowns.

| Flag | Description |
|------|-------------|
| `--type` | Filter by type: `BUG`, `FEAT`, `ENH`, `EPIC` |
| `--priority` | Filter by priority: `P0`–`P5`, or comma-separated e.g. `P1,P2` |
| `--status` | Filter by status: `open` (default), `in_progress`, `blocked`, `deferred`, `done`, `cancelled`, `all`. Note: synonyms in on-disk frontmatter are normalized on read, but `--status` arguments must use canonical values (argparse validates choices before normalization runs). |
| `--json` / `-j` | Output JSON with `total`, `status`, `by_type`, and `by_priority` breakdowns |
| `--config` | Path to project root |

#### `ll-issues show <issue_id>` / `ll-issues s <issue_id>`

Show summary card for a single issue. Accepts short form (`518`), type-prefixed (`FEAT-518`), or full (`P3-FEAT-518`). Searches all type directories regardless of status.

The card includes: ID, title, priority, status, effort, risk, confidence scores, dimension scores (Cmplx, Tcov, Ambig, Chsrf — when present), source (discovered_by), integration file count, labels, `captured_at` / `completed_at` timestamps (when present), session history, and path.

Rendering is scanning-first (ENH-2574): the title is bold, borders/field labels/the Path line are dimmed, status is colored per state, and the inter-field separator is `·` rather than the border glyph. Several rows are pruned or collapsed for signal:

- **Source** is omitted when `discovered_by` is absent *or* when its value is `manual` (the default case).
- **Norm/Fmt** collapse into a single `Needs: formatting` row, shown only when the file is actually missing required sections — nothing renders when formatting is already correct.
- **`captured_at` / `completed_at`** render date-only (the `T00:00:00Z` time component is dropped); `Captured at` is omitted entirely when it's the same calendar date as `Discovered`.
- Once the capture/discovery/relationships/history/closure block has 4 or more rows, labels right-pad into a column so every row's value starts at the same position.

The card also surfaces, when present in frontmatter (ENH-2535):

- **Closure context** — `closing_note` / `cancelled_reason` / `deferred_reason` plus `closed_by`, `closed_at`, `deferred_date` (only when status is `done`, `cancelled`, or `deferred`). Under `deferred_by: automation` (ENH-2664), `deferred_reason` holds a machine enum code (`blocked_by_unmet`, `remediation_stalled`, or — ENH-2666, autodev's not-ready exits — `low_readiness`, `gate_blocked`, `decision_unresolved`, `oversized_atomic` (BUG-2734), `readiness_stagnated` (FEAT-2751)) instead of free-text prose — rendered as-is.
- **Relationships** — `parent` (with epic title when resolvable), `relates_to`, `depends_on`, `blocked_by`, `blocks`, `supersedes`, `superseded_by` (derived reverse edge; ENH-2829), `decomposed_into`, `affects`, `focus_area`.
- **Discovery** — `discovered_date` (distinct from `captured_at`), `discovered_commit` (short-SHA, first 7 chars), `discovered_branch`, `discovered_source`, `discovered_external_repo`.
- **Decision coupling** — when `decision_needed: true` is paired with `decision_ref` (e.g., `ARCHITECTURE-049`), the card renders `Decision needed → ARCHITECTURE-049`; explicit `Decision needed: no` for `decision_needed: false`.

| Flag | Description |
|------|-------------|
| `--json` / `-j` | Output issue fields as JSON (includes `source`, `norm`, `fmt` keys) |

#### `ll-issues path <issue_id>` / `ll-issues p <issue_id>`

Print the relative file path for an issue ID. Accepts short form (`1009`), type-prefixed (`FEAT-1009`), or full (`P3-FEAT-1009`). Searches all type directories regardless of status. Exits 0 on match, 1 if not found.

| Flag | Description |
|------|-------------|
| `--json` / `-j` | Output as JSON object `{"path": "..."}` |

#### `ll-issues search [query]` / `ll-issues sr [query]`

Search issues with filters and sorting.

| Argument/Flag | Description |
|---------------|-------------|
| `query` | (Optional) Text to match against title and body (case-insensitive) |
| `--type` | Filter by type: `BUG`, `FEAT`, `ENH`, `EPIC` (repeatable) |
| `--priority` | Filter by priority: `P0`–`P5` or range e.g. `P0-P2` (repeatable) |
| `--status` | Filter by status: `open` (default), `in_progress`, `blocked`, `deferred`, `done`, `cancelled`, `all` |
| `--include-completed` | Include issues of all statuses (alias for `--status all`) |
| `--label` | Filter by label tag (repeatable) |
| `--since` | Only issues on or after DATE (YYYY-MM-DD) |
| `--until` | Only issues on or before DATE (YYYY-MM-DD) |
| `--date-field` | Date field to filter on: `discovered` (default) prefers `captured_at` frontmatter (sub-day resolution) and falls back to `discovered_date`; `updated` uses the last `## Session Log` entry timestamp, falling back to file mtime |
| `--sort` | Sort field: `priority` (default), `id`, `date`, `type`, `title`, `created`, `completed`, `confidence`, `outcome`, `refinement` |
| `--asc` / `--desc` | Sort direction |
| `--format` | Output format: `table` (default), `list`, `ids` |
| `--limit` | Cap results at N |
| `--json` / `-j` | Output as JSON array; each entry includes `id`, `title`, `priority`, `type`, `status`, `path`, `labels`, `milestone`, and `parent` |

#### `ll-issues sequence` / `ll-issues seq`

Suggest a dependency-ordered implementation sequence.

| Flag | Description |
|------|-------------|
| `--type` | Filter by issue type: `BUG`, `FEAT`, `ENH`, `EPIC` |
| `--limit` | Maximum issues to show (default: 10) |
| `--json` / `-j` | Output sequence as JSON array |
| `--config` | Path to project root |

For an issue with an empty structured `blocked_by` set, a prose dependency
claim (e.g. "Depends on FEAT-109" in the body) that references a non-terminal
issue is surfaced as an annotation rather than silently reported as
`no blockers` — text output appends `⚠ prose dep FEAT-109, not in blocked_by`,
and `--json` adds an `"unverified_prose_deps"` array field to each record.
This never changes topological order; it only flags rows worth a human check
(ENH-2847).

Ordering itself is constrained by both `blocked_by` (hard) and `depends_on`
(soft) edges — an issue is placed only after every prerequisite from either
field is scheduled ahead of it (BUG-2848). Earlier versions of `sequence`
honored `blocked_by` only, so a `depends_on`-only prerequisite could sort
after its dependent; `topological_sort()` now folds both into the same pass.

**Dependency cycle fallback** (BUG-2899): when a `blocked_by`/`depends_on`
cycle makes topological order impossible, text output prints a warning plus
a second line clarifying the fallback ("Ordering below is priority-only;
cycle members marked ⚠ and cannot be sequenced."), then falls back to a
genuine global priority sort (`(priority_int, issue_id)` — the same
tiebreaker `topological_sort()` uses) rather than raw directory-walk order.
Cycle-participating issues print `⚠ in cycle: A -> B -> A` in place of their
`blocked by:`/`after:` rationale, since those structured edges are exactly
what forms the unsatisfiable cycle. `--json` adds an always-present
`"in_cycle": true/false` boolean per record instead of the warning text
(which would break the single JSON document on stdout); check that field to
detect a degraded fallback ordering programmatically.

`--json`'s `"blocks"` field is graph-derived like `"blocked_by"` and
`"depends_on"`: non-terminal-filtered (excludes `done`/`cancelled`, includes
`deferred`) and sorted, not the raw frontmatter declaration order (ENH-2900).

#### `ll-issues impact-effort` / `ll-issues ie`

Display an impact vs. effort matrix for active issues.

| Flag | Description |
|------|-------------|
| `--type` | Filter by type: `BUG`, `FEAT`, `ENH`, `EPIC` |
| `--json` / `-j` | Output as JSON object with quadrant keys |

#### `ll-issues refine-status` / `ll-issues rs`

Show refinement depth table sorted by commands touched. Columns: ID, Pri, size, Title, source, norm, fmt, per-command session indicators (✓/—), Ready (confidence score), conf (outcome confidence), cmplx (complexity score 0–25), tcov (test coverage score 0–25), ambig (ambiguity score 0–25), chsrf (change surface score 0–25), total.

| Argument/Flag | Description |
|---------------|-------------|
| `ISSUE-ID` | (Optional) Filter to a single issue by ID (e.g. `FEAT-873`, `BUG-525`, or a bare number like `873`), resolved regardless of status (`open`, `deferred`, `done`, `cancelled`, etc). Ignores `--type` when set. Prints `Error: Issue '<id>' not found.` to stderr and exits 1 if the issue is not found. |
| `--type` | Filter by type: `BUG`, `FEAT`, `ENH`, `EPIC` (ignored when `ISSUE-ID` is provided) |
| `--format` | Output format: `table` (default), `json` (NDJSON) |
| `--json` / `-j` | Output as JSON array; with `ISSUE-ID` outputs a single JSON object instead |
| `--no-key` | Suppress the key/legend section at the bottom of output |
| `--config` | Path to project root |

The `Norm` column checks filenames against `^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]{3,}-[a-z0-9-]+\.md$`. JSON output includes a `"normalized": true/false` boolean field per record.

**Narrow terminal support**: When the table exceeds the available terminal width, columns are automatically elided in priority order. The default drop sequence is `source` → `norm` → `fmt` → `size` → `chsrf` → `ambig` → `tcov` → `cmplx` → `confidence` → `ready` → `total`; any remaining command columns are then dropped rightmost-first. `id`, `priority`, and `title` are always pinned. The `title` column maintains a minimum width of 20 characters. The drop order is configurable via `refine_status.elide_order` in `ll-config.json` — see [CONFIGURATION.md](CONFIGURATION.md#refine_status).

#### `ll-issues next-action` / `ll-issues na`

Print the next refinement action needed across all active issues. Designed for FSM loop integration — exits 1 when work remains, exits 0 when all issues are ready.

Output format: `<ACTION> <issue-id>` (one line), or `ALL_DONE`.

| Action token | Meaning |
|--------------|---------|
| `NEEDS_FORMAT` | Issue file does not match template v2.0 structure |
| `NEEDS_VERIFY` | `/ll:verify-issues` has not been run on this issue |
| `NEEDS_SCORE` | Confidence/outcome score is missing |
| `NEEDS_REFINE` | Score is below threshold and refine-cap not reached |

| Flag | Default | Description |
|------|---------|-------------|
| `--refine-cap N` | `5` | Max `/ll:refine-issue` runs before moving on |
| `--ready-threshold N` | `85` | Minimum readiness score to consider issue ready |
| `--outcome-threshold N` | `70` | Minimum outcome confidence score to consider issue ready |
| `--skip / -s ISSUE_ID[,...]` | — | Comma-separated issue IDs to exclude (e.g. `ENH-929,BUG-001`); absent `--skip` preserves existing behavior |
| `--config` | (auto) | Override the config file path |

> **Config-driven defaults**: `next-action` reads `commands.confidence_gate.readiness_threshold` from `.ll/ll-config.json` before falling back to the CLI default of `85`. Set `commands.confidence_gate.readiness_threshold: 90` in your project config to raise the bar globally without passing `--ready-threshold` on every call. The `--ready-threshold` flag still overrides the config value when provided explicitly.

#### `ll-issues next-issue` / `ll-issues nx`

Print the issue ranked highest by outcome confidence and readiness score. Designed for FSM loop integration — use this to pick the best issue to work on next based on implementation readiness rather than raw priority.

**Sort order:** Config-driven via `issues.next_issue.strategy` (default: `confidence_first` — `outcome_confidence` desc, `confidence_score` desc, `priority` asc). Issues without scores are ranked below all scored issues.

**Dependency filter:** By default (ENH-2436), issues whose `Blocked By` references a non-terminal (`done`/`cancelled`) issue are filtered out before ranking, so the returned ID is always actionable. Pass `--include-blocked` to revert to the legacy behavior (return any active issue, blocked or not).

**EPIC exclusion:** EPIC-type ids are never returned (BUG-2638). EPICs are umbrella containers meant to be decomposed via scope resolution (`SprintManager.load_or_resolve`), not implemented as leaves; the exclusion applies to all output modes (`--json`, `--path`, `--include-blocked`).

**Exit codes:** 0 = issue found, 1 = no active issues OR every active issue is currently blocked. The all-blocked case emits `Error: No ready issues (N blocked, 0 ready)` on stderr.

| Flag | Description |
|------|-------------|
| `--json` / `-j` | Output a JSON object: `{id, path, outcome_confidence, confidence_score, priority}`. With `--include-blocked`, the row also carries `blocked` (bool), `blocked_by` (sorted list of issue IDs), and `pending_prerequisites` (sorted list of still-open soft `depends_on` targets). `blocked` reflects hard `blocked_by` edges only, so the three states are distinguishable: hard-blocked (`blocked: true`), soft-deferred (`blocked: false` with a non-empty `pending_prerequisites`), and ready (`blocked: false`, `pending_prerequisites: []`). |
| `--path` | Output only the file path (useful for shell scripting: `$(ll-issues next-issue --path)`) |
| `--skip / -s ISSUE_ID[,...]` | Comma-separated issue IDs to exclude (e.g. `FEAT-007,BUG-001`); absent `--skip` preserves existing behavior |
| `--include-blocked` | Include issues with unresolved blockers in the ranked output. With `--json`, each row carries `blocked`, `blocked_by`, and `pending_prerequisites` fields. |
| `--config` | Path to project root |

#### `ll-issues next-issues [N]` / `ll-issues nxs [N]`

Print all active issues in ranked order by outcome confidence and readiness score. Designed for FSM loop integration — use this to get a ranked list of all issues, not just the top one.

**Sort order:** Config-driven via `issues.next_issue.strategy` (default: `confidence_first` — `outcome_confidence` desc, `confidence_score` desc, `priority` asc). Issues without scores are ranked below all scored issues.

**Dependency filter:** By default (ENH-2436), issues whose `Blocked By` references a non-terminal (`done`/`cancelled`) issue are filtered out before ranking. Pass `--include-blocked` to revert to the legacy behavior.

**EPIC exclusion:** EPIC-type ids are never returned (BUG-2638), in any output mode. EPICs are decomposed via scope resolution, not ranked as implementable leaves.

**Exit codes:** 0 = at least one unblocked issue found, 1 = no active issues OR every active issue is currently blocked. The all-blocked case emits `Error: No ready issues (N blocked, 0 ready)` on stderr.

| Flag/Arg | Description |
|----------|-------------|
| `N` | Optional count — limit output to top N issues |
| `--json` / `-j` | Output a JSON array of objects: `{id, path, outcome_confidence, confidence_score, priority}`. With `--include-blocked`, each row also carries `blocked` (bool), `blocked_by` (sorted list), and `pending_prerequisites` (sorted list of still-open soft `depends_on` targets). As with `next-issue`, `blocked` reflects hard `blocked_by` edges only, so hard-blocked, soft-deferred, and ready rows are distinguishable. |
| `--path` | Output file paths instead of issue IDs |
| `--include-blocked` | Include issues with unresolved blockers in the ranked list. With `--json`, each row carries `blocked`, `blocked_by`, and `pending_prerequisites` fields. |
| `--config` | Path to project root |

#### `ll-issues skip <issue_id>` / `ll-issues sk`

Deprioritize an active issue by bumping its priority prefix and appending a `## Skip Log` entry. Use this to move refinement failures or blocked issues out of the active queue without completing or deleting them.

| Argument / Flag | Short | Description |
|-----------------|-------|-------------|
| `<issue_id>` | | Issue to deprioritize. Accepts numeric ID (`955`), type+ID (`FEAT-955`), or full prefix (`P3-FEAT-955`) |
| `--priority` | `-p` | Target priority P0–P5 (default: `P5`) |
| `--reason TEXT` | | Reason text appended to the `## Skip Log` entry in the issue file |

**Behavior:**
- Renames the issue file with the new priority prefix (e.g., `P3-FEAT-955` → `P5-FEAT-955`) using `git mv` for tracked files to preserve history, falling back to an atomic rename for untracked files
- Appends a `## Skip Log` section with ISO timestamp and the provided reason (or `"No reason provided"` if omitted)
- If the issue is already at the target priority, the file is not renamed but the Skip Log entry is still appended
- Works on issues in any type directory (`bugs/`, `features/`, `enhancements/`, `epics/`)
- Prints the new file path to stdout on success

**Examples:**
```bash
ll-issues skip FEAT-955                                          # Deprioritize to P5 (default)
ll-issues skip 955 --priority P4                                 # Deprioritize to P4
ll-issues skip BUG-042 --reason "retry after CI fix"             # With reason
ll-issues sk ENH-123 -p P3 --reason "blocked on upstream change"
```

---

#### `ll-issues prioritize`

Priority-rename mechanics (ENH-2953), extracted from `commands/prioritize-issues.md`'s glob discovery, `git mv` blocks, and report tables — only the P0-P5 judgment step stays in the command. Discovery is scoped to active issues only (`find_issues`'s default `status_filter=None` skips `done`/`cancelled`/`deferred`); the "is it prioritized" test is a narrow `^P[0-5]-` filename match built from `config.issues.priorities`, not `is_normalized()` (which also fails on ID/slug defects that are `ll-issues normalize`'s job, not this command's).

`--apply -` reads a `{"ISSUE_ID": "P[X]", ...}` JSON map from stdin (or a file path instead of `-`) and performs the renames via the shared `git_mv_with_fallback()` helper — prepending a prefix on an unprioritized file, replacing the existing `P[X]-` on an already-prioritized one. An entry already at its target priority is a reported no-op, not an error; an unresolvable issue ID is skipped silently.

| Argument/Flag | Default | Description |
|---------------|---------|-------------|
| `--all` | `false` | List every active issue with its `current_priority` (`null` if unprioritized), not just unprioritized ones — the re-prioritize mode's input |
| `--check` | `false` | Check-only: exit 1 if any active issue is unprioritized, 0 if clean (FSM `evaluate: type: exit_code` gate). Ignores `--all` — re-prioritization is never a gate failure |
| `--apply FILE` | — | Path to a `{issue_id: priority}` JSON map, or `-` for stdin; performs the renames |
| `--json` / `-j` | `false` | Print `{"findings": [...], "applied": [...]}` instead of text |

**Examples:**
```bash
ll-issues prioritize --json                            # list unprioritized issues
ll-issues prioritize --all --json                       # list every active issue + current_priority
ll-issues prioritize --check                            # FSM gate: exit 0 clean / 1 unprioritized found
echo '{"ENH-2953": "P2"}' | ll-issues prioritize --apply - --json
```

---

#### `ll-issues finalize-decomposition <parent> [children...]` / `ll-issues fd`

Close a decomposed parent issue and re-link its children to the parent's EPIC. Sets the parent's status to `done` in place at its existing type-based path (ENH-1418 convention) and updates the EPIC's child references.

| Argument/Flag | Description |
|---------------|-------------|
| `parent` | Decomposed parent issue ID (e.g., `ENH-123`) |
| `children` | (Optional) Child issue IDs as positional arguments |
| `--children-file PATH` | File with one child ID per line (e.g., the `children_<id>.txt` artifact from `rn-decompose`) |
| `--issues-dir DIR` | Issues base directory (default: `.issues`) |
| `--move` | Move the closed parent into the legacy `completed/` directory instead of closing it in place (deprecated) |
| `--config` | Path to project root |

**Examples:**
```bash
ll-issues finalize-decomposition ENH-123 ENH-124 ENH-125     # Close ENH-123 in place; re-link children
ll-issues fd ENH-123 --children-file run_dir/children_ENH-123.txt  # Load children from file
ll-issues fd ENH-123 --move                                    # Legacy: move into .issues/completed/
```

---

#### `ll-issues append-log <issue_path> <log_command>` / `ll-issues al`

Append a session log entry to an issue file.

| Argument | Description |
|----------|-------------|
| `issue_path` | Path to the issue markdown file |
| `log_command` | Command name to record (e.g., `/ll:refine-issue`) |

---

#### `ll-issues sections <type>` / `ll-issues sec <type>`

Print the JSON content of the per-type section template for `<type>`. Resolves via 4-tier precedence — explicit `issues.templates_dir` config → `<project_root>/.ll/templates/` (project-deployed copy) → bundled wheel templates — so project-local overrides (deployed via `ll-init --deploy-templates`) are returned automatically. Skills and commands should call this instead of reading `scripts/little_loops/templates/{type}-sections.json` directly.

| Argument/Flag | Description |
|---------------|-------------|
| `type` | Issue type: `bug`, `feat`, `enh`, or `epic` |
| `--path` | Output only the resolved file path (useful for shell scripting) |

**Examples:**
```bash
ll-issues sections bug                # Print bug-sections.json content
ll-issues sections feat --path        # Print resolved path (for shell scripting)
ll-issues sec enh                     # Alias: sec
ll-issues sections epic --path        # Resolved path to epic-sections.json
```

---

#### `ll-issues create`

Atomically allocate a globally unique ID and write a new issue file (FEAT-2947). Replaces the
prose ID-allocation / slugify / template-assembly dance previously restated in every
issue-creating skill (`capture-issue`, `scope-epic`): under a single file lock, allocates the
next issue number (retrying on a filesystem collision), slugs the title, selects the type
directory from config, and writes frontmatter + template body. If `--parent` is given, writes
`parent:` in the new issue's frontmatter and — if the parent has a `## Children` section (EPICs
only) — appends a wired bullet there too.

| Argument/Flag | Default | Description |
|---------------|---------|--------------|
| `--type` / `-T` | *(required)* | `BUG`, `FEAT`, `ENH`, or `EPIC` |
| `--title` | *(required)* | Issue title |
| `--priority` / `-p` | `P2` | `P0`-`P5` |
| `--body-file PATH\|-` | — | File (or `-` for stdin). Plain prose becomes the `## Summary` body; a body containing headings that match the variant's sections is merged section-by-section instead of nested under a duplicate scaffold (BUG-3193) |
| `--parent EPIC-N` | — | Parent to wire both directions |
| `--labels a,b` | — | Comma-separated labels |
| `--variant` | `minimal` | Template variant: `minimal`, `full`, or `legacy` |
| `--stage` | `false` | `git add` the created file (and any rewired parent) |
| `--json` / `-j` | `false` | Print `{"id", "path"}` instead of `ID PATH` |

**Examples:**
```bash
ll-issues create --type BUG --title "Login button unresponsive" --stage --json
ll-issues create --type FEAT --title "Add X" --parent EPIC-071 --body-file - --json
```

---

#### `ll-issues scaffold-epic`

Compose `create` into an atomic EPIC + pre-wired child stubs (FEAT-2947). Assembles every file's
content in memory first, then writes them all; on any failure, unlinks every path this call
created and re-raises — every file it touches is one it just created, so this is a complete
undo, not transactional rollback machinery.

| Argument/Flag | Default | Description |
|---------------|---------|--------------|
| `--title` | *(required)* | EPIC title |
| `--children` | *(required)* | JSON array of `{type,title,priority,summary}` objects, or `@file` (or `@-` for stdin) |
| `--priority` / `-p` | `P2` | EPIC priority |
| `--stage` | `false` | `git add` every created file in one call on success |
| `--json` / `-j` | `false` | Print `{"epic": {...}, "children": [...]}` instead of text |

**Examples:**
```bash
ll-issues scaffold-epic --title "Ship X" --children '[{"type":"FEAT","title":"Do A","priority":"P2"}]' --json
ll-issues scaffold-epic --title "Ship X" --children @children.json --stage
```

---

**Examples:**
```bash
ll-issues next-id
ll-issues list --type FEAT --priority P2
ll-issues list --priority P1,P2              # Filter by multiple priorities
ll-issues list --json                         # JSON array of all active issues
ll-issues list --type BUG --json             # JSON filtered by type
ll-issues count                              # Total active issue count
ll-issues count --json                       # JSON with breakdowns
ll-issues count --type BUG                   # Count bugs only
ll-issues count --status done                # Count done issues
ll-issues count --status all                 # Total across all statuses
ll-issues show FEAT-518
ll-issues show 518
ll-issues show FEAT-518 --json        # Issue fields as JSON
ll-issues path 1009                   # Resolve numeric ID to file path
ll-issues path FEAT-1009              # Resolve TYPE-NNN to file path
ll-issues path P3-FEAT-1009           # Resolve full ID to file path
ll-issues path FEAT-1009 --json       # Output as {"path": "..."}
ll-issues search "caching"                   # Search by keyword
ll-issues search --type BUG --priority P0-P2  # Filter bugs by priority range
ll-issues search --since 2026-01-01 --json   # Issues since date as JSON
ll-issues sequence --limit 10
ll-issues sequence --json             # Ordered sequence as JSON
ll-issues impact-effort
ll-issues impact-effort --type BUG    # Only bugs
ll-issues impact-effort --json        # JSON object with quadrant arrays
ll-issues impact-effort --json --type BUG  # Filtered JSON output
ll-issues refine-status
ll-issues refine-status FEAT-873              # Single-issue view
ll-issues refine-status FEAT-873 --json       # Single issue as JSON object
ll-issues refine-status --type BUG --format json
ll-issues next-action                            # Next refinement action needed (exits 1 if work remains)
ll-issues next-action --refine-cap 3             # Lower the refine-cap
ll-issues next-action --ready-threshold 90       # Stricter readiness threshold
ll-issues next-action --skip ENH-929,BUG-001     # Exclude specific issues from consideration
ll-issues next-issue                             # Highest-confidence issue ID
ll-issues next-issue --json                      # As JSON: {id, path, outcome_confidence, confidence_score, priority}
ll-issues next-issue --path                      # File path only (for shell scripting)
ll-issues next-issue --skip FEAT-007,BUG-001     # Exclude specific issues from consideration
ll-issues next-issues                            # All active issues in ranked order
ll-issues next-issues 5                          # Top 5 ranked issues
ll-issues nxs --json                             # Ranked list as JSON array
ll-issues nxs --path                             # Ranked list as file paths
ll-issues skip FEAT-955                          # Deprioritize to P5
ll-issues skip BUG-042 --priority P4 --reason "retry after CI fix"
ll-issues append-log .issues/bugs/P2-BUG-123-foo.md /ll:refine-issue
ll-issues anchor-sweep --dry-run                 # Preview file:line rewrites
ll-issues anchor-sweep                           # Rewrite file:line refs in active issues
ll-issues asw --dry-run                          # Alias: asw
ll-issues set-status ENH-1725 in_progress        # Transition status
ll-issues sst BUG-042 done                       # Alias: sst
ll-issues epic-progress EPIC-1773                # EPIC progress summary (text)
ll-issues ep EPIC-1773 --format json             # EPIC progress as JSON
ll-issues ep EPIC-1773 --format markdown         # EPIC progress as markdown
```

---

#### `ll-issues clusters` / `ll-issues cl`

Visualize issue dependency clusters. Walks all relationship types across active issues by default and renders each connected component. The default `tree` layout draws an indented, multi-root dependency tree (`├──`/`└──` connectors) in which **every** edge is shown — hub/parent hierarchies (e.g. one EPIC with many `parent:` children) render with the hub at the root and depth shown naturally, and DAG cross-edges or cycle back-edges appear as `⤷` cross-references rather than being demoted to a trailing skip-edge list.

**Flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--layout {tree,list,boxes}` | `tree` | Diagram layout. `tree` (default): indented multi-root dependency tree with every edge shown inline. `list`: one line per issue with edge annotations (compact). `boxes`: legacy vertical box-stack with arrows between consecutive boxes and a trailing skip-edge list. An explicit `--layout` overrides `--compact`. |
| `--compact` / `--summary` | off | Alias for `--layout list`. |
| `--edges SET` | `all` | Relationship types to follow. Aliases: `all` (all types), `blocking` (`blocked_by`+`blocks` only — legacy behaviour), `hard` (`blocked_by`+`blocks`+`depends_on`). Or a comma-separated list of: `blocked_by,blocks,depends_on,relates_to,parent`. |
| `--status SET` | `active` | Issue statuses to include. Aliases: `active` (`open`/`in_progress`/`blocked`), `+deferred` (active + deferred), `all` (everything except cancelled). Or a comma-separated list of canonical status values. |
| `--cluster N` | — | Render only the Nth cluster (1-indexed). |
| `--limit N` | — | Render at most N clusters; the footer reports how many were suppressed. |
| `--include-orphans` | off | Include 1-issue clusters (isolated issues with no relationships). |
| `--min-connections N` | 0 | Only show clusters where at least one issue has N or more connections. |
| `--json` / `-j` | off | Output as JSON array. Each element has `cluster_index`, `issue_count`, `issues`, and `edges` (with `relationship` values: `blocked_by`, `blocks`, `depends_on`, `relates_to`, `parent`). Output is identical across all `--layout` values. |

**Examples:**

```bash
ll-issues clusters                          # Indented dependency tree (default), active issues
ll-issues clusters --layout list            # Compact one-line-per-issue view
ll-issues clusters --layout boxes           # Legacy vertical box-stack
ll-issues clusters --edges=blocking         # Legacy view: blocked_by/blocks only
ll-issues clusters --status=+deferred       # Include deferred issues
ll-issues clusters --status=all             # All statuses except cancelled
ll-issues clusters --json | jq '[.[] | {n: .issue_count, types: [.edges[].relationship] | unique}]'
ll-issues cl --include-orphans              # Show isolated issues too
```

---

#### `ll-issues anchor-sweep` / `ll-issues asw`

Scan all active issue files (`bugs/`, `features/`, `enhancements/`, `epics/`) for bare `file:line` references outside code fences and rewrite them to enclosing function/class/section anchors. Uses a language-agnostic regex backwards-scan (no AST) covering Python, TypeScript, JavaScript, Go, Rust, Ruby, Java, C#, and Markdown.

| Flag | Description |
|------|-------------|
| `--dry-run` | Print what would change without modifying files |
| `--issues-dir DIR` | Issues base directory (default: `.issues`) |

**Behavior:**
- Scans backwards from the cited line number to find the nearest enclosing `def`/`func`/`fn`/`function`/`class`/`struct`/`#` heading.
- Replaces `file.py:42` with `` `file.py` (near function `foo`) ``.
- References inside code fences are skipped.
- References with no resolvable anchor are left unchanged with a warning.
- Always run `--dry-run` before the first production sweep.

**Examples:**
```bash
ll-issues anchor-sweep --dry-run
ll-issues anchor-sweep
ll-issues anchor-sweep --issues-dir custom/issues
ll-issues asw --dry-run
```

---

#### `ll-issues research-triage`

Report which of `/ll:refine-issue`'s three research axes an issue already covers, so Step 3 can spawn only the subagents whose findings are actually missing (ENH-2971). Pure function of the issue file plus disk state — no model call.

| Argument | Description |
|----------|-------------|
| `issue_id` | Issue ID to triage (e.g. `ENH-2971`) |

| Flag | Description |
|------|-------------|
| `--json` / `-j` | Emit `{"locator": {...}, "analyzer": {...}, "pattern_finder": {...}}`, each value `{"covered": bool, "evidence": str}` |
| `--config` | Path to project root |

**Axes and what satisfies them:**

| Axis | Sections read | Also requires |
|------|---------------|---------------|
| `locator` | `## Integration Map` | — (the locator's output *is* a set of file locations) |
| `analyzer` | `## Root Cause`, `## Current Behavior` | a backtick-quoted symbol in the same section |
| `pattern_finder` | `## Proposed Solution` | a backtick-quoted symbol in the same section |

**Behavior:**
- Path references are extracted with `extract_file_paths()` (code fences stripped) and classified with `classify_file_ref()` — globs, `<placeholder>` paths and bare basenames come back `unresolvable_form` and are excluded from both sides of the fraction. `resolved`, `stale`, and `ambiguous` (ENH-2999) all stay denominator-eligible; only `resolved` counts toward the numerator.
- An axis is **covered** when **≥80%** of its qualified references resolve. The rule is fraction-based on purpose: per-path staleness is ~15% at every Integration Map size, so an "all must resolve" rule would compound to `0.85^k` and measure map *size* rather than currency.
- **Staleness**: every resolved path's `max(git commit time, filesystem mtime)` is compared against the issue's most recent `` `/ll:refine-issue` `` `## Session Log` timestamp. A target that moved after that pass makes the axis uncovered, with `evidence` naming the stale path. Both clocks are needed — a git-only check misses uncommitted working-tree edits. An issue with no prior refine entry skips the comparison.
- **Program Design gate override (BUG-3003)**: on a project where the Program Design gate is active for this issue (`.ll/program-design-cutover.json` stamped, issue not grandfathered, `program_design_not_applicable` not set), `analyzer` is forced `covered: false` — regardless of Root Cause/Current Behavior evidence — whenever `## Program Design` is missing, empty, boilerplate, or graded non-specific, with `evidence` naming the gate as the reason. Without this override, an already-refined issue with a resolving Root Cause would triage `analyzer: covered` and `/ll:refine-issue` would never re-spawn the analyzer agent needed to write the section.
- **Exit 0 whenever the issue is readable, including when every axis is unmet** — a nonzero exit there would be indistinguishable from a missing issue. Only an unresolvable issue ID exits 1.

**Examples:**
```bash
ll-issues research-triage ENH-2971
ll-issues research-triage ENH-2971 --json
```

---

#### `ll-issues fold-findings`

Merge a markdown batch from **stdin** into the single `### Codebase Research Findings` block under a named H2, folding any blocks that have stacked up from earlier passes (ENH-2993). This is the only supported route for `/ll:refine-issue` to write a findings block — hand-writing the heading re-creates the sibling-block accumulation the command exists to prevent.

| Argument | Description |
|----------|-------------|
| `issue_id` | Issue ID to write into (e.g. `ENH-2993`) |

| Flag | Description |
|------|-------------|
| `--section` | **Required.** Parent H2 heading text, without the leading `## `. Matched case-insensitively, whitespace-stripped |
| `--dry-run` | Print the resulting block to stdout and write nothing |
| `--no-create` | Exit 2 instead of creating `--section` when it is absent |
| `--config` | Path to project root |

**Behavior:**
- **stdin is a verbatim markdown block, never parsed into bullets.** It is inserted byte-for-byte apart from trailing-newline normalization, so multi-line bullets with continuation indents and `**Option A**` / `**Option B**` blocks at column 0 (which carry no `- ` bullets at all, and which `count_enumerable_options()` must still find) both survive intact. Content goes on stdin rather than argv because the payload carries backticks, `$`, `!`, em-dashes and newlines.
- The `###` heading and the dated `_Added by `/ll:refine-issue` — YYYY-MM-DD — based on codebase analysis:_` provenance line are both supplied by the command. One heading per H2; one provenance line per merged batch, since pass boundaries are load-bearing for ENH-2995's superseded carve-out and ENH-2992's contradiction detection.
- **Fold-on-touch**: 0 existing blocks → create one at the end of the H2 slice (after any nested H3s, before the next `##`). 1 → append beneath it. N>1 → collapse all N into the *first* block's position, in document order, then append the new batch.
- **Relocation only** — nothing is deleted, summarized or deduped. Every bullet and every earlier provenance line survives. Consequently folding identical bullets twice yields them twice, by design; the invariants are the heading count (1 per H2) and provenance-line conservation (M in, M+1 out).
- No corpus sweep: an H2 the command never writes to keeps its stack. The `duplicate_findings_block` gap in `ll-issues format-check` keeps the remaining backlog visible.
- Findings are always addressed by their nearest **H2** ancestor, even when the bullets logically belong to an H3 beneath it (`### Files to Modify` under `## Integration Map`).

**Exit codes:**

| Code | Meaning |
|------|---------|
| `0` | Folded — including when the findings block or the parent H2 had to be created. A missing `--section` is created in v2.0 template order, because `/ll:refine-issue` legitimately populates sections that do not yet exist |
| `1` | Issue ID does not resolve, or stdin carried no payload |
| `2` | `--section` names an absent H2 and `--no-create` was passed |

**Examples:**
```bash
ll-issues fold-findings ENH-2993 --section "Program Design" <<'EOF'
- `find_subsections()` returns all matches, not one — see `scripts/little_loops/issues/fold_research_findings.py`
EOF

ll-issues fold-findings ENH-2993 --section "Integration Map" --dry-run < findings.md
```

---

#### `ll-issues fingerprint` / `ll-issues fp`

Extract a structured fingerprint from an issue file for cross-theme conflict detection. Returns JSON with the issue id, `files_to_modify` (file paths from the Integration Map), and `key_terms` (significant words after stop-word filtering). Used by `/ll:audit-issue-conflicts --cross-theme` Phase 2b to identify cross-batch overlap pairs without an LLM call.

| Argument | Description |
|----------|-------------|
| `issue_path` | Path to the issue file (absolute or relative to project root) |

**Output (JSON):**
```json
{"id": "ENH-1801", "files_to_modify": ["scripts/config.py"], "key_terms": ["authentication", "conflict"]}
```

**Examples:**
```bash
ll-issues fingerprint .issues/enhancements/P3-ENH-1801-example.md
ll-issues fp .issues/bugs/P2-BUG-042-example.md
```

---

#### `ll-issues find-similar` / `ll-issues fs`

Score title word-overlap similarity (Jaccard, via `text_utils.py`) between a query text and the issue corpus, or pairwise across the whole corpus in `--batch` mode. Distinct from `ll-issues search`: `search` filters/sorts issues by fields and substrings, while `find-similar` scores fuzzy text similarity between titles. Both modes compare **titles only**, never full issue bodies.

| Argument/Flag | Description |
|----------------|-------------|
| `text` | Text to score against issue titles (omit when using `--batch`) |
| `--batch` | Pairwise title-similarity scan over the corpus instead of single-text mode |
| `--against open\|all` | Corpus to compare against (default: `open`) |
| `--threshold T` | Minimum score to include (default: `config.issues.duplicate_detection.similar_threshold`) |
| `--limit N`, `-n N` | Cap the number of returned results |

**Output (JSON), single-text mode:**
```json
[{"id": "ENH-1801", "title": "Add fingerprint conflict detection", "path": ".issues/enhancements/P3-ENH-1801-example.md", "score": 0.667}]
```

**Output (JSON), `--batch` mode:**
```json
[{"a": "BUG-100", "b": "BUG-101", "score": 0.5}]
```

**Examples:**
```bash
ll-issues find-similar "auth token refresh failure" --against all
ll-issues fs "auth token refresh failure" --threshold 0.6 --limit 5
ll-issues find-similar --batch --against open
```

---

**`check-*` family exit-code convention (BUG-3294):** every probe below
(`check-flag`, `check-decidable`, `check-design`, `check-acceptance-criteria`,
`check-verify-verdict`, `check-open-questions`, `check-readiness`) shares one
contract — **0** = yes / gate passes, **1** = no / genuine negative verdict,
**2** = cannot evaluate (the issue ID could not be resolved, or — for
`check-flag` — argparse usage errors such as a missing positional), **3**
reserved for future abstain semantics and never emitted today. Under the FSM
`shell_exit` evaluator this routes 0→`on_yes`, 1→`on_no`, 2+→`on_error`, so a
bad or renamed issue ID reaches the error branch instead of being silently
treated as a real "no". Scope boundary: a resolvable issue file whose
frontmatter fails to parse, or that is simply missing the queried field,
still returns 1 — only the not-found half of "cannot evaluate" is separated
by this convention.

#### `ll-issues check-flag` / `ll-issues cf`

Exit 0 if a named boolean frontmatter field in the issue equals `true`. Designed for use as a shell gate in FSM loop states.

| Argument | Description |
|----------|-------------|
| `issue_id` | Issue ID (e.g., `518`, `FEAT-518`, `P3-FEAT-518`) |
| `field` | Frontmatter field name (e.g., `decision_needed`) |

**Examples:**
```bash
ll-issues check-flag 518 decision_needed   # Exit 0 if decision_needed: true
ll-issues cf FEAT-518 implementation_ready # Exit 0 if implementation_ready: true
```

**FSM loop use**: Use as a shell action with `evaluate: {type: exit_code}` to branch on a single frontmatter boolean without an LLM call.

Read-side counterpart to `ll-issues set-flags` (ENH-2946), which writes
`decision_needed`/`missing_artifacts`/`implementation_order_risk`/`spike_needed`
from confidence-check findings — this command is the gate that reads them back.

**Which gate states consume which flag (ENH-3250):** `decision_needed` is read
by `check_decision_mid_refine`/`check_decision_mid_wire`/`check_decision_needed`
in `refine-to-ready-issue.yaml` and by `check_decision_before_size_review` in
`autodev.yaml`. `missing_artifacts` is read by `check_missing_artifacts` in both
loops. `spike_needed` is read by `check_spike_needed` in both loops (paired with
a `spike_attempted` re-check via an inline `show --json` predicate, not a plain
`check-flag` call, since the gate is a two-field one-shot guard).
`implementation_order_risk` is written by `set-flags` but **consumed by no gate
state anywhere in the repo** — it remains a recorded-but-unrouted flag; wiring it
needs its own issue that first defines the remedy an `on_yes` branch would route
to. `unproven_mechanism` (ENH-3350, written by `/ll:refine-issue`, not
`set-flags`) is **not itself read by any loop gate state** — it affects gating
only indirectly, by making `/ll:confidence-check` cap `outcome_confidence`
below `outcome_threshold`, which in turn makes `set-flags`' `spike_needed`
`FlagRule` fire directly on the `unproven_mechanism: true` frontmatter trigger
(bypassing its usual `score_test_coverage <= 10` numeric gate and phrase
match). `check_spike_needed` (both loops, above) is the actual gate this
reaches — the same state `spike_needed` already routes to.

---

#### `ll-issues check-decidable`

Exit 0 if an issue has >=1 enumerable option to decide between (ENH-2443). Deterministic (no-LLM) companion to `/ll:decide-issue --validate-only` — re-implements the same option-extraction patterns in pure Python (`count_enumerable_options`), so FSM `shell` states can pre-check decidability without dispatching an LLM call. Mirrors the `ll-issues format-check` / `ensure_formatted` precedent (ENH-2426). Also covers Pattern E — un-preferenced decision directives (ENH-2936): a passage naming 2+ concrete alternatives alongside an imperative decide-marker ("decide before implementation", "do not leave unaddressed") but no stated preference, not just formal `### Option A/B` blocks. The Pattern E probe runs alongside every other stage, not only when they all miss (BUG-3287): when a tier match wins the gate and a separate directive is also present, the success line names it as a residual, uncounted decision point (`+ residual decision directive in '<heading>' (line N) — not counted`) rather than silently dropping it.

| Argument | Description |
|----------|-------------|
| `issue_id` | Issue ID (e.g., `518`, `FEAT-518`, `P3-FEAT-518`) |

**Examples:**
```bash
ll-issues check-decidable FEAT-398   # Exit 1 (OPTIONS_MISSING) — no enumerable options
ll-issues check-decidable ENH-277    # Exit 0 — 2+ options found
```

**FSM loop use**: The `check_decision_decidable` gate lives in the shared `oracles/resolve-decision.yaml` sub-loop (extracted from `autodev.yaml` by BUG-3065/ENH-3075; adopted by `rn-remediate.yaml` via ENH-3090) and calls this as a shell action with `evaluate: {type: exit_code}`, routing to a bounded `/ll:refine-issue --auto` deposit-options retry on exit 1 rather than letting `run_decide` run with nothing to score.

---

#### `ll-issues check-design`

Exit 0 if the Program Design gate passes for an issue (ENH-2967). Single owner of the `design_gate_failed()` predicate (`issue_parser.py`, beside `FormatGaps`) — a `bool(program_design_nonspecific) or "Program Design" in missing or "Program Design" in empty` OR that `autodev.yaml` previously re-derived independently in three inline `python3 -c "..."` blocks, each with its own fail-quiet `except Exception` / `|| echo "false"` scaffolding. Fails open (exit 0) on projects that haven't armed the Program Design specificity gate (no `.ll/program-design-cutover.json` stamp), mirroring `check_format_gaps()`'s existing fail-open behavior.

| Argument | Description |
|----------|-------------|
| `issue_id` | Issue ID (e.g., `518`, `FEAT-518`, `P3-FEAT-518`) |

**Examples:**
```bash
ll-issues check-design BUG-2967   # Exit 0 — gate passes or is inert
ll-issues check-design BUG-9999   # Exit 2 — issue not found (BUG-3294)
```

**FSM loop use**: `autodev.yaml`'s `recheck_scores`, `regate_after_atomic_remediation`, and `recheck_after_size_review` states each call `ll-issues check-design "$ID"` in place of the old inline JSON-parsing block, chaining its exit code into the surrounding readiness/outcome gate exactly like the `check-readiness` idiom.

---

#### `ll-issues check-acceptance-criteria`

Exit 0 if every `## Acceptance Criteria` checkbox item is machine-checkable, 1 if any require manual verification (ENH-3031). Deterministic companion to the readiness gates — lets an FSM `shell` state reject an issue whose ACs can only be confirmed by a human before spending a run on it.

| Argument | Description |
|----------|-------------|
| `issue_id` | Issue ID (e.g., `3031`, `ENH-3031`, `P2-ENH-3031`) |

| Flag | Description |
|------|-------------|
| `--config` | Path to `ll-config.json` |

**Examples:**
```bash
ll-issues check-acceptance-criteria ENH-3031   # Exit 0 — all criteria machine-checkable
ll-issues check-acceptance-criteria BUG-3186   # Exit 1 — at least one needs manual verification
```

---

#### `ll-issues check-verify-verdict`

Exit 0 if the issue's persisted `verify_verdict` is `VALID` **or absent** (fail-open), 1 if it is `NON_VALID` (ENH-3031). On failure it writes the token `VERIFY_VERDICT_NON_VALID` to stderr so an FSM evaluator can route on the reason rather than the bare exit code.

| Argument | Description |
|----------|-------------|
| `issue_id` | Issue ID (e.g., `3031`, `ENH-3031`, `P2-ENH-3031`) |

| Flag | Description |
|------|-------------|
| `--config` | Path to `ll-config.json` |
| `--proposal-unsound` | Query mode (ENH-3250): exit 0 if `verify_verdict == PROPOSAL_UNSOUND`, 1 otherwise (including when the field is absent). Does not change the default flag's VALID/NON_VALID contract — `PROPOSAL_UNSOUND` still exits 1 without this flag. Used by `refine-to-ready-issue.yaml`'s `check_proposal_unsound` gate to route that failure kind to `reconcile_issue` instead of `refine_followup`. |

**Examples:**
```bash
ll-issues check-verify-verdict ENH-3031   # Exit 0 — verdict VALID, or never recorded
ll-issues check-verify-verdict BUG-9999   # Exit 1 — verdict NON_VALID (stderr: VERIFY_VERDICT_NON_VALID)
ll-issues check-verify-verdict ENH-3250 --proposal-unsound  # Exit 0 only if verdict is PROPOSAL_UNSOUND
```

---

#### `ll-issues locate-options`

Print count/pattern/heading/spans of enumerable options in an issue (ENH-2950). Data frontend over the same `issue_parser.locate_enumerable_options()` precedence chain `check-decidable` gates on — where `check-decidable` only reports an exit code, this exposes the full result so a consumer (notably `/ll:decide-issue` Phase 3/3b) can read option spans instead of re-implementing the same pattern precedence in prose.

| Argument/Flag | Description |
|---------------|-------------|
| `issue_id` | Issue ID (e.g., `518`, `FEAT-518`, `P3-FEAT-518`) |
| `--json`, `-j` | Output as JSON object |

**Examples:**
```bash
ll-issues locate-options ENH-2950 --json
# {"id": "ENH-2950", "count": 2, "pattern": "bold_label", "heading": "Proposed Solution",
#  "options": [{"label": "Option A", "text": "...", "start_line": 12, "end_line": 14}, ...],
#  "residual_directive": null}
```

`pattern` names which precedence tier fired: `section_header` (`### Option A`), `bold_label` (`**Option A**: ...`), `numbered` (`1. **Option A** ...`), `bullet` (`- (a) ...` / `- **(a) ...**`), `decision_rules_numbered` (2+ bold-numbered items under `## Program Design → ### Decision Rules`, e.g. `1. **Identifier shape.** ...`, BUG-3293), or `provisional_e` (an un-preferenced decision directive, ENH-2936/BUG-3293 — `options` holds a single span covering the matched window rather than per-alternative entries, since that heuristic only proves a decision exists, not how many alternatives). `pattern`/`heading` are `null` and `options` is empty when `count` is 0.

`residual_directive` (BUG-3287): a co-located Pattern E directive that a tier or H2-scan match preempted from being the primary result — the directive probe runs alongside those stages, not only as a terminal fallback, so a document holding both an enumerated option set and a separate un-preferenced decision directive reports both. It is a nested `LocatedOptions` object (same shape, `pattern` always `"provisional_e"`) rather than a bare option, and is `null` whenever no such directive exists (including on the nested object itself — it never recurses). The human-readable (non-`--json`) output prints an additional `+ residual decision directive in '<heading>' (line N) — not counted` line when present.

**FSM loop use**: Prefer `check-decidable` for a pure gate (`evaluate: {type: exit_code}`); use `locate-options --json` when a downstream state needs the actual option text, not just a boolean.

---

#### `ll-issues check-unresolved-decisions`

Decision-*group*-aware residual probe (BUG-3278). Not a drop-in substitute for `check-open-questions`: that command counts unresolved *option blocks* (a decided 3-option group with 2 losers reports 2, not 0) plus free-form open questions elsewhere; this command counts unresolved *decision points* — Phase 7a of `/ll:decide-issue` marks only the winning option, so the unit of resolution has to be the decision point, not the block, or a correctly-decided single-decision issue would never clear `decision_needed`. This is the gate `/ll:decide-issue` Phase 7b and Phase 3b step 4 run before writing `decision_needed: false`.

A group is resolved when any member option's own span carries a `> **Selected:**` callout, or the group's enclosing section carries a `### Decision Rationale` subsection AND holds exactly one group (the single-group restriction — an unrestricted section-level check would let deciding one group in a multi-group section silently resolve every sibling group by side effect). Runs with the widened tier scan (`numbered`/`bullet` tiers plus a co-located Pattern E directive), unlike `check-open-questions`'/`check_open_question_progress`'s conservative default. Never reports a `decision_rules_numbered` block (BUG-3293's Program Design → Decision Rules) as a decision group — those are settled design rulings, not alternatives to pick between.

| Argument/Flag | Description |
|---------------|-------------|
| `issue_id` | Issue ID (e.g., `3278`, `BUG-3278`, `P2-BUG-3278`) |
| `--json`, `-j` | Output as JSON object |

**Exit codes**: `0` — no unresolved decision group remains. `1` — `UNRESOLVED_DECISIONS_REMAIN`, naming each surviving group's heading and line range. `2` — the issue ID does not resolve. Exit 2 is not a divergence from `check-open-questions`/`check-decidable` — BUG-3294 already moved both of those to 2 for a missing issue; all three probes agree on the house convention (0 clean / 1 residual-or-negative / 2 unresolvable). The FSM `exit_code` evaluator maps 0→`on_yes`, 1→`on_no`, 2+→`on_error` (`fsm/evaluators.py:255-259`), which is why 2 is distinct from 1 — collapsing them would make an unresolvable ID indistinguishable from a genuine residual.

**Examples:**
```bash
ll-issues check-unresolved-decisions BUG-3278 --json
# {"id": "BUG-3278", "unresolved": [{"heading": "Proposed Solution", "tier": "bullet",
#  "options": [...], "start_line": 24, "end_line": 25}]}

ll-issues check-unresolved-decisions ENH-2446   # Exit 0 — no unresolved decision group
```

**FSM loop use**: `oracles/resolve-decision.yaml`'s `check_residual_decision` state runs this after `assert_decision_cleared` finds the flag still set — exit 1 (a real residual) routes to `done`, exit 0 (nothing justifies the still-set flag) preserves BUG-2595's silent-no-op detection and routes to `failed`.

---

#### `ll-issues check-open-questions`

Coverage-aware decidability probe (ENH-2446). Companion to `check-decidable` — exits 0 only when **both** (a) every option block in `## Proposed Solution` carries a `> **Selected:**` or `### Decision Rationale` marker AND (b) no bullet items in `## Edge Cases` / `## Confidence Check Notes` / `## Open Questions` carry an open-question signal (`Q:`, `?`, `open question`, `needs decision`, `decision needed`, `open decision`, `unresolved decision`, `decision point`) without a `✅ RESOLVED` / `✔ RESOLVED` / `**RESOLVED**` / `> **RESOLVED**` marker. Exits 1 with `OPEN_QUESTIONS_REMAIN: <ID> — N open question(s) and M unresolved option(s); run /ll:refine-issue <ID> --auto` otherwise.

Closes the mixed-issue gap that the count-based `check-decidable` misses: an issue with already-resolved options PLUS unresolved free-form questions previously routed straight to `decide` (an idempotent no-op) and bypassed `deposit_options` entirely.

| Argument | Description |
|----------|-------------|
| `issue_id` | Issue ID (e.g., `2446`, `ENH-2446`, `P2-ENH-2446`) |

**Examples:**
```bash
ll-issues check-open-questions FEAT-2339  # Exit 1 (mixed: 0 unresolved options + N open questions)
ll-issues check-open-questions ENH-2446   # Exit 0 — no unresolved decision surface
```

**FSM loop use**: The `check_decision_decidable` gate in `oracles/resolve-decision.yaml` (the shared sub-loop `rn-remediate.yaml` and `autodev.yaml` both call into, per ENH-3090/ENH-3075) chains this probe BEFORE `check-decidable` (`check-open-questions || check-decidable`) so the coverage gap is caught before the count-based fallback runs. Pair with the `open_question_stall` evaluator (`open_question_stall_gate` fragment in `lib/common.yaml`) for progress-gated re-fire.

---

#### `ll-issues format-check`

Deterministic (no-LLM) structural linter for issue formatting (ENH-2426). Grades an issue against its type template and reports gaps in twenty-six classes (re-derive this count from `dataclasses.fields(FormatGaps)` rather than trusting the number written here): `missing` (a required section header absent entirely), `renamed` (a present section header is deprecated with an extractable canonical replacement, e.g. `Proposed Fix` → `Proposed Solution`), `empty` (a required header present with a whitespace-only body), `boilerplate` (a required section's body still equals its `creation_template`), `malformed_id` (frontmatter `id` present but not matching the filename-derived `TYPE-NNN`, BUG-2769), `prose_dep_drift` (FEAT-2849: the body claims a dependency in prose — "Depends on ID", "Blocked by ID", "Requires ID", the synonyms "blocked on"/"gated on"/"waiting on"/"contingent on"/"predicated on", or a `## Blocked By` section — on an active issue absent from `blocked_by`/`depends_on`; temporal phrasings like "after ID"/"once ID" are deliberately not matched), `stale_prose_dep` (FEAT-2849: the body's prose dependency claim names a `done`/`cancelled` issue — the remedy is deleting the stale text, not adding an edge), `program_design_nonspecific` (ENH-2852: the `## Program Design` section is present and non-boilerplate but lacks a signature-shaped line or a resolving `Call Path` anchor; opt-in per project via `.ll/program-design-cutover.json`), `deprecated_key` (ENH-2876: frontmatter carries a retired key like hand-authored `superseded_by` or a coerced status synonym like `status: completed`, each reported with its mandatory prose reason), `multi_frontmatter` (BUG-2955: the issue carries more than one YAML frontmatter block in its header region), `testable`, `stale_file_ref`, `unmarked_superseded_directive`, `duplicate_findings_block`, `ambiguous_file_ref`, `missing_behavior_parity`, `soft_dep_hard_edge`, `malformed_dep_id`, `stale_symbol_ref`, `mislocated_symbol_ref`, `stale_cli_flag`, `duplicate_heading`, `empty_provenance_stub`, `template_placeholders`, `unapplied_decision` (ENH-3256: a recorded `> **Selected:**` decision whose rejected option's discriminating identifiers still appear, unmarked, in a directive section — caps `/ll:confidence-check` Criterion C), and `priority_drift` (BUG-3286: the filename's `P<n>-` prefix and the frontmatter `priority:` key are both present and disagree — the filename prefix is authoritative; the remedy is `ll-issues prioritize --apply`) (each documented below). Fails open — an unresolved template or unreadable issue file reports no gaps (exit 0) rather than blocking.

A single-ID run still parses the whole corpus internally (needed to classify `prose_dep_drift` vs `stale_prose_dep` against every other issue's status), but suppresses *other* issues' `deprecated frontmatter key` warnings rather than printing one line per offending file — the targeted issue's own warnings (if any) still surface normally. When other issues were suppressed, a one-line stderr tally follows the verdict: `(N other issue(s) have deprecated frontmatter keys — run \`ll-issues format-check\` to list)`. The full `--all` sweep is unaffected — it still reports every file's deprecated keys (ENH-2961).

Also reports `testable` (ENH-2946, precision-tuned by ENH-2966): a doc-only
keyword inference (signal-keyword tuple, 2+ distinct word-boundary matches
against title + `## Summary` only) advising that the issue looks
documentation-only — advisory only, never auto-written; a caller uses it to
decide whether to add `testable: false`. It is also non-gating (ENH-2966
Option E): a `testable`-only gap is still reported in every output surface,
but does not fail `format-check`'s exit code (`FormatGaps.has_blocking_gaps`,
narrower than the reporting predicate `has_gaps`).

Also reports `stale_file_ref` (ENH-2983; reworded BUG-3194): a file path
reference extracted from the body classifies as `stale` — a `/`-qualified
path that is not git-tracked (`little_loops.text_utils.classify_file_ref()`
against a `RefIndex` built once per invocation from `git ls-files`). This
covers both a file that moved/was deleted *and* a file that is present on
disk but gitignored — the printed line states the actual predicate
("not git-tracked; it may exist on disk but gitignored") rather than
implying the file is missing. A bare basename, glob (including brace
expansion `{a,b}`), `<placeholder>`-bearing path, or a slash-joined pair of
filenames (`ARCHITECTURE.md/CONTRIBUTING.md` — two filenames joined by
prose, not one path) is `unresolvable_form` and never reported here; a path
on a line marked `(new)` is `planned_new` and also never reported.
Reporting only — a moved file can't be safely re-pointed without knowing
intent.

Also reports `ambiguous_file_ref` (ENH-2999): a file path reference classifies
as `ambiguous` — the unrooted suffix matches more than one tracked file after
the host-adapter mirror tie-break, so the reference can't be resolved without
disambiguation. Distinct from `stale_file_ref`: the file was not deleted or
moved, the reference just lacks enough path prefix to pick one of several real
matches. Each entry names the candidate count and up to three candidate paths,
elided with `…` beyond that, e.g.
`agents/openai.yaml (66: skills/align-issues/agents/openai.yaml, …)`.

Also reports `missing_behavior_parity` (ENH-3045): a file ref in `## Summary`,
`## Proposed Solution`, or `### Files to Modify` resolves and shares a line
with a replacement keyword (`delete`, `remove`, `replace`, `rewrite`,
`supersede`, `delegate`, and their inflections — same line only), while no
`### Behavior Parity` subsection exists under `## Integration Map`. Suppressed
by `behavior_parity_not_applicable: true` in frontmatter (a human decision,
never set by `/ll:refine-issue` or `/ll:wire-issue` themselves).

Also reports `soft_dep_hard_edge` (ENH-3046): an ID in `blocked_by`/
`depends_on` that the body describes with soft-dependency language ("soft
dep", "optional", "nice to have", "has not landed") in the same
blank-line-delimited paragraph as the ID. The hard structured edge
contradicts the soft prose; remedy is moving the ID to `relates_to`, not
deleting the prose (the soft language is usually the accurate statement). No
suppression escape hatch.

Also reports `malformed_dep_id` (BUG-3059): an entry in `blocked_by`,
`depends_on`, `blocks`, `relates_to`, or `supersedes` that is not a
well-formed `TYPE-NNN` ID — most often a bare number (`depends_on: [3038]`
instead of `[FEAT-3038]`). This is not cosmetic: `DependencyGraph` matches
IDs by exact string, so a malformed entry drops the edge from the graph
entirely while only emitting a library-logger warning that is easily lost
among unrelated ones. The optional `P<n>-` filename prefix is accepted.

Also reports `stale_symbol_ref`, `mislocated_symbol_ref`, and `stale_cli_flag`
(FEAT-3048/BUG-3063), extending the same drift-detection architecture the
prose-dependency gap kinds use to two more claim classes issue bodies assert
in backticks. `stale_symbol_ref` fires when a backticked symbol is attributed
to a cited file that itself resolves (e.g. `` `extract_prose_deps` `` in
`` `prose_deps.py` ``, or the dotted
`` `prose_deps.extract_prose_deps` ``/explicit
`` `prose_deps.py:extract_prose_deps` `` forms) but the symbol does not
resolve as a function/class def-site or module-level constant in that file
**and** does not resolve as a def-site anywhere else in the repo either.
`mislocated_symbol_ref` (BUG-3063) is the mis-attribution sibling: the symbol
does not resolve in the cited file but does resolve in some other tracked
file — a mismatch between where the claim points and where the symbol
actually lives, not a stale claim. A claim is dropped before either check
(BUG-3194) — never rerouted between the two — when its symbol fails a
shape floor (under 3 characters, or all-lowercase with no underscore,
internal capital, or `()` suffix — kills index-pollution noise like `ec`,
`codex`, `enabled` while keeping `install_qwen_adapter`, `FSMExecutor`) or
resolves as a def-site in more than 8 tracked files other than the cited
one. Both are extracted only from a
current-state section allowlist (`## Summary`, `## Current Behavior`,
`## Root Cause`, `## Context`, matched by H2 span) — a symbol named in a
forward-looking section such as `## Program Design`, `### Files to Modify`,
or `## Implementation Steps` is never read as an existence assertion,
regardless of section name (allowlist, not denylist). `stale_cli_flag` fires
when a backticked `` `ll-<tool> <subcommand> [--flag ...]` `` invocation names
a subcommand or long flag the tool's argparse parser does not accept,
resolved via a `--help`-scraped surface index (short flags are ignored —
ambiguous in prose). A bare backticked identifier with no file attribution is
never a symbol claim. All three kinds respect the `<!-- ll-prose-ok: ... -->`
suppression comment on the line before a claim (the same convention
`cli/verify_skill_prose.py` uses). `stale_cli_flag` ships **report-only**
first (the repo-wide pytest sweep prints but does not fail the suite) until
measured precision on a sampled backlog slice clears the bar; the symbol-claim
sweep asserts a real ceiling as of BUG-3063.

Also reports `unmarked_superseded_directive` (ENH-2995): the issue's
`### Codebase Research Findings` block contains a correction phrase from a
closed list (`is wrong`, `does not exist`, `will not work`, `must be
dropped`, `target file is wrong`, `is stale`, `omit entirely` — the same
phrases `/ll:refine-issue`'s Preservation Rule carve-out uses as
non-exhaustive LLM guidance) while none of the three directive sections
(`## Implementation Steps`, `### Files to Modify`, `## Acceptance Criteria`)
carries a `⚠ Superseded` marker. Report-only keyword-inference heuristic
(like `testable`) — it flags that a correction and a marker are both
absent/present, not that the correction actually refutes a specific line.

Also reports `duplicate_findings_block` (ENH-2993): one entry per H2 —
formatted `"<H2 heading> (N)"` — carrying more than one
`### Codebase Research Findings` block. Evaluated **per H2**, not
document-wide: an issue with one block under each of several H2s is compliant.
`ll-issues fold-findings` clears the entry for any H2 it writes to; there is no
corpus sweep, so entries for untouched sections are expected and are reported
rather than fixed (`/ll:refine-issue` § 6.7 spells out the two branches).

The single-issue `--format json` payload additionally carries
`superseded_marker_count` (ENH-2992): an **integer** count of `⚠ Superseded`
markers actually present in those same three directive sections — the inverse
of `unmarked_superseded_directive` above, which reports the
refine-did-not-mark defect. Backed by the public helper
`issue_parser.superseded_marker_count()`. Marker presence is not a structural
gap, so it never affects `has_gaps` or the exit code; `autodev.yaml`'s
`check_reconcile_needed` reads this key as its contradiction predicate. Not
emitted on the `--all` payload, which maps `issue_id → gaps`.

Also reports `duplicate_heading` (ENH-3247) — the same `###` heading text
appearing more than once under one `##` parent, formatted
`"<H2> > <H3> (N)"` — and `empty_provenance_stub` (ENH-3247) — an
`_Added by \`/ll:refine-issue\` — DATE — based on codebase analysis:_`
provenance line with no bullet before the next heading or the next stub,
formatted `"line N"`. Both are structural debris, not content judgments: for
any given input there is exactly one correct output, so `--fix` can repair
them deterministically (no LLM). `duplicate_heading` excludes
`### Codebase Research Findings`, which stays owned by
`duplicate_findings_block`/`ll-issues fold-findings`. Both detectors mask
fenced code blocks — a duplicate heading or empty stub inside an illustrative
` ``` ` block is documentation, not a gap.

Also reports `template_placeholders` (ENH-3244) — a literal unfilled template
placeholder (e.g. `TBD - requires codebase analysis`, `[Major phase 1]`)
still present in the section whose `creation_template` emits it, formatted
`"<section>: <placeholder>"`. The pattern set is derived at runtime from
`scripts/little_loops/templates/*-sections.json`'s `creation_template`
values — not hand-transcribed — so a placeholder line added to a template
is picked up with zero code changes. Detection applies a three-part rule:
section-scoped (a mention in a different section does not count),
fence- and inline-backtick-masked (composed the way
`issues/prose_deps.py` masks prose dependency claims), and `## Program
Design` is excluded from the derived pattern set entirely — its
placeholders are the only ones every template already wraps in backticks,
so inline masking would swallow them anyway, and full/partial residue there
is already caught by `boilerplate`/`program_design_nonspecific`. A `--fix`
handler (ENH-3248) covers only the four tokens whose correct value is a pure
function of the issue's own frontmatter — `Impact: [P0-P5]` / `Status:
[P0-P5]` ← `priority`, `Status: [YYYY-MM-DD]` ← `discovered_date`, `Labels:
[type-label]` ← `type`. Every other placeholder (judgment assessments like
Effort/Risk/Breaking Change, and research-shaped prose like `TBD -` tokens)
needs content the tool cannot invent and is left untouched.

`--fix` runs every repair whose gap class fired, via a gap-class → repair
function dispatch table: `prose_dep_drift` (backfill `blocked_by` via
`ll-issues link`'s idempotent, cycle-safe write path — FEAT-2851; this is a
reactive backfill, layered with `/ll:refine-issue`'s Step 5a Dependency
Classification rule, ENH-3284, which can write the same edge proactively at
deposit time — the idempotent write makes either order safe),
`duplicate_findings_block` (collapse via the same transform
`ll-issues fold-findings` uses), `duplicate_heading` (collapse duplicate
headings, concatenating bodies in document order — never drops a body),
`empty_provenance_stub` (delete empty stubs, normalizing surrounding
whitespace to exactly one blank line), and `template_placeholders`
(ENH-3248: fill the four frontmatter-derivable tokens above; every other
placeholder token is left in place). Dry-run by default; combine with
`--apply` to write. **`--all --fix --apply` (sweep mode) is restricted to
`prose_dep_drift`** — the only repair that writes frontmatter through an
existing idempotent command rather than rewriting the markdown body; the
other four repairs run in single-issue mode only, to keep a sweep's blast
radius reviewable.

| Argument/Flag | Default | Description |
|---------------|---------|-------------|
| `issue_id` | _(required unless `--all`/`--next`)_ | Issue ID (e.g., `2426`, `ENH-2426`, `P3-ENH-2426`) |
| `--all` / `-a` | `false` | Sweep every active issue instead of one (FEAT-2850) |
| `--next` | `false` | Target the highest-priority active issue, no type filter (same selection as `find_highest_priority_issue`); mutually exclusive with `issue_id`/`--all`; exits 1 with "No active issues found." on an empty backlog (ENH-2946) |
| `--format {text,json}` | `text` | Output format |
| `--fix` | `false` | Preview repairs for `prose_dep_drift`, `duplicate_findings_block`, `duplicate_heading`, `empty_provenance_stub`, and `template_placeholders` (frontmatter-derivable tokens only) gaps via the repair dispatch table (dry-run by default; the latter four are single-issue mode only — ENH-3247, ENH-3248) |
| `--apply` | `false` | With `--fix`, write the proposed repairs instead of previewing them |

**Examples:**
```bash
ll-issues format-check ENH-2426               # text report, exit 0/1
                                               # stderr: "(N other issue(s) have deprecated frontmatter keys — run `ll-issues format-check` to list)" when applicable
ll-issues format-check ENH-2426 --format json # {"missing": [...], "renamed": [...], "empty": [...], "boilerplate": [...], "malformed_id": [...], "prose_dep_drift": [...], "stale_prose_dep": [...], "program_design_nonspecific": [...], "deprecated_key": [...], "multi_frontmatter": [...], "testable": [...], "stale_file_ref": [...], "unmarked_superseded_directive": [...], "duplicate_findings_block": [...], "ambiguous_file_ref": [...], "missing_behavior_parity": [...], "soft_dep_hard_edge": [...], "malformed_dep_id": [...], "stale_symbol_ref": [...], "mislocated_symbol_ref": [...], "stale_cli_flag": [...], "duplicate_heading": [...], "empty_provenance_stub": [...], "template_placeholders": [...], "unapplied_decision": [...], "priority_drift": [...], "superseded_marker_count": 0}
ll-issues format-check --all --fix            # preview blocked_by backfills for every drifting issue (dry-run)
ll-issues format-check --all --fix --apply    # write the previewed edges via `ll-issues link`
ll-issues format-check ENH-2426 --fix --apply # single-issue: also collapses duplicate headings/findings blocks, deletes empty provenance stubs, and fills frontmatter-derivable template placeholders
ll-issues format-check --next                 # target the highest-priority active issue
```

---

#### `ll-issues set-flags`

Writes `decision_needed` / `missing_artifacts` / `implementation_order_risk` /
`spike_needed` frontmatter flags from confidence-check findings (ENH-2946). Ports the
phrase-list + numeric-gate rules that used to live as prose in
`skills/confidence-check/SKILL.md` Phases 4.6/4.7/4.9/4.10 into data (`FLAG_RULES`,
`scripts/little_loops/cli/issues/set_flags.py`) — the CLI is now the single source of
truth; `check-flag` (already shipped) is its read-side counterpart. Rules evaluate in
declared order: `missing_artifacts`' co-deliverable suppression (a file named in the
findings that also appears under the issue's own `### Files to Create`) blocks that
write and makes `implementation_order_risk` fire instead, even without its own phrase
match. **Set-only**: never writes `false` — a flag already `true` is left alone when a
re-run's notes no longer match; clearing a flag stays owned by `/ll:decide-issue`.

| Argument/Flag | Default | Description |
|---------------|---------|-------------|
| `issue_id` | _(required)_ | Issue ID (e.g., `1307`, `BUG-1307`, `P0-BUG-1307`) |
| `--from-notes FILE` | _(issue's own notes)_ | Findings text to scan, or `-` for stdin; omit to read the issue's own `## Confidence Check Notes` section |
| `--dry-run` | `false` | Report what would be set without writing |
| `--json` / `-j` | `false` | Output as a JSON object: `{"id", "set_flags", "matched_phrases", "suppressed"}` — `suppressed` distinguishes "matched but suppressed" from "no phrase matched" |

**Examples:**
```bash
ll-issues set-flags BUG-1307                        # read the issue's own Confidence Check Notes
ll-issues set-flags BUG-1307 --from-notes - --json   # pipe findings on stdin, machine-readable output
ll-issues set-flags BUG-1307 --dry-run               # preview without writing
```

---

#### `ll-issues normalize`

Deterministic filename/ID-mechanics linter and fixer (ENH-2944), extracted from `commands/normalize-issues.md`'s mechanical rename/ID bookkeeping. Scans all categories/statuses for `missing_id`/`malformed_filename` filenames (fail `is_normalized()` — `malformed_filename` distinct from `format-check`'s own `malformed_id` gap class, which is frontmatter `id:` vs. filename drift, not a filename shape problem), `duplicate_id` (the same numeric ID used by >1 file — the oldest by git history keeps it, others get reassigned the next globally unique number via `get_next_issue_number()`), `legacy_dir` (non-empty `completed/`/`deferred/` directories, base-level or nested), and `type_mismatch` (a keyword-signal heuristic ported from the command's Step 1c: `confidence = signals_for_top_type / (total_signals + 1)`, flagged at ≥0.7; only reported for `open`/`in_progress`/`blocked` issues — `done`/`cancelled`/`deferred` are excluded (ENH-3053) since reclassifying closed work has no actionable follow-up).

`--auto` applies `missing_id`/`malformed_filename`/`duplicate_id` findings via `git mv` (shared `git_mv_with_fallback()` helper in `issue_lifecycle.py`, also used by `ll-issues skip`) — it never overwrites an existing path and never allocates a colliding ID. Each rename also writes the new ID into the moved file's frontmatter `id:` and repoints any inbound `blocked_by`/`depends_on`/`parent`/`epic`/`relates_to`/`supersedes` edge that named the reassigned ID. `type_mismatch` findings are **never** auto-applied: reclassification is a semantic judgment left to the calling command's LLM-review step, not a deterministic rename.

| Argument/Flag | Default | Description |
|---------------|---------|-------------|
| `ISSUE_ID...` | — | Scope reported/applied findings to these issues; duplicate detection and ID allocation always stay corpus-wide |
| `--check` | `false` | Check-only: exit 1 if any auto-fixable finding exists, 0 if clean (FSM `evaluate: type: exit_code` gate; implies no writes) |
| `--auto` | `false` | Apply auto-fixable findings via `git mv` + frontmatter/edge sync |
| `--strict` | `false` | Widen `--check`'s exit code to also cover `legacy_dir`/`type_mismatch` |
| `--json` | `false` | Print `{"findings": [...], "applied": [...]}` instead of text |

**Examples:**
```bash
ll-issues normalize --check           # FSM gate: exit 0 clean / 1 violations found
ll-issues normalize --auto --json     # apply ID-mechanics fixes, print JSON report
ll-issues normalize ENH-2944 --auto   # scope to one issue
```

No loop currently wires `normalize --check` into its routing — the exit-code contract above is designed for a future consumer (the convergence guarantee makes it safe to adopt later), not an existing gate.

---

#### `ll-issues size`

Deterministic size scoring for `issue-size-review` (ENH-2945), replacing the skill's
hand-computed Phase 1-3 scoring table. Computes five signals over an issue's parsed body —
`file_count` (>=3 distinct file paths via `text_utils.extract_file_paths`, +2), `section_complexity`
(a `Proposed Solution`/`Implementation Steps`/`Implementation` section >300 words, +2),
`multiple_concerns` (>=2 `###` subsections in that section, or "additionally"/"also need to"
phrasing, +3), `dependency_mentions` (a `BUG-`/`FEAT-`/`ENH-`/`EPIC-` reference other than the
issue's own ID, or "depends on"/"blocked by" phrasing, +2), and `word_count` (>800 words total,
+2) — for a 0-11 total mapped to a label: `Small` (0-2) / `Medium` (3-4) / `Large` (5-7) /
`Very Large` (8+). The weight table (`SIZE_SIGNAL_WEIGHTS`) lives in
`scripts/little_loops/cli/issues/size.py` as the single source both the CLI and the skill's
prose reference.

Exactly one of a bare `ISSUE_ID`, `--all`, or `--sprint NAME` selects the scoring target.
`--all` scores active bugs/features/enhancements (excludes EPICs, matching the skill's original
Phase 1 backlog scan). `--write` stamps the `size:` frontmatter field via `update_frontmatter`;
without it, scoring is read-only.

| Argument/Flag | Default | Description |
|---------------|---------|-------------|
| `ISSUE_ID` | — | Score a single issue (mutually exclusive with `--all`/`--sprint`) |
| `--all` | `false` | Score all active bugs/features/enhancements |
| `--sprint NAME` | — | Score only the issues listed in `.sprints/NAME.yaml` |
| `--write` | `false` | Stamp `size:` frontmatter with the computed label |
| `--json` | `false` | Print `[{"id", "score", "label", "signals": {...}}, ...]` instead of text |

**Examples:**
```bash
ll-issues size ENH-2945                    # score one issue, text output
ll-issues size --all --json                # score the backlog, JSON report
ll-issues size --sprint my-sprint --write  # score + stamp size: for a sprint's issues
```

**Scope note**: this CLI covers Phases 1-3 only (scoring + frontmatter write-back). Phase 6's
child-issue creation mechanics now go through `ll-issues create` / `ll-issues scaffold-epic`
(FEAT-2947) rather than restating ID/filename templating in the skill.

---

#### `ll-issues check-readiness` / `ll-issues cr`

Exit 0 if an issue's `confidence_score` and `outcome_confidence` frontmatter fields both meet the configured thresholds. Reads thresholds from `commands.confidence_gate` in `ll-config.json`, falling back to `--readiness` / `--outcome` CLI args.

| Argument/Flag | Default | Description |
|---------------|---------|-------------|
| `issue_id` | _(required)_ | Issue ID (e.g., `518`, `FEAT-518`, `P3-FEAT-518`) |
| `--readiness N` | `90` | Fallback readiness threshold when not set in `ll-config.json` |
| `--outcome N` | `75` | Fallback outcome confidence threshold when not set in `ll-config.json` |

**Examples:**
```bash
ll-issues check-readiness 518             # Use thresholds from ll-config.json
ll-issues cr FEAT-518 --readiness 85      # Override readiness threshold
ll-issues check-readiness 518 --readiness 80 --outcome 70
```

**FSM loop use**: Use as a shell gate in `refine-to-ready-issue`-style loops to branch without an LLM call. Pair with `ll-issues show --json` when you need the raw scores.

#### `ll-issues set-scores` / `ll-issues ss`

Write `confidence_score`, `outcome_confidence`, and the four per-dimension scores into an issue's YAML frontmatter. Writes idempotently: existing fields are overwritten, unrelated keys are preserved, and missing frontmatter is created from scratch. If no score flags are provided, returns 0 with a warning and writes nothing.

| Argument/Flag | Default | Description |
|---------------|---------|-------------|
| `issue_id` | _(required)_ | Issue ID (e.g., `518`, `FEAT-518`, `P3-FEAT-518`) |
| `--confidence N` | `None` | Overall readiness score (0–100) |
| `--outcome N` | `None` | Outcome confidence score (0–100) |
| `--score-complexity N` | `None` | Complexity dimension score (0–25) |
| `--score-test-coverage N` | `None` | Test-coverage dimension score (0–25) |
| `--score-ambiguity N` | `None` | Ambiguity dimension score (0–25) |
| `--score-change-surface N` | `None` | Change-surface dimension score (0–25) |

**Examples:**
```bash
ll-issues set-scores BUG-1307 --confidence 95 --outcome 80
ll-issues ss FEAT-518 --confidence 88 --outcome 72 --score-complexity 22 --score-test-coverage 20 --score-ambiguity 25 --score-change-surface 15
```

**Used by**: `/ll:confidence-check` Phase 4 to persist scores deterministically instead of a free-form `Edit` call.

---

#### `ll-issues set-status` / `ll-issues sst`

Transition an issue to a new status value. Validates the target status against the canonical enum, updates the `status:` frontmatter field in-place, and prints the before→after transition to stdout.

**Side effect**: also writes a content snapshot to `issue_snapshots` and, since BUG-2770, a matching row to `issue_events` in `.ll/history.db` (best-effort, direct `record_issue_event()` call — not an EventBus emit), so `ll-session recent --issue` and `issue_effort()` resolve sessions for issues closed via this command. As of BUG-3006 the write is wrapped in a narrowed `except (sqlite3.Error, ImportError, OSError)` that logs a warning instead of the previous blanket `except Exception: pass`, so a genuine DB failure is no longer silent; a suppressed `(issue_num, transition)` dedup collision against a *different* issue id also logs a warning (see `ll-history audit-issue-collisions` below).

| Argument | Description |
|----------|-------------|
| `issue_id` | Issue ID (e.g., `518`, `ENH-518`, `P3-ENH-518`) |
| `status` | New status value: `open`, `in_progress`, `blocked`, `deferred`, `done`, `cancelled` |
| `--cascade` | Propagate status to issues with `parent: <EPIC-ID>` (EPIC closure only; only valid with `done`/`cancelled`). Only follows `parent:` edges — `relates_to:`, `blocked_by:`, and other relationship types are not traversed. |
| `--cascade-to <status>` | Status to apply to cascaded children (default: `deferred`) |
| `--by <human\|automation>` | Who initiated a `deferred` transition (default: `human`). Stamped into `deferred_by`; no-op for other target statuses. |
| `--reason <code>` | Machine-readable reason code. Deferral codes (`blocked_by_unmet`, `remediation_stalled`, `low_readiness`, `gate_blocked`, `decision_unresolved`, `oversized_atomic`, `readiness_stagnated`; ENH-2664, the last five added by ENH-2666/BUG-2734/FEAT-2751) are valid only with a `deferred` transition and stamp `deferred_reason`. Closure codes (`already_fixed`, `superseded`, `not_reproducible`, `invalid_ref`; ENH-2749, `superseded` added by BUG-2844, `not_reproducible`/`invalid_ref` added by ENH-2969) are valid only with a `done`/`cancelled` transition and stamp `closed_reason`, reusing the same key ENH-2535 introduced for closure-context prose. Passing a code with a mismatched target status is rejected (exit 1). |

**Examples:**
```bash
ll-issues set-status ENH-1725 in_progress   # ENH-1725: open → in_progress
ll-issues sst BUG-042 done                  # BUG-042: in_progress → done
ll-issues set-status FEAT-100 blocked
ll-issues set-status EPIC-042 cancelled --cascade              # Close EPIC + defer children
ll-issues set-status EPIC-042 done --cascade --cascade-to done # Close EPIC + all children
ll-issues set-status ENH-999 deferred --by automation --reason blocked_by_unmet
ll-issues set-status BUG-731 done --reason already_fixed        # Closed elsewhere; record why
ll-issues set-status BUG-905 cancelled --reason superseded      # Superseded; edge lives on the replacement issue
```

---

#### `ll-issues link <issue_id>` / `ll-issues lk <issue_id>`

Write or remove a dependency edge in an issue's YAML frontmatter (FEAT-2842) —
the deterministic primitive for "add this edge" the way `set-status` is the
primitive for "change this status". Idempotent (re-running is a no-op that
reports `unchanged`), list-aware (creates the key when absent, appends to the
existing list when present, preserving order and the rest of the frontmatter
byte-for-byte), validating (the target must resolve to an existing issue file
unless `--force`), and cycle-safe (a `--blocked-by`/`--depends-on` edge that
would introduce a cycle in the blocking graph is refused).

This is a **frontmatter-key writer**. It is distinct from `ll-deps fix`/`ll-deps
apply` (below), which write the same fields as **markdown-body sections**
(`## Blocked By`, etc.); frontmatter takes precedence when an issue has both.

| Argument/Flag | Description |
|---------------|-------------|
| `issue_id` | Issue ID (e.g., `518`, `FEAT-518`, `P3-FEAT-518`) |
| `--blocked-by <ID>` | Target hard-blocks `issue_id` (mutually exclusive with the two below) |
| `--depends-on <ID>` | Target is a soft prerequisite of `issue_id` |
| `--relates-to <ID>` | Target is related to `issue_id` |
| `--unlink` / `--remove` | Remove the edge instead of adding it |
| `--reciprocal` | Also write the matching reverse edge on the target (`blocked_by` → `blocks`; `relates_to` is already bidirectional) |
| `--force` | Skip target-existence validation |
| `--json` | Output result as JSON |
| `--dry-run` | Report what would change without writing |
| `--config` | Path to project root |

**Examples:**
```bash
ll-issues link FEAT-110 --blocked-by FEAT-109   # First run: writes the edge
ll-issues link FEAT-110 --blocked-by FEAT-109   # Second run: no-op, exit 0
ll-issues link FEAT-110 --blocked-by FEAT-109 --unlink   # Remove the edge
ll-issues link FEAT-110 --depends-on FEAT-050 --dry-run  # Preview only
```

---

#### `ll-issues link-epics`

Score orphan issues (open BUG/FEAT/ENH with no `parent:`/`epic:`) for EPIC
assignment, or cluster them into new-EPIC proposals (FEAT-2942). Similarity
comes from `text_utils.py`'s title word-overlap (Jaccard) — the same primitive
`ll-issues find-similar` uses, but scored orphan-vs-EPIC (`assign`) or
orphan-vs-orphan via union-find (`synthesize`) rather than `find-similar`'s
single-corpus all-pairs scan. Distinct from `ll-issues clusters`, which
visualizes existing *dependency-edge* relationships, not text similarity.

| Argument/Flag | Description |
|---------------|-------------|
| `--mode assign\|synthesize` | `assign` (default) scores orphans against existing open EPICs; `synthesize` union-find clusters orphans against each other |
| `--threshold <N>` | Minimum score to include; default `config.issues.link_epics.min_score` |
| `--apply` | Write accepted `assign`-mode proposals (`parent:`/`epic:` frontmatter + EPIC `## Children` append); unsupported for `--mode synthesize` (exits 1) — EPIC creation from clusters is not implemented by this subcommand |
| `--json` | Output as JSON: `{"proposals": [...], "applied": [...]}` (assign) or `{"clusters": [...], "applied": []}` (synthesize) |
| `--config` | Path to project root |

`--apply` is idempotent — re-running is a no-op on any pair already applied.

**Examples:**
```bash
ll-issues link-epics --mode assign --json                    # proposals only
ll-issues link-epics --mode assign --threshold 0.5 --apply   # apply proposals >= 0.5
ll-issues link-epics --mode synthesize --json                # cluster proposals only
```

---

#### `ll-issues epic-progress <epic_id>` / `ll-issues ep <epic_id>`

Show a progress summary for an EPIC and all its child issues. Aggregates child statuses into a completion bar, counts by status, surfaces the oldest open child, and lists any blocked children with their `blocked_by` links.

| Argument/Flag | Short | Default | Description |
|---------------|-------|---------|-------------|
| `epic_id` | | _(required)_ | EPIC ID to summarize (e.g., `EPIC-1773`) |
| `--format` | `-f` | `text` | Output format: `text`, `json`, or `markdown` |
| `--config` | | | Path to project root |

**Sample text output:**
```
EPIC-1773: Audit & simplify built-in FSM loops
  Progress:     ████████░░░░░░░░  8/12 resolved (67%)
  Status:       2 in_progress  •  1 blocked  •  1 open  •  8 done
  Oldest open:  ENH-1641 (24 days)
  Blocked:      ENH-1820 → blocked_by BUG-1701
```

The "resolved" count on the Progress line is `done + cancelled` (terminal states). When cancelled issues are present, a breakdown is appended: e.g., `8/12 resolved (67%) (7 done, 1 cancelled)`. The Status line always shows individual status buckets including the raw `done` and `cancelled` counts separately.

<!-- TODO: update-docs stub — BUG-2441 — drafted 2026-07-02 -->

> **Rollup semantics** (BUG-2441): The child set is collected by walking the `parent:` chain transitively, so grandchildren (and any deeper descendants) of the EPIC roll up into the Progress and Status counts — not just direct children. This matches the bucketing behavior of `ll-issues list --bucket epic`. Note: `ll-sprint`'s EPIC resolution still counts direct children only; for a sprint-aware breakdown use `ll-sprint show`.
>
> **Nested EPIC visibility** (BUG-2480): a nested EPIC (a `type: EPIC` child of another EPIC) counts toward its parent's `(N/M done)` denominator and is rendered as its own row in a `Sub-EPICs (k)` sub-section under `ll-issues list --group-by epic`, carrying its own `(j/m done)` rollup from a separate `compute_epic_progress` call. The nested EPIC's own descendants (grandchildren of the outer EPIC) are bucketed under the nested EPIC, not the outer one — so they appear once, either under the outer EPIC's leaf rows or under the nested EPIC's own heading, never duplicated.

<!-- END TODO stub -->

**Examples:**
```bash
ll-issues epic-progress EPIC-1773              # Text summary (default)
ll-issues ep EPIC-1773 --format json           # JSON object with counts and child list
ll-issues ep EPIC-1773 --format markdown       # Markdown-formatted summary
```

---

#### `ll-issues epic-consistency [epic_id]` / `ll-issues ec [epic_id]`

Detect and reconcile EPIC body/parent drift — cases where an EPIC's `## Children` section disagrees with the set of issues actually carrying `parent: EPIC-NNN`. Report-only by default; `--fix` rewrites `## Children` for the drift category it can resolve mechanically. Exits 0 when no drift is found (or after a clean `--fix`), 1 on drift or error.

| Argument | Description |
|----------|-------------|
| `epic_id` | EPIC ID (e.g., `EPIC-1773`). Optional — omit it when using `--all`. |

| Flag | Short | Description |
|------|-------|-------------|
| `--all` | `-a` | Check every EPIC in the epics directory |
| `--fix` | | Rewrite `## Children` for category-(a) drift instead of only reporting it |
| `--format` | `-f` | Output format: `text` (default) or `json` |
| `--config` | | Path to `ll-config.json` |

**Examples:**
```bash
ll-issues epic-consistency EPIC-1773           # Report drift for one EPIC
ll-issues ec --all                             # Sweep every EPIC
ll-issues ec EPIC-1773 --fix                   # Rewrite ## Children to match parent: fields
ll-issues ec --all --format json               # Machine-readable drift report
```

---

#### `ll-issues deferred-triage` / `ll-issues dt`

List `status: deferred` issues that were parked by automation (`deferred_by: automation`,
stamped by `ll-issues set-status <ID> deferred --by automation --reason <code>`), showing
`deferred_reason` and age-since-`deferred_date`. Issues deferred by a human (`deferred_by:
human` or no `deferred_by` at all) are excluded — this is a cross-run resurfacing report for
the automation circuit-breaker deferral path (FEAT-2665), covering both `rn-implement.yaml`'s
codes and `autodev.yaml`'s not-ready exits (ENH-2666) — not a general deferred-issue list.

Rank order (highest first): `remediation_stalled`, `blocked_by_unmet`, `gate_blocked`,
`decision_unresolved`, `oversized_atomic`, `readiness_stagnated`, `design_gate_failed`
(ENH-2870), `blocked_by_gate` (ENH-3148), `low_readiness`, then any other (unranked) code;
within each group, the oldest issue is listed first.

| Argument/Flag | Short | Default | Description |
|---------------|-------|---------|-------------|
| `--format` | `-f` | `text` | Output format: `text`, `json`, or `markdown` |
| `--config` | | | Path to project root |

**Examples:**
```bash
ll-issues deferred-triage                      # Text report (default)
ll-issues dt --format json                     # JSON array of {issue_id, title, deferred_reason, age_days}
ll-issues dt --format markdown                 # Markdown table
```

---

#### `ll-issues decisions`

Manage rules, decisions, and exceptions log.

**Sub-sub-commands:**

| Sub-command | Description |
|-------------|-------------|
| `list` | List decisions log entries (with optional filters) |
| `add` | Add a new rule, decision, or exception entry |
| `outcome <ID>` | Record the outcome of a decision entry |
| `generate` | Generate entries from completed issues |
| `sync` | Sync active rules to `.ll/ll.local.md` |
| `suggest-rules` | Analyze decision entries and surface candidates ready for promotion to rules |
| `promote <ID>` | Convert a `decision` entry into an enforced `rule` (rewrites entry in-place; auto-syncs when `--enforcement required`) |
| `extract-from-completed` | Extract rules from completed issues via LLM; appends `RuleEntry` records to the decisions log as `.ll/decisions.d/*.json` fragments with deduplication |

**`list` flags:**

| Flag | Description |
|------|-------------|
| `--type` | Filter by entry type: `rule`, `decision`, `exception` |
| `--category` | Filter by category string |
| `--label` | Filter by label |
| `--no-outcome` | Show only `DecisionEntry` records with no outcome |
| `--before <ISO-8601>` | Show entries with timestamp before this date |
| `--scope <scope>` | Filter `DecisionEntry` records by scope |
| `--active-only` | Exclude entries superseded by a newer entry |
| `--enforcement` | Filter `rule`/`coupling` entries by enforcement level: `required` or `advisory` |
| `--format` / `-f` | Output format: `text` (default), `json` |

**`add` flags:**

| Flag | Applies to | Description |
|------|-----------|-------------|
| `--type` | all | Entry type: `rule`, `decision`, `exception` (required) |
| `--category` | all | Category string (required) |
| `--rule` | rule, decision | Rule or decision text (required for these types) |
| `--rationale` | all | Why this entry applies (required) |
| `--issue` | all | Related issue ID |
| `--label` | all | Comma-separated labels |
| `--source-session <SESSION_ID>` | all | Session ID that produced this entry (provenance backlink; ENH-2667) |
| `--source-issue-id <ISSUE_ID>` | all | Issue ID that produced this entry (provenance backlink; ENH-2667) |
| `--enforcement` | rule | `required` or `advisory` (default: `advisory`) |
| `--rule-ref` | exception | Rule being excepted (required for exception) |
| `--alternatives-rejected` | decision, exception | Alternatives considered |
| `--supersedes` | rule | ID of the rule this supersedes |
| `--scope` | decision | `issue` (default) or `project` |
| `--id` | all | Explicit entry ID (auto-generated if omitted) |

**`outcome` flags:**

| Flag | Description |
|------|-------------|
| `<ID>` | Entry ID to record outcome for (positional, required) |
| `--result` | Outcome: `worked`, `did_not_work`, `mixed`, `reversed` (required) |
| `--notes` | Free-text notes about the outcome |
| `--measured-at <ISO-8601>` | When the outcome was measured (default: now) |
| `--force` | Overwrite an existing outcome |

**`generate` flags:**

| Flag | Description |
|------|-------------|
| `--from` | Source to generate from: `completed` (default). Scans issue type directories (`.issues/bugs/`, `.issues/features/`, `.issues/enhancements/`, `.issues/epics/`) for files with `status: done` frontmatter, skips entries already present in the decisions log (both `.ll/decisions.yaml` and `.ll/decisions.d/*.json` fragments), and appends new `decision` entries (as fragments) for each issue not yet logged. |

**`sync` flags:**

No additional flags. Reads active required rules from the decisions log (both `.ll/decisions.yaml` and `.ll/decisions.d/*.json` fragments) and writes them to the `## Active Rules` section in `.ll/ll.local.md`. Creates `.ll/ll.local.md` if absent. Silently skips when the decisions log is absent (neither tier present).

**`suggest-rules` flags:**

No additional flags. Analyzes `decision` entries and clusters them by category and shared token overlap to surface candidates with recurring patterns. Requires at least 3 decision entries to produce output (exits 1 with a message if fewer).

**`promote` flags:**

| Flag | Description |
|------|-------------|
| `<ID>` | ID of the `decision` entry to promote (positional, required) |
| `--enforcement` | Enforcement level for the new rule: `required` (default) or `advisory`. When `required`, auto-runs `sync` to push the rule into `.ll/ll.local.md` immediately. |

**`extract-from-completed` flags:**

| Flag | Description |
|------|-------------|
| `--since YYYY-MM-DD` | Only process issues completed on or after this date |
| `--issue ID` | Only extract from this specific issue (e.g. `ENH-2151`) |
| `--dry-run` | Print candidates without writing to `decisions.yaml` |
| `--min-confidence FLOAT` | Minimum LLM confidence to accept a candidate (default: `0.7`) |

```bash
ll-issues decisions list
ll-issues decisions list --type rule --active-only
ll-issues decisions list --type rule --enforcement required --active-only  # only enforced rules
ll-issues decisions list --no-outcome
ll-issues decisions add --type=decision --category=architecture --rule="Use atomic_write" --rationale="Prevents partial state"
ll-issues decisions outcome dec-001 --result=worked --notes="No incidents in 30 days"
ll-issues decisions generate                     # Generate from completed issues (default)
ll-issues decisions generate --from completed    # Explicit source
ll-issues decisions sync                         # Sync active rules → .ll/ll.local.md
ll-issues decisions suggest-rules                # Surface decision candidates for promotion
ll-issues decisions promote dec-007              # Promote dec-007 → required rule (auto-sync)
ll-issues decisions promote dec-007 --enforcement advisory  # Promote as advisory rule
ll-issues decisions extract-from-completed       # Extract rules from all completed issues via LLM
ll-issues decisions extract-from-completed --since 2026-01-01  # Only issues completed since date
ll-issues decisions extract-from-completed --issue ENH-2151    # Only one issue
ll-issues decisions extract-from-completed --dry-run           # Preview candidates without writing
```

---

### ll-deps

Cross-issue dependency discovery and validation.

**Global flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--issues-dir` | `-d` | Path to issues directory (default: `.issues`) |
| `--intent QUERY` | | Intent query for output filtering (no-op until FTS5 ranking lands) |
| `--intent-limit N` | | Max lines for intent-filtered output (default: `50`) |

**Subcommands:**

#### `ll-deps analyze`

Full dependency analysis combining file overlaps and validation.

| Flag | Short | Description |
|------|-------|-------------|
| `--format` | `-f` | Output format: `text` (default), `json` |
| `--graph` | | Include ASCII dependency graph |
| `--sprint` | | Restrict analysis to issues in named sprint |

#### `ll-deps validate`

Validate existing dependency references only (broken refs, cycles, stale completed refs).

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | `-j` | Output as JSON (serializes `ValidationResult` fields) |
| `--sprint` | | Restrict validation to named sprint |

#### `ll-deps fix`

Auto-fix broken refs, stale refs, and missing backlinks. Cycles are always
enumerated in the report (member edges plus a suggested lowest-priority-edge
cut); pass `--break-cycles` to apply the suggested cut, keeping bidirectional
`Blocked By`/`Blocks` consistency (paired removal, same shape `ll-deps apply`
uses for paired writes).

| Flag | Short | Description |
|------|-------|-------------|
| `--dry-run` | `-n` | Preview fixes without modifying files |
| `--sprint` | | Restrict fixes to named sprint |
| `--break-cycles` | | Cut the suggested lowest-priority edge of each detected cycle |

#### `ll-deps apply`

Write proposed dependency relationships to issue files. Re-runs analysis internally and writes accepted proposals (above a confidence threshold) to `## Blocked By` sections. Backlinks are intentionally not written — run `ll-deps fix` afterward to add missing `## Blocks` entries.

| Flag | Short | Description |
|------|-------|-------------|
| `--min-confidence` | | Minimum confidence to apply (default: `0.7`) |
| `--dry-run` | `-n` | Preview without writing |
| `--sprint` | | Restrict to issues in named sprint |
| `<source> <relation> <target>` | | Explicit pair: `FEAT-001 blocks FEAT-002` or `FEAT-001 blocked-by FEAT-002` |

#### `ll-deps tree`

Render an EPIC's child issue hierarchy as a Unicode box-drawing tree with dependency edges.

| Flag | Short | Description |
|------|-------|-------------|
| `--epic` | | EPIC issue ID to render (required, e.g. `EPIC-1773`) |
| `--format` | `-f` | Output format: `text` (default), `json` |

JSON output (`--format json`) emits `{"root": "EPIC-NNN", "nodes": [...], "edges": [...]}`.
Exits 0 on success; exits non-zero if the EPIC is not found.

**Examples:**
```bash
ll-deps analyze                       # Full analysis with markdown output
ll-deps analyze --format json         # JSON output
ll-deps analyze --graph               # Include ASCII dependency graph
ll-deps analyze --sprint my-sprint    # Analyze only sprint issues
ll-deps validate                      # Validation only
ll-deps validate --json               # JSON output
ll-deps validate --sprint my-sprint   # Validate sprint issue deps
ll-deps fix                           # Auto-fix broken refs and backlinks
ll-deps fix --dry-run                 # Preview fixes
ll-deps fix --break-cycles            # Also cut the lowest-priority edge of each cycle
ll-deps apply                         # Apply proposals >= 0.7 confidence
ll-deps apply --min-confidence 0.5    # Lower threshold
ll-deps apply --dry-run               # Preview only (no writes)
ll-deps apply --sprint my-sprint      # Sprint-scoped apply
ll-deps apply FEAT-001 blocks FEAT-002       # Manual explicit pair
ll-deps apply FEAT-001 blocked-by FEAT-002   # Manual explicit pair (inverse)
ll-deps tree --epic EPIC-1773        # Text tree with ├──/└── connectors
ll-deps tree --epic EPIC-1773 -f json  # Structured JSON (root, nodes, edges)
```

---

### ll-code

Structural code queries (callers, callees, imports, impact) via a pluggable `CodeQueryProvider`
protocol (FEAT-2576). Ships with a grep/AST **fallback** provider that requires no external
index — every subcommand works out of the box. Graph-backed providers (e.g. ENH-2613's
`codegraph`, a read-only reader over a `.codegraph/codegraph.db` index) register in the same
resolver and take priority under `--provider auto`.

**Global flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--provider` | | Provider name (`fallback`, `codegraph`), or `auto` (default) to pick the first available |
| `--json` | `-j` | Output as JSON: `{provider, freshness, query, results: [CodeRef...]}` |

**Subcommands:**

| Subcommand | Description |
|------------|--------------|
| `status` | Provider name, availability, freshness, capabilities |
| `callers-of <symbol>` | Who calls this symbol (heuristic on `fallback`, exact on `codegraph`) |
| `callees-of <symbol>` | What this symbol calls (exact) |
| `importers-of <module>` | Who imports this module/file (heuristic on `fallback`, exact on `codegraph`) |
| `defines <path>` | Symbols defined in a file (exact) |
| `references <symbol>` | All reference sites — defs + uses (heuristic on `fallback`, exact on `codegraph`) |
| `impact-of <paths...> [--depth N]` | Reverse transitive closure of files impacted by changes to *paths* (default depth: `2`; heuristic on `fallback` (AST-parsed import graph), exact on `codegraph` (indexed 'imports' edges walked to depth)) |

Every result carries a `confidence` (`exact` or `heuristic`) and `provider` field. Exit codes:
`0` = hits, `1` = no hits, `2` = provider error.

**`status` freshness fields (`codegraph` provider):** the `detail` string reports
`indexed_at` (index build time, ISO 8601), `head_moved` (commits landed since the index was
built), `dirty_files` (uncommitted/untracked file count), and the active `policy`
(`code_query.staleness`, ENH-2612). Enforcement: `strict` makes a stale index report
`available: false` (the resolver falls through to `fallback` automatically); `warn` (default)
serves stale results with `freshness: stale`; `off` always reports `freshness: fresh`.

**Auto-sync on staleness (ENH-2863):** when `code_query.codegraph.auto_sync` is `true`
(default), a non-fresh `status()` read synchronously shells out to `codegraph sync --quiet`
before returning — so `stale` should be transient/rare rather than a steady-state condition.
No-op if the `codegraph` binary isn't on `PATH`, or on sync failure/timeout; either way it
falls through to the pre-sync `stale`-but-`available` behavior without raising. Staleness
clears on the *next* `status()` call once the sync updates the index in place — the call that
triggered the sync still reports the pre-sync freshness.

**Examples:**
```bash
ll-code status                                     # provider name, availability, freshness
ll-code callers-of little_loops.issue_manager.IssueManager.load
ll-code --json callers-of <symbol>                 # machine-readable output for skills/loops
ll-code --provider fallback callers-of <symbol>    # force a specific provider
ll-code --provider codegraph status                # inspect the codegraph index's freshness
ll-code impact-of little_loops/state.py --depth 3
```

**Skill consumers:** `/ll:wire-issue` (Phase 3.6) and `/ll:refine-issue` (Step 3.05)
seed their agent waves from these queries; `/ll:verify-issues` (§2B.0) uses them to
corroborate or correct verdicts. The shared contract they follow — probe
procedure, the three safety rules, staleness handling, and why the orchestrator
queries instead of the `ll:codebase-*` agents — is
[docs/guides/GRAPH_DISCOVERY_GUIDE.md](../guides/GRAPH_DISCOVERY_GUIDE.md).

---

## History & Analysis

### ll-history

Display summary statistics and analysis for completed issues.

When present in issue frontmatter, `captured_at` and `completed_at` are preferred over the legacy `discovered_date` field and Resolution body regex / git-log fallbacks; the JSON serialization of `CompletedIssue` includes both fields at sub-day ISO 8601 resolution.

**Global flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--intent QUERY` | | Intent query for output filtering (no-op until FTS5 ranking lands) |
| `--intent-limit N` | | Max lines for intent-filtered output (default: `50`) |

**Subcommands:**

#### `ll-history summary`

Show issue statistics for completed issues.

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | `-j` | Output as JSON |
| `--directory` | `-d` | Path to issues directory (default: `.issues`) |
| `--since` | `-S` | Only count issues/loop-runs completed/started on or after DATE (YYYY-MM-DD) (ENH-3237) |
| `--until` | | Only count issues/loop-runs completed/ended on or before DATE (YYYY-MM-DD) (ENH-3237) |

When the unified session DB (`.ll/history.db`, FEAT-1112) contains `issue_events` rows, `summary` reads from the DB instead of re-parsing every completed-issue file. An empty/absent DB falls back to file parsing — no behavior change for projects without recorded events (ENH-1621). As of ENH-1691, `ll-auto` writes issue lifecycle events live during each run via `AutoManager`'s internal `SQLiteTransport`; `ll-session backfill` is retained for importing historical data captured before ENH-1691. Only the `summary` subcommand is DB-backed; `analyze` and `export` still scan the files because they need bodies and git history.

**Windowed summary (`--since`/`--until`, ENH-3237):** the DB-vs-fallback trigger is
source availability, not row count — an empty window on a populated DB still
returns DB-sourced zero counts rather than silently falling through to an
unfiltered file scan. `--json` output gains: `source` (`"issue_events"` or
`"files"`, naming which store answered — the two sources can disagree on
counts, since `issue_events` records emitted events while the file scan
counts completed issue files), `since`/`until` (the requested bounds, or
`null` when unbounded), and `loop_runs_started`/`loop_runs_ended` (counts from
`loop_runs` for the window; `null`, not `0`, when the session DB can't answer
— an in-flight run with `ended_at IS NULL` counts as started-not-ended).
`date_range_days`/`velocity` use the requested `--since`/`--until` span as the
denominator when both bounds are given; otherwise they fall back to the span
actually observed between the earliest and latest completion in the result
(unchanged, pre-ENH-3237 behavior).

#### `ll-history analyze`

Full analysis with trends, subsystems, and debt metrics.

| Flag | Short | Description |
|------|-------|-------------|
| `--format` | `-f` | Output format: `text` (default), `json`, `markdown`, `yaml` |
| `--directory` | `-d` | Path to issues directory |
| `--period` | `-p` | Trend grouping: `weekly`, `monthly` (default), `quarterly` |
| `--compare` | `-c` | Compare last N days to previous N days |
| `--since` | | Only analyze issues completed on or after DATE (YYYY-MM-DD) |
| `--until` | | Only analyze issues completed on or before DATE (YYYY-MM-DD) |

#### `ll-history export <topic>`

Export topic-filtered excerpts from completed issue history.

| Argument/Flag | Short | Description |
|---------------|-------|-------------|
| `topic` | | Topic, area, or system to export |
| `--output` | | Write to file instead of stdout |
| `--format` | `-f` | Format: `narrative` (default), `structured` |
| `--directory` | `-d` | Path to issues directory |
| `--since` | | Only include issues completed after DATE (YYYY-MM-DD) |
| `--min-relevance` | | Minimum relevance score (default: 0.5) |
| `--type` | | Filter by type: `BUG`, `FEAT`, `ENH`, `EPIC` |
| `--scoring` | | Relevance method: `intersection` (default), `bm25`, `hybrid` |

#### `ll-history rework`

Reopen/follow-up/touch-back/revert rates as a time series across `(calendar month, orchestrator)`
windows, plus a quality-adjusted throughput figure (FEAT-2867) — the epic-level rework
measurement EPIC-2856 promises. Sourced entirely from `issue_events`/`commit_events`/
`orchestration_runs` in `.ll/history.db` plus on-disk `supersedes:` edges; read-only, no LLM calls.

| Flag | Short | Description |
|------|-------|-------------|
| `--format` | `-f` | Output format: `text` (default), `json`, `markdown`, `yaml` |
| `--min-sample N` | | Minimum closed issues per window before a rate is reported (default: 5) |
| `--follow-up-days N` | | Lookahead window in days for follow-up/touch-back detection (default: 14) |

Each window reports: `reopen`/`follow_up`/`touch_back`/`revert` rates (each with an
`improving`/`stable`/`degrading` verdict against the earliest window sharing its orchestrator
label), `quality_adjusted` throughput (`closed x (1 - max(reopen_rate, revert_rate))`, the pinned
formula), and `commit_attribution_coverage` (share of the window's commits carrying an
`issue_id`, flagged `low_attribution_coverage` below 50%). Windows below `--min-sample` report
`insufficient_history: true` instead of a computed ratio. Issues with no matching
`orchestration_runs` row fall into the `unattributed` orchestrator bucket rather than being
dropped. Reopen rate counts issues that ever reopened (or were cancelled-and-superseded via a
`supersedes:` edge), not reopen events — `issue_events` dedups per `(issue_num, transition)`, so a
second done→open→done cycle collapses into the first. Revert rate is computed from commit-message
lineage (`This reverts commit <sha>`) only; diff-inverse detection is out of scope. Orchestrator
attribution is correlational, not causal.

#### `ll-history quality`

Agent-quality report (FEAT-3183): fix-rate, correction rate, cost per issue, and tokens per
issue as a time series across the same `(calendar month, orchestrator)` windows `ll-history
rework` uses, plus retry inflation on its own `(calendar month, loop_name)` axis. Read-only
against `.ll/history.db`; no network access, no LLM calls.

| Flag | Short | Description |
|------|-------|-------------|
| `--format` | `-f` | Output format: `text` (default), `json`, `markdown`, `yaml` |
| `--min-sample N` | | Minimum closed issues (or loop runs, for retry inflation) per window before a rate is reported (default: 5) |

Metric definitions, per window:

- **fix-rate** = `1 - rework_share` (reusing `ll-history rework`'s pinned formula, so the two
  reports cannot disagree). Verdict is derived from `rework_share`'s own trend, not re-derived
  from the (nonlinearly related) fix-rate value.
- **correction rate** = non-retired `user_corrections` rows attributed to closed issues via
  `session_id -> issue_sessions -> issue_num` (split evenly across sessions that touched more
  than one issue), divided by closed issues in the window. `user_corrections` has no `issue_id`
  column, so sessions with no recorded issue association are excluded.
- **cost per issue** = `usage_events.cost_usd` summed per issue (same session-split rule),
  divided by closed issues. Each window also reports `coverage` — the share of attributed
  `usage_events` rows with a non-null `cost_usd` — and **suppresses the verdict** (not the
  number) when `coverage < 0.5`: `cost_usd` is null for any model absent from
  `pricing.MODEL_PRICING`, and that gap is not evenly distributed across time, so an unguarded
  trend would read pricing-table coverage as an agent-behavior regression.
- **tokens per issue** = the four `usage_events` token columns summed the same way. Always
  computable — no pricing-table dependency — so it has no coverage gate and stays a useful
  spend signal even when cost coverage is poor.
- **retry inflation** = mean `loop_runs.iterations` per `(calendar month, loop_name)`. Bucketed
  by loop rather than orchestrator because `loop_runs` has no `issue_id` column and the two-hop
  join needed to recover one is only partially reachable.

Every window below `--min-sample` reports `insufficient_history: true` on every metric instead
of a computed value. Issues with no matching `orchestration_runs` row fall into the
`unattributed` orchestrator bucket, which is typically the dominant bucket, not an edge case.
Every metric's formula, window, denominator, and caveats are also emitted as a `MetricDefinition`
in the JSON/YAML payload, so a downstream consumer never has to re-derive them.

```bash
ll-history quality                        # Text report
ll-history quality --format json          # JSON output, includes metric definitions
ll-history quality --min-sample 3         # Lower the sample-size gate
```

#### `ll-history audit-issue-collisions`

Read-only report (BUG-3006) of every `issue_num` held by more than one `issue_id` in
`issue_events`/`issue_snapshots` — a symptom of the dedup index's type-blind
`(issue_num, transition)` key (v36, ENH-2771). Groups each table independently by
`issue_num` where `COUNT(DISTINCT issue_id) > 1`, and classifies each group as a
`retype` (one issue changed type prefix mid-life; expected and harmless) or a
`number_reuse` collision (two distinct issues sharing a bare number; a completion
transition was silently discarded) by checking whether the lone on-disk survivor's
current `status:` frontmatter matches one of its own recorded transitions in that
table — a mismatch means its true current-status write was the one dropped by the
collision. Performs no writes; add `--json` for structured output.

```bash
ll-history audit-issue-collisions        # Text report
ll-history audit-issue-collisions --json # JSON output
```

#### `ll-history sessions <ISSUE_ID>`

List sessions that co-occurred with the given issue's active period. Queries the `issue_sessions` VIEW (v5 schema, ENH-1711) which joins `issue_events` to `message_events` via overlapping timestamps. Issues processed after ENH-1839 populate `captured_at` immediately on live events; a prior `ll-session backfill` pass (or ENH-1830 auto-backfill) is only needed for older issues.

| Flag | Description |
|------|-------------|
| `--limit N` | Maximum results (default: 20) |
| `--json` / `-j` | Output as JSON array |

**Examples:**
```bash
ll-history sessions ENH-1710              # Sessions that touched ENH-1710
ll-history sessions ENH-1710 --json       # JSON output
```

**Examples (all subcommands):**
```bash
ll-history summary                         # Summary statistics
ll-history summary --json                  # JSON output
ll-history analyze                         # Full analysis report
ll-history analyze --format markdown       # Markdown report
ll-history analyze --compare 30            # Compare last 30 days to previous
ll-history export "session log"            # Export excerpts for topic
ll-history export "sprint CLI" --output docs/arch/sprint.md
ll-history rework                          # Reopen/follow-up/touch-back/revert rates
ll-history quality                         # Fix-rate/correction/cost/tokens/retry trends
ll-history sessions ENH-1710              # Sessions that touched ENH-1710
ll-history sessions ENH-1710 --json       # JSON output
```

#### `ll-history root`

Show the project-root summary node — the top-level condensed node that covers all sessions in the project (ENH-1955). Requires `ll-session backfill` with compaction and cross-session condensation enabled.

| Flag | Description |
|------|-------------|
| `--expand` | Expand and display all messages under the root node |
| `--limit N` | Maximum messages to show with `--expand` (default: 20) |
| `--json` / `-j` | Output root node metadata + message count as JSON |

**Examples:**
```bash
ll-history root                  # Show root node metadata
ll-history root --expand         # Show metadata + first 20 messages
ll-history root --expand --limit 5  # Show metadata + first 5 messages
ll-history root --json           # JSON output
```

---

### ll-workflows

Identify multi-step workflow patterns from user message history. Steps 2 and 3 of the `/ll:analyze-workflows` pipeline.

**Subcommands:**

#### `ll-workflows analyze`

Analyze workflows from messages and Step 1 patterns.

| Flag | Short | Description |
|------|-------|-------------|
| `--input` | `-i` | Input JSONL file with user messages (default: `.ll/workflow-analysis/step1-patterns.jsonl`) |
| `--patterns` | `-p` | **Required.** Input YAML from Step 1 (workflow-pattern-analyzer) |
| `--output` | `-o` | Output YAML file (default: `.ll/workflow-analysis/step2-workflows.yaml`) |
| `--verbose` | `-v` | Show verbose analysis output |

The Python API (`analyze_workflows()`) accepts an optional `db_path` argument that prefers the unified session store's `message_events` table over the JSONL input when populated (ENH-1621); an empty/missing DB transparently falls back to the JSONL file. The `--patterns` YAML is a generated analysis artifact and stays a file input.

**Examples:**
```bash
# Use conventional path (no --input needed if ll-messages wrote to the default location)
ll-messages --output .ll/workflow-analysis/step1-patterns.jsonl
ll-workflows analyze --patterns .ll/workflow-analysis/step1-patterns.yaml

# Explicit input
ll-workflows analyze -i messages.jsonl -p patterns.yaml -o output.yaml
ll-workflows analyze --input .ll/user-messages.jsonl \
                     --patterns .ll/workflow-analysis/step1-patterns.yaml
```

#### `ll-workflows propose`

Run Step 3 automation proposals from workflow analysis output. Invokes the `workflow-automation-proposer` skill and writes the proposals to a file. Use this as a CLI-native fallback when the interactive skill invocation is unavailable (e.g., `disable-model-invocation` breakage).

| Flag | Short | Description |
|------|-------|-------------|
| `--patterns` | `-p` | **Required.** Step 1 patterns YAML (from `ll-messages` or `workflow-pattern-analyzer`) |
| `--workflows` | `-w` | **Required.** Step 2 workflows YAML (from `ll-workflows analyze`) |
| `--output` | `-o` | Output path (default: `.ll/workflow-analysis/step3-proposals.yaml` or `.json`) |
| `--format` | `-f` | Output format: `yaml` (default) or `json` |

**Examples:**
```bash
# Full pipeline — Steps 1, 2, 3 non-interactively
ll-messages --output .ll/workflow-analysis/step1-patterns.jsonl
ll-workflows analyze --patterns .ll/workflow-analysis/step1-patterns.yaml
ll-workflows propose \
  --patterns .ll/workflow-analysis/step1-patterns.yaml \
  --workflows .ll/workflow-analysis/step2-workflows.yaml

# JSON output at a custom path
ll-workflows propose \
  --patterns step1.yaml \
  --workflows step2.yaml \
  --output out.json \
  --format json
```

---

## Synchronization

### ll-sync

Sync local `.issues/` files with GitHub Issues.

**Global flags:**

| Flag | Description |
|------|-------------|
| `--config` | Path to project root |
| `--quiet` | Suppress non-essential output |
| `--dry-run` | Show what would happen without making changes |

**Subcommands:**

#### `ll-sync status`

Show sync status between local issues and GitHub.

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | `-j` | Output as JSON (serializes `SyncStatus.to_dict()`) |

#### `ll-sync push [issue_ids...]`

Push local issues to GitHub. If no IDs given, pushes all. When an issue has a `milestone:` frontmatter field, `ll-sync push` passes it to `gh issue create/edit --milestone <name>` to assign the issue to the matching GitHub milestone (by title).

#### `ll-sync pull`

Pull GitHub Issues to local.

| Flag | Short | Description |
|------|-------|-------------|
| `--labels` | `-l` | Filter by labels (comma-separated) |

#### `ll-sync diff [issue_id]`

Show differences between local and GitHub issues. Omit `issue_id` for a summary of all synced issues.

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | `-j` | Output as JSON (serializes `SyncResult.to_dict()`) |

#### `ll-sync close [issue_ids...]`

Close GitHub issues for completed local issues.

| Flag | Description |
|------|-------------|
| `--all-completed` | Close all GitHub issues whose local counterparts have `status: done` or `status: cancelled` |

#### `ll-sync reopen [issue_ids...]`

Reopen GitHub issues for locally-active issues. After a successful reopen, the issue's `status` frontmatter is updated to `open`; the file stays in its type directory (`bugs/`, `features/`, etc.).

| Flag | Description |
|------|-------------|
| `--all-reopened` | Reopen all GitHub issues whose local counterparts are not closed on GitHub |

#### `ll-sync reconcile`

Promote feature-branch issues to `done` when their PR is merged. Takes no subcommand-specific flags — only the shared `--config` / `--quiet` / `--dry-run` globals apply. Prints `Reconcile complete: N issue(s) promoted to done`.

**Examples:**
```bash
ll-sync status                    # Show sync status
ll-sync status --json             # Sync status as JSON
ll-sync push                      # Push all local issues to GitHub
ll-sync push BUG-123              # Push specific issue
ll-sync pull                      # Pull GitHub Issues to local
ll-sync diff BUG-123              # Show diff for specific issue
ll-sync diff                      # Diff summary for all synced issues
ll-sync diff --json               # Diff summary as JSON
ll-sync close ENH-123             # Close GitHub issue for ENH-123
ll-sync close --all-completed     # Close all completed issues on GitHub
ll-sync reopen BUG-042            # Reopen GitHub issue for BUG-042
ll-sync reopen --all-reopened     # Reopen all issues moved back to active locally
ll-sync reconcile                 # Promote issues to done whose PR has merged
ll-sync reconcile --dry-run       # Preview promotions without writing
```

Requires `"sync": { "enabled": true }` in `.ll/ll-config.json`.

---

## Utilities

### ll-help

Generate the `/ll:*` command and skill catalog directly from `commands/*.md` and `skills/*/SKILL.md` frontmatter (FEAT-2940). Replaces the hand-maintained catalog that used to live in `commands/help.md`, so the listing can never drift from what's actually installed.

**Flags:**

| Flag | Description |
|------|-------------|
| `-C, --directory PATH` | Plugin root override (default: resolved via `CLAUDE_PLUGIN_ROOT` or repo root) |
| `--json` | Emit JSON |
| `--format {md,json}` | Output format (overrides `--json` when given) |
| `--area NAME` | Filter to a single area (e.g. `"Issue Refinement"`) |

**Examples:**
```bash
ll-help                          # Full catalog, grouped by area, markdown
ll-help --area "Code Quality"    # Just one area
ll-help --format json            # Structured output for tooling
```

---

### ll-messages

Extract user messages from Claude Code session logs.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--limit` | `-n` | Maximum messages to extract (default: 100) |
| `--since` | | Include only messages after this date (YYYY-MM-DD or ISO) |
| `--output` | `-o` | Output file path (default: `.ll/user-messages-{timestamp}.jsonl`) |
| `--cwd` | | Working directory to use (default: current directory) |
| `--exclude-agents` | | Exclude agent session files (`agent-*.jsonl`) |
| `--stdout` | | Print to stdout instead of writing to file |
| `--verbose` | `-v` | Print verbose progress information |
| `--include-response-context` | | Include metadata from assistant responses |
| `--skip-cli` | | Exclude CLI commands from output |
| `--commands-only` | | Extract only CLI commands, no user messages |
| `--tools` | | Comma-separated tools to extract commands from (default: `Bash`) |
| `--skill` | | Filter to sessions where this skill was invoked (e.g. `capture-issue`) |
| `--examples-format` | | Output `(input, output)` training pairs instead of raw messages (requires `--skill`); mutually exclusive with `--sft-format` |
| `--sft-format` | | Output conversation turns in SFT training format as JSON-lines (`chatml`, `alpaca`, `sharegpt`); mutually exclusive with `--examples-format` |
| `--context-window` | | Number of context turn-pairs per window in `--examples-format` or `--sft-format` (default: 3) |

**Examples:**
```bash
ll-messages                               # Last 100 messages to file
ll-messages -n 50                         # Last 50 messages
ll-messages --since 2026-01-01            # Messages since date
ll-messages -o output.jsonl               # Custom output path
ll-messages --stdout                      # Print to terminal
ll-messages --include-response-context    # Include response metadata
ll-messages --skip-cli                    # Exclude CLI commands
ll-messages --commands-only               # Extract only CLI commands
ll-messages --skill capture-issue         # Filter to sessions where /ll:capture-issue was invoked
ll-messages --skill capture-issue --examples-format --since 2026-01-01 -o examples.jsonl
ll-messages --skill refine-issue --examples-format --context-window 5 --stdout
ll-messages --sft-format chatml --stdout
ll-messages --sft-format sharegpt --context-window 3 --since 2026-05-01 --stdout
ll-messages --sft-format alpaca --output data/sft/raw.jsonl
```

---

### ll-logs

Discover and extract ll-relevant JSONL entries from Claude Code session logs. Also generates `logs/index.md` after extraction. The `sequences` subcommand mines tool-chain n-grams for workflow analysis. The `stats` subcommand aggregates per-skill invocation frequency and correction rate from `.ll/history.db`. The `dead-skills` subcommand cross-references the skill catalog against the log corpus to flag never-invoked and rarely-invoked skills. The `scan-failures` subcommand mines failed `ll-*` Bash calls to propose bug issue files.

**Subcommands:**

| Subcommand | Description |
|------------|-------------|
| `discover` | List all Claude projects with ll activity (one path per line, sorted) |
| `tail` | Stream live events from an active loop session |
| `extract` | Extract ll-relevant JSONL records to `logs/<slug>/<session-id>.jsonl` |
| `sequences` | Extract tool-chain n-grams of ll invocations from JSONL logs |
| `stats` | Aggregate skill invocation frequency and correction rate from history.db |
| `dead-skills` | Cross-reference skill catalog against log corpus to flag never/rarely-invoked skills |
| `scan-failures` | Mine failed ll-* Bash calls from session logs; cluster by error signature; optionally create bug issues |
| `diff` | Compare two sessions' ll-invocation behavior: skills added/removed, per-skill count deltas, and unified sequence diff |
| `eval-export` | Export EvalFixture v1 records reconstructed from session logs for use with `ll-harness` |
| `loop-fleet` | Aggregate cross-project loop-run outcomes for built-in loop improvement |

**`discover` flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | `-j` | Output as JSON: `{"paths": [...]}` |

**`tail` flags:**

| Flag | Description |
|------|-------------|
| `--loop NAME` | Loop name to tail (required) |
| `--project DIR` | Project root to tail loops from (default: CWD) |

**`extract` flags:**

| Flag | Description |
|------|-------------|
| `--all` | Extract all projects with ll activity |
| `--project DIR` | Working directory of the target project |
| `--cmd TOOL` | Filter to records containing this ll- tool name (e.g. `ll-history`) |
| `-j`, `--json` | Output as JSON (per-project rows, totals, `skipped`, `cmd_filter`, `zero_match`) |

On success, `extract` prints a per-project + totals summary (sessions/records
written, output dir) instead of nothing; unreadable JSONL files are reported
as `skipped` rather than silently dropped, and a `--cmd` filter that matches
zero records says so explicitly rather than looking like a no-op.

**`sequences` flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--all` | | Analyze all projects with ll activity |
| `--project DIR` | | Working directory of the target project |
| `--min-len N` | | Minimum n-gram length (default: 2) |
| `--min-count M` | | Minimum occurrence count to include (default: 1) |
| `--top N` | | Limit output to top N chains by frequency |
| `--window-days D` | | Only consider records within D days of latest record |
| `--since DATE` | | Only consider records on or after DATE (YYYY-MM-DD); mutually exclusive with `--window-days` |
| `--until DATE` | | Only consider records on or before DATE (YYYY-MM-DD); composes with `--window-days` or `--since` for a closed range |
| `--json` | `-j` | Output as JSON: `[{"chain": [...], "count": N, "edges": [{"from": "...", "to": "...", "freq": f, "pmi": 1.23, "lift": 3.4}], "pmi": 1.23, "lift": 3.4}]`; `pmi`/`lift` are optional additive fields; `lift < 1.0` signals a frequency-prior-equivalent pair |

`--all` and `--project` are mutually exclusive for `extract`, `sequences`, `stats`, `dead-skills`, `scan-failures`, `loop-fleet`, and `eval-export`. `--window-days` and `--since` are mutually exclusive (both express a lower bound); `--until` composes with either.

**`stats` flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--all` | | Aggregate across all projects with ll activity |
| `--project DIR` | | Working directory of the target project |
| `--window-days D` | | Only consider records within D days of latest record |
| `--since DATE` | | Only consider records on or after DATE (YYYY-MM-DD); mutually exclusive with `--window-days` |
| `--until DATE` | | Only consider records on or before DATE (YYYY-MM-DD) |
| `--sort {freq,corrections}` | | Sort by invocation frequency or correction count (default: freq) |
| `--json` | `-j` | Output as JSON: `[{"skill": str, "invocations": int, "corrections": int, "correction_rate": float}]` |

**`dead-skills` flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--all` | | Aggregate across all projects; catalog loaded from current directory |
| `--project DIR` | | Working directory of the target project (also used as catalog root) |
| `--window-days D` | | Only consider records within D days of latest record |
| `--since DATE` | | Only consider records on or after DATE (YYYY-MM-DD); mutually exclusive with `--window-days` |
| `--until DATE` | | Only consider records on or before DATE (YYYY-MM-DD) |
| `--threshold N` | | Skills with invocations ≤ N are "rarely" invoked (default: 3) |
| `--sort {tier,name}` | | Sort by tier (never before rarely) then invocation count, or alphabetically (default: tier) |
| `--json` | `-j` | Output as JSON: `[{"skill": str, "invocations": int, "tier": "never"\|"rarely"}]` |

**`scan-failures` flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--all` | | Scan all projects with ll activity |
| `--project DIR` | | Working directory of the target project |
| `--window-days D` | | Only consider records within D days of latest record |
| `--since DATE` | | Only consider records on or after DATE (YYYY-MM-DD); mutually exclusive with `--window-days` |
| `--until DATE` | | Only consider records on or before DATE (YYYY-MM-DD) |
| `--capture` | | Create BUG issue files for each failure cluster. When combined with `--all`, scopes capture to `Path.cwd()` by default — foreign-project clusters are reported but not filed. Use `--capture-foreign` to also create issues for clusters from other projects |
| `--capture-foreign` | | When `--capture --all` is active, also create BUG issues for failure clusters from projects outside the current working directory |
| `--limit N` | | Cap output to top N clusters by count (0 = unlimited, default) |
| `--skill NAME` | | Limit clusters to `ll-*` CLI failures that occurred while NAME was the enclosing skill (`<command-name>` marker or `Skill` tool_use block); `ll:` prefix optional. Does not filter failures of NAME's own `Read`/`Edit`/`Grep` calls — this subcommand never sees those. Attribution is heuristic |
| `--json` | `-j` | Output as JSON: `[{"tool": str, "count": int, "normalized_sig": str, "sample_error": str, "session_ids": [...], "skills": [...]}]` |

**`diff` flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `SESSION_A` | | First session ID or JSONL file path (positional) |
| `SESSION_B` | | Second session ID or JSONL file path (positional) |
| `--json` | `-j` | Output diff as JSON object |

**`eval-export` flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--project DIR` | | Project working directory (default: cwd) |
| `--skill NAME` | | Filter exported fixtures to this skill name |
| `--issue ID` | | Filter to fixtures where this issue ID appears in session context |
| `--limit N` | | Cap output record count (0 = unlimited) |
| `--out PATH` | | Write output to file (default: stdout) |
| `--json` | `-j` | JSON output instead of default YAML |

**`loop-fleet` flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--all` | | Aggregate across all projects with ll activity |
| `--project DIR` | | Working directory of the target project |
| `--loop NAME` | | Filter to a specific loop name |
| `--window-days D` | | Only consider runs within D days of latest run |
| `--since DATE` | | Only consider runs on or after DATE (YYYY-MM-DD); mutually exclusive with `--window-days` |
| `--until DATE` | | Only consider runs on or before DATE (YYYY-MM-DD) |
| `--existing-only` | | Skip projects that no longer exist on disk (only meaningful with `--all`) |
| `--sort {success,name}` | | Sort by success rate ascending (worst first) or alphabetically (default: success) |
| `--limit N` | | Cap `--json` output to N most recent per-run rows (0 = unlimited, default); does not affect the aggregated table |
| `--json` | `-j` | Output as JSON: one row per run — `[{"loop_name": str, "project": str, "run_folder": str, "final_state": str, "iterations": int, "outcome": str, "ts": str, "attribution": "builtin"\|"custom"}]` |

**Examples:**
```bash
ll-logs discover                          # List all projects with ll activity
ll-logs discover --json                   # Output paths as JSON array
ll-logs tail --loop my-loop              # Stream live events from an active loop session
ll-logs extract --all                    # Extract all projects to logs/
ll-logs extract --project /path/to/proj  # Extract one project to logs/<slug>/
ll-logs extract --all --cmd ll-history   # Filter to ll-history invocations
ll-logs sequences --all                  # Find all tool-chain bigrams (default min-len=2)
ll-logs sequences --project /path -j     # Output n-grams as JSON for one project
ll-logs sequences --all --top 10         # Top 10 most frequent chains
ll-logs sequences --all --min-len 3 --min-count 3  # Trigrams appearing ≥3 times
ll-logs stats --all                      # Skill frequency/correction table across all projects
ll-logs stats --project /path --json     # JSON stats for one project
ll-logs stats --all --sort corrections   # Sort by correction count (highest first)
ll-logs stats --all --window-days 30     # Limit to last 30 days of data
ll-logs stats --all --since 2026-01-01 --until 2026-01-31  # Closed date range
ll-logs dead-skills --project /path/to/proj --json  # List never/rarely-invoked skills as JSON
ll-logs dead-skills --project . --threshold 5       # Skills with <=5 invocations
ll-logs dead-skills --all --window-days 90          # Dead skills across all projects, last 90 days
ll-logs dead-skills --all --sort name               # Alphabetical order instead of tier-then-count
ll-logs scan-failures --all                         # Report all failed ll-* calls across all projects
ll-logs scan-failures --project /path --json        # JSON failure clusters for one project
ll-logs scan-failures --all --window-days 30        # Only failures from last 30 days
ll-logs scan-failures --all --limit 10              # Top 10 failure clusters by count
ll-logs scan-failures --all --capture               # Create BUG issues for each failure cluster
ll-logs scan-failures --project . --skill review-epic --json  # Failures attributed to one skill
ll-logs loop-fleet --all                            # Loop success-rate table, worst-first
ll-logs loop-fleet --project . --sort name          # Alphabetical instead of success-rate order
ll-logs loop-fleet --all --json --limit 50          # Most recent 50 per-run JSON rows
ll-logs diff SESSION_A SESSION_B                    # Compare behavioral diff between two sessions
ll-logs diff SESSION_A SESSION_B --json             # Diff output as JSON
ll-logs eval-export --project .                     # Export all fixtures from current project (YAML)
ll-logs eval-export --skill refine-issue --json     # JSON fixtures for refine-issue only
ll-logs eval-export --issue ENH-1710 --limit 10     # Up to 10 fixtures touching ENH-1710
```

**Companion loop — `ll-logs-telemetry-digest`** (FEAT-1925)

A project-local FSM loop that orchestrates the full `ll-logs` analysis pipeline in a single unattended run:
1. Refreshes the log corpus (`ll-logs extract`)
2. Runs `stats`, `sequences`, `scan-failures`, and `dead-skills` subcommands
3. Triages findings into issue files
4. Writes a digest artifact to `.loops/runs/ll-logs-telemetry-digest-<timestamp>/digest.md`

Subcommands not yet available are skipped gracefully via capability detection — the loop gains depth as new subcommands land.

```bash
ll-loop run ll-logs-telemetry-digest    # Full telemetry digest pass
```

---

### ll-session

Query the unified session store (SQLite + FTS5) — the per-project `.ll/history.db` populated by `SQLiteTransport`, `AutoManager` (live-writes issue lifecycle events during `ll-auto` runs), and `ll-session backfill` (for historical data captured before ENH-1691). Lets operators search and inspect session activity without re-parsing the scattered JSON/markdown sources the analyze-* skills read.

**Global flags:**

| Flag | Description |
|------|-------------|
| `--db PATH` | Path to the session database (default: `.ll/history.db`) |

**Subcommands:**

| Subcommand | Description |
|------------|-------------|
| `search` | FTS5 full-text query with BM25-ranked results |
| `recent` | Most recent rows for an event kind; optionally filtered by issue |
| `skill-stats` | Per-skill invocation/completion/success-rate rollup from `skill_events` completion columns; `--since DATE` bounds the window (ENH-2460) |
| `backfill` | Seed the database from existing on-disk sources; `--since DATE` uses incremental JSONL-only mode (ENH-1830); `--snapshots` seeds the `issue_snapshots` table from `.issues/` files (ENH-2151); `--extract-decisions` runs `extract-from-completed` after backfill (ENH-2152); `--max-sessions N` caps how many sessions are compacted in this run (newest first, useful for large DBs) (ENH-2252) |
| `export` | Dump selected history tables as JSONL to stdout or a file — for visualization, external tooling, or backup (ENH-2252) |
| `related` | Issue events for a given issue ID |
| `subagents SESSION_ID` | Subagent spawn tree for a session, or `--budget` for a spawn-count/duration rollup (ENH-3211) |
| `subagent-retries AGENT_TYPE` | Sessions that re-spawned `AGENT_TYPE` more than once; `--since DATE` bounds the window (ENH-3211) |
| `path` | Resolve the JSONL file path for a session ID |
| `grep` | Regex search over `message_events` with optional summary-node scope filtering; condensed nodes use recursive CTE for N-level DAG traversal (ENH-1955) |
| `expand` | Return all `message_events` covered by a given summary node ID; condensed nodes use recursive CTE for N-level DAG traversal (ENH-1955) |
| `describe` | Show metadata (level, block span, parent) for a summary node |
| `rebuild` | Re-derive the JSONL-cache tables (`tool_events`, `message_events`, …) from `raw_events`; idempotent (ENH-2581) |
| `compact` | Sweep `raw_events` past the retention max-age into per-session `retention` summary nodes; `--and-prune` also deletes and VACUUMs (ENH-2581) |
| `recompress` | Rewrite legacy uncompressed `raw_events` payloads (`raw_line`/`parsed_json`) as zlib BLOBs and VACUUM; idempotent, off-hot-path maintenance (ENH-2624) |
| `prune` | Delete raw event rows older than configured `analytics.retention` max-age and VACUUM the DB |

**`grep` flags:**

| Flag | Description |
|------|-------------|
| `PATTERN` | Regex pattern (required, positional; case-insensitive) |
| `--summary-id ID` | Restrict search to messages covered by this summary node ID |
| `--limit N` | Maximum results (default: 50) |
| `--json` | Output results as a JSON array |

**`expand` flags:**

| Flag | Description |
|------|-------------|
| `SUMMARY_ID` | Summary node ID to expand (required, positional) |
| `--json` | Output message events as a JSON array |

**`describe` flags:**

| Flag | Description |
|------|-------------|
| `NODE_ID` | Summary node ID to describe (required, positional) |
| `--json` | Output metadata as a JSON object |

**`search` flags:**

| Flag | Description |
|------|-------------|
| `--fts QUERY` | FTS5 match query (required) |
| `--kind {tool,file,issue,loop,correction,message,skill,cli,snapshot,commit,test_run,usage,orchestration_run,loop_run,learning_test,session_lifecycle,subagent_run,hook_event,harness,prompt_opt,verdict,context_pressure}` | Filter results by event kind (optional; choices come from `VALID_KINDS`) |
| `--limit N` | Maximum results (default: 20) |
| `--json` / `-j` | Output results as a JSON array |

**`recent` flags:**

| Flag | Description |
|------|-------------|
| `--kind {tool,file,issue,loop,correction,message,skill,cli,snapshot,commit,test_run,usage,orchestration_run,loop_run,learning_test,session_lifecycle,subagent_run,hook_event,harness,prompt_opt,verdict,context_pressure}` | Event kind to list (required unless `--issue` is given). `skill` rows include `exit_code`/`success`/`duration_ms` when a completion-side host recorded them (ENH-2460). The full choice list is sourced from `VALID_KINDS`; `orchestration_run` exposes per-issue `ll-auto`/`ll-parallel`/`ll-sprint` outcomes (ENH-2492); `loop_run` exposes per-run FSM loop summaries (ENH-2463); `learning_test` exposes the Learning Test Registry mirror (ENH-2466); `session_lifecycle` exposes session-lifecycle/handoff transitions — `handoff_needed`/`compaction`/`stale_ref_sweep` (ENH-2495); `subagent_run` exposes the subagent (Task/Agent) spawn tree recorded by the `SubagentStart`/`SubagentStop` lifecycle hooks (ENH-2505). |
| `--issue ID` | Filter to sessions that co-occurred with this issue (e.g. `ENH-1710`). Without `--kind`, lists sessions directly from the `issue_sessions` view. Issues processed after ENH-1839 populate `captured_at` immediately; a prior `backfill` pass is only needed for older issues. |
| `--mcp-server NAME` / `--mcp-tool NAME` / `--mcp-outcome {success,error,timeout}` | With `--kind tool`, filter to MCP tool-call rows by server/tool/outcome (`tool_events.mcp_server`/`mcp_tool`/`mcp_outcome`, ENH-2511). Ignored for other `--kind` values. |
| `--limit N` | Maximum rows (default: 20) |
| `--json` | Output as a JSON array |

**`subagents` flags:**

| Flag | Description |
|------|-------------|
| `SESSION_ID` | Parent session ID to look up (required, positional) |
| `--budget` | Show spawn count + total duration (`subagent_budget`) instead of the per-row tree; also reports rows excluded from the duration total (no `ended_at`), split into `running`/`orphaned` counts so a still-in-flight spawn is never mislabeled as orphaned |
| `--json` / `-j` | Output as JSON |

**`subagent-retries` flags:**

| Flag | Description |
|------|-------------|
| `AGENT_TYPE` | Agent type to check for repeat spawns (required, positional) |
| `--since DATE` | Only count spawns at or after this ISO 8601 date/datetime |
| `--json` / `-j` | Output as JSON |

**`backfill` flags:**

`backfill` ingests session JSONL lines into `raw_events` only (ENH-2581) —
issue/loop-state/commit data is still written directly. The JSONL-derived
cache tables (`tool_events`, `message_events`, `assistant_messages`,
`skill_events`, `sessions`) are populated by a separate `rebuild` (or
`backfill --rebuild` in the same call).

| Flag | Description |
|------|-------------|
| `--since DATE` | Incremental mode: only process JSONL files modified on or after DATE (ENH-1830) |
| `--host HOST` | Filter to a single host source: `claude-code`, `codex`, `opencode`, or `pi` |
| `--rebuild` | Also materialize the JSONL-derived cache tables from `raw_events` in this call (ENH-2581) |
| `--snapshots` | Also seed the `issue_snapshots` table from `.issues/` files (ENH-2151) |
| `--extract-decisions` | Run `extract-from-completed` on issue history after backfill (ENH-2152) |
| `--max-sessions N` | Cap the number of sessions compacted in this run (newest first); useful for large DBs that would otherwise time out (ENH-2252) |

**`rebuild` flags:**

| Flag | Description |
|------|-------------|
| `--config PATH` | Path to `ll-config.json` (default: auto-resolve from cwd) |
| `--json` | Output row counts as JSON |

Wipes and re-derives `tool_events`, `message_events`, `assistant_messages`,
`skill_events`, `sessions`, `user_corrections`, `summary_nodes`/
`summary_spans`, and their `search_index` rows from `raw_events`. Idempotent.
Issue/loop/commit/cli/file/test_run/orchestration tables are outside `raw_events`'s scope
and are untouched (ENH-2581, ENH-2492).

**`compact` flags:**

| Flag | Description |
|------|-------------|
| `--and-prune` | Also delete the newly-compacted `raw_events` rows and VACUUM afterward |
| `--config PATH` | Path to `ll-config.json` (default: auto-resolve from cwd) |
| `--json` | Output result summary as JSON |

Sweeps `raw_events` rows past `analytics.retention.raw_event_max_age_days`
into per-session `kind='retention'` `summary_nodes` rows (a deterministic
one-liner, not an LLM summary) and marks them `compacted=1` so `prune` can
delete them safely later (ENH-2581).

**`recompress` flags:**

| Flag | Description |
|------|-------------|
| `--batch N` | Rows to rewrite per transaction (default: 2000) |
| `--json` | Output result summary as JSON |

New `raw_events` rows written by `backfill` already store `raw_line`/`parsed_json`
as zlib-compressed BLOBs (~2.9× smaller per row). `recompress` is a one-time
maintenance sweep that converts pre-existing uncompressed TEXT rows (written
before ENH-2624) to the compressed form and VACUUMs afterward. The read path
(`rebuild`) transparently decompresses either representation, so the command is
idempotent and byte-lossless — running it twice is a no-op on the second pass.

**`export` flags:**

| Flag | Description |
|------|-------------|
| `--tables TYPE [TYPE…]` | Tables to include (default: all types except `message_event`). Choices: `session`, `issue_event`, `issue_snapshot`, `skill_event`, `loop_event`, `correction`, `summary_node`, `message_event`, `commit_event`, `test_run_event`, `usage_event`, `orchestration_run`, `loop_run`, `session_lifecycle_event`, `harness_event`, `prompt_opt_event`, `verdict_event`, `context_pressure_event`, `review_event` — 19 in total. The `--help` text is derived from `_EXPORT_TABLE_MAP` (BUG-3197), so it is authoritative if this table ever falls behind again |
| `--since DATE` | Only rows at or after this ISO 8601 date/datetime |
| `--include-messages` | Also include `message_events` (potentially large); ignored when `--tables` is given explicitly |
| `-o / --output FILE` | Write output to FILE instead of stdout |

**Examples:**
```bash
ll-session search --fts "rate limit"            # Full-text search, BM25-ranked
ll-session recent --kind loop                   # Recent loop events
ll-session recent --kind commit                 # Recent git commits (ENH-2458)
ll-session recent --kind test_run               # Recent pytest runs (ENH-2459)
ll-session recent --kind orchestration_run       # Per-issue automation outcomes (ENH-2492)
ll-session recent --kind loop_run                # Recent FSM loop run summaries (ENH-2463)
ll-session recent --kind learning_test           # Recent Learning Test Registry mirror rows (ENH-2466)
ll-session recent --kind session_lifecycle       # Recent session-lifecycle/handoff transitions (ENH-2495)
ll-session recent --kind subagent_run            # Recent subagent (Task/Agent) spawns (ENH-2505)
ll-session recent --kind hook_event              # Recent hook fires: exit_code/duration_ms/stderr_preview (ENH-2506)
ll-session recent --kind harness                 # Recent ll-harness / eval outcomes (ENH-2739)
ll-session recent --kind verdict                 # Recent verifier verdicts (ENH-2504)
ll-session recent --kind context_pressure        # Recent context-window pressure samples (ENH-2507)
ll-session recent --kind review                  # Recent audit/review outcomes (ENH-2512)
ll-session search --fts "streaming" --kind learning_test  # Registry records by claim/target (ENH-2466)
ll-session recent --kind tool --mcp-server pencil --mcp-outcome error  # MCP failures for one server (ENH-2511)
ll-session skill-stats --since 2026-06-01       # Per-skill success rates (ENH-2460)
ll-session recent --issue ENH-1710              # Sessions that touched ENH-1710
ll-session recent --kind message --issue ENH-1710  # Messages from those sessions
ll-session subagents <session_id>               # Subagent spawn tree for a session (ENH-3211)
ll-session subagents <session_id> --budget      # Spawn count + total duration, with excluded-row count (ENH-3211)
ll-session subagent-retries Explore             # Sessions that re-spawned Explore more than once (ENH-3211)
ll-session backfill                             # Ingest on-disk sources (raw_events + issues/loops/commits)
ll-session backfill --rebuild                   # Ingest, then materialize cache tables in one call
ll-session backfill --since 2026-01-01          # Incremental JSONL backfill since date
ll-session backfill --max-sessions 50           # Compact at most 50 sessions this run
ll-session rebuild                              # Re-derive cache tables from raw_events (ENH-2581)
ll-session compact --and-prune                  # Sweep+summarize old raw_events, then delete (ENH-2581)
ll-session path <session_id>                    # Resolve JSONL file path for a session ID
ll-session grep "error"                         # Regex search over messages
ll-session grep "traceback" --summary-id 5      # Search within a summary node's span
ll-session expand 5                             # List messages covered by summary node 5
ll-session describe 5                           # Show metadata for summary node 5
ll-session export                               # Dump all non-message tables to stdout as JSONL
ll-session export --tables issue_event loop_event -o history.jsonl  # Selective export to file
ll-session export --since 2026-01-01 --include-messages             # Full dump since date
ll-session prune --dry-run                      # Preview what would be pruned without deleting
ll-session prune                                # Delete old raw events and VACUUM
ll-session prune --json                         # Prune result as JSON
ll-session recompress                           # Compress legacy raw_events payloads and VACUUM (ENH-2624)
ll-session recompress --batch 5000              # Rewrite 5000 rows per transaction
```

**`prune` flags:**

| Flag | Description |
|------|-------------|
| `--dry-run` | Report rows that would be deleted without actually deleting them |
| `--json` | Output result summary as JSON |

Pruning is dual-gated by `analytics.retention` config: both `min_project_age_days` and `min_db_size_mb` must be exceeded before any rows are deleted (defaults: 365 days, 800 MB). Only `raw_events` rows already marked `compacted=1` (by `compact`) past `raw_event_max_age_days` are deleted (ENH-2581) — issue/loop/commit/cli/file/test_run tables and uncompacted `raw_events` rows are never pruned. See `analytics.retention` in [CONFIGURATION.md](CONFIGURATION.md).

---

### ll-compact-session

Manually trigger LCM session-memory compaction for **one** session, collapsing its messages into summary nodes.

**Not the same command as [`ll-session compact`](#ll-session).** `ll-session compact` is the retention sweep — it folds aged `raw_events` into per-session `retention` summary nodes across the whole database. `ll-compact-session` is the LCM memory compaction for a single named session, and is the manual equivalent of what the PreCompact hook path runs automatically.

| Argument | Description |
|----------|-------------|
| `SESSION_ID` | Session ID to compact |

| Flag | Short | Description |
|------|-------|-------------|
| `--db PATH` | | Path to the session database (default: `.ll/history.db`) |
| `--json` | `-j` | Output as JSON |

JSON keys: `session_id`, `new_leaves`, `summary_text`, `compacted_messages`, `context_token_estimate`.

**Examples:**
```bash
ll-compact-session abc123-session-id           # Compact one session, human-readable output
ll-compact-session abc123-session-id --json    # Machine-readable result
```

---

### ll-queue

Persisted work-item queue, backed by a dedicated `.ll/queue.db` (FEAT-2682) — distinct from [`ll-loop queue`](#queue-entries-loopsqueue)'s PID-liveness marker mechanism, which FEAT-2684 preserves unchanged as a compat shim rather than migrating. Schema: `{id, action, enqueuedAt, priority, status, result, claimedAt, ownerPid}`, ordered by priority tier then FIFO within tier.

**Subcommands:**

| Subcommand | Description |
|------------|-------------|
| `add TARGET` | Classify and persist a new entry |
| `list` | List all entries, ordered by priority then FIFO |
| `status ID` | Show one entry's state and result by full id or 8+-char prefix |
| `remove ID` | Delete a `pending` entry by full id or 8+-char prefix |
| `run` | Serially dequeue and dispatch all `pending` entries in priority/FIFO order; `--watch` (FEAT-2930) keeps it running |
| `requeue ID [--force]` | (FEAT-2930) Return a stranded `running` entry to `pending` |

**`add` flags:**

| Flag | Description |
|------|-------------|
| `TARGET` | FSM loop name, skill/command name, or raw CLI invocation (required, positional) |
| `--priority {P0,P1,P2,P3,P4,P5}` | Priority tier (default: `P3`) |
| `--runner {skill,cmd,mcp,prompt,loop}` | Force a specific runner kind instead of classifying `TARGET` |
| `--arg KEY=VALUE` | Extra `ActionSpec` arg (repeatable) |
| `--input INPUT` | (FEAT-2906) Input for a `LOOP`-runner target, same semantics as `ll-loop run <loop> [input]` — stored verbatim and interpreted at dequeue time, not re-parsed here |
| `--timeout N` | Subprocess timeout in seconds. Default is per-runner: unbounded (no outer deadline) for `--runner loop`, since the FSM already enforces its own budget stack (`timeout:`/`max_steps`); `120` for every other runner kind. An explicit `--timeout N` always overrides (BUG-2928). |
| `--json` | Output the new entry as JSON |

Without `--runner`, `TARGET` is classified in order: an FSM loop name (resolved the same way `ll-loop run` resolves a loop), a skill/command name (resolved via `skills/<name>/SKILL.md` / `commands/<name>.md`), else falls back to a raw CLI invocation.

**`list` flags:**

| Flag | Description |
|------|-------------|
| `--json` | Output all entries as JSON |
| `--wide` | (ENH-2931) Show the untruncated args/timeout summary instead of truncating to 40 chars |

Each row appends an args/timeout summary to the `runner:target` column: the entry's
`loop_input` (if any), the effective `timeout` (`timeout=∞` for the unbounded `LOOP`
default), and — for `running` entries — elapsed time since `enqueuedAt`. Truncated to
40 chars unless `--wide` is passed; full values remain available via `ll-queue status
<id> --json`.

**`status`/`remove` flags:**

| Flag | Description |
|------|-------------|
| `ID` | Entry id — full uuid or an 8+-char prefix (required, positional) |
| `--force` | (`remove` only) remove even if the entry is not `pending` |
| `--json` | Output as JSON |

**`run`** (FEAT-2906): `SKILL`/`CMD`/`MCP`/`PROMPT` entries dispatch through `run_action()`; `LOOP` entries are intercepted beforehand and driven via a subprocess `ll-loop run <target> [input]` shell-out (process isolation, matching `worker_pool.py`/`cli/sprint/run.py`'s precedent) — never through `run_action()`, whose contract explicitly refuses `RunnerType.LOOP`. Exit code `0` → `done`; `FAILURE_TERMINAL_EXIT_CODE` (2) or any other nonzero → `failed`, with `stdout`/`stderr` captured into the entry's `result`.

Without `--watch`, this behavior is unchanged: drain what's pending, then exit. With `--watch` (FEAT-2930), it becomes a long-lived drainer — after draining, it sleep-polls for new entries (`--poll-interval`, default 3s) instead of exiting. Shutdown is two-stage: a first `SIGINT`/`SIGTERM` lets the in-flight entry finish and records its real result, then exits 0 without claiming further work; a second forwards `SIGTERM` to an in-flight `LOOP` child's process group (launched with `start_new_session=True`), marks that entry `failed` with `error: "interrupted by operator"`, and exits 0. An idle wait (no entry in flight) exits 0 immediately on either signal. On startup and each idle poll, a `--watch` drainer also sweeps `running` entries whose `owner_pid` is dead back to `pending` (psutil identity-checked liveness, same approach as `ll-loop queue`'s FEAT-2684 mechanism but parameterized for `ll-queue`'s own process markers) — a `SIGKILL`ed/OOM-killed/rebooted owner is the normal failure mode for a long-lived drainer, not a rare one.

**`--json` under `--watch` is NDJSON, a deliberate departure from this file's single-array `--json` convention**: one compact JSON object per line, one line per processed entry, flushed immediately — a watcher never reaches a natural end-of-list, so it can't emit one accumulated array. Without `--watch`, `--json` is unchanged (single array).

| Flag | Description |
|------|-------------|
| `--json` | Output processed entries as JSON — a single array without `--watch`, NDJSON (one object per line) with it |
| `--watch` | (FEAT-2930) Long-lived drainer: sleep-poll for new work instead of exiting after draining |
| `--poll-interval SECONDS` | (FEAT-2930) Seconds between polls under `--watch` (default: `3`) |

**`requeue` flags:**

| Flag | Description |
|------|-------------|
| `ID` | Entry id — full uuid or an 8+-char prefix (required, positional) |
| `--force` | Requeue even if the owner process still appears alive |
| `--json` | Output as JSON |

`requeue` (FEAT-2930) is the manual escape hatch for a `running` entry whose owner is gone or wedged. Without `--force`, it refuses (leaving the entry `running`) when the owner still looks alive — that's the automatic stale-reclaim sweep's job. `--force` is for the case the sweep can't decide: owner still alive but wedged, per the operator's own judgement. Errors if the entry isn't `running` at all.

**Examples:**
```bash
ll-queue add audit-docs                                  # Enqueue a skill (classified automatically)
ll-queue add "pytest scripts/tests/" --runner cmd --priority P1
ll-queue add rn-refine --input '{"issue_id": "FEAT-2900"}' --priority P1
ll-queue list --json
ll-queue list --wide                                      # Untruncated args/timeout summary
ll-queue status abcd1234
ll-queue remove abcd1234 --force
ll-queue run                                              # Execute all pending entries serially
ll-queue run --watch --poll-interval 5                    # Long-lived drainer, polling every 5s
ll-queue requeue abcd1234                                 # Return a stranded running entry to pending
```

---

### ll-history-context

Query `.ll/history.db` for user corrections and FTS5 matches related to an issue ID and print a ready-to-inject `## Historical Context` markdown block. Returns empty output (exit 0) when the DB is missing, has no matches, or all rows are stale (>30 days old).

Pass `--project` instead of an issue ID to print the project-wide context digest that `session_start` would inject (dry-run / config-tuning mode, ENH-1907).

**Flags:**

| Flag | Description |
|------|-------------|
| `ISSUE_ID` | Issue ID to query (optional, e.g. `ENH-1708`). Mutually exclusive with `--project`. |
| `--project` | Print the project-wide context digest (dry-run of session-start injection). |
| `--file PATH` | Also include recent file events for this path (issue-mode only) |
| `--db PATH` | Path to the session database (default: `.ll/history.db`) |
| `--effort` | Output a `## Effort Context` block with per-issue session count and cycle time (ENH-1905) |
| `--for-skill NAME` | Exit 0 with no output if NAME is not in `history.planning_skills` (ENH-1909) |

When `learning_tests.enabled` is `true` and the queried issue has `learning_tests_required` declared, an additional `## Learning Test Evidence` block is appended (ENH-2217). The block lists each declared target with its current registry status (proven / stale / refuted / missing), so planning skills that call `ll-history-context` automatically surface assumption coverage without an extra `ll-learning-tests check` call.

**Output cap:** At most 5 rows are rendered in issue mode. Project mode respects `history.session_digest.char_cap` (default 1200 chars).

**Effort Context block:** When `--effort` is passed, a `## Effort Context` section is appended after the `## Historical Context` block (or emitted alone when no corrections/FTS matches exist). It includes the session count and cycle time (first-to-last session span in days) for the queried issue, plus a velocity table of recently completed issues drawn from `recent_issue_velocity()`. Returns empty output when the DB is absent or the issue has no recorded sessions.

**Examples:**
```bash
ll-history-context ENH-1708                        # Corrections matching the issue ID
ll-history-context ENH-1708 --file src/foo.py      # Also include recent file events
ll-history-context ENH-9999                        # Returns empty output when no matches
ll-history-context --project                        # Print project-wide digest (dry-run)
ll-history-context --project --db .ll/history.db   # Use a specific DB path
```

---

### ll-gitignore

Suggest and apply `.gitignore` patterns based on untracked files.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--dry-run` | `-n` | Preview suggestions without modifying `.gitignore` |
| `--json` | `-j` | Output as JSON (serializes `GitignoreSuggestion` fields) |
| `--quiet` | `-q` | Suppress non-essential output |
| `--config` | | Path to project root (default: current directory) |

**Examples:**
```bash
ll-gitignore                  # Show suggestions and apply approved patterns
ll-gitignore --json           # Output suggestions as JSON
ll-gitignore --dry-run        # Preview suggestions without modifying .gitignore
ll-gitignore --quiet          # Suppress non-essential output
```

---

### ll-migrate

One-time migration script that moves all issues from `completed/` and `deferred/` directories into their type-based directories, backfills `completed_at:` for older completed files, and sets correct `status:` frontmatter. Part of the ENH-1390 status-decoupling migration.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--dry-run` | `-n` | Preview all planned moves without modifying files |
| `--config` | `-C` | Path to project root (default: current directory) |

**Examples:**
```bash
ll-migrate --dry-run   # Preview all planned moves (strongly advised before running)
ll-migrate             # Execute migration
ll-migrate --config /path/to/project  # Run for a specific project
```

---

### ll-migrate-relationships

One-time migration script that renames deprecated relationship frontmatter keys in all `.md` files under `.issues/`: `parent_issue:` → `parent:` and `related:` → `relates_to:`. Part of the ENH-1434 relationship field standardization.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--dry-run` | `-n` | Preview all planned renames without modifying files |
| `--config` | `-C` | Path to project root (default: current directory) |

**Examples:**
```bash
ll-migrate-relationships --dry-run   # Preview all planned renames
ll-migrate-relationships             # Execute migration
ll-migrate-relationships --config /path/to/project  # Run for a specific project
```

---

### ll-migrate-labels

One-time migration script that reads the freeform `## Labels` body section from all `.md` files under `.issues/` and writes the labels as a `labels:` YAML list in frontmatter. Part of the ENH-1392 labels field addition.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--dry-run` | `-n` | Preview all planned migrations without modifying files |
| `--config` | `-C` | Path to project root (default: current directory) |

**Examples:**
```bash
ll-migrate-labels --dry-run   # Preview all planned migrations
ll-migrate-labels             # Execute migration
ll-migrate-labels --config /path/to/project  # Run for a specific project
```

---

### ll-migrate-status

One-time migration script that reads the `status:` frontmatter field from all `.md` files under `.issues/` and rewrites any non-canonical synonyms (e.g. `completed`, `wip`) to their canonical equivalents. Uses the authoritative `STATUS_SYNONYMS` map from `frontmatter.py`. Part of the ENH-1551 cleanup pass.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--dry-run` | `-n` | Preview all planned normalizations without modifying files |
| `--config` | `-C` | Path to project root (default: current directory) |

**Examples:**
```bash
ll-migrate-status --dry-run   # Preview all planned normalizations
ll-migrate-status             # Execute migration
ll-migrate-status --config /path/to/project  # Run for a specific project
```

---

### ll-verify-docs

Verify that documented counts (commands, agents, skills, loops) match actual file counts.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | `-j` | Output as JSON |
| `--format` | `-f` | Output format: `text` (default), `json`, `markdown` |
| `--fix` | | Auto-fix count mismatches in documentation files |
| `--directory` | `-C` | Base directory (default: current directory) |

Each mismatch carries a closed-vocabulary `action_severity` field (`auto`/`mention`/`route`, ENH-2886), mirroring `ll-doctor`'s `CheckResult.severity` shape: `auto` is safe to rewrite silently, `mention` needs a human to confirm, `route` names the command that owns the repair (`route_owner`). `--fix` only rewrites `auto`-severity mismatches — `mention`/`route` findings are reported but left untouched. `verify_documentation()` currently emits `auto` for every count mismatch it finds; the other two values exist for callers that construct `CountResult` directly. `--json`/`--format json` output includes `action_severity` and `route_owner` on each mismatch.

**Exit codes:** `0` = all counts match, `1` = mismatches found, `2` = error

**Examples:**
```bash
ll-verify-docs                    # Check and show results
ll-verify-docs --json             # Output as JSON
ll-verify-docs --format markdown  # Markdown report
ll-verify-docs --fix              # Auto-fix mismatches (auto-severity only)
```

---

### ll-verify-skill-budget

Check that the total skill description token footprint stays within the Claude Code listing budget.

Scans all `skills/*/SKILL.md` frontmatter `description` fields. Skips skills with `disable-model-invocation: true`. Token estimate: `len(description) // 4`. Exits 1 if total exceeds the threshold.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--threshold` | | Token budget threshold (default: 2000; overrides ll-config.json) |
| `--json` | `-j` | Output as JSON |
| `--directory` | `-C` | Base directory (default: current directory) |

**Exit codes:** `0` = under budget, `1` = over budget

**Examples:**
```bash
ll-verify-skill-budget                # Check against default 2000-token budget
ll-verify-skill-budget --json          # Output as JSON
ll-verify-skill-budget --threshold 1500  # Custom threshold
```

---

### ll-verify-skills

Check that no `SKILL.md` file exceeds the 500-line limit.

Scans all `skills/*/SKILL.md` files. Skips skills with `disable-model-invocation: true`. Exits 1 if any file exceeds the limit.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--limit` | | Maximum lines per SKILL.md (default: 500) |
| `--json` | `-j` | Output as JSON |
| `--directory` | `-C` | Base directory (default: current directory) |

**Exit codes:** `0` = all within limit, `1` = violations found

**Examples:**
```bash
ll-verify-skills                    # Check against default 500-line limit
ll-verify-skills --limit 400        # Custom limit
ll-verify-skills --json             # Output as JSON
```

---

### ll-verify-triggers

Validate skill description trigger accuracy against should-fire and should-NOT-fire
phrasings. Reports per-skill precision/recall and a cross-skill collision matrix.

Only **model-invocable** skills are scored — skills declaring
`disable-model-invocation: true` are excluded from the table, the coverage
denominator, and the exit code, since trigger accuracy is meaningless for a skill
the model can never auto-invoke.

A skill that declares no `trigger_fixtures` is reported as **unmeasured** in its
own section and counted against the `Fixture coverage: M/N` line — it is *not*
scored 0% and cannot fail a threshold. Collision detection is reported as skipped
rather than clean when no fixtures were available to test.

**Matching semantics (ENH-2884):** a phrasing is scored against every
model-invocable skill's keyword set (`_match_score`, shared-token count) and
resolves to whichever skill scores highest — modeling a host resolving a
phrasing to a single best-matching skill, not every skill that happens to
share a token. A collision is reported only when two or more skills tie for
the top score.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | | Output as JSON |
| `--directory` | `-C` | Base directory (default: current directory) |
| `--precision-threshold` | | Minimum precision required (default: 0.5) |
| `--recall-threshold` | | Minimum recall required (default: 0.5) |

**Exit codes:** `0` = all *measured* skills meet thresholds, no collisions (a tree
with zero fixtures exits 0); `1` = a skill that has fixtures missed a threshold, or
a collision was detected.

**Examples:**
```bash
ll-verify-triggers                         # Validate all skills against default thresholds
ll-verify-triggers --json                  # Machine-readable JSON output
ll-verify-triggers --precision-threshold 0.8 --recall-threshold 0.6
```

---

### ll-verify-package-data

Lint the `little_loops` package source for `__file__`-escape patterns that break non-editable installs, and verify every declared asset is accessible via `importlib.resources` in the current installation. Both gates must pass for exit 0.

**Two checks run by default:**

1. **`__file__`-escape lint** — regex-scans every `.py` file under `little_loops/` for `Path(__file__).parents[N]` or `.parent.parent...` chains whose traversal depth exits the package directory. Reports violations with file and line number.
2. **Manifest completeness check** — verifies every asset in `PACKAGE_DATA_ASSETS` (`package_data.py`) is reachable via `importlib.resources`. Catches assets missing from the wheel (e.g., omitted from `MANIFEST.in` or `pyproject.toml`).

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | | Output as JSON |
| `--directory` | `-C` | Project root containing the `little_loops` package (default: cwd) |
| `--lint-only` | | Run only the `__file__`-escape lint (skip manifest check) |
| `--manifest-only` | | Run only the manifest completeness check (skip lint) |

**Exit codes:** `0` = no escape violations and all assets accessible; `1` = one or more violations or missing assets.

**Examples:**
```bash
ll-verify-package-data                     # Run both checks from cwd
ll-verify-package-data --json              # Machine-readable JSON output
ll-verify-package-data --lint-only         # Lint only (no manifest check)
ll-verify-package-data --manifest-only     # Manifest check only
ll-verify-package-data -C /path/to/root    # Run from a specific project root
```

---

### ll-verify-skill-prose

Scan `skills/*/SKILL.md` and `commands/*.md` for prose reimplementations of algorithms that already exist in `scripts/little_loops/`. A curated marker table (not a general duplicate-algorithm detector) catches six known shapes: a Jaccard/word-overlap formula spelled out in prose (owned by `text_utils.calculate_word_overlap`), an inline stop-word list (`text_utils.extract_words`), manual `~/.claude/projects/` session-JSONL scanning instructions (`ll-issues append-log`), inline `python3 -c` computation the model is told to run (the owning CLI), `git mv` loops over globbed/bracketed issue filenames (`ll-issues normalize`), and union-find/cluster-merge instructions (`ll-issues link-epics`). Skills with `disable-model-invocation: true` are skipped, matching `ll-verify-skills`.

A `<!-- ll-prose-ok: reason -->` comment on the line immediately preceding a match suppresses that one finding.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | | Output as JSON |
| `--directory` | `-C` | Project root containing `skills/` and `commands/` (default: cwd) |

**Exit codes:** `0` = no unsuppressed findings; `1` = one or more unsuppressed findings.

**Examples:**
```bash
ll-verify-skill-prose                      # Scan from cwd
ll-verify-skill-prose --json               # Machine-readable JSON output
ll-verify-skill-prose -C /path/to/root     # Scan a specific project root
```

---

### ll-verify-design-tokens

Structural lint for *half-flipped* design-token theme profiles. A profile's `themes/dark.json` (or any theme) that inverts the foreground/background pair — overriding both `surface` and `text` to move onto a near-black surface — but leaves `border`/`action` falling through to the light-tuned `semantic.json` defaults produces harsh gridlines, muddy accents, and a `danger == action.primary` collision. This lint catches that class at authoring time.

For every profile under the profiles directory, each theme that performs a full inversion (overrides both `surface` and `text`) must override every semantic color group `semantic.json` defines (`border`, `action`). A theme that does not invert (e.g. a `light.json` restating only `surface`) is exempt.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | | Output as JSON |
| `--directory` | `-C` | Project root to discover the profiles directory under (default: cwd) |
| `--profiles-dir` | | Explicit path to a design-token `profiles/` directory (overrides `-C` discovery) |

**Exit codes:** `0` = every inverting theme overrides all semantic color groups; `1` = one or more half-flipped themes (or no profiles directory found).

**Examples:**
```bash
ll-verify-design-tokens                          # Auto-discover profiles dir from cwd
ll-verify-design-tokens --json                   # Machine-readable JSON output
ll-verify-design-tokens --profiles-dir DIR       # Lint a specific profiles directory
ll-verify-design-tokens -C /path/to/root         # Discover under a specific project root
```

---

### ll-verify-decisions

Validate the decisions log by loading `.ll/decisions.yaml` through `load_decisions()` **and** re-globbing the derived `.ll/decisions.d/*.json` fragment directory in a strict second pass (bypassing the read path's silent skip of malformed fragments), asserting no YAML/JSON syntax errors, missing required fields, or unknown entry-type discriminators in either tier. Gates the three transport-layer corruption checks (ENH-2589): the pre-commit hook (ENH-2590), the pytest CI gate (ENH-2591), and the Claude Code `PreToolUse` hook (ENH-2592) all delegate to this binary and rely on its exit-code contract.

The validator catches three corruption classes:

1. **YAML syntax corruption** (e.g. an unescaped `""` inside a double-quoted `rationale:` scalar → `yaml.YAMLError`).
2. **Schema drift** — entries missing required fields (`id`, `result`/`measured_at` for outcomes, etc.) → `KeyError`.
3. **Unknown `type` discriminator** → `ValueError("Unknown entry type")`.

**Flags:**

| Flag | Description |
|------|-------------|
| `--config-root` | Project root whose decisions log (`.ll/decisions.yaml` + `.ll/decisions.d/`) to validate (default: cwd). Equivalent to `BRConfig.project_root`. |

**Exit codes:** `0` = loadable via `load_decisions()` and schema-clean; `1` = any caught `yaml.YAMLError`/`KeyError`/`ValueError`, with a single-line `ERROR: <path>: <ExcType>: <msg>` on stderr.

**Examples:**
```bash
ll-verify-decisions                       # Validate .ll/decisions.yaml + .ll/decisions.d/ from cwd
ll-verify-decisions --config-root /repo   # Validate under a specific project root
```

See [CONTRIBUTING.md § Decisions YAML Validation](../../CONTRIBUTING.md#decisions-yaml-validation-ll-verify-decisions) for the pre-commit wiring and [docs/guides/DECISIONS_LOG_GUIDE.md § Validation](../guides/DECISIONS_LOG_GUIDE.md) for the full three-layer defense model.

---

### ll-verify-kinds

Assert every `CREATE TABLE` in `session_store._MIGRATIONS` is either registered in `_KIND_TABLE` (so `recent()`/`search --kind` can query it) or explicitly listed in `_KINDLESS_TABLES` (support tables with no "recent by kind" concept — `meta`, `search_index`, `sessions`, `assistant_messages`, `summary_nodes`, `summary_spans`, `raw_events`, `correction_retirements`). Catches the case a new `*_events` table is added without registering its kind — the gap this issue fixed for `snapshot` (ENH-2581).

**Exit codes:** `0` = every table is registered or explicitly kindless; `1` = one or more tables are neither, listed on stderr.

**Examples:**
```bash
ll-verify-kinds    # Check the current tree's session_store._MIGRATIONS
```

---

### ll-verify-evidence

Certify that an issue's quoted **evidence** — a span attributed to another artifact, usually another `.issues/` file — actually exists there (BUG-3282). `/ll:verify-issues` validates *code* claims but historically never checked evidence quotes, so an issue with accurate code citations and one fabricated evidence quote passed verification and scored `verify_verdict: VALID`.

**Scope.** Only evidence-bearing sections are checked — `## Current Behavior`, `## Steps to Reproduce`, `## Root Cause`, `## Motivation`, `### Codebase Research Findings`. This is an allowlist: forward-looking sections (`## Proposed Solution`, `## Expected Behavior`, `## Implementation Steps`, `## Integration Map`, `## Program Design`) quote code that intentionally does not exist yet, so a presence check there would be meaningless, and a section named in neither list is out of scope by default.

**Pipeline.** Extract fenced-block and inline-backtick spans -> attribute each to a named file path or issue ID (a following parenthetical wins, else the mention whose prose block covers the span; **abstains** when no mention covers it or when the block names two artifacts) -> drop command output, bare identifiers/paths, command/skill invocations, template reference fields (`- **Anchor**: …`), elisions, author annotations, and metavariable placeholders -> drop spans under the character floor -> resolve the cited artifact -> match the normalized span against the artifact's working tree, then its blob history newest-first, short-circuiting on the first hit.

**Matching.** One `git log --all --raw` pass builds a `path -> blob OIDs` index for the whole run, and one long-lived `git cat-file --batch` reads blobs from it — two git processes per run, not two per artifact. This replaced a four-tier `working tree -> HEAD -> git log -p -> git log --follow -p` pipeline that took 13+ minutes on a 3200-issue corpus. It is also **more correct**: `git log -p` interleaves commit-message text with file content, so the old pipeline certified quotes that appeared only in some commit message and in no revision of the cited artifact.

`--max-revisions` (default 80) caps how far back each artifact is searched. Renames are not followed; a rename's add-commit blob is the complete file, so only text overwritten *before* a rename is out of reach.

**Verdict cache.** `.ll/evidence-verdict-cache.json` (gitignored) memoizes span-presence verdicts, taking a warm full scan to ~3s. It is a cache, **not policy** — safe to delete at any time, and it can never change a finding set. A found verdict never expires (git history only grows); a not-found verdict is revalidated against the artifact's working-tree hash and searched revision set. Do not confuse it with `.ll/evidence-baseline.json`, which is tracked, curated, and decides what the gate forgives.

**Modes**, mirroring `ll-verify-private-refs`:

- **changed-files** (`ll-verify-evidence FILE...`) — whole-file scan, no baseline. The skill / host-hook invocation.
- **`--added-only FILE...`** — only spans on lines the staged diff adds. The pre-commit hook.
- **`--all`** — full scan of `issues.base_dir`, compared against the tracked baseline `.ll/evidence-baseline.json` (keyed on the anchored numeric issue ID, holding normalized span hashes — not file path or per-file counts, since issue files are renamed constantly). The ID comes from frontmatter when present and from the canonical `P<n>-TYPE-NNN-` filename anchor otherwise; ~34% of a mature corpus carries no `id:` line, and keying on frontmatter alone leaves those findings permanently unbaselineable. This is the pytest CI gate.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--all` | | Scan every tracked issue file against the baseline |
| `--update-baseline` | | Rewrite the baseline from a full scan with the baseline ignored, so the re-seed is complete and idempotent (requires `--all`) |
| `--added-only` | | Only lines added in the staged diff (pre-commit) |
| `--max-revisions N` | | Newest-first revisions searched per artifact (default: 80) |
| `--directory` | `-C` | Project root to scan (default: cwd) |
| `--json` | | Output as JSON |

**Suppression:** `<!-- ll-evidence-ok: reason -->` on the span's own or preceding line — required for the counter-example class, where an issue reports a fabricated quote and must therefore reproduce it verbatim.

**Exit codes:** `0` = clean (or nothing beyond baseline under `--all`); `1` = one or more unsuppressed findings.

**Examples:**
```bash
ll-verify-evidence .issues/bugs/BUG-1.md      # Gate one issue file
ll-verify-evidence --all                      # Full scan vs. baseline
ll-verify-evidence --all --update-baseline    # Re-record the grandfathered corpus
ll-verify-evidence --all --json               # Machine-readable output
```

**Gates:** pre-commit (`.pre-commit-config.yaml`, warn-only on first release), pytest CI (`scripts/tests/test_verify_evidence.py::TestRepoGate`), and the `/ll:verify-issues` skill invocation — the same three-layer model as `ll-verify-private-refs`.

---

### ll-verify-private-refs

Scan for private-codebase references in files this public repo publishes. Loop runs, audits, and issue refinement execute against private codebases, and their prose quotes absolute machine paths and sibling project directories. `gitleaks` (already in `.pre-commit-config.yaml`) does not cover this — the leak is paths and project names, not credentials.

**Rule families.** *Structural* rules are built in and name-free, matching the shape of a machine-local path rather than any particular project, so the checker itself is safe to track publicly:

| Rule | Matches |
|------|---------|
| `abs_user_path` | `/Users/<name>/…`, `/home/<name>/…`, `C:\Users\<name>\…` |
| `host_session_path` | `~/.claude/projects/<slug>/…` (the slug is a mangled absolute path) |

*Name* rules are opt-in, one regex per line in `.ll/private-refs.local.txt`, which is **gitignored**: a tracked list of private project names would publish exactly what the check exists to withhold. Structural rules still apply on a fresh clone with no local file.

**Modes.**

- **changed-files** (`ll-verify-private-refs FILE...`) — all rules, no baseline. The forward-only gate used by pre-commit (staged files) and the Claude Code PreToolUse hook (candidate content, before the write lands). Any match blocks.
- **full-scan** (`--all`) — structural rules only, compared against the tracked baseline `.ll/private-refs-baseline.json`. Exits 1 only on counts *beyond* baseline, so the existing corpus is grandfathered and anything new is blocked. Structural rules are deterministic across machines, which is what makes the baseline portable; local name rules are not, so they are excluded from this mode.

Report excerpts are redacted — a finding names the file and line but never reproduces the matched path, since the output goes to CI logs and hook stderr.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--all` | | Scan every git-tracked file against the baseline |
| `--update-baseline` | | Rewrite the baseline from the current full scan (requires `--all`) |
| `--directory` | `-C` | Project root to scan (default: cwd) |
| `--json` | | Output as JSON |

**Suppression:** `ll-private-ok: <reason>` on the matching line or the line above (`<!-- … -->`, `# …`, and `// …` forms all work).

**Exit codes:** `0` = clean (or nothing beyond baseline under `--all`); `1` = one or more unsuppressed findings.

**Examples:**
```bash
ll-verify-private-refs .issues/bugs/BUG-1.md   # Gate specific files
ll-verify-private-refs --all                   # Full scan vs. baseline
ll-verify-private-refs --all --update-baseline # Re-record the grandfathered corpus
ll-verify-private-refs --all --json            # Machine-readable output
```

**Gates:** pre-commit (`.pre-commit-config.yaml`), pytest CI (`scripts/tests/test_verify_private_refs.py::TestRepoGate`), and Claude Code PreToolUse (`hooks/scripts/check-private-refs.sh`) — the same three-layer model as `ll-verify-decisions`.

---

### ll-verify-des-audit

Walk the source tree and verify every event-emit site maps to a registered DES variant — the F5 adoption gate (ENH-2475). The audit reads every emit-call string literal in `scripts/little_loops/`, then checks each against the canonical `DES_VARIANTS` registry (defined in `little_loops.observability.schema`). Exit 0 means every currently-emitted event type has a registered variant; exit 1 means a new event was emitted without being registered — block F5's `gen_ai.usage.*` adoption until the variant is added.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | | Output as JSON |
| `--directory` | `-C` | Project root to discover the source directory under (default: cwd) |
| `--source-dir` | | Explicit path to a `little_loops` source/ directory (overrides `-C` discovery) |

**Exit codes:** `0` = every emit site maps to a registered DES variant; `1` = one or more uncovered event types (or source dir not found).

**Examples:**
```bash
ll-verify-des-audit                          # Auto-discover source dir from cwd
ll-verify-des-audit --json                   # Machine-readable JSON output
ll-verify-des-audit --source-dir DIR         # Walk a specific source directory
ll-verify-des-audit -C /path/to/root         # Discover under a specific project root
```

---

### ll-verify-cli-allowlist

Assert that `skills/configure/areas.md` and `writers._LL_PERMISSIONS` cover every `ll-` console entry point declared in `pyproject.toml` (BUG-2764). A new CLI added without a matching allowlist preset entry means consuming projects hit a permission prompt for a tool little-loops itself installs; this gate catches that drift at commit time.

**Flags:** none (beyond `-h`/`--help`).

**Exit codes:** `0` = every entry point is covered by both presets; `1` = one or more missing, printed as `ERROR: missing from <preset>: <tools>` on stderr. If `skills/configure/areas.md` is absent (running from an installed package rather than the plugin repo), that preset is skipped with a `SKIP:` notice on stderr and only `writers._LL_PERMISSIONS` is checked.

**Examples:**
```bash
ll-verify-cli-allowlist   # OK: all ll- CLI presets cover every pyproject.toml entry point.
```

Note: `ll-doctor --full` does **not** wrap this verifier — run it directly (or via the pytest suite).

---

### ll-verify-host-map

Assert that the adapter host-capability map agrees with [HOST_COMPATIBILITY.md](HOST_COMPATIBILITY.md), `host_runner.HostCapabilities`, and the emitters' actual behavior (ENH-2873). Includes the ENH-2874 cross-check that a host declaring `subagents='none'` alongside `agents=True` has a working degraded-mode `agent_output_format`.

**Flags:** none (beyond `-h`/`--help`).

**Exit codes:** `0` = the map agrees with all cross-checks; `1` = drift, with one `ERROR: <detail>` line per disagreement on stderr. If HOST_COMPATIBILITY.md is absent, the doc cross-check is skipped with a `SKIP:` notice and only runtime/emitter agreement is verified.

**Examples:**
```bash
ll-verify-host-map   # OK: adapter host-capability map agrees with all cross-checks.
```

---

### ll-check-links

Check markdown documentation for broken links. External link failures are classified into two distinct outcomes (ENH-2836): **broken** (the host answered and said no — HTTP 404/410/500/etc.) and **unreachable** (no usable answer — timeout, DNS failure, connection reset/refused). A single retry with a short backoff runs before a result is finalized as unreachable, to smooth over one slow host. Only broken links fail the exit code by default, so a flaky or offline network doesn't turn this into a red gate for reasons unrelated to the repo's correctness.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--json` | `-j` | Output as JSON |
| `--format` | `-f` | Output format: `text` (default), `json`, `markdown` |
| `--directory` | `-C` | Base directory (default: current directory) |
| `--ignore` | | Ignore URL patterns — repeatable |
| `--timeout` | | HTTP request timeout in seconds (default: 10) |
| `--workers` | `-w` | Maximum concurrent HTTP requests (default: 10) |
| `--verbose` | `-v` | Show verbose output |
| `--strict-network` | | Also fail the exit code on unreachable (timeout/DNS/connection) links, restoring the pre-ENH-2836 behavior |

Each result also carries an `action_severity` field (`auto`/`mention`/`route`, ENH-2886), the same closed vocabulary `ll-verify-docs` uses: `valid`/`internal`/`ignored` results are `auto` (no action needed), `broken`/`unreachable` results are `mention` (a human should review — `ll-check-links` has no `--fix` path, so these are never silently rewritten). `route` is supported on `LinkResult` for callers that construct it directly with a different provenance, naming the owning command via `route_owner`.

**Exit codes:** `0` = no broken links (unreachable links are reported but don't fail the gate, unless `--strict-network` is set), `1` = broken links found (or unreachable links found, with `--strict-network`), `2` = error

**Examples:**
```bash
ll-check-links                            # Check all markdown files
ll-check-links --json                     # Output as JSON
ll-check-links --format markdown          # Markdown report
ll-check-links -C docs/                   # Check specific directory
ll-check-links --ignore 'http://localhost.*'  # Ignore pattern
ll-check-links --strict-network           # Also fail on unreachable (network) links
ll-check-links --timeout 30 --workers 5   # Custom timeout and concurrency
```

---

### ll-create-extension

Scaffold a new little-loops extension project directory. Generates a ready-to-install Python package with an `LLExtension` implementation, a `pyproject.toml` registered under the `little_loops.extensions` entry point, and a starter test using `LLTestBus`.

**Arguments:**

| Argument | Description |
|----------|-------------|
| `name` | Extension name in kebab-case (e.g. `my-dashboard-ext`) |

The name is automatically converted: hyphens become underscores for the package directory (`my_dashboard_ext`) and each word is capitalized for the class name (`MyDashboardExt`).

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--dry-run` | `-n` | Preview files that would be created without writing them |

**Generated layout:**
```
<name>/
├── pyproject.toml          # Package metadata + little_loops.extensions entry point
├── <pkg_name>/
│   ├── __init__.py
│   └── extension.py        # LLExtension implementation stub
└── tests/
    └── test_extension.py   # Starter test using LLTestBus
```

**Generated file contents:**

`pyproject.toml` — wires automatic extension discovery via the `little_loops.extensions` entry point group:
```toml
[project.entry-points."little_loops.extensions"]
my-dashboard-ext = "my_dashboard_ext.extension:MyDashboardExt"
```

`<pkg_name>/extension.py` — skeleton implementing the `LLExtension` protocol:
```python
class MyDashboardExt:
    """MyDashboardExt extension.

    Implement on_event to handle little-loops lifecycle events.
    Optional mixin Protocols (InterceptorExtension, ActionProviderExtension,
    EvaluatorProviderExtension, LLHookIntentExtension) are opt-in — implement
    their methods to activate.
    """

    def on_event(self, event: LLEvent) -> None:
        """Handle an incoming event."""
        # See docs/reference/EVENT-SCHEMA.md for all available event types and payload fields
        pass
```

`tests/test_extension.py` — starter test using `LLTestBus`:
```python
class TestMyDashboardExt:
    def test_receives_events(self) -> None:
        """Extension receives events via LLTestBus replay."""
        bus = LLTestBus([])
        ext = MyDashboardExt()
        bus.register(ext)
        bus.replay()
        assert bus.delivered_events == []
```

**Dry-run output:**
```
[DRY RUN] Would create: my-dashboard-ext/
  pyproject.toml
  my_dashboard_ext/__init__.py
  my_dashboard_ext/extension.py
  tests/test_extension.py
```

**Exit codes:** `0` = scaffold created successfully, `1` = directory already exists or error

**Examples:**
```bash
ll-create-extension my-dashboard-ext              # Scaffold extension
ll-create-extension my-dashboard-ext --dry-run    # Preview without writing files
```

After scaffolding:
```bash
cd my-dashboard-ext
pip install -e .          # Install with entry point registration
python -m pytest tests/   # Run starter tests
```

> **See also:** [Write a little-loops hook](../claude-code/write-a-hook.md) — full authoring walkthrough for the `LLHookIntentExtension` Protocol, including the adapter flow and pure-function + subprocess testing patterns.

---

### ll-artifact

Generate self-contained, human-facing artifacts from project data. `policy-builder` stamps project-derived inputs into an HTML page at generation time, so the output works over `file://` with no runtime fetch. `design-md export` renders a design-token profile as a portable DESIGN.md document. `render` (FEAT-3036 Phase 1) deterministically stamps a user-authored `.llat/` artifact template against a `data.json`, with zero LLM cost per render. `templatize` (FEAT-3314 Phase A) turns a generated artifact back into a reusable `.llat/` template via a hand-written region map, with a byte-exact round-trip guarantee. `extract` (FEAT-3310 Phase 2) derives `data.json` from a source document via one LLM call, schema-checked; `refresh` composes `extract` + `render` against a template's bound source and records the render in `<template>.llat.lock`.

**Subcommands:**

| Subcommand | Description |
|------------|-------------|
| `policy-builder` | Emit a visual builder for policy-router / rubric FSM loop YAML |
| `design-md export` | Export a design-token profile as a single-theme DESIGN.md document |
| `render` | Deterministic `template + data.json -> artifact` stamp for a `.llat/` artifact template |
| `templatize` | Save a generated artifact as a reusable `.llat/` template (Phase A: deterministic, `--regions` map) |
| `extract` | LLM extraction: source document -> `data.json`, schema-checked |
| `refresh` | `extract` + `render` composed against a template's bound source, recording `<template>.llat.lock` |
| `status` | Lockfile staleness detection: FRESH/STALE/SOURCE-MISSING/OUTPUT-MISSING/NO-LOCK per `(template, source)` pair |
| `dashboard` | Export a filtered, redacted `.ll/history.db` snapshot into a single self-contained HTML page that runs read-only SQL client-side via an inlined `sql.js` |

**Exit codes:** `0` = artifact generated successfully, `1` = error (see `templatize` below for its distinct `2`, and `status` / `dashboard` below for their own exit-code rules)

#### ll-artifact policy-builder

Emit `policy-router-builder.html` — a single self-contained page for visually authoring Decision Table and Rubric loop YAML. The page inlines three project-derived blobs: design-token CSS variables (light + dark, from `load_design_tokens` / `render_as_css_vars_themed`), the canonical predicate grammar (`policy_rules.grammar_spec()`), and the skill/command catalog (from `skills/*/SKILL.md` + `commands/*.md`). Decision Table mode presents an ordered, numbered rule list with ↑/↓ reorder controls (on-screen order is precedence order), a "Try it" panel that highlights the first-matching rule for sample values, and a pinned, non-deletable "Otherwise →" fallback picker (a structured dropdown over existing outcomes, not free text). The generated YAML is demoted behind a collapsed "View generated file" `<details>` disclosure; the default view is a plain one-line summary plus Copy/Download, shadow / unreachable-outcome / unknown-action validation hints, and a light/dark theme toggle that honors the project's configured `active_theme` before falling back to OS preference.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--output` | `-o` | Output directory (default: `config.artifacts.default_output_dir`, normally `.`) |

**Examples:**
```bash
ll-artifact policy-builder                   # Write policy-router-builder.html to the default output dir
ll-artifact policy-builder -o build/         # Write to a custom directory
```

> **Note:** Generated YAML can be validated with `ll-loop validate <name>` after downloading. Decision Table output imports `lib/rubric-router.yaml` then `lib/policy-router.yaml`; Rubric output imports only `lib/rubric-router.yaml`.

#### ll-artifact design-md export

Export the project's design tokens as a valid [DESIGN.md](https://github.com/google-labs-code/design.md) document — for handoff to Cursor / Copilot / another little-loops project. The export is **lossy by construction**: the spec has no theme mechanism and no home for several token groups little-loops profiles carry (`shadow.*`, `border.width.*`, most typography axes, and — for a DESIGN.md → DESIGN.md round trip — the spec's `components:` block). Every dropped axis is named in a `[little-loops] Warning: design-md export dropped: ...` note on stderr, never silently omitted. Semantic colors are exported under classifier-recognized names (e.g. `color.border.subtle` → `outline-subtle`) so a re-import of the document recovers the original semantic role; typography is synthesized into the spec's role-organized shape (`display`, `headline-lg`, …) from little-loops' axis-organized token scales.

**Flags:**

| Flag | Description |
|------|-------------|
| `--profile <name>` | Named profile to export — the project's `profiles_dir` first, then the packaged built-ins (`default`, `warm-paper`, `editorial-mono`). Default: the project's active/configured source. |
| `--theme <name>` | Theme to flatten into the single-theme output (default: `active_theme`). Ignored for a `design_tokens.source: design_md` project unless `--profile` is also given. |
| `-o, --output <path>` | Output file (default: stdout). The dropped-groups note always goes to stderr, so `ll-artifact design-md export > DESIGN.md` yields a clean document. |

**Examples:**
```bash
ll-artifact design-md export                                  # Project's active profile -> stdout
ll-artifact design-md export -o DESIGN.md                     # -> file
ll-artifact design-md export --profile warm-paper --theme dark -o DESIGN.md
```

**Exit codes:** `0` = export written, `1` = no design tokens available (`design_tokens.enabled: false`, missing path, missing active profile, or an unresolvable `--profile`), or a color-name collision in the export.

#### ll-artifact render

Deterministic stamp: `template + data.json -> artifact`. No LLM call — rendering the same template + data twice always produces byte-identical output. `<template>` resolves path-first (a `.llat/` directory); if that path does not exist it is resolved as a name under `config.artifacts.templates_dir` (default `artifacts/templates`). If neither exists, exits non-zero naming both paths tried.

A `.llat/` template directory contains `manifest.yaml` (identity, `data_schema`, optional `theme`/`source`/`extraction`), a single `template.<ext>.j2` Jinja2 body, and an optional `assets/` directory. The Jinja2 environment uses a fixed non-default delimiter set (`[[= =]]` for variables, `[[% %]]` for blocks, `[[# #]]` for comments) chosen to avoid colliding with `{{`/`{%`/`${...}` in generated HTML/JS/CSS content, `StrictUndefined`, `autoescape=False`, and is loaded with `Environment.from_string()` — there is no loader, so `{% include/extends/import %}` are unavailable and a template is exactly one file. `data.json` is validated against `manifest.data_schema` (a documented JSON Schema subset: `type`, `required`, `properties`, `items`, `enum`, `description`) before rendering; a schema violation, or an unsupported schema construct at manifest load time, exits non-zero and writes nothing.

The render context is `data.json`'s top-level keys plus a reserved `ll` namespace: `ll.theme_css` (themed CSS custom properties, populated only when `manifest.theme: design-tokens`) and `ll.assets` (every file under `assets/`, keyed by relative path, read as UTF-8 text). A top-level `ll` key in `data.json` or `data_schema` is a validation error.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--data <path>` | | Path to `data.json` (default: `<template>/data.json`) |
| `--output <dir>` | `-o` | Output directory (default: `config.artifacts.default_output_dir`). The manifest's `output:` is a filename; the effective path is `(-o DIR \| default_output_dir) / manifest.output`. The only error case is `-o` naming an existing file. |
| `--source <path>` | | (FEAT-3311) Asserts "this `data.json` came from this file." When given, checked for existence *before* the render (a bad `--source` costs nothing), then after a successful render writes/updates `<template>.llat.lock` recording the source's sha256, an ISO-8601-UTC `rendered_at`, and the rendered `output` file path. Omit to render without touching any lockfile — the unchanged Phase-1 behavior. |

**Examples:**
```bash
ll-artifact render my-report                 # Resolve artifacts/templates/my-report.llat, render against its data.json
ll-artifact render ./my-report.llat --data data.json -o build/
ll-artifact render my-report --data data.json --source docs/risk-register.md  # render + lock
```

**Producing a `.llat/` from a loop (FEAT-3320 pilot)**: `ll-loop run html-anything
"a dashboard showing real-time server metrics" --context artifact_mode=template`
writes a `manifest.yaml` + `template.*.j2` + `data.json` triple to
`run_dir/artifact.llat/` (instead of a fused `index.html`) and, on success,
promotes it to `<templates_dir>/html-anything.llat/` — render it again any time
with `ll-artifact render html-anything --data new-data.json`, no LLM call
required. See [LOOPS_REFERENCE.md § html-anything](../guides/LOOPS_REFERENCE.md#html-anything--generalized-html-artifact-harness).

**Exit codes:** `0` = artifact rendered (and, with `--source`, the lockfile updated), `1` = template not found, an invalid manifest, missing/malformed/schema-invalid data, `-o` naming an existing file, a `--source` that does not resolve to an existing file, or — with `--source` — a render that succeeded but whose lockfile write then failed.

#### ll-artifact dashboard

Export a filtered, ENH-075-redacted snapshot of `.ll/history.db` as a gzip+base64 blob embedded in `history-dashboard.html`, alongside an inlined `sql.js` (SQLite compiled to WASM). The page opens over `file://` with **zero network requests** — the WASM is handed to `initSqlJs({ wasmBinary })` directly rather than fetched — and lets the viewer run arbitrary read-only SQL against the snapshot, plus predefined views that need no SQL at all.

Rendered as a real `.llat/` template (`theme: design-tokens`) that ships **inside the package** and is resolved via `importlib.resources`, so it works from an installed wheel, not only a source checkout.

**Export scope is decided here, not in the page.** In the default `shareable` mode only the ENH-075 column allowlist is copied — `loop_runs` without `error` (free text) or `diagnostics_path` (absolute path), and `usage_events` without anything outside the allowlist — and `--tables` may select only from the types the allowlist covers. `--local` lifts the projection (`SELECT *`) and accepts any `ll-session export` type; the resulting page is stamped `mode: local` so a recipient can always tell.

**Reading the source database is non-mutating by construction.** The snapshot is built by `ATTACH` + `CREATE TABLE … AS SELECT` over a raw `file:…?mode=ro` connection, never the store's normal open path (which migrates on open) — so generating an artifact cannot alter `.ll/history.db`. The resulting snapshot carries no indexes and no free pages, so no `VACUUM` step is needed.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--tables <types>` | | Comma-separated `ll-session export` **type names** (`loop_run`, `usage_event`, …), not physical table names. Default: `loop_run,usage_event` — the shareable-allowlist types, in both modes. Deliberately **not** `ll-session export`'s 20-type default set, 18 of which have no allowlist entry. In `shareable` mode a type outside the allowlist exits `1`. |
| `--since <when>` | | ISO 8601 or `YYYY-MM-DD` (matching `ll-session export`; no relative durations like `30d`). **No default** — omitting it embeds all history, which on a real database will exceed the size ceiling. For `loop_run` the predicate is `COALESCE(ended_at, started_at)`, so a run that *started* inside the window is kept even if it is still in flight and has no end timestamp. |
| `--local` | | Export in local mode: no column projection, any export type selectable. Overrides `config.artifacts.export.mode`. |
| `--db <path>` | | Path to the history database (default: `<project root>/.ll/history.db`). |
| `--output <dir>` | `-o` | Output **directory** (default: `config.artifacts.promotion_dir`, i.e. `.loops/artifacts` — *not* `default_output_dir`, which is `.` and would drop a multi-MB file into the project root). The filename comes from the packaged manifest: `history-dashboard.html`. |

**In the page:** `PRAGMA query_only = 1` is applied immediately after every database instantiation, which is what actually rejects writes at the engine level (`attempt to write a readonly database`). The submitted-text check that rejects multi-statement input and `PRAGMA` exists to give a clear error message — it is a UX guardrail, **not** a security boundary; the viewer owns the bytes and the console, and data scope was settled at export time. A "reset snapshot" action re-instantiates the database from the embedded bytes. Results are capped at 500 rendered rows with a truthful `showing 500 of N rows` line, applied at the render step via `prepare()`/`step()` — the submitted SQL is never rewritten with a `LIMIT`.

**Stamped into the page:** export timestamp, the `--tables`/`--since` filter that produced it, the export mode, the ENH-075 allowlist version, and both the source database's recorded `schema_version` and the installed `SCHEMA_VERSION`, with a visible warning when they diverge. Divergence is detected at *export* time — once written the artifact contains its own snapshot and has nothing left to mismatch against.

**Vendored `sql.js`** (1.14.2) lives at `scripts/little_loops/assets/vendor/sql.js/` with version, upstream URL, SHA-256 per file, license, and update procedure recorded in `PROVENANCE.md`. It contributes a fixed ~924 KB floor to every generated artifact.

**Examples:**
```bash
ll-artifact dashboard --since 2026-07-26                       # shareable, both allowlist types
ll-artifact dashboard --tables loop_run --since 2026-07-26 -o build/
ll-artifact dashboard --local --since 2026-08-01               # unredacted, personal use
```

**Exit codes:** `0` = `history-dashboard.html` written, `1` = the raw snapshot or the final rendered HTML exceeded `artifacts.export.max_artifact_bytes` (default `8000000` — both messages name the measured size, the limit, and `--since` as the remedy, and **no file is written**), a `--tables` selection that would widen the ENH-075 allowlist in `shareable` mode, an unknown export type, an unparseable `--since`, a missing history database, or `-o` naming an existing file.

#### ll-artifact templatize

Decomposed from FEAT-3308. Given an artifact plus a region map, splices the located spans into Jinja2 expressions/blocks, derives `data.json` and `data_schema` from the artifact bytes at each span, and verifies a **byte-exact round trip** before promoting the result into a `.llat/` template directory. The region map is either hand-written (`--regions <map.json>`, Phase A / FEAT-3314, deterministic, no LLM call) or LLM-discovered when `--regions` is omitted (Phase B / FEAT-3315, `discover_regions`) — both paths converge on the same `{regions, groups}` shape and the same splice/verify/promote pipeline below.

`<artifact>` is the generated file to templatize; `<source>` is the document it was generated from. With `--regions`, `source` is only recorded into `manifest.source` and **not read**, since every `data.json` value is captured from an artifact byte span. Without `--regions`, `source` **is read** and sent to the LLM discovery call alongside the artifact — a missing/unreadable `source` file exits `1` before any host call. `-o` resolves to a `<name>.llat` directory (`.llat` is appended if omitted); default is `config.artifacts.templates_dir/<artifact-stem>.llat`. An existing `-o` is an error unless `--force` is given.

The `--regions` map's top level carries only `regions` and `groups` (both required; either may be empty). A `Region` is `{start, end, expr, group?, anchor_before?, anchor_after?}` — `start`/`end` are **UTF-8 byte offsets** (not `str` indices — non-ASCII artifacts diverge under the two), `expr` is the dotted `data.json` path the extracted bytes bind to, and `group` names an owning `RegionGroup` for a repeated element. A `RegionGroup` is `{id, binding, array_path, start, end, iterations}`, where `iterations` is an ordered list of `[start, end]` sub-spans; iteration 1 becomes the Jinja2 loop body (its member regions rewritten to `[[= <binding>.<field> =]]`), and iterations 2..N are deleted from the template (their extracted values populate the `array_path` array in `data.json` instead). `data`/`data_schema` are derived outputs, never map inputs — a map supplying either key is rejected.

**Without `--regions`** (the default), `discover_regions` sends the artifact and the source document to the configured LLM host and asks it to quote each source-derived span's **exact literal text** rather than a numeric offset — offsets are never LLM-supplied; Python resolves them via a forward-only `bytes.index` scan, because the round-trip gate below is self-consistent by construction and cannot catch a uniformly-wrong-but-orderly offset map. A response missing a required key, carrying an unknown key, or quoting text that can't be located unambiguously (absent, ambiguous with no disambiguating `anchor_before`/`anchor_after`, or anchor-mismatched) fails loud at exit `1` before anything is written to disk. The combined artifact+source size is checked against `artifacts.templatize_max_input_bytes` (default `400000` bytes) **before** issuing the call — over the ceiling exits `1` naming the measured size, with no host call issued. **Every failure downstream of the host call** — exit `1` or exit `2` — writes both `discovery.json` (the raw LLM response) and `regions.json` (the resolved `{regions, groups}` map, directly re-feedable as `--regions` for a deterministic retry) into `<out>.llat.rejected/`, so no failure requires re-paying for the call. The emitted manifest's `extraction` is `{"method": "llm_discovery", "host": ..., "model": ...}` on this branch, vs. `{"method": "regions", "regions_map": ...}` for a hand-written map. `--regions`, when given, always takes precedence — no host call, no size-ceiling check, no `source` read.

The artifact is read and processed as raw `bytes` throughout, never via `read_text`/`write_text` — a CRLF or lone-CR artifact is rejected up front (exit `1`) because the frozen renderer's own body read (`render_template`) applies universal-newline translation and cannot round-trip one. An extensionless artifact is also rejected (exit `1`): the template body name is derived from `Path(artifact).suffix`, and an empty suffix would produce a nonsensical `template..j2`.

**Design-token report and lift (Phase C / FEAT-3316, ENH-3319).** After round-trip verification succeeds and before promote, `templatize` scans the *spliced template body* (never the original artifact — extracted data regions are not part of the template) for baked color literals (`#rgb`/`#rgba`/`#rrggbb`/`#rrggbbaa`, `rgb()`/`rgba()`/`hsl()`/`hsla()` — every other token namespace, e.g. `space.*`/`radius.*`/`font.*`, is out of scope for v1) that match the project's resolved design tokens. `unlifted-tokens.json` is written into the template directory with two lists — `lifted` and `unlifted` — plus a `lift_skipped_reason` key, and a non-silent warning names the count of anything left unlifted.

With `--lift-tokens` **off** (the default), behavior is exactly as before this flag existed: nothing is rewritten, the manifest never sets `theme: design-tokens`, `lifted` is always `[]`, and the byte-exact round-trip guarantee holds unconditionally. Degradation is explicit: tokens unconfigured/disabled writes no file and no warning; tokens loaded with zero matches writes the file with an empty `unlifted` list and no warning. No failure in this step can change the exit code, block promote, or suppress the success line.

With `--lift-tokens` **on**, a matched literal in *CSS-value position* — inside a `<style>` element or a `style="..."` attribute, with the nearest preceding delimiter a `:` and the nearest following delimiter a `;`/`}` — that resolves unambiguously to a single design-token name (after preferring a semantic alias over the primitive it points at) is rewritten to a `var(--dotted-name)` reference, e.g. `var(--color-surface-primary)`. The template gains a `[[= ll.theme_css =]]` expression inside a `<style>` placed immediately after `<head>` (ahead of every author `<style>`, so equal-specificity author declarations still win by source order), a `data-theme="<active_theme>"` attribute on the root `<html>` element, and `manifest["theme"] = "design-tokens"`. A literal outside CSS-value position, with an ambiguous candidate set, or one of five hard preconditions unmet (no `<head>`/`<style>` to stamp; no root `<html>`; a pre-existing `data-theme` disagreeing with the active theme; `active_theme` outside `{light, dark}` with no `design_md` source; or the token set failing to declare every var name the lift would emit) is left as a literal and reported in `unlifted` — a failed precondition names itself in `lift_skipped_reason` and blocks the *entire* lift for that body (all-or-nothing), leaving the manifest untouched at exit `0`.

Verification is three-stage under `--lift-tokens`: (1) the byte-exact round trip against the original artifact, unchanged; (2) a span-tracked reversibility check — undoing the recorded lift and stamp spans must reproduce the verified pre-lift body byte-for-byte; (3) a runtime post-lift render check — the re-serialized template is rendered from disk and every emitted `var(--x)` reference must have a matching `--x:` declaration in the output, which also catches an inert or unevaluated stamp point. A failure at stage (2) or (3) routes to `<out>.llat.rejected/` with exit code `2`, exactly like the round-trip rejection.

**Two accepted limitations, stated rather than left implicit:** (1) *render-time token availability* — the declarations come from `themed_css_vars(config)` evaluated in whatever project later re-renders the `.llat` (`render`, `extract`, `fsm/persistence.py::promote_run_artifact`); a lifted template re-rendered in a project with no design tokens configured emits empty `:root {}`/`[data-theme=dark] {}` blocks and renders **colorless**, with no error. The lift-time precondition above only guards that the *authoring* project's tokens cover every emitted name — it cannot guard a different rendering project. (2) *presentation-attribute under-lift* — the CSS-value-position guard's scope test admits only `<style>` elements and `style="..."` attributes, so color-valued presentation attributes (inline SVG `fill`/`stroke`/`stop-color`, `bgcolor`, `<meta name="theme-color">`) are reported in `unlifted` but never rewritten. Both are deliberate v1 scope decisions, not bugs.

**Fan-out verification.** The template kit's payoff is reuse: a template produced from one artifact is expected to render correctly against a *different* source document of the same kind by supplying a new `data.json` to `render --data`, not by re-running `templatize`. `scripts/tests/test_artifact_templatize.py::TestCmdTemplatizeFanOut` exercises exactly this — templatizing one document, then rendering the produced template against a second, structurally-divergent document's hand-authored data — as the project's regression coverage for that contract.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--regions <path>` | | Path to a hand-written region map. When omitted, an LLM discovery call identifies the regions instead. |
| `--output <dir>` | `-o` | Output `<name>.llat` directory (default: `config.artifacts.templates_dir/<artifact-stem>.llat`). Note this `-o` names a **template directory**, unlike `render`'s `-o`, which names an **output directory** — the two subcommands sit adjacent in this reference deliberately. |
| `--force` | | Overwrite an existing template at the resolved `-o` path |
| `--lift-tokens` | | Rewrite baked-in color literals matching a resolved design token, in CSS-value position, to `var(--dotted-name)` references, and inject the `[[= ll.theme_css =]]` stamp point plus `data-theme` attribute so they resolve. Default off — report-only, byte-exact round trip. |

**Examples:**
```bash
ll-artifact templatize out/index.html docs/ARCHITECTURE.md \
    -o arch-review.llat --regions map.json
ll-artifact templatize out/index.html docs/ARCHITECTURE.md --regions map.json --force
ll-artifact templatize out/index.html docs/ARCHITECTURE.md -o arch-review.llat  # LLM discovery, no --regions
```

**Exit codes:** `0` = template written and round-trip verified (with `--lift-tokens`, this also covers a lift blocked by a hard precondition — the body is left unlifted, not rejected), `1` = malformed input / IO failure (missing artifact/source/regions map, CRLF artifact, extensionless artifact, malformed `--regions` map or discovery response, oversized discovery input, an existing `-o` without `--force`), `2` = round-trip verification rejected the extraction, or — under `--lift-tokens` — the lift's reversibility check or post-lift render check rejected it — the candidate plus a `roundtrip.diff` / `lift-reversibility.diff` / `lift-render-check.txt` (and, on the discovery branch, `discovery.json`/`regions.json`) are written to `<out>.llat.rejected/` and any pre-existing `-o` template is left untouched.

> **Note:** `templatize` (FEAT-3308, Phases A–C), `render` (Phase 1 of FEAT-3036), `extract`/`refresh` (Phase 2, FEAT-3310), and `status` (Phase 3, FEAT-3311, staleness detection) are all implemented (see `.issues/features/P3-FEAT-3036-artifact-templates-design.md`).

#### ll-artifact extract

LLM extraction: maps a source document to `data.json` per the template's `manifest.data_schema` + `extraction.prompt`, via a direct `build_blocking_json(json_schema=...)` host call — the same shape `templatize`'s discovery call and `advisor.consult()` use. Fails loud: any host-call failure (timeout, missing binary, non-zero exit, unparseable output), an empty response, or a response that fails `artifact_templates.validate_top_level_data` against `manifest.data_schema` exits `1` and writes nothing — there is no fail-soft fallback. `json_schema` enforcement is host-dependent (Claude Code drops it silently; Codex materializes it), so the post-call schema validation is the only guarantee on the Claude Code path, not defense in depth.

The prompt sent to the host is not `manifest.extraction.prompt` verbatim: a module-level template composes the author's `extraction.prompt` (what to extract) with the serialized `data_schema` (the shape to return) and the source document text (the material). A manifest with no usable `extraction.prompt` fails loud, naming the template and the missing key — `templatize`-produced manifests need a hand-added `prompt` before `extract` works on them, since `templatize` writes `extraction` as `{"method": ..., ...}`, never `{"prompt": ...}`.

Model resolution: `--model` > `manifest.extraction.model` > the fsm default model. `manifest.extraction.host` is diagnostic only and never overrides `resolve_host()`'s ambient host selection (`LL_HOST_CLI` / `orchestration.host_cli`) — a manifest committed on one machine must not silently redirect another machine's host. The source document is guarded against `artifacts.templatize_max_input_bytes` (default `400000` bytes; for `extract` this measures the source document alone, unlike `templatize`'s combined artifact+source measurement) before the host call is built — over the ceiling exits `1` naming the measured size, with no host call issued.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--data <path>` | | Path to write `data.json` (default: `<template>/data.json`). Relative paths resolve against the project root, exactly like `render`'s `--data`. |
| `--model <name>` | | LLM model for the extraction call (default: `manifest.extraction.model`, else the fsm default model). New CLI surface — no other artifact subcommand exposes `--model`. |
| `--timeout <seconds>` | | Host call timeout in seconds (default: `180`) |

**Examples:**
```bash
ll-artifact extract my-report docs/risk-register.md
ll-artifact extract my-report docs/risk-register.md --data out/data.json --model opus
```

**Exit codes:** `0` = `data.json` written and schema-validated, `1` = template not found, an invalid manifest, missing/oversized/undecodable source, no usable `extraction.prompt`, a host-call failure, or a schema-invalid response (no partial write in any of these cases).

#### ll-artifact refresh

Composes `extract` + `render` in one shot: extracts `data.json` from a source document, validates and writes it, renders the template against it, then writes/updates `<template>.llat.lock` recording the render. When `<source-file>` is omitted, the source defaults to the manifest's bound `source` (project-root-relative if not absolute) — a `source` that doesn't resolve to an existing file fails loud naming the resolved absolute path, with no cwd-relative fallback.

The lockfile write happens only after the render's output-file write succeeds, and only records the **same source bytes the extraction consumed** (never a re-read, which would open a TOCTOU window against a source edited mid-refresh). The write is atomic (temp sibling + `os.replace`) and merges into any existing `renders` mapping — refreshing one source's entry never drops another source's entry for the same template (EPIC-3299's one-template-many-sources case). A lock-write failure after a successful render still exits `1`, but the message states that the render already succeeded and only the lock write failed, so a filesystem problem doesn't cost a re-paid LLM call to fix.

Every path recorded in the lockfile (`renders` keys and `output`) goes through the same path-storage rule as `manifest.source`: project-root-relative (POSIX separators) when inside the project root, absolute otherwise, never `..`-prefixed.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--data <path>` | | Path to write `data.json` (default: `<template>/data.json`), same semantics as `extract`'s `--data` |
| `--output <dir>` | `-o` | Output directory for the rendered artifact (default: `config.artifacts.default_output_dir`), passed through to the render half with `render`'s exact semantics |
| `--model <name>` | | LLM model for the extraction call (default: `manifest.extraction.model`, else the fsm default model) |
| `--timeout <seconds>` | | Host call timeout in seconds (default: `180`) |

**Examples:**
```bash
ll-artifact refresh my-report                              # extract + render against manifest.source
ll-artifact refresh my-report docs/risk-register.md -o build/   # ...against an explicit source
```

**Exit codes:** `0` = artifact rendered and lockfile updated, `1` = any `extract` failure, a render failure, an unresolvable default source, or a render that succeeded but whose lockfile write then failed.

#### ll-artifact status

Lockfile staleness detection (FEAT-3311 Phase 3): compares each recorded source's current sha256 against `<template>.llat.lock`, reporting one of five states per `(template, source)` pair — evaluated first-match-wins in this order:

1. **SOURCE-MISSING** — the recorded source path no longer exists on disk.
2. **STALE** — the source exists but its current sha256 differs from the recorded one.
3. **OUTPUT-MISSING** — the source hash matches, but the recorded `output` artifact file no longer exists (deleted after the last render/refresh).
4. **FRESH** — the source hash matches and the `output` file exists.
5. **NO-LOCK** — reported per explicitly-named `<template>` (not per source): no `.llat.lock` sibling exists, or one exists but its `renders` mapping is empty. "I cannot tell whether this is fresh" must not read as "it is fresh."

With `<template>` arguments, each is resolved via the same path-first `resolve_template` rule as `render`/`extract` — a template resolved by a path outside `config.artifacts.templates_dir` gets its lockfile read from beside it, wherever that is (the "lockfile is committed" guarantee only holds for in-repo templates). With no `<template>` arguments (**discovery mode**), `status` enumerates every `.llat/` template under `config.artifacts.templates_dir` that has a `.llat.lock` sibling and skips the rest — a lockfile-less template is silently omitted (not NO-LOCK) in this mode, and a missing/empty `templates_dir` produces an empty report plus a distinct info-level "no templates with a lockfile found under `<dir>`" log line, so a mistyped `templates_dir` is visible rather than passing silently.

A `renders` key or its `output` value is resolved absolute-as-is when `os.path.isabs`, otherwise against `config.project_root` — **never against cwd**, so `status` run from a project subdirectory still resolves entries it wrote itself. `rendered_at` is diagnostic only (ISO-8601 UTC, trailing `Z`); it is never read back or classified on. A malformed `.llat.lock` (unparseable YAML, non-mapping top level, missing/non-mapping `renders`, or an unknown `version`) is an exit-1 `LockfileError`, not a sixth reported state.

**Flags:**

| Flag | Description |
|------|-------------|
| `<template>` (positional, 0+) | Template(s) to check (path or name under `config.artifacts.templates_dir`). Omit to discover every lockfile-bearing template under `templates_dir`. |

**Examples:**
```bash
ll-artifact status                    # Discover every tracked template under templates_dir
ll-artifact status my-report          # Check one template (NO-LOCK if it has never been refreshed)
ll-artifact status my-report other    # Check several by name
```

**Exit codes:** `0` = every reported `(template, source)` pair is FRESH — an empty report (nothing discovered, or `templates_dir` missing) counts as vacuously FRESH; `1` = any pair is STALE/SOURCE-MISSING/OUTPUT-MISSING, an explicitly-named template is NO-LOCK, a `<template>` argument is unresolvable, or the lockfile is malformed (`LockfileError`). An explicitly-named untracked template (`NO-LOCK`) always exits non-zero even though the equivalent discovery-mode run (which just skips it) can exit `0` — an explicit argument asserts the caller expects tracking.

> **Note:** the lockfile (`<template>.llat.lock`) is committed to version control, not gitignored — the CI use case above only works against a lockfile the build actually checks out.

---

### ll-generate-schemas

> **Internal:** Maintainer/developer tool. End users do not need to run this directly.

Generate JSON Schema (draft-07) files for all 38 `LLEvent` types and write them to `docs/reference/schemas/`.

**Flags:**

| Flag | Short | Description |
|------|-------|-------------|
| `--output` | `-o` | Output directory (default: `docs/reference/schemas/` relative to cwd) |

**Exit codes:** `0` = schemas generated successfully, `1` = error

**Examples:**
```bash
ll-generate-schemas                          # Write to docs/reference/schemas/
ll-generate-schemas -o path/to/schemas/      # Custom output directory
```

> **Note:** Run this after modifying `SCHEMA_DEFINITIONS` in `scripts/little_loops/generate_schemas.py` or adding a new `LLEvent` type. See [CONTRIBUTING.md](../../CONTRIBUTING.md) for the full schema maintenance workflow.

---

### ll-generate-skill-descriptions

> **Release utility:** Run before tagging a release to batch-refresh skill descriptions.

Auto-generate concise (≤100 character) descriptions for LLM-discoverable skills using the Claude CLI. For each `skills/*/SKILL.md` that does **not** have `disable-model-invocation: true`, it extracts trigger keywords and a body excerpt, prompts Claude to produce a single-line description, and optionally writes it back to the frontmatter.

Dry-run by default (previews proposed descriptions without modifying files).

**Flags:**

| Flag | Description |
|------|-------------|
| `--apply` | Write generated descriptions back to `SKILL.md` frontmatter |
| `--quiet` | Suppress per-skill output; only print final summary |

**Exit codes:** `0` = success (no errors), `1` = one or more skills failed or skills directory not found

**Examples:**
```bash
ll-generate-skill-descriptions               # Dry-run: preview proposed descriptions
ll-generate-skill-descriptions --apply       # Write descriptions back to SKILL.md files
ll-generate-skill-descriptions --quiet       # Suppress per-skill output
```

> **See also:** [CONTRIBUTING.md New Skill Checklist](../../CONTRIBUTING.md) for the classification policy and when to run this tool.

---

### ll-adapt

Unified host-parameterized adapter. Dispatches to a host-specific emitter via `--host <host>` and generates all skill, command, agent, and MCP config artefacts for that host in one pass. Codex additionally merges an `[mcp_servers.ll-mcp]` TOML table into its global `~/.codex/config.toml` (or `$CODEX_HOME/config.toml`) registering the `ll-mcp` server (FEAT-3138, corrected under BUG-3178 — Codex has no project-local MCP config read path); `--host claude-code` emits a JSON `.mcp.json` snippet at the project root instead, merging into (not overwriting) any existing `mcpServers` content (FEAT-3139); other hosts skip this artefact until their own emitter is implemented.

**Flags:**

| Flag | Description |
|------|-------------|
| `--host HOST` | Target host (e.g. `codex`, `claude-code`, `omp`) — required |
| `--apply` | Write changes (default: dry-run) |
| `--dry-run` | Explicit dry-run alias |
| `--only NAME` | Restrict agent processing to a single agent stem |
| `--quiet` | Suppress per-entry output; only print final summary |

**Exit codes:** `0` = success (no errors), `1` = unknown host or one or more entries failed

**Examples:**
```bash
ll-adapt --host codex                # Dry-run: preview all Codex artefacts
ll-adapt --host codex --apply        # Write Codex artefacts
ll-adapt --host codex --only codebase-analyzer --apply  # Single agent
```

---

### ll-adapt-skills-for-codex

> **Deprecated alias** — use `ll-adapt --host codex` instead. This entry point remains available as a convenience alias but is no longer the documented path.

Adapt ll's `skills/*/SKILL.md` files for the Codex Skills API **and** bridge every `commands/*.md` slash command into a Codex-discoverable `skills/ll-<name>/` entry.

**Skills adaptation (in-place).** For each `skills/<name>/SKILL.md`, inserts `name:` (the directory slug) and `metadata.short-description:` (first line of the existing `description:` field, ≤80 chars) into the SKILL.md frontmatter, and creates `agents/openai.yaml` with `display_name` and `short_description` under an `interface:` block. Uses targeted string manipulation — no YAML roundtrip — to preserve existing frontmatter formatting.

**Commands bridge (synthesized).** For each `commands/<name>.md`, synthesizes a wrapper `skills/ll-<name>/SKILL.md` (with `name: ll-<name>`, the source command's `description:` copied verbatim, and a derived `metadata.short-description:`) plus a matching `agents/openai.yaml`. The `ll-` namespace prefix prevents collisions with skills sharing a base name (e.g. `commit`). Commands whose frontmatter declares `disable-model-invocation: true` are skipped, mirroring the skills-adapter contract. Multi-line descriptions are emitted as YAML block scalars so the synthesized frontmatter parses cleanly. Bridged `ll-<name>/` entries are committed in-repo and discovered by Codex via the same Skills API path as adapted real skills.

Dry-run by default (previews proposed changes without modifying files).

**Flags:**

| Flag | Description |
|------|-------------|
| `--apply` | Write skill frontmatter updates and create bridged `skills/ll-<name>/` directories on disk |
| `--quiet` | Suppress per-entry output; only print final summary |

**Exit codes:** `0` = success (no errors), `1` = one or more entries failed or `skills/` directory not found

**Examples:**
```bash
ll-adapt-skills-for-codex            # Dry-run: preview proposed skill + command changes
ll-adapt-skills-for-codex --apply    # Write frontmatter, bridge commands → skills/ll-<name>/
ll-adapt-skills-for-codex --quiet    # Suppress per-entry output
```

---

### ll-adapt-agents-for-codex

> **Deprecated alias** — use `ll-adapt --host codex` instead. This entry point remains available as a convenience alias but is no longer the documented path.

Generate `.codex/agents/*.toml` files from `agents/*.md` so Codex CLI can select ll subagents via `--agent <name>`.

For each `agents/<name>.md`, reads the agent's name and description from its frontmatter (falling back to the H1 heading), then writes a TOML file to `.codex/agents/<name>.toml` with `name`, `description`, `model`, and `developer_instructions` fields. Uses an idempotent marker comment (`# generated by ll-adapt`) to detect and skip previously generated files unless `--force` is passed. User-edited TOML files (files lacking the marker) are never overwritten.

Dry-run by default (previews proposed changes without writing files).

**Flags:**

| Flag | Description |
|------|-------------|
| `--apply` | Write `.codex/agents/*.toml` files to disk |
| `--force` | Overwrite previously generated files even if already up-to-date |
| `--quiet` | Suppress per-entry output; only print final summary |

**Exit codes:** `0` = success (no errors), `1` = one or more entries failed or `agents/` directory not found

**Examples:**
```bash
ll-adapt-agents-for-codex            # Dry-run: preview proposed agent TOML changes
ll-adapt-agents-for-codex --apply    # Write .codex/agents/*.toml files
ll-adapt-agents-for-codex --force --apply  # Regenerate all files (including up-to-date)
```

---

### ll-mcp

MCP server (2026-07-28 spec) — stdio by default, streamable HTTP with `--http` — exposing
sixteen coarse tools over the `little_loops` library. Eight read: `issues_query`,
`issue_get`, `history_search`, `deps_check`, `capabilities`, `queue_list`, `queue_get`,
`loop_list` (FEAT-3352).
Seven write, dry-run by default: `issue_capture`, `issue_set_status`, `issue_link`,
`issue_append_log` (FEAT-3149), `queue_add`, `queue_remove`, `queue_requeue` (FEAT-3343).
One starts a run: `loop_start` (FEAT-3151, see below). Started by an MCP-capable host (Claude
Code, Codex, ...) from the config `ll-adapt --host <host> --apply` emits (`.mcp.json`,
Codex's `~/.codex/config.toml`) — not run directly by a human. Requires the `mcp` optional extra
(`pip install "little-loops[mcp]"`); without it, exits `2` with an actionable message
instead of an `ImportError`.

Every tool wraps an existing library call directly — no subprocess invocation of the `ll-*`
CLIs. `ll-auto`, `ll-parallel`, and `ll-action invoke` are intentionally off the tool
surface; `ll-loop` is the one exception — `loop_start` starts a detached run, and `tasks/*`
below polls/stops it. No request handler depends on state from a prior request: each
`tools/call` resolves entirely from its own arguments plus the filesystem/SQLite.

The seven mutating tools are guarded twice. **Dry-run by default:** each takes an `apply`
boolean defaulting to `false`; without an explicit `true` the tool returns the change it
would make (`{"applied": false, "tool": …, "target": …, "changes": […]}`) and writes
nothing. The check is fail-closed — only the literal boolean `true` opts in. **Per-transport
policy:** `mcp.transport_policy.<http|stdio>.allow_mutations` in `.ll/ll-config.json`
governs whether they may run at all, defaulting to `false` for HTTP (which ships without
authentication) and `true` for stdio. On HTTP, a denied call is refused in ASGI middleware
from the SEP-2243 `Mcp-Method`/`Mcp-Name` headers, before the JSON-RPC body is parsed, with
a JSON-RPC error (`-32001`) and HTTP 403; the `tools/call` handler itself also enforces the
same policy on both transports (FEAT-3168), so the decision is uniform even when the ASGI
layer is bypassed or the call arrives over stdio. Reads on the same server are unaffected. The seven
carry a `readOnlyHint: false` annotation in `tools/list`; the eight read-only tools carry no
annotations, which is how a host tells the groups apart.

`ll-queue`'s three mutating tools (`queue_add`, `queue_remove`, `queue_requeue`, FEAT-3343)
follow the same two tier-2 escape-hatch omissions `issue_link` set precedent for:
`queue_remove`/`queue_requeue` drop the CLI's `--force` flag (removing/requeuing a non-
matching-state entry), keeping the MCP surface to the coarse, safe path. There is no
`queue_run`/`--watch` tool — draining the queue is a long-lived process, not a stateless
request/response call, so it does not fit the MCP tool-call model.

A dry-run `issue_capture` returns **no issue ID** — not even a predicted one. It reports the
resolved type, priority, slug, target directory, and rendered body, because the ID is
allocated inside `create_issue`'s lock hold at write time; the apply response carries the
real one.

**Tool parameters** (all schemas use `additionalProperties: false`):

| Tool | Parameter | Type | Required | Description |
|------|-----------|------|----------|-------------|
| `issues_query` | `status` | `open`\|`done`\|`deferred`\|`all` | no (default `open`) | Status bucket to include |
| | `issue_type` | `BUG`\|`FEAT`\|`ENH`\|`EPIC` | no | Restrict to one issue type |
| | `priority` | `P[0-5]` | no | Restrict to one priority level, e.g. `P1` |
| | `limit` | integer ≥ 1 | no | Maximum number of issues to return |
| `issue_get` | `issue_id` | string | **yes** | Issue ID in any of: `3135`, `FEAT-3135`, `P3-FEAT-3135` |
| `history_search` | `query` | string | **yes** | FTS5 phrase to search `.ll/history.db` for |
| | `kind` | `tool`\|`file`\|`issue`\|`loop`\|`correction`\|`message` | no | Restrict results to one event kind |
| | `limit` | integer ≥ 1 | no (default `10`) | Maximum number of results |
| `deps_check` | — | — | — | No parameters; validates the cross-issue dependency graph |
| `capabilities` | — | — | — | No parameters; reports the resolved AI-host CLI's capability surface |
| `queue_list` | — | — | — | No parameters; lists all persisted `ll-queue` entries |
| `queue_get` | `id` | string | **yes** | Entry id (full uuid or 8+-char prefix) |
| `issue_capture` | `type` | `BUG`\|`FEAT`\|`ENH`\|`EPIC` | **yes** | Issue type |
| | `title` | string | **yes** | Issue title |
| | `priority` | `P[0-5]` | no (default `P2`) | Priority level |
| | `body` | string | no | Summary section body |
| | `parent` | string | no | Parent EPIC ID to wire |
| | `labels` | string[] | no | Labels to set in frontmatter |
| | `apply` | boolean | no (default `false`) | Set `true` to actually create the issue |
| `issue_set_status` | `issue_id` | string | **yes** | Issue ID in any resolvable form |
| | `status` | `open`\|`in_progress`\|`blocked`\|`deferred`\|`done`\|`cancelled` | **yes** | Target status |
| | `reason` | string | no | Deferral or closure reason code, per the target status |
| | `by` | string | no (default `human`) | Actor recorded as `deferred_by` on a deferral |
| | `apply` | boolean | no (default `false`) | Set `true` to actually write the transition |
| `issue_link` | `issue_id` | string | **yes** | Source issue ID |
| | `field` | `blocked_by`\|`depends_on`\|`relates_to` | **yes** | Which edge type to write |
| | `target` | string | **yes** | Target issue ID |
| | `unlink` | boolean | no (default `false`) | Remove the edge instead of adding it |
| | `reciprocal` | boolean | no (default `false`) | Also write the matching reverse edge |
| | `force` | boolean | no (default `false`) | Skip target-existence validation |
| | `apply` | boolean | no (default `false`) | Set `true` to actually write the edge |
| `issue_append_log` | `issue_id` | string | **yes** | Issue to append to |
| | `command` | string | **yes** | Command name to record, e.g. `/ll:manage-issue` |
| | `apply` | boolean | no (default `false`) | Set `true` to actually append the entry |
| `queue_add` | `target` | string | **yes** | Loop name, skill/command name, or raw CLI invocation |
| | `priority` | `P[0-5]` | no (default `P3`) | Priority tier |
| | `runner` | `skill`\|`cmd`\|`mcp`\|`prompt`\|`loop` | no | Force a specific runner kind instead of classifying `target` |
| | `args` | object | no | Extra `ActionSpec` args as key/value pairs |
| | `timeout` | integer | no (default `120`, unbounded for `runner=loop`) | Timeout in seconds |
| | `input` | string | no | Input for a loop-runner target, same semantics as `ll-loop run <loop> [input]` |
| | `apply` | boolean | no (default `false`) | Set `true` to actually queue the entry |
| `queue_remove` | `id` | string | **yes** | Entry id (full uuid or 8+-char prefix); must be `pending` |
| | `apply` | boolean | no (default `false`) | Set `true` to actually remove the entry |
| `queue_requeue` | `id` | string | **yes** | Entry id (full uuid or 8+-char prefix); must be `running` |
| | `apply` | boolean | no (default `false`) | Set `true` to actually requeue the entry |
| `loop_start` | `loop` | string | **yes** | Loop name to run |
| | `context` | string[] | no | `KEY=VALUE` context overrides, mirrors `ll-loop run --context` |

`issues_query` returns a list of `{id, priority, type, title, path, status, parent, labels}` dicts. `issue_get` returns the same summary-card field set `ll-issues show` uses, or a tool-level error if `issue_id` doesn't resolve. `history_search` returns a list of `SearchResult` dicts. `deps_check` returns `{has_issues, broken_refs, missing_backlinks, cycles, stale_completed_refs, broken_depends_on_refs, broken_relates_to_refs}`. `capabilities` returns `{host, binary, version, capabilities}`. `queue_list` returns a list of entries, byte-identical to `ll-queue list --json` (each entry's `to_dict()` shape). `queue_get` returns a single entry's `to_dict()` shape, or a tool-level error if `id` doesn't resolve. Each mutating tool returns
`{applied, tool, target, changes}`; `issue_capture`'s `target` is `{type, priority, slug,
directory}` plus a `rendered_body` on a dry-run and `{issue_id, path}` on apply. `queue_add`
returns `{entry: {name, runner, target, args, timeout, priority}}` on a dry-run (the classified
preview) and `{entry: <to_dict()>}` on apply. `queue_remove`/`queue_requeue` return
`{target: {id, target, status}}`, `queue_requeue` adding a `changes` list describing the
`running` → `pending` transition either way.

**`loop_start`** (FEAT-3151): starts a detached `ll-loop` run — the same spawn
`ll-loop run --background` performs — and returns immediately. Ordinary callers get
`{instance_id, loop}`; a client that declared the SEP-2663 tasks extension in its
per-request capabilities *and* set `params.task` on that call instead gets a task-shaped
result, `{resultType: "task", taskId, status: "working"}`, where `taskId` is the same
`instance_id` verbatim. Either shape, the run started — the envelope is the only thing
that differs, never whether a run was spawned. A spawn failure (scope conflict, unloadable
loop) is always an ordinary tool error, never a task id for a run that does not exist. Not
one of the seven mutating tools above — a dry-run "start" has no coherent meaning, so it
takes no `apply` parameter and is gated by `allow_tasks` (below), not `allow_mutations`.

**`tasks/get` / `tasks/cancel`** (FEAT-3145): not tools — custom JSON-RPC methods,
registered directly on the server via `Server.add_request_handler`, shaped to track the
(unshipped) `io.modelcontextprotocol/tasks` extension so a later swap is a registration
change, not a client-visible one. Poll or stop an `ll-loop` run — one started via
`loop_start` above, or by existing means (`ll-loop run` on the workstation); `ll-queue` is
out of scope. Polling a run immediately after `loop_start` returns (before its child
process has written a state file) still resolves, via a PID-file fallback that reports
`{taskId, status: "working", runStatus: "starting"}`. `initialize`'s capabilities never
advertise the extension itself.

| Method | Param | Type | Required | Description |
|--------|-------|------|----------|-------------|
| `tasks/get` | `taskId` | string | **yes** | The `ll-loop` `instance_id` verbatim (same string `ll-loop status` prints) |
| `tasks/cancel` | `taskId` | string | **yes** | Same semantics as `tasks/get`'s `taskId` |

`tasks/get` returns `{taskId, status, runStatus, …}` — `status` reconciles PID liveness
before ever reporting `"working"` (a run whose process died without updating its state
file is reported not-running); when no PID is resolvable at all, an `updated_at`-age
fallback catches permanently PID-less orphans the same way (BUG-3317). Once terminal, the result also carries the
`ExecutionResult` field set (`final_state`, `iterations`, `terminated_by`, `duration_ms`,
`captured`). An unresolvable `taskId` is a distinct JSON-RPC error (`-32002`), never a
default `"working"` shape. `tasks/cancel` returns `{taskId, status: "cancelled",
resumable, runStatus}` — never bare `"cancelled"`: neither backend has a genuinely
terminal cancelled state, so `resumable` and the backend's raw status always ride
alongside (e.g. `{"status": "cancelled", "resumable": true, "runStatus":
"user_stopped"}`).

Gated by the same deny-by-default-on-HTTP transport policy as the mutating tools, but as
an independent grant: `mcp.transport_policy.<http|stdio>.allow_tasks` (default `false` /
`true`), separate from `allow_mutations` — consenting to issue-file writes over HTTP does
not imply consenting to starting or stopping a running agent. `loop_start` shares this same
grant (starting a run is the same class of authority as stopping one). A denied `tasks/get`
reports itself as a `tasks/get` denial, and a denied `loop_start` call reports itself as a
`tools/call/loop_start` denial — not a generic `tools/call` one. Enforced uniformly on both
transports (FEAT-3168): the `tasks/get`/`tasks/cancel` handlers and `loop_start`'s
`tools/call` handler each consult the policy directly, so `stdio.allow_tasks: false` denies
with `-32001` over stdio exactly as `http.allow_tasks: false` does over HTTP.

Also advertises a `resources` capability (FEAT-3136): issue files, `.ll/ll-goals.md`, and
`docs/**/*.md` are listed and readable under an `ll://` scheme (`ll://issues/<ID>`,
`ll://goals`, `ll://docs/<relative-path>`). Unlike the tools, the resource surface is *not*
fully stateless — the exact set of readable `ll://` URIs is enumerated once when the server
starts (a "discovery-time enumeration"), and `resources/read` only ever serves a `uri`
already present in that enumeration; a request for any other `uri` is rejected without a
filesystem read. `resources/list` returns name/description from frontmatter only (no full
bodies); `resources/read` returns a resource's full body — the same summary-card field dict
`issue_get` returns for issues, `ProductGoals.raw_content` for `ll://goals`, and raw file
text for docs. Both `resources/list` and `resources/read` responses carry `ttlMs`/
`cacheScope` per SEP-2549. It also unconditionally advertises one interactive `ui://`-scheme
resource, `ui://issues/view` (ENH-3306), `mimeType: "text/html;profile=mcp-app"` per the
MCP Apps extension — a static package-data template (not project data), linked from
`issue_get` via `_meta.ui.resourceUri`, for hosts that negotiated the
`io.modelcontextprotocol/ui` capability at `initialize`.

Also advertises a `prompts` capability (FEAT-3137): every discovered `SKILL.md` — walked
recursively so a nested `SKILL.md` registers as its own independent prompt rather than being
absorbed as a parent skill's supporting file — is listed as an MCP prompt, with name (the
containing directory name), description, and args read from frontmatter. A skill with
`disable-model-invocation: true` is skipped. Like the resource surface, the prompt
enumeration is built at startup and then rebuilt on demand whenever the skills root's mtime
changes (ENH-3172), so a skill added mid-session is served without a restart; `prompts/get`
only ever serves a `name` present in the current enumeration, rejecting anything else without
a filesystem read. `prompts/list` returns
name/description/args from frontmatter only; `prompts/get` returns the skill's full body
(frontmatter stripped) as a single user-role prompt message. `prompts/list` responses carry
`ttlMs`/`cacheScope` per SEP-2549.

The skills root that surface enumerates is resolved on every install source (BUG-3177), not
only a plugin checkout: `LL_MCP_SKILLS_ROOT` env var if set and a valid directory, then
`CLAUDE_PLUGIN_ROOT/skills` if set and valid, then the copy shipped inside the installed
`little_loops` package, then the checkout-relative fallback. If none resolve, the server logs
an `ERROR:` line on stderr naming every path it tried and serves an empty prompt list rather
than failing silently.

**Arguments:** `--http` selects the streamable HTTP transport instead of stdio (the
`LL_MCP_TRANSPORT=http` env var is the equivalent for hosts that invoke `ll-mcp` with no
args). `LL_MCP_SKILLS_ROOT` overrides the prompts-from-skills root (see above).
`--project-root PATH` (or `LL_MCP_PROJECT_ROOT`) resolves the project the tool surface
operates on (ENH-3171). `--host HOST` / `--port PORT` (HTTP transport only, ENH-3173) bind
somewhere other than the `127.0.0.1:8765` default — flags win over `mcp.http.host` /
`mcp.http.port` in `.ll/ll-config.json`, which is the config-only equivalent. Loopback stays
the default with neither set: no path here defaults to `0.0.0.0`. Binding a non-loopback
`--host` also widens `TransportSecuritySettings.allowed_hosts`/`allowed_origins` to that
host, since the SDK only auto-fills that allow-list for a loopback bind — otherwise the
server would reject every request's `Host`/`Origin` header. This does not add
authentication; `mcp.transport_policy` (above) still governs what a connected client may
do, and remains deny-by-default for HTTP mutations/tasks regardless of bind address. It is
a protocol server, not a general CLI — these are the only flags.

**Exit codes:** `0` = clean EOF/shutdown, `2` = missing the `mcp` extra, or a usage error

**Examples:**
```bash
ll-mcp   # normally launched by an MCP host, not invoked directly
```

For host registration (including clients `ll-adapt` has no emitter for), the
working-directory requirement, `mcp-call` verification recipes, and troubleshooting, see
the [MCP Server Guide](../guides/MCP_SERVER_GUIDE.md).

---

### mcp-call

Thin CLI wrapper for direct MCP tool invocation via JSON-RPC. Reads `.mcp.json` from the current directory, spawns the MCP server subprocess, performs the JSON-RPC initialize handshake, calls `tools/call`, and writes the MCP response envelope to stdout.

**Arguments:**

| Argument | Description |
|----------|-------------|
| `server/tool-name` | MCP server name and tool name joined by `/` (e.g., `pencil/batch_get`) |
| `params_json` | Tool parameters as a JSON object string |
| `--timeout SECONDS` | Request timeout in seconds (default: 30). Exit code `124` on timeout. |

**Exit codes:** `0` = success, `1` = tool error, `2` = usage/config error, `124` = timeout, `127` = server or tool not found in `.mcp.json`

**Examples:**
```bash
mcp-call pencil/batch_get '{"patterns": ["**/*.pen"]}'
mcp-call my-server/my-tool '{"key": "value"}'
mcp-call pencil/batch_design '{"nodes": [...]}' --timeout 120
```

---

### ll-learning-tests

Query and manage the learning test registry. Skills and loops call this via `Bash` to check coverage before proceeding.

**Subcommands:**

| Subcommand | Description |
|------------|-------------|
| `check <target> [--stale-aware]` | Print record JSON (with a derived `failing_claims` count) and, on stderr, the text of any `result: fail` assertions; exit 1 if not found or (with `--stale-aware`) if the record is stale. A `proven` record only requires one passing assertion, so it can still carry contradicted claims — `failing_claims` surfaces that independent of `status` (BUG-3072) |
| `list` | Print all records as a JSON array |
| `mark-stale <target>` | Set status=stale; exit 1 if not found |
| `orphans [--mark-stale]` | List records whose target package is not imported by any project file; optionally mark them all stale |
| `prove <target>` | Trigger proving via `ready-to-implement-gate` (retry-then-`/ll:explore-api`); stamp `proven_package`/`proven_version` onto the refreshed record (ENH-3125) and print it; exit 0 if `proven`, 1 otherwise (ENH-2430) |
| `backfill-versions [--dry-run]` | Stamp `proven_package`/`proven_version` onto every existing record whose target resolves to an installed non-stdlib distribution, enabling version-drift staleness for records proven before the fields existed. Stdlib and free-text targets are left untouched. Idempotent (ENH-3125) |

**Examples:**
```bash
ll-learning-tests check "Anthropic SDK streaming"
ll-learning-tests check "Anthropic SDK streaming" --stale-aware   # exit 1 if stale
ll-learning-tests list
ll-learning-tests list | jq -r '.[] | "\(.status)\t\(.target)"'
ll-learning-tests mark-stale "Anthropic SDK streaming"
ll-learning-tests orphans                # list orphaned records
ll-learning-tests orphans --mark-stale   # atomically mark all orphans stale
ll-learning-tests prove "Anthropic SDK streaming"   # trigger proving directly, no issue file required
ll-learning-tests backfill-versions --dry-run       # preview version stamping across the registry
ll-learning-tests backfill-versions                 # stamp proven_package/proven_version
ll-learning-tests --help
```

**Exit codes:** `0` = success, `1` = target not found (or stale with `--stale-aware`)

---

## See Also

- [COMMANDS.md](COMMANDS.md) — `/ll:` slash commands reference
- [ARCHITECTURE.md](../ARCHITECTURE.md) — System design
- [LOOPS_GUIDE.md](../guides/LOOPS_GUIDE.md) — FSM loop configuration guide
- [API.md](API.md) — Python module API reference
- [write-a-hook.md](../claude-code/write-a-hook.md) — hook authoring guide for `LLHookIntentExtension`
