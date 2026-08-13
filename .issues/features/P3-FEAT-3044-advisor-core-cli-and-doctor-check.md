---
id: FEAT-3044
title: Advisor core - ll-advise CLI, capability floor, and ll-doctor check
type: FEAT
parent: FEAT-3037
priority: P3
status: done
testable: true
discovered_date: 2026-08-04
reconcile_attempted: true
depends_on:
- FEAT-3042
- FEAT-3043
labels:
- planning-hub
verify_verdict: NON_VALID
---

# FEAT-3044: Advisor core - ll-advise CLI, capability floor, and ll-doctor check

## Summary

Ship the advisor-facing surface: `advisor.py` (`consult`, capability-rank
table, `check_floor`), the `ll-advise` CLI, `/ll:advise` skill, and the
`ll-doctor` advisor-reachability check. This is the accountable layer on top
of the shared transport (FEAT-3042) and config block (FEAT-3043) — it
composes them into the actual one-shot consult path.

## Parent Issue

Decomposed from FEAT-3037: Host-agnostic advisor. FEAT-3037 scored Very Large
(11/11) on `ll-issues size` and covers three architecturally separable
concerns (shared transport, config plumbing, advisor core + CLI). This child
covers the advisor core + CLI + doctor-check concern, and depends on both
FEAT-3042 (`run_blocking_json`, `resolve_host_named`) and FEAT-3043
(`AdvisorConfig`).

## Current Behavior

- A second-model consult is not expressible. Escalating to a stronger model
  means switching `orchestration.host_cli` / `--model` globally, or spawning a
  subagent (same host, same model family, prose back into the transcript, no
  budget accounting).
- No existing `@register_check` in `cli/doctor.py` pings a host CLI for
  reachability — the closest analog, `_capability_check_results()`
  (`doctor.py:98-113`), is deliberately *not* `@register_check`-registered
  because it needs the resolved `HostRunner` at call time (comment at
  `doctor.py:76-80`).
- `apply_host_cli_from_config()` (`host_runner.py:1612-1637`) has three
  early-return guards that make it a no-op: `os.environ.get("LL_HOST_CLI")`
  already truthy, `config.orchestration.host_cli` raising `AttributeError`,
  or `host_cli` falsy. Its one production call site is `cli/doctor.py:1050`,
  immediately before `resolve_host()` inside `main_doctor`.

## Expected Behavior

- `ll-advise --signal <name> --question <q> [--context-file F]` resolves the
  configured advisor host **independently of** `orchestration.host_cli`,
  issues one blocking call, and prints a structured verdict as JSON on
  stdout.
- `/ll:advise` wraps the CLI for the model-decided path: assemble decision
  context → call `ll-advise` → structured verdict lands in the transcript.
- `--signal` is **required**. Every consult records what prompted it
  (`user_requested` is a valid, explicit value). There is no unsignalled
  consult path.
- A consult against an unwired host (`opencode`, `pi`) or an unauthenticated
  host **fails soft**: no consult, non-zero exit with a clear reason, never a
  traceback.
- `ll-doctor` reports advisor host reachability and warns when the advisor
  model does not outrank the main model.
- The advisor must **not** call `apply_host_cli_from_config()` — that mutates
  the process-global `LL_HOST_CLI` and would rebind the orchestration host
  for everything downstream.

## Use Case

A `refine-to-ready-issue` loop run is on its third iteration of a
`check_semantic` gate that keeps returning `no` with drifting reasons. Rather
than burn a fourth Sonnet iteration, the operator runs:

```bash
ll-advise --signal score_stall \
  --question "Gate keeps failing with different reasons across 3 iterations. Is the criteria prompt underspecified, or is the artifact genuinely failing?" \
  --context-file .loops/tmp/scratch/gate-history.txt
```

An Opus advisor returns `{recommendation: "...", risks: [...], confidence: 0.8,
dissent: "..."}`. The operator sees a second, stronger opinion tied to a
measurable signal — not the same model re-grading itself.

## Motivation

little-loops has committed, in writing, to the position that a model should
not self-decide escalation on vibes: `MR-1` and the "LLM self-grades are
33-55% accurate" citation in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`
exist to guard against self-evaluation bias.

