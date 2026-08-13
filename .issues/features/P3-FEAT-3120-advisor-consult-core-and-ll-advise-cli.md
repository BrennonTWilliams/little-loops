---
id: FEAT-3120
title: Advisor consult() core and ll-advise CLI
type: FEAT
parent: FEAT-3044
priority: P3
status: open
testable: true
verify_verdict: VALID
discovered_date: 2026-08-08
depends_on:
- FEAT-3042
- FEAT-3043
- FEAT-3108
labels:
- planning-hub
size: Very Large
reconcile_attempted: true
confidence_score: 80
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-3120: Advisor consult() core and ll-advise CLI

> **Provenance note — 2026-08-08.** Authored as `FEAT-3111` inside a
> non-worktree sandbox whose stray `.ll/` shadowed the project root, so its
> IDs were minted against a shadow issue tree. Salvaged and re-IDed to
> `FEAT-3120`; sibling `FEAT-3112` → `FEAT-3121`, `FEAT-3110` → `FEAT-3122`,
> and the redundant `FEAT-3109` grouping layer collapsed into `FEAT-3044`.
> Research content is unchanged and its `FEAT-3042`/`FEAT-3043`/`FEAT-3108`
> dependency edges point at real canonical issues.

## Summary

Ship `consult()` in `advisor.py` and the `ll-advise` CLI (`main_advise`).
This composes the shared transport (FEAT-3042), the config block
(FEAT-3043), and the capability floor (FEAT-3108) into the accountable,
signal-cited consult contract — the Python implementation half of
FEAT-3044's original scope. The `/ll:advise` skill that wraps this CLI is
tracked separately as [FEAT-3121](P3-FEAT-3121-advisor-advise-skill-wrapping-ll-advise-cli.md),
since the skill is a genuinely separate, differently-tested artifact
(markdown, not Python) that must land after this CLI exists.

## Parent Issue

Decomposed from [FEAT-3044](P3-FEAT-3044-advisor-consult-ll-advise-cli-and-skill.md):
Advisor consult() core, `ll-advise` CLI, and `/ll:advise` skill.

## Current Behavior

- A second-model consult is not expressible. Escalating to a stronger
  model means switching `orchestration.host_cli` / `--model` globally, or
  spawning a subagent (same host, same model family, prose back into the
  transcript, no budget accounting).
- `AdvisorConfig` (a FEAT-3043 deliverable, still `status: open` as of
  this decomposition) is not yet defined in `config/orchestration.py`,
  which currently only defines `ComposerAdaptiveConfig`, `ClusterConfig`,
  `ComposerConfig`, and `OrchestrationConfig`.
- FEAT-3042's `resolve_host_named` / `run_blocking_json` are this issue's
  `blocked_by` dependency. Until they ship, `consult()` cannot compose
  against a stable, named-host transport API; the only existing primitive
  is `HostRunner.build_blocking_json` via direct registry indexing
  (`_HOST_RUNNER_REGISTRY[name]()`, `host_runner.py:1522-1530`), bypassing
  the env/probe-based `resolve_host()` entirely.
- `apply_host_cli_from_config()` (`host_runner.py:1622-1647`) mutates the
  process-global `LL_HOST_CLI` — the advisor must never call it.

## Expected Behavior

- `ll-advise --signal <name> --question <q> [--context-file F]` resolves
  the configured advisor host **independently of** `orchestration.host_cli`,
  issues one blocking call, and prints a structured verdict as JSON on
  stdout.
- `--signal` is **required**. Every consult records what prompted it
  (`user_requested` is a valid, explicit value). There is no unsignalled
  consult path.
- A consult against an unwired host (`opencode`, `pi`) or an
  unauthenticated host **fails soft**: no consult, non-zero exit with a
  clear reason, never a traceback.
- The advisor must **not** call `apply_host_cli_from_config()`.
- `check_floor` (FEAT-3108) gates the consult: `violation` refuses it
  (non-zero exit), `advisory`/`unknown` proceed with a stderr warning.

