---
id: FEAT-3044
title: Advisor core - ll-advise CLI, capability floor, and ll-doctor check
type: FEAT
parent: FEAT-3037
priority: P3
status: open
testable: true
discovered_date: 2026-08-04
depends_on:
- FEAT-3042
- FEAT-3043
labels:
- planning-hub
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

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/doctor.py` — `_advisor_check`.
- `scripts/pyproject.toml` — `ll-advise = "little_loops.cli:main_advise"`.
- `scripts/little_loops/cli/__init__.py` — `main_advise` entry point.
- `skills/configure/areas.md` — add `ll-advise` to the "All ll- commands"
  preset-tools list.
- `scripts/little_loops/init/writers.py` — add `"Bash(ll-advise:*)"` to
  `_LL_PERMISSIONS` (line ~61-115) and add `ll-advise` to `_LL_COMMANDS`
  (lines 137-199, renders the "little-loops" section of *consuming projects'*
  generated `CLAUDE.md`/`AGENTS.md`). **`_LL_PERMISSIONS` is test-enforced**:
  `ll-verify-cli-allowlist` (BUG-2764) fails
  `scripts/tests/test_verify_cli_allowlist.py::TestRun::test_clean_state_returns_zero`
  if any `pyproject.toml` `[project.scripts]` entry is missing from either
  this tuple or `areas.md`.
- `.claude/CLAUDE.md` — add `/ll:advise` to the command list.

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

## Acceptance Criteria

1. `ll-advise --signal user_requested --question "..."` returns exit 0 and
   prints JSON with exactly the keys `recommendation`, `risks`, `confidence`,
   `dissent`, `signal`, `host`, `model`.
2. Omitting `--signal` exits non-zero with a usage error. No code path
   performs a consult without a recorded signal.
3. With `advisor.host` differing from `orchestration.host_cli`, the consult
   invokes the advisor host's binary and the ambient `LL_HOST_CLI` /
   `orchestration.host_cli` is unchanged after the call (asserted, not
   assumed).
4. `advisor.host: "opencode"` or `"pi"` produces a non-zero exit with a
   message naming the unwired host — no traceback, no partial output.
5. `check_floor("claude-code", "haiku", "claude-code", "opus")` returns
   `violation`; `ll-advise` refuses the consult. The same mismatch across
   hosts returns `advisory` and the consult proceeds with a warning on
   stderr.
6. `rank_model` returns the same rank for `"opus"` and its concrete ID from
   `MODEL_ALIASES`; an unknown/dated model returns `None` and `check_floor`
   returns `unknown` (warn, proceed) — never a silent pass.
7. `ll-doctor` reports advisor host reachability and emits a warning (not an
   error) when the floor is `advisory` or `unknown`; exit code is unaffected
   by an advisory-only finding.
8. Advisor consults are excluded from FSM resume/replay input hashing and are
   never cache-marked (satisfied by construction per the Proposed Solution;
   verified by a test asserting `consult()` never calls
   `dispatch_anthropic_request` or touches `derive_input_hash`).
9. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
   `python -m mypy scripts/little_loops/` all pass.

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


## Session Log
- `/ll:issue-size-review` - 2026-08-04T20:47:21 - `b57cebec-46d2-436b-b650-9a1afa94ec18.jsonl`