**Design principle:** model-requested consults are *allowed*; signal-gated
consults are *preferred*. This issue encodes that discipline as a required
`--signal` argument in the CLI contract from day one rather than retrofitting
it later.

## Proposed Solution

### Surface A — invocation (`ll-advise` CLI + `/ll:advise` skill)

`ll-advise` is a thin sibling of `ll-action` / `ll-harness`: context in →
structured verdict out. The skill is the human/model-facing entry; the CLI is
the single code path hooks and FSM states call in later slices.

`ll-action` / `ll-harness` (the cited CLI-shape precedent) both wrap their
entire body in `cli_event_context(DEFAULT_DB_PATH, "ll-<name>", sys.argv[1:])`,
dispatch to `cmd_<subcommand>(args) -> int` functions that return ints rather
than raising or calling `sys.exit`, and use `with suppress(Exception):` around
best-effort side-writes so a non-critical failure never changes the CLI's own
exit code (`cli/action.py:262-277`). `ll-advise`'s "fails soft, no traceback"
requirement should follow this same shape: catch host/timeout errors at the
`cmd_*` boundary and return a nonzero int, never let them propagate.

Structured output (not prose) is deliberate — it keeps the consult auditable
and lets gates consume `confidence` programmatically.

### Capability floor

Ship a static rank table beside `HostCapabilities`. Two details:

- **Table keys must tolerate concrete IDs.** `MODEL_ALIASES`
  (`host_runner.py:79-96`) has 4 entries: `fable → claude-fable-5`,
  `opus → claude-opus-5`, `sonnet → claude-sonnet-5`,
  `haiku → claude-haiku-4-5` (case-insensitive, whitespace-stripped lookup;
  unknown values pass through unchanged). A table keyed only on alias names
  silently no-ops on every non-alias value. Normalize through
  `resolve_model_alias()` first, then rank; an unrankable model yields
  "unknown" (warn), never "passes". `MODEL_RANKS`/`rank_model()` should cover
  `fable` alongside `opus`/`sonnet`/`haiku`.
- **There is no ambient "main model."** It is per-FSM-state `model:`,
  per-CLI `--model`, or a host default — nothing in `BRConfig` holds it. So:
  `ll-advise` accepts `--main-model`, defaulting to
  `fsm.schema.DEFAULT_LLM_MODEL` (`"sonnet"`), and `ll-doctor` compares
  against that same default.

Alternatives considered: **B. Trust the user** (no floor) silently permits a
weaker "advisor", reintroducing the self-eval bias the design fights.
**C. Empirical floor** from `ll-harness` eval history is principled but heavy
and cold-start-blocked. **A** (static table) is recommended, honest about its
limits.

### `ll-doctor` check

`CheckResult.severity: Literal["error", "informational"]`
(`cli/doctor.py:54-73`) is the existing mechanism for "warn but don't fail" —
`_exit_code_for` (`doctor.py:124-127`) only fails the overall exit code on
`severity == "error" and status == "unsupported"`. `_advisor_check` should
set `severity="informational"` for `advisory`/`unknown` floor results,
mirroring the existing `_ADVISORY_CAPABILITIES` frozenset pattern
(`doctor.py:95`). Follow the non-`@register_check` pattern used by
`_capability_check_results()` (or resolve the advisor host inside a thin
`@register_check` wrapper), since it needs the resolved `HostRunner` at call
time.

### Determinism (satisfied by construction, no code needed)

`derive_input_hash` (`cli/loop/_helpers.py:1395`) only seeds
`context["input_hash"]` from FSM loop-launch input; `decide_cache_marking`
(`cache_marking_oracle.py:76`) is only invoked from `dispatch_anthropic_request`
(the SDK path), never from `build_blocking_json`/subprocess-transport code.
`consult()` uses the subprocess transport exclusively (via FEAT-3042's
`run_blocking_json`), so it structurally never touches either mechanism — this
is satisfied by construction. Add a one-line comment in `advisor.py` noting
this is deliberate, so a future FSM-integrated advisor state (FEAT-3039)
doesn't accidentally wire a consult into either path.

## API/Interface

```python
# scripts/little_loops/advisor.py (new)
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

def rank_model(host: str, model: str) -> int | None:
    """Capability rank within *host*; None when unrankable."""

def check_floor(
    advisor_host: str, advisor_model: str, main_host: str, main_model: str
) -> FloorResult:
    """`ok` | `violation` (same host) | `advisory` (cross host) | `unknown`."""
```