## Use Case

A `refine-to-ready-issue` loop stalled on a `check_semantic` gate runs
`ll-advise --signal score_stall --question "..." --context-file ...` and
gets a structured, stronger-model second opinion instead of a same-model
re-grade.

## Motivation

little-loops has committed, in writing, to the position that a model
should not self-decide escalation on vibes: `MR-1` and the "LLM
self-grades are 33-55% accurate" citation in
`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` exist to guard against
self-evaluation bias. `--signal` being required encodes that discipline
in the CLI contract from day one.

## Proposed Solution

`ll-advise` is a thin sibling of `ll-action` / `ll-harness`: context in →
structured verdict out. Both wrap their entire body in
`cli_event_context(DEFAULT_DB_PATH, "ll-<name>", sys.argv[1:])`, dispatch
to `cmd_<subcommand>(args) -> int` functions that return ints rather than
raising or calling `sys.exit`, and catch **specific** expected exceptions
at the `cmd_*` boundary (not a blanket `except Exception`) — e.g.
`cmd_invoke` catches `subprocess.TimeoutExpired` (`cli/action.py:249-250`),
`cmd_mcp`'s shared `_report()`/`_evaluate_and_report()` helpers
(`cli/harness.py:447-466`, `378-388`) catch `json.JSONDecodeError`.
`ll-advise`'s fail-soft contract should catch `HostNotConfigured`
(raised by `OpenCodeRunner`/`PiRunner`, `host_runner.py:779-907`) plus
host/transport timeouts at this same boundary. The closest existing
exception-tuple precedent for the fail-soft catch is
`cli/doctor.py:_probe_version` (lines 912-932):
`(subprocess.TimeoutExpired, FileNotFoundError, OSError,
HostNotConfigured)`.

Structured output (not prose) is deliberate — it keeps the consult
auditable and lets gates consume `confidence` programmatically.

For the `resolve_host_named(...)` call itself, the dominant codebase
pattern is a narrow, standalone `except HostNotConfigured:` wrapped
tightly around only that call, separate from any subprocess-execution
catch — `cli/loop/_helpers.py:2071-2074`, `init/install_check.py:76-79,146`,
`init/cli.py:173`.

### Determinism (satisfied by construction, no code needed)