CLI:

```
ll-advise --signal <name> --question <text>
          [--context-file PATH] [--main-model MODEL]
          [--host HOST] [--model MODEL] [--json]
```

## Program Design

### Types

- `AdvisorVerdict: {recommendation: str, risks: list[str], confidence: float, dissent: str, signal: str, host: str, model: str}`
- `FloorResult: {status: Literal["ok", "violation", "advisory", "unknown"], detail: str}`
- `MODEL_RANKS: dict[str, dict[str, int]]` — e.g. `{"claude-code": {"haiku": 1, "sonnet": 2, "opus": 3, "fable": ?}, ...}`

### Signatures

- `consult(*, question: str, signal: str, context: str, config: BRConfig | None, main_model: str | None) -> AdvisorVerdict`
- `rank_model(host: str, model: str) -> int | None`
- `check_floor(advisor_host: str, advisor_model: str, main_host: str, main_model: str) -> FloorResult`
- `main_advise(argv: list[str] | None = None) -> int`
- `_advisor_check() -> list[CheckResult]` (registered via `@register_check` or a thin wrapper)

### Call Path

`main_advise` -> `consult` -> `resolve_host_named` (FEAT-3042) ->
`HostRunner.build_blocking_json` -> `run_blocking_json` (FEAT-3042) ->
`AdvisorVerdict`

`ll-doctor` -> `_run_registered_checks` -> `_advisor_check` -> `check_floor` /
`HostRunner.build_version_check`

### Decision Rules

- `--signal` is required: a missing `--signal` is a usage error via the
  argparse required-argument path — non-zero exit, no consult; `user_requested`
  is an explicit, valid signal.
- Capability floor (new classification rule): `check_floor(...)` returns `ok`
  (proceed), `violation` (same host, consult refused, non-zero exit), `advisory`
  (cross-host, proceed with stderr warning), or `unknown` (unrankable model,
  warn + proceed — never a silent pass). Pinned case:
  `check_floor("claude-code", "haiku", "claude-code", "opus")` → `violation`.
- Unwired/unauthenticated host: `HostNotConfigured` (or a host/transport
  timeout) at the `cmd_*` boundary → non-zero exit with a clear reason — no
  traceback, no partial stdout.
- Open threshold: whether advisor == main rank counts as `ok` or `violation`
  is not pinned by this issue (only the haiku<opus case is given). Equality
  semantics must be fixed before the floor gate is wired.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

- No capability-rank/ordering table exists anywhere in the codebase — `MODEL_RANKS` is genuinely new. Adjacent model tables are not ranks: `MODEL_ALIASES` (`host_runner.py:79-84`, alias→concrete-ID map), `MODEL_PRICING` (`pricing.py:15-79`, insertion order implies a hierarchy but is not a rank), `MODEL_CONTEXT_WINDOW` (`context_window.py:19-33`). Rank lookup must normalize through `resolve_model_alias()` (`host_runner.py:87-96`: case-insensitive, whitespace-stripped, unknown values pass through unchanged) before table lookup, per the issue's own requirement.
- The canonical host-name set `MODEL_RANKS` keys on is `_HOST_RUNNER_REGISTRY`'s keys (`host_runner.py:1522-1530`): `claude-code`, `codex`, `opencode`, `pi`, `gemini`, `omp`, `kimi-code` — these are the names `resolve_host_named`/`consult` will present. `opencode`/`pi` are unwired stubs (`HostNotConfigured`), so their rank rows are unreachable: an unwired host fails soft in `consult` before `check_floor` ever sees it.

## Integration Map

### Files to Modify

Superseded by the 2026-08-10 decomposition (see Acceptance Criteria and
Verification Notes) — this issue no longer owns direct file changes. Each
listed file is now tracked under its own child's Integration Map instead:

- `scripts/little_loops/cli/doctor.py` (`_advisor_check`) — FEAT-3122.
- `scripts/pyproject.toml`, `scripts/little_loops/cli/__init__.py`
  (`ll-advise` entry point) — FEAT-3120.
- `skills/configure/areas.md`, `scripts/little_loops/init/writers.py`
  (`_LL_PERMISSIONS`, `_LL_COMMANDS`) — FEAT-3120.
- `.claude/CLAUDE.md` — FEAT-3121.

### New Files

- `scripts/little_loops/advisor.py` — `consult`, `MODEL_RANKS`, `rank_model`,
  `check_floor`.
- `scripts/little_loops/cli/advise.py` — argparse surface.
- `skills/advise/SKILL.md` — `/ll:advise`.

### Similar Patterns

- `apply_host_cli_from_config` — the config→env precedence pattern the
  advisor deliberately does **not** reuse (it must not mutate global
  `LL_HOST_CLI`); its sole production call site is `cli/doctor.py:1050`, so
  the "must not call this" constraint is a plain grep-absence check against
  `advisor.py`/`cli/advise.py`.
- `ll-action` / `ll-harness` — the one-shot-CLI-returns-JSON shape to mirror.
- Existing tests always patch `resolve_host` at the *calling* module in most
  cases, but `test_cli_doctor.py`/`test_cli_doctor_full.py` patch
  `little_loops.host_runner.resolve_host` directly at ~10 call sites (e.g.
  `test_cli_doctor.py:74,92,120,153,...`) — only `test_fsm_evaluators.py:933`
  patches at the caller namespace. `test_advisor.py`'s mocking should follow
  whichever convention matches how `advisor.py` imports `resolve_host_named`
  into its own namespace.

### Tests

- `scripts/tests/test_advisor.py` (new) — `rank_model` normalizes through
  `resolve_model_alias`; unrankable → `None`; `check_floor` returns
  `violation` same-host, `advisory` cross-host, `unknown` on unrankable;
  `consult` contract against a mocked host runner; `--signal` required.
- `scripts/tests/test_cli_advise.py` (new) — the repo's own convention splits
  CLI-argparse-contract tests from core-logic tests into a separate file per
  CLI (`cli/harness.py` -> `test_cli_harness.py`; `cli/action.py` ->
  `test_action.py`). `test_advisor.py` covers `consult`/`rank_model`/
  `check_floor` only; `main_advise(argv) -> int` contract tests (required-arg
  `SystemExit`, `--json` output via `capsys`) belong here, modeled on
  `TestMainHarness` (`test_cli_harness.py:739`) and
  `TestMainAction.test_no_subcommand_exits_with_error`
  (`test_action.py:714`).
- `scripts/tests/test_cli_doctor.py` — model `_advisor_check`'s
  "informational severity never fails exit code" behavior after
  `test_exit_code_ignores_informational_unsupported` (~line 699), and use the
  save/clear/restore-`_CHECKS` isolation pattern from
  `test_register_check_appends_and_runs` (~line 682) /
  `test_mixed_severity_registered_check_affects_exit_code_via_main_doctor`
  (~line 715) if `_advisor_check` needs a fake-check test double.

### Documentation

- `docs/reference/CLI.md` — `ll-advise`.
- `docs/reference/API.md` — `little_loops.advisor`.
- `docs/reference/HOST_COMPATIBILITY.md` — advisor host support matrix;
  explicit note that cross-host capability floors are **advisory, not
  enforced**.
- `.claude/CLAUDE.md` — add `/ll:advise` to the command list.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-07 — based on codebase analysis:_