`derive_input_hash` (`cli/loop/_helpers.py:1395`) only seeds
`context["input_hash"]` from FSM loop-launch input; `decide_cache_marking`
(`cache_marking_oracle.py:76`) is only invoked from
`dispatch_anthropic_request` (the SDK path), never from
`build_blocking_json`/subprocess-transport code. `consult()` uses the
subprocess transport exclusively (via FEAT-3042's `run_blocking_json`),
so it structurally never touches either mechanism — this is satisfied by
construction. Add a one-line comment in `advisor.py` noting this is
deliberate, so a future FSM-integrated advisor state (FEAT-3039) doesn't
accidentally wire a consult into either path.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- **Correction to `cmd_mcp`'s exception-catch citation**: the `json.JSONDecodeError` catch is not inside `_report()`/`_evaluate_and_report()` (`cli/harness.py:378-388,447-466` — those two functions are report-formatting helpers only). The actual catch site is in `cmd_mcp`'s own body at `cli/harness.py:543-547` (`try: params = json.loads(args.mcp_args) except json.JSONDecodeError as e:`). The cited line ranges for the two helper *functions* are themselves accurate; only the attribution of where the catch happens needs correcting.
- **Line-number refresh for the `HostNotConfigured` narrow-catch precedent** (currently cited as `init/install_check.py:76-79,146` and `init/cli.py:173`): confirmed current locations are `init/install_check.py:76-79` and a second occurrence at `init/install_check.py:143-147`, and `init/cli.py:171-174` (the `try:`/`except HostNotConfigured:` block). `cli/loop/_helpers.py:2071-2074` is unchanged.

## API/Interface

```python
# scripts/little_loops/advisor.py (extends the module FEAT-3108 creates)
@dataclass(frozen=True)
class AdvisorVerdict:
    recommendation: str
    risks: list[str]
    confidence: float
    dissent: str
    signal: str
    host: str
    model: str

def consult(
    *,
    question: str,
    signal: str,
    context: str = "",
    config: BRConfig | None = None,
    main_model: str | None = None,
) -> AdvisorVerdict: ...
```

CLI:

```
ll-advise --signal <name> --question <text>
          [--context-file PATH] [--main-model MODEL]
          [--host HOST] [--model MODEL] [--json]
```

- There is no ambient "main model" in `BRConfig` — it is per-FSM-state
  `model:`, per-CLI `--model`, or a host default. `ll-advise` accepts
  `--main-model`, defaulting to `fsm.schema.DEFAULT_LLM_MODEL` (`"sonnet"`).

## Program Design

### Types

- `AdvisorVerdict: {recommendation: str, risks: list[str], confidence: float, dissent: str, signal: str, host: str, model: str}`

### Signatures

- `consult(*, question: str, signal: str, context: str, config: BRConfig | None, main_model: str | None) -> AdvisorVerdict`
- `main_advise(argv: list[str] | None = None) -> int`

### Call Path

`main_advise` -> `consult` -> `resolve_host_named` (FEAT-3042) ->
`HostRunner.build_blocking_json` -> `run_blocking_json` (FEAT-3042) ->
`AdvisorVerdict`

Closest existing call-path precedent: `runner_spec.py:_run_prompt`
(lines 287-303) — `resolve_host().build_blocking_json(prompt=...,
model=...)` then `subprocess.run([inv.binary, *inv.args],
capture_output=True, text=True, timeout=...)` inside a `try` that catches
`subprocess.TimeoutExpired` and `FileNotFoundError` narrowly.

### Decision Rules

- `--signal` is required: a missing `--signal` is a usage error via the
  argparse required-argument path — non-zero exit, no consult;
  `user_requested` is an explicit, valid signal.
- `check_floor(...)` (FEAT-3108) gates the consult: `violation` (same
  host) refuses the consult with a non-zero exit; `advisory` (cross-host)
  or `unknown` (unrankable) proceed with a stderr warning — never a
  silent pass.
- Unwired/unauthenticated host: `HostNotConfigured` (or a host/transport
  timeout) at the `cmd_*` boundary → non-zero exit with a clear reason —
  no traceback, no partial stdout.
- `AdvisorConfig.min_tier` reconciliation (open decision inherited from
  FEAT-3044's refine pass, resolved here): `min_tier` is validated at
  config-load time only (a separate, simpler check), and `check_floor`'s
  signature stays exactly as FEAT-3108 specifies it, ignoring `min_tier`
  at the `consult()` call level. This is the simpler of the two options
  left open, chosen to avoid coupling `consult()`'s call boundary to a
  config field that has no test coverage proving the combined-floor
  semantics yet; revisit if a future issue needs `min_tier` enforced at
  call time.

### Codebase Research Findings

- `AdvisorVerdict`/`FloorResult` (FEAT-3108) → JSON on stdout:
  `cli/doctor.py` (the sibling module FEAT-3122 extends) manually
  reconstructs a dict from named fields at every JSON emission site
  rather than calling `dataclasses.asdict()`. Follow that convention for
  `main_advise`'s `--json` output rather than the disagreeing
  `cli/help.py:13,230` precedent that does call `asdict()` on a frozen
  dataclass.
- **Contested `--json`/`--output` convention**: `cli/doctor.py` uses a
  bare `store_true -j/--json` flag; `ll-harness` uses `--output
  {text,json}` (choice, default `text`); `ll-action` uses `--output
  {stream-json,json}` per-subcommand. `cli/code.py` (FEAT-2576, the
  closest one-shot context-in/structured-out CLI in shape to
  `ll-advise`) uses neither — it calls the shared `add_json_arg(parser)`
  helper in `cli_args.py:324-331` (`"-j", "--json",
  action="store_true"`), reused by 12 other CLI modules
  (`cli/issues/link_epics.py`, `cli/docs.py`, `cli/deps.py`,
  `cli/history.py`, `cli/verify_private_refs.py`,
  `cli/verify_skill_prose.py`, `cli/logs.py`, `cli/session.py`,
  `cli/compact_session.py`, `cli/sync.py`, `cli/gitignore.py`,
  `cli/code.py`). This is a wider footprint than either `--output
  {choices}` shape — a reasonable default for `ll-advise`, though the
  implementer should decide knowingly since `doctor.py` also uses the
  bare-flag shape independently. Both `ll-action` and `ll-harness` route
  JSON output through the shared `little_loops.cli.output.print_json`
  helper rather than hand-rolling `json.dumps`+`print`.
- **`AdvisorConfig`-into-`BRConfig` wiring precedent**: no config block
  currently wired into `BRConfig` matches "advisor" by name, but
  `CodeQueryConfig` (`config/features.py:848-862`, explicitly
  docstringed "inert until ENH-2613") is the closest same-shape
  precedent for a config dataclass that ships inert and gets a first
  reader in a later issue — aggregated at `config/core.py:268`
  (`self._code_query = CodeQueryConfig.from_dict(...)`), exposed via a
  property at `core.py:367-369`, and surfaced in the config-dump dict at
  `core.py:916-923`. Its first reader, `cli/code.py:_default_provider()`
  (lines 17-21), accesses it as
  `BRConfig(Path.cwd()).code_query.provider` — the pattern `consult()`'s
  `config: BRConfig | None` parameter should expect once `AdvisorConfig`
  lands.

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- `resolve_host()`'s `env` parameter defaults to `dict(os.environ)`
  (`host_runner.py:1599-1600`) and never mutates `os.environ` itself —
  this is why FEAT-3042's `resolve_host_named(name)` can be a one-line
  `return resolve_host({"LL_HOST_CLI": name})` with no global side
  effects, consistent with this issue's "independently of
  `orchestration.host_cli`" requirement.
- `CapabilityNotSupported` (`UserWarning` subclass, `host_runner.py:108-116`)
  is a distinct signal from `HostNotConfigured`: it is *emitted* (warned),
  not raised, when a caller requests an unsupported capability on an
  otherwise-configured host (e.g. `--agent` on `codex`/`gemini`/`omp`).
  `consult()`'s fail-soft contract is about `HostNotConfigured` and
  transport timeouts; a `CapabilityNotSupported` warning is not itself a
  reason to refuse the consult.
- `HostInvocation.cleanup_paths: tuple[Path, ...]` (`host_runner.py:164`)
  is populated only by `CodexRunner.build_blocking_json` (writes a temp
  schema file, `host_runner.py:679-687`) and must be unlinked by the
  caller after the subprocess call completes. If `advisor.host` ever
  resolves to `codex`, `consult()`'s implementation must unlink these
  paths — none of the other host runners populate this field, so it is
  easy to omit without a codex-specific test catching it.

## Integration Map

### Files to Modify

- `scripts/pyproject.toml` — `ll-advise = "little_loops.cli:main_advise"`.
- `scripts/little_loops/cli/__init__.py` — three edits: the module
  docstring's CLI-inventory bullet list (top of file, lines 1-44), an
  `import` line (`from little_loops.cli.advise import main_advise`,
  alphabetized by module path among lines ~64-67), and the `__all__`
  list entry `"main_advise"` (alphabetized by symbol name, lines
  ~103-157).
- `scripts/little_loops/init/writers.py` — add
  `"Bash(ll-advise:*)"` to `_LL_PERMISSIONS`
  (`init/writers.py:80-134`, alphabetical, between
  `"Bash(ll-adapt-skills-for-codex:*)"` and `"Bash(ll-artifact:*)"`;
  **test-enforced** by `ll-verify-cli-allowlist`
  (`test_verify_cli_allowlist.py::TestRun::test_clean_state_returns_zero`)
  — that gate reads the **installed** distribution's entry points via
  `importlib_metadata.distribution("little-loops")`, not a live parse of
  `pyproject.toml`, so a `pip install -e "./scripts[dev]"` reinstall is
  required after adding the entry point before the gate will see it.
  Also add `ll-advise` to `_LL_COMMANDS`
  (`init/writers.py:156-218`, not independently test-enforced, but the
  convention every other `ll-*` CLI follows).
- `skills/configure/areas.md` — append `ll-advise` to the comma-separated
  `ll-` tool list in the "All ll- commands" preset description (line 849).
  _Wiring pass added by `/ll:wire-issue`:_ this is the **second** gate
  target `ll-verify-cli-allowlist` checks (`cli/verify_cli_allowlist.py`)
  alongside `writers._LL_PERMISSIONS` — the file's own docstring
  (`verify_cli_allowlist.py:5-6`) names both `skills/configure/areas.md`'s
  "All ll- commands" preset and `writers._LL_PERMISSIONS` as the two
  hand-maintained lists it cross-checks against installed entry points;
  the issue's existing `init/writers.py` bullet cites only the
  `_LL_PERMISSIONS` half of that gate. Missing this file leaves
  `ll-verify-cli-allowlist` failing after the `writers.py` edit alone.
- `scripts/little_loops/cli/help.py` — add an `"advise"` entry to the
  hand-maintained `_AREA_MAP` dict (`help.py:28-112`). Not test-gated,
  but a missed entry silently falls back to area `"Other"`.

### New Files

- `scripts/little_loops/advisor.py` — extends the module FEAT-3108
  creates with `consult`, `AdvisorVerdict`.
- `scripts/little_loops/cli/advise.py` — argparse surface.

### Similar Patterns

- `apply_host_cli_from_config` — the config→env precedence pattern the
  advisor deliberately does **not** reuse; its sole production call site
  is `cli/doctor.py:1050`, so the "must not call this" constraint is a
  plain grep-absence check against `advisor.py`/`cli/advise.py`.
- `ll-action` / `ll-harness` — the one-shot-CLI-returns-JSON shape to
  mirror.
- `resolve_host` mocking convention: tests patch at the *importing*
  module's namespace when that module does
  `from little_loops.host_runner import resolve_host` at module level
  (`fsm/evaluators.py`, `cli/action.py:15`); tests patch
  `little_loops.host_runner.resolve_host` directly when the caller
  imports it lazily inside a function body (`cli/doctor.py:998`).
  `test_advisor.py`'s mocking should follow whichever convention matches
  how `advisor.py` imports `resolve_host_named` into its own namespace.

### Tests

- `scripts/tests/test_advisor.py` — extends FEAT-3108's file with:
  `consult` contract against a mocked host runner; `--signal` required;
  a test asserting `consult()` never calls `dispatch_anthropic_request`
  or touches `derive_input_hash` (no existing "assert X never called"
  test for these to copy — construct fresh with
  `unittest.mock.patch(...).assert_not_called()`, per
  `test_cli_doctor.py:575-579`'s idiom).
- `scripts/tests/test_cli_advise.py` (new) — the repo's own convention
  splits CLI-argparse-contract tests from core-logic tests into a
  separate file per CLI (`cli/harness.py` -> `test_cli_harness.py`;
  `cli/action.py` -> `test_action.py`). `main_advise(argv) -> int`
  contract tests (required-arg `SystemExit`, `--json` output via
  `capsys`), modeled on `TestMainHarness` (`test_cli_harness.py:739`) and
  `TestMainAction.test_no_subcommand_exits_with_error`
  (`test_action.py:714`). Model the unwired-host fail-soft assertion on
  `test_skips_probe_when_binary_not_detected` (`test_cli_doctor.py:562`).
- `scripts/tests/test_wiring_cli_registry.py` — add
  `("docs/reference/CLI.md", "ll-advise", "FEAT-3120")` to the
  `DOC_STRINGS_PRESENT` tuples (test-enforced lockstep doc-coverage
  convention).
- `scripts/tests/test_wiring_reference_docs.py` — add one row per new
  public symbol expected in `docs/reference/API.md`:
  `("docs/reference/API.md", "little_loops.advisor", "FEAT-3120")`,
  `("docs/reference/API.md", "AdvisorVerdict", "FEAT-3120")`,
  `("docs/reference/API.md", "consult", "FEAT-3120")`.

### Documentation

- `docs/reference/CLI.md` — `ll-advise`, placed under the existing
  `## Skill Invocation` heading (`CLI.md:100`, siblings `ll-action`/
  `ll-harness`), not under `## Diagnostics`.
- `docs/reference/API.md` — `## Module Overview` table row for
  `little_loops.advisor`, plus the `## little_loops.advisor` body section
  for `consult`/`AdvisorVerdict` (FEAT-3108 already added the
  `FloorResult`/`check_floor`/`rank_model` rows to the same section).
- `docs/reference/HOST_COMPATIBILITY.md` § "Orchestration CLI"
  (`HOST_COMPATIBILITY.md:271-309`) — the hand-maintained table of every
  tool that routes host-CLI invocation through `host_runner.py`'s
  `HostRunner` Protocol. `consult()`'s key symbols
  (`resolve_host_named`, `run_blocking_json`, FEAT-3042) are
  host_runner-abstraction primitives, so `ll-advise` is conceptually a
  new row once FEAT-3042 lands. Update the table row and bump the
  "Last Verified" banner (`:265-269`) when this lands.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

- **Concrete test template for the unwired-host fail-soft assertion**
  (`scripts/tests/test_cli_doctor.py:562-581`,
  `test_skips_probe_when_binary_not_detected`): patches `sys.argv`
  directly (not `main_advise(argv=...)`), patches
  `little_loops.host_runner.resolve_host` at its *defining* module
  namespace, patches `builtins.print` via a capture helper, patches the
  module-under-test's `subprocess.run`, then asserts
  `mock_run.assert_not_called()` and inspects the parsed JSON payload.
  `test_cli_advise.py`'s unwired-host test can copy this exact
  patch/assert shape.

## Acceptance Criteria

1. `ll-advise --signal user_requested --question "..."` returns exit 0
   and prints JSON with exactly the keys `recommendation`, `risks`,
   `confidence`, `dissent`, `signal`, `host`, `model`.
2. Omitting `--signal` exits non-zero with a usage error. No code path
   performs a consult without a recorded signal.
3. With `advisor.host` differing from `orchestration.host_cli`, the
   consult invokes the advisor host's binary and the ambient
   `LL_HOST_CLI` / `orchestration.host_cli` is unchanged after the call
   (asserted, not assumed).
4. `advisor.host: "opencode"` or `"pi"` produces a non-zero exit with a
   message naming the unwired host — no traceback, no partial output.
5. `check_floor("claude-code", "haiku", "claude-code", "opus")`
   (FEAT-3108) causes `ll-advise` to refuse the consult, non-zero exit.
   The same mismatch across hosts (`advisory`) proceeds with a warning on
   stderr.
6. Advisor consults are excluded from FSM resume/replay input hashing and
   are never cache-marked (satisfied by construction; verified by the
   `assert_not_called()` test above).
7. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
   `python -m mypy scripts/little_loops/` all pass.

## Why not subagents / detached sessions?

- Subagents are **same-host, same-model-family** and lack the
  model-override + structured-verdict-back-into-transcript contract. The
  advisor's point is a *different, stronger, possibly different-provider*
  model.
- A detached session is fire-and-forget; the advisor is **synchronous and
  in-band** — the verdict must return before the primary continues.
- The consult must be signal-cited and (from Slice 2) budget-counted.
  Ad-hoc subagent spawns are neither.

Reuse the *transport*; the advisor is a thin accountable layer on top.

## Out of Scope

- **FEAT-3108** — `MODEL_RANKS`, `rank_model`, `FloorResult`; this issue
  only consumes `check_floor`.
- **FEAT-3122** — the `ll-doctor` advisor-reachability check.
- **FEAT-3121** — the `/ll:advise` skill wrapping this CLI.
- **FEAT-3038 (Slice 2)** — wire `confidence_gate` and `pre_done` to
  auto-consult; add `max_consults_per_task` plus the per-task counter.
- **FEAT-3039 (Slice 3)** — FSM stall escalation consuming
  `evaluate_diff_stall` / `evaluate_score_stall` verdicts.
- **FEAT-3040 (Slice 4)** — log consults to `.ll/history.db` for
  `ll-ctx-stats` analytics.

Also unresolved and deferred:

- **Overlap with `/ll:go-no-go`.** Decide in Slice 2 whether the advisor
  becomes go-no-go's different-model engine or stays a separate surface.
- **Context assembly** — this issue uses an explicit, caller-authored
  payload (`--context-file`), never an auto-slurp of the working tree.
- **Cross-host auth** — a `codex`/`gemini` advisor needs that host
  authenticated. Headless/cron runs may lack interactive auth;
  `ll-doctor` (FEAT-3122) surfaces it and the consult fails soft.

## Impact

- **Priority**: P3 — a capability gap, not a defect.
- **Effort**: Medium — composes FEAT-3042, FEAT-3043, and FEAT-3108 into
  the consult path and CLI.
- **Risk**: Low-Medium — additive surface, off by default
  (`advisor.enabled` false / block absent); the main risk is the
  fail-soft contract for unwired/unauthenticated hosts.
- **Breaking Change**: No.

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — MR-1, self-evaluation bias.
- `docs/reference/HOST_COMPATIBILITY.md#orchestration-cli` — host abstraction.
- `docs/reference/API.md#little_loopshost_runner`

## Status

open

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-08_

**Readiness Score**: 80/100 → STOP — ADDRESS GAPS (Dependencies Hard Override, BUG-3051)
**Outcome Confidence**: 82/100 → HIGH CONFIDENCE

### Gaps to Address
- `blocked_by: [FEAT-3042, FEAT-3043, FEAT-3108]` are not resolved: `FEAT-3042` and `FEAT-3043` are `status: open` and their deliverables (`resolve_host_named`, `run_blocking_json`, `AdvisorConfig`) do not exist anywhere in `scripts/little_loops/` yet — confirmed by grep, not just frontmatter status. `FEAT-3108` is `status: in_progress`; its code (`FloorResult`, `check_floor`, `rank_model`, `MODEL_RANKS`) has landed in `advisor.py` (commit `9dbe5943`), but the issue itself is not marked `done`. Per `.claude/CLAUDE.md` § Issue File Format, only `done`/`cancelled` resolve a `blocked_by` edge — `open`/`in_progress` do not. `consult()` cannot be implemented until FEAT-3042 and FEAT-3043 land; FEAT-3108's issue should be moved to `done` once its remaining scope (if any) is confirmed complete.

### Outcome Risk Factors
- Complexity — Breadth scored 14/25 (5 pts): ~14 distinct change sites across source, tests, and docs (Integration Map lists 5 files to modify, 2 new source files, 4 test files, 3 docs). Depth is Local (composing existing transport/floor primitives), which offsets the breadth penalty.

================================================================================
CONFIDENCE CHECK: FEAT-3120
================================================================================

## READINESS SCORES

| Criterion                     | Score | Details |
|--------------------------------|-------|---------|
| No duplicate implementations   | 20/20 | `consult()`/`AdvisorVerdict`/`ll-advise` don't exist; `advisor.py` (FEAT-3108) is designed to be extended, not duplicated |
| Architecture compliance        | 20/20 | Mirrors `ll-action`/`ll-harness` shape with exact line-number precedents throughout |
| Requirements clarity           | 20/20 | 7 concrete, testable acceptance criteria |
| Issue well-specified           | 20/20 | Extensive Integration Map, Program Design, Out of Scope; no `missing_behavior_parity`/`stale_symbol_ref`/`stale_cli_flag` gaps found |
| Dependencies satisfied         | 0/20  | `blocked_by` FEAT-3042/FEAT-3043 (open, code absent) and FEAT-3108 (in_progress) all unresolved — hard override |

## OUTCOME CONFIDENCE SCORES

| Criterion       | Score | Details |
|-----------------|-------|---------|
| Complexity      | 14/25 | Breadth 5/12 (~14 sites), Depth 9/13 (Local — composes existing primitives) |
| Test coverage   | 25/25 | Every new/extended file has a specified test target mirroring existing precedent |
| Ambiguity       | 18/25 | One decision pre-resolved in-issue (`min_tier`); one flagged-but-defaulted convention choice (`--json` shape) |
| Change surface  | 25/25 | New additive surface, 0 existing callers of `consult()` to break |

## SUMMARY

READINESS SCORE:    80/100 → STOP — ADDRESS GAPS (Dependencies Hard Override, BUG-3051)
OUTCOME CONFIDENCE: 82/100 → HIGH CONFIDENCE

## RECOMMENDATION: STOP — ADDRESS GAPS

### Gaps to Address
- Unresolved `blocked_by`: FEAT-3042 and FEAT-3043 are `open` with no code landed (`resolve_host_named`, `run_blocking_json`, `AdvisorConfig` absent from `scripts/little_loops/`); FEAT-3108 is `in_progress` despite its code being on `main`. This issue is otherwise exceptionally well-specified and should proceed immediately once those land.

VERDICT_JSON: {"verdict": "fail", "confidence": 80, "target_id": "FEAT-3120", "target_kind": "issue", "severity_counts": {"p0": 0, "p1": 1, "p2": 0, "info": 0}, "findings_count": 1}

================================================================================


## Session Log
- `/ll:verify-issues` - 2026-08-13T03:05:56 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:confidence-check` - 2026-08-08T19:53:33 - `f538a129-ed8b-4afd-b2c2-959e931d430a.jsonl`
- `/ll:confidence-check` - 2026-08-08T19:53:29 - `f538a129-ed8b-4afd-b2c2-959e931d430a.jsonl`
- `/ll:reconcile-issue` - 2026-08-08T19:50:27 - `f8a4aba2-de02-4fa0-b7f5-8cba8a090215.jsonl`
- `/ll:verify-issues` - 2026-08-08T19:46:56 - `3417dab5-06b4-4242-b368-8647bbc17bb9.jsonl`
- `/ll:refine-issue` - 2026-08-08T19:44:26 - `3fcbd097-b2d5-4d93-b8b8-eeb42b11485e.jsonl`
- `/ll:verify-issues` - 2026-08-08T19:39:51 - `c9e6efc0-99b8-4465-82e3-4ccae93d1b04.jsonl`
- `/ll:wire-issue` - 2026-08-08T19:37:49 - `a1109f8a-707c-4af7-aea2-d0c9704bccbb.jsonl`
- `/ll:refine-issue` - 2026-08-08T19:33:03 - `bbcfdf05-e78f-406a-9e7c-4702b3f10e64.jsonl`
- `/ll:issue-size-review` - 2026-08-08T19:27:04 - `a0b28a4d-10ef-4d55-8a0b-7d1cfa69c530.jsonl`