- FEAT-3042's `resolve_host_named` / `run_blocking_json` have **zero code presence today** — grep across `scripts/little_loops/` returns nothing. The only existing transport primitive to compose against is `HostRunner.build_blocking_json`, present on every runner class (Protocol: `host_runner.py:250-258`; concrete build→`subprocess.run` shape at `fsm/evaluators.py:1120-1130`). `consult()` composes against whatever FEAT-3042 ships; this issue's `blocked_by: FEAT-3042` edge must be resolved before the consult path is implementable by name.
- The unwired-host fail-soft (AC 4) maps onto a concrete exception: `opencode`/`pi` are registered in `_HOST_RUNNER_REGISTRY` (`host_runner.py:1522-1530`) but their runner classes raise `HostNotConfigured` (`OpenCodeRunner`: `host_runner.py:779-851`, `PiRunner`: `:853-907`). The `cmd_*` boundary must catch `HostNotConfigured` plus host/transport timeouts and return a nonzero int, per the `ll-action`/`ll-harness` fails-soft shape (`cli/action.py:262-277`).
- New-CLI registration has a sixth lockstep surface beyond the five listed here: `cli/__init__.py`'s module docstring (`cli/__init__.py:1-44`) enumerates every `ll-*` entry point with a one-line description and is part of the CLI's discoverable surface.
- `_LL_COMMANDS` (`init/writers.py:156-218`) is **not** test-enforced — `ll-verify-cli-allowlist` imports and checks only `_LL_PERMISSIONS` (`init/writers.py:80-134`) and the `areas.md` "All ll- commands" preset (`skills/configure/areas.md:849`; gate wiring: `cli/verify_cli_allowlist.py:23,75-95`). Adding `ll-advise` to `_LL_COMMANDS` is still the convention — it renders consuming projects' `CLAUDE.md`/`AGENTS.md` command blocks via `_render_commands_block` (`init/writers.py:231-245`) — but a missing entry fails no test. Current anchors: `_LL_PERMISSIONS` at `init/writers.py:80-134`, `_LL_COMMANDS` at `:156-218` (the `~61-115` / `137-199` citations above predate the current layout).
- Non-registered doctor-check wiring site: `_capability_check_results(report)` is folded into the same `CheckResult` vocabulary at `main_doctor` (`cli/doctor.py:1088`: `results = _capability_check_results(report) + _run_registered_checks()`), the existing precedent for "needs resolved HostRunner at call time" checks (`cli/doctor.py:76-80`).
- `/ll:advise` skill-shape precedent: the closest non-prefixed skill wrapping an `ll-` CLI is `skills/init/SKILL.md` — `disable-model-invocation: true` frontmatter, `allowed-tools` granting `Bash(ll-init:*)` (`skills/init/SKILL.md:6-11`), a `<!-- PLUGIN_VERSION: x.y.z -->` marker, numbered Process body. The 500-line SKILL.md cap (`doc_counts.py:384-420`) does **not** apply to `disable-model-invocation` skills (`doc_counts.py:414`). The bridged `ll-`-prefixed skills (`skills/ll-check-code/SKILL.md`) are a different shape (thin pointers to `commands/*.md`) — the issue's non-prefixed `/ll:advise` name selects the `init` shape, not the bridged one.

## Acceptance Criteria

Per the 2026-08-10 `/ll:verify-issues` finding under Verification Notes, this
issue's scope has been re-decomposed into four child issues (all
`parent: FEAT-3044`), each carrying its own acceptance criteria covering the
sub-slice of what was originally listed here:

- **FEAT-3108** — capability floor (`MODEL_RANKS`, `rank_model`,
  `check_floor`) — `status: done`.
- **FEAT-3120** — `consult()` core and the `ll-advise` CLI — `status: open`.
- **FEAT-3121** — `/ll:advise` skill wrapping the `ll-advise` CLI —
  `status: open`.
- **FEAT-3122** — `ll-doctor` advisor-reachability check — `status: open`.

FEAT-3044 itself is satisfied when all four children reach `done`; it carries
no independent acceptance criteria of its own beyond that roll-up.

## Why not subagents / detached sessions?

- Subagents are **same-host, same-model-family** and lack the model-override
  + structured-verdict-back-into-transcript contract. The advisor's point is
  a *different, stronger, possibly different-provider* model.
- A detached session is fire-and-forget; the advisor is **synchronous and
  in-band** — the verdict must return before the primary continues.
- The consult must be signal-cited and (from Slice 2) budget-counted. Ad-hoc
  subagent spawns are neither.

Reuse the *transport*; the advisor is a thin accountable layer on top.

## Out of Scope (follow-up slices)

- **FEAT-3038 (Slice 2)** — wire `confidence_gate` and `pre_done` to
  auto-consult; add `max_consults_per_task` plus the per-task counter that
  makes it enforceable.
- **FEAT-3039 (Slice 3)** — FSM stall escalation consuming
  `evaluate_diff_stall` / `evaluate_score_stall` verdicts.
- **FEAT-3040 (Slice 4)** — log consults to `.ll/history.db` for
  `ll-ctx-stats` analytics.

Also unresolved and deferred:

- **Overlap with `/ll:go-no-go`.** That skill already *is* an adversarial
  second opinion. Decide in Slice 2 whether the advisor becomes go-no-go's
  different-model engine or stays a separate surface.
- **Context assembly** — this issue uses an explicit, caller-authored payload
  (`--context-file`), never an auto-slurp of the working tree.
- **Cross-host auth** — a `codex`/`gemini` advisor needs that host
  authenticated. Headless/cron runs may lack interactive auth; `ll-doctor`
  surfaces it and the consult fails soft.

## Impact

- **Priority**: P3 — a capability gap, not a defect.
- **Effort**: Medium — composes two already-shipped pieces (FEAT-3042,
  FEAT-3043) into the consult path, CLI, and doctor check; the
  capability-rank table is the one genuinely new algorithmic piece.
- **Risk**: Low-Medium — additive surface, off by default (`advisor.enabled`
  false / block absent); the main risk is the fail-soft contract for
  unwired/unauthenticated hosts.
- **Breaking Change**: No.

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — MR-1, self-evaluation bias.
- `docs/reference/HOST_COMPATIBILITY.md#orchestration-cli` — host abstraction.
- `docs/reference/API.md#little_loopshost_runner`

## Status

**Open** | Created: 2026-08-04 | Priority: P3

## Verification Notes

### 2026-08-10 (`/ll:verify-issues`)

Verified 2026-08-10: scope has been re-decomposed since this issue was written. FEAT-3108 (capability floor: `MODEL_RANKS`/`rank_model`/`check_floor`) already shipped as `status: done`, sourced under `scripts/little_loops/advisor.py` (112 lines) instead of this issue. FEAT-3120/3121/3122 (consult core, `/ll:advise` skill, doctor check) now cover the remaining scope as open children. FEAT-3044 itself is still `status: open` with no `depends_on`/parent update reflecting this decomposition. Recommend running `/ll:reconcile-issue` on this issue, or closing it in favor of its children (FEAT-3108 done; FEAT-3120/3121/3122 open) to avoid duplicated acceptance criteria.

### 2026-08-12 (`/ll:verify-issues`)

This issue self-documented its own decomposition on 2026-08-10 (see the note directly above and the Acceptance Criteria section, which already lists FEAT-3108/3120/3121/3122 as the four children carrying the real scope), but `status` was never flipped to reflect it. Following the closure convention set by ENH-3094 (`.issues/enhancements/P3-ENH-3094-collapse-per-call-automation-kwargs-into-automationcontext.md`) for a decomposed-not-superseded issue: `status` set to `done` and a `## Resolution` section added below recording the decomposition. `depends_on: [FEAT-3042, FEAT-3043]` is left unchanged — those are this issue's own real prerequisites, not part of the decomposition record.

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-08-10
- **Reason**: Scope re-decomposed into four architecturally separable children during a `/ll:verify-issues` pass; this issue carries no independent acceptance criteria beyond their roll-up.

### Decomposed Into
- FEAT-3108: Advisor capability floor (`MODEL_RANKS`, `rank_model`, `check_floor`) — `status: done`
- FEAT-3120: `consult()` core and the `ll-advise` CLI — `status: open`
- FEAT-3121: `/ll:advise` skill wrapping the `ll-advise` CLI — `status: open`
- FEAT-3122: `ll-doctor` advisor-reachability check — `status: open`

## Session Log
- `/ll:verify-issues` - 2026-08-13T03:08:32 - `10ce6a50-a4a8-4b29-a122-e05a925e303c.jsonl`
- `/ll:reconcile-issue` - 2026-08-10T18:23:28 - `19363ee8-c8d6-48d5-8b4b-21cba59c01cd.jsonl`
- `/ll:reconcile-issue` - 2026-08-10T16:32:50 - `8f3abfd3-6623-4955-b89f-579e5adefbdd.jsonl`
- `/ll:verify-issues` - 2026-08-10T16:25:24 - `50b69f30-8ca9-4ab9-8b06-6ee21c203b10.jsonl`
- `/ll:refine-issue` - 2026-08-07T01:31:56 - `122ea141-1333-4987-8849-731d61382a3b.jsonl`
- `/ll:issue-size-review` - 2026-08-04T20:47:21 - `b57cebec-46d2-436b-b650-9a1afa94ec18.jsonl`
