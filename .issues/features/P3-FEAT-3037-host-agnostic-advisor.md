---
id: FEAT-3037
title: Host-agnostic advisor
type: FEAT
priority: P3
status: open
testable: true
discovered_date: 2026-08-03
blocks:
- 3038
- 3039
- 3040
labels:
- planning-hub
---

# FEAT-3037: Host-agnostic advisor

## Summary

Add a host-agnostic advisor consult path: a one-shot escalation to a second,
stronger — possibly different-provider — model that returns a **structured
verdict** (`{recommendation, risks[], confidence, dissent}`) in-band, before the
primary model commits to an approach.

Slice 1 (this issue) ships the invocation mechanism, config, capability floor,
and `ll-doctor` check. It reuses the existing `HostRunner.build_blocking_json`
transport — no new orchestration engine — and layers on accountability: a
mandatory signal citation, a capability floor, and a timeout.

## Current Behavior

- A second-model consult is not expressible. Escalating to a stronger model
  means switching `orchestration.host_cli` / `--model` globally, or spawning a
  subagent (same host, same model family, prose back into the transcript, no
  budget accounting).
- `resolve_host()` (`host_runner.py:1564`) resolves **one** host per process,
  from `LL_HOST_CLI` / `LL_HOOK_HOST` / a PATH probe. Every existing call site
  calls it bare — there is no per-call host selection anywhere in the codebase.
- Structured-output handling is inlined at each call site: builders drop the
  `json_schema` argument, and `fsm/evaluators.py:_structured_output_args`
  re-appends `--json-schema` only for hosts advertising
  `HostCapabilities.structured_output`. The run-subprocess-and-parse loop
  (timeout, empty-stdout-with-exit-0 guard, tag fallback) exists only inline in
  `evaluate_llm_structured` (`fsm/evaluators.py:1083-1270`).

## Expected Behavior

- `ll-advise --signal <name> --question <q> [--context-file F]` resolves the
  configured advisor host **independently of** `orchestration.host_cli`, issues
  one blocking call, and prints a structured verdict as JSON on stdout.
- `/ll:advise` wraps the CLI for the model-decided path: assemble decision
  context → call `ll-advise` → structured verdict lands in the transcript.
- `--signal` is **required**. Every consult records what prompted it
  (`user_requested` is a valid, explicit value). There is no unsignalled consult
  path, in Slice 1 or later.
- A consult against an unwired host (`opencode`, `pi`) or an unauthenticated
  host **fails soft**: no consult, non-zero exit with a clear reason, never a
  traceback.
- `ll-doctor` reports advisor host reachability and warns when the advisor model
  does not outrank the main model.

## Use Case

A `refine-to-ready-issue` loop run is on its third iteration of a
`check_semantic` gate that keeps returning `no` with drifting reasons. Rather
than burn a fourth Sonnet iteration, the operator (or, in Slice 3, the FSM's
`score_stall` route) runs:

```bash
ll-advise --signal score_stall \
  --question "Gate keeps failing with different reasons across 3 iterations. Is the criteria prompt underspecified, or is the artifact genuinely failing?" \
  --context-file .loops/tmp/scratch/gate-history.txt
```

An Opus advisor returns `{recommendation: "...", risks: [...], confidence: 0.8,
dissent: "..."}`. The operator sees a second, stronger opinion tied to a
measurable signal — not the same model re-grading itself.

## Motivation

little-loops has committed, in writing, to the position that a model should not
self-decide escalation on vibes: `MR-1` and the "LLM self-grades are 33–55%
accurate" citation in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` exist to guard
against self-evaluation bias. Anthropic's bundled Advisor Tool (Claude Code
v2.1.98+) is purely model-decided at three trigger points, and is
Anthropic-API-only.

The little-loops version differs on two axes:

- **Stronger — cross-host advisors.** A Sonnet-on-`claude-code` session can
  consult Opus-on-`claude-code` **or** GPT-on-`codex` **or** a Gemini model on
  `gemini`. The advisor `host` is deliberately decoupled from
  `orchestration.host_cli`, so cross-provider consults (and, indirectly,
  Bedrock/Vertex auth by routing through a different host binary) work.
- **Weaker — capability floor.** "advisor ≥ main" is free on one tier ladder;
  across providers there is no shared ranking. little-loops ships its own rank
  table, enforces it within a host, and downgrades cross-host floors to a
  warning.

**Design principle:** model-requested consults are *allowed*; signal-gated
consults are *preferred*. Slice 1 encodes this as a required `--signal`
argument so the discipline is in the CLI contract from day one rather than
retrofitted in Slice 2.

## Proposed Solution

### Surface A — invocation (`ll-advise` CLI + `/ll:advise` skill)

`ll-advise` is a thin sibling of `ll-action` / `ll-harness`: context in →
structured verdict out. The skill is the human/model-facing entry; the CLI is
the single code path hooks and FSM states call in later slices.

Structured output (not prose) is deliberate — it keeps the consult auditable and
lets gates consume `confidence` programmatically.

### Per-call host resolution (new plumbing — not free)

`resolve_host()` takes an *environment dict*, not a host name:

```python
def resolve_host(env: dict[str, str] | None = None) -> HostRunner: ...
```

Add an explicit named-resolution helper rather than overloading `env` at the
call site:

```python
def resolve_host_named(name: str) -> HostRunner:
    """Resolve a specific registered host, ignoring ambient LL_HOST_CLI."""
    return resolve_host({"LL_HOST_CLI": name})
```

The advisor must **not** call `apply_host_cli_from_config()` — that mutates the
process-global `LL_HOST_CLI` and would rebind the orchestration host for
everything downstream.

### Structured verdict across hosts (three paths, not one)

`HostCapabilities.structured_output` is `True` **only** for `ClaudeCodeRunner`.
The verdict extraction therefore needs:

| Host | Mechanism |
|------|-----------|
| `claude-code` | inline `--json-schema` (via `_structured_output_args`) |
| `codex` | `--output-schema <tmpfile>`, built by `CodexRunner.build_blocking_json`; caller **must** unlink `HostInvocation.cleanup_paths` |
| `gemini`, `omp`, `kimi-code` | prompt-and-parse, with the `_extract_tagged_structured_output` tag fallback |
| `opencode`, `pi` | stubs — `build_*` raises `HostNotConfigured`; fail soft |

Rather than duplicating ~80 lines from `evaluate_llm_structured`, extract the
run-and-parse loop into a reusable `run_blocking_json()` in `host_runner.py`
(alongside `dispatch_anthropic_request`, which already executes rather than just
builds). `evaluate_llm_structured` and `ll-advise` then share one
implementation, including the timeout, the empty-stdout-with-exit-0 guard, and
`cleanup_paths` unlinking.

### Surface B — configuration (`advisor:` block)

```jsonc
"advisor": {
  "enabled": true,
  "host": "claude-code",     // registry key; may differ from orchestration.host_cli
  "model": "opus",
  "min_tier": "opus",        // capability floor; enforced within a host, warned across
  "timeout_seconds": 180,
  "triggers": ["confidence_gate", "loop_stall", "pre_done"]
}
```

- `host` validates against the same enum as `orchestration.host_cli`:
  `claude-code | codex | opencode | pi | gemini | omp | kimi-code`. Not
  `"claude"` — that is not a registry key.
- `timeout_seconds` is mandatory-with-a-default: a synchronous in-band consult
  with no timeout can hang a loop indefinitely.
- `max_consults_per_task` is **deliberately absent** from the Slice 1 schema.
  Enforcement needs task identity, which arrives in Slice 2; shipping an
  accepted-but-ignored key is a footgun.

### Capability floor

Ship a static rank table beside `HostCapabilities`. Two details that the
"just add a table" framing hides:

- **Table keys must tolerate concrete IDs.** `MODEL_ALIASES`
  (`host_runner.py`) maps `opus`/`sonnet`/`haiku` → concrete IDs and passes
  unknown values (already-concrete IDs, dated snapshots, Bedrock-prefixed IDs)
  through untouched. A table keyed only on the three aliases silently no-ops on
  every non-alias value. Normalize through `resolve_model_alias()` first, then
  rank; an unrankable model yields "unknown" (warn), never "passes".
- **There is no ambient "main model."** It is per-FSM-state `model:`, per-CLI
  `--model`, or a host default — nothing in `BRConfig` holds it. So: `ll-advise`
  accepts `--main-model`, defaulting to `fsm.schema.DEFAULT_LLM_MODEL`
  (`"sonnet"`), and `ll-doctor` compares against that same default. Without this
  the floor is not evaluable at all.

Alternatives considered: **B. Trust the user** (no floor) silently permits a
weaker "advisor", reintroducing the self-eval bias the design fights.
**C. Empirical floor** from `ll-harness` eval history is principled but heavy
and cold-start-blocked. **A** is recommended, honest about its limits.

### Determinism

Consults are **non-cacheable**: excluded from the FSM resume/replay input hash
and never marked for prompt caching. Decided, not open.

## API/Interface

```python
# scripts/little_loops/host_runner.py (new)
def resolve_host_named(name: str) -> HostRunner: ...

def run_blocking_json(
    invocation: HostInvocation,
    *,
    schema: dict[str, Any] | None = None,
    timeout: int = 180,
) -> dict[str, Any] | None:
    """Execute a blocking invocation and return parsed JSON.

    Handles host-gated schema flags, the empty-stdout-with-exit-0 guard, the
    tagged-output fallback, and `invocation.cleanup_paths` unlinking.
    """

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

- `AdvisorConfig: {enabled: bool, host: str | None, model: str, min_tier: str | None, timeout_seconds: int, triggers: list[str]}`
- `AdvisorVerdict: {recommendation: str, risks: list[str], confidence: float, dissent: str, signal: str, host: str, model: str}`
- `FloorResult: {status: Literal["ok", "violation", "advisory", "unknown"], detail: str}`
- `MODEL_RANKS: dict[str, dict[str, int]]` — e.g. `{"claude-code": {"haiku": 1, "sonnet": 2, "opus": 3}, ...}`

### Signatures

- `resolve_host_named(name: str) -> HostRunner`
- `run_blocking_json(invocation: HostInvocation, *, schema: dict | None, timeout: int) -> dict | None`
- `AdvisorConfig.from_dict(data: dict[str, Any]) -> AdvisorConfig`
- `consult(*, question: str, signal: str, context: str, config: BRConfig | None, main_model: str | None) -> AdvisorVerdict`
- `rank_model(host: str, model: str) -> int | None`
- `check_floor(advisor_host: str, advisor_model: str, main_host: str, main_model: str) -> FloorResult`
- `main_advise(argv: list[str] | None = None) -> int`
- `_advisor_check() -> list[CheckResult]` (registered via `@register_check`)

### Call Path

`main_advise` -> `consult` -> `resolve_host_named` -> `HostRunner.build_blocking_json`
-> `run_blocking_json` -> `AdvisorVerdict`

`ll-doctor` -> `_run_registered_checks` -> `_advisor_check` -> `check_floor` / `HostRunner.build_version_check`

`evaluate_llm_structured` -> `run_blocking_json` (refactor: shares the extracted helper)

## Integration Map

### Files to Modify

- `scripts/little_loops/host_runner.py` — add `resolve_host_named`,
  `run_blocking_json`; export both in `__all__`.
- `scripts/little_loops/fsm/evaluators.py` — refactor `evaluate_llm_structured`
  onto `run_blocking_json`; `_structured_output_args` and
  `_extract_tagged_structured_output` move or are imported by the helper.
- `scripts/little_loops/config/orchestration.py` — add `AdvisorConfig`
  (advisor is host/orchestration-shaped; keep it beside `OrchestrationConfig`).
- `scripts/little_loops/config/core.py` — parse + expose `advisor` property;
  add to the `to_dict()` round-trip near line 782.
- `scripts/little_loops/config-schema.json` — `advisor` block, `host` enum
  matching `orchestration.host_cli` (line 1560).
- `scripts/little_loops/cli/doctor.py` — `_advisor_check` via `@register_check`.
- `scripts/pyproject.toml` — `ll-advise = "little_loops.cli:main_advise"`.
- `scripts/little_loops/cli/__init__.py` — `main_advise` entry point.

### New Files

- `scripts/little_loops/advisor.py` — `consult`, `MODEL_RANKS`, `rank_model`,
  `check_floor`.
- `scripts/little_loops/cli/advise.py` — argparse surface.
- `skills/advise/SKILL.md` — `/ll:advise`.

### Dependent Files (Callers/Importers)

- All 9 existing `build_blocking_json` call sites (`runner_spec.py:290`,
  `parallel/worker_pool.py:805`, `cli/issues/decisions.py:797`,
  `fsm/evaluators.py:1120,1314,1566`, `learning_tests/extractor.py:132`,
  `session_store/lifecycle.py:154`) keep working unchanged — the refactor is
  additive. Only `evaluate_llm_structured` migrates onto the shared helper in
  this slice.

### Similar Patterns

- `apply_host_cli_from_config` — the config→env precedence pattern the advisor
  deliberately does **not** reuse (it must not mutate global `LL_HOST_CLI`).
- `ll-action` / `ll-harness` — the one-shot-CLI-returns-JSON shape to mirror.
- `OrchestrationConfig.from_dict` — dataclass config plumbing convention.

### Tests

- `scripts/tests/test_host_runner.py` — `resolve_host_named` for every registry
  key; `HostNotConfigured` for `opencode`/`pi`; `run_blocking_json` schema-flag
  branching per capability; `cleanup_paths` unlinked on the codex path.
- `scripts/tests/test_config.py` — `advisor` block parse, defaults, and
  `ll.local.md` merge (arrays replace, nested deep-merge, `null` removes).
- `scripts/tests/test_advisor.py` (new) — `rank_model` normalizes through
  `resolve_model_alias`; unrankable → `None`; `check_floor` returns `violation`
  same-host, `advisory` cross-host, `unknown` on unrankable; `consult` contract
  against a mocked host runner; `--signal` required.
- `scripts/tests/test_cli_doctor.py` — advisor check warning path.
- `scripts/tests/test_fsm_evaluators.py` — `evaluate_llm_structured` behavior
  unchanged after the refactor (regression guard).

### Documentation

- `docs/reference/CLI.md` — `ll-advise`.
- `docs/reference/API.md` — `little_loops.advisor`, new `host_runner` exports.
- `docs/reference/HOST_COMPATIBILITY.md` — advisor host support matrix; explicit
  note that cross-host capability floors are **advisory, not enforced**.
- `.claude/CLAUDE.md` — add `/ll:advise` to the command list.

### Configuration

- `.ll/ll-config.json` — new optional `advisor` block (absent = disabled).

## Acceptance Criteria

1. `ll-advise --signal user_requested --question "..."` returns exit 0 and prints
   JSON with exactly the keys `recommendation`, `risks`, `confidence`,
   `dissent`, `signal`, `host`, `model`.
2. Omitting `--signal` exits non-zero with a usage error. No code path performs
   a consult without a recorded signal.
3. With `advisor.host` differing from `orchestration.host_cli`, the consult
   invokes the advisor host's binary and the ambient `LL_HOST_CLI` /
   `orchestration.host_cli` is unchanged after the call (asserted, not assumed).
4. `advisor.host: "opencode"` or `"pi"` produces a non-zero exit with a message
   naming the unwired host — no traceback, no partial output.
5. A verdict is parsed correctly on all three structured-output paths:
   claude-code inline `--json-schema`, codex `--output-schema` temp file, and
   prompt-and-parse tag fallback (mocked host runners).
6. The codex path unlinks every `HostInvocation.cleanup_paths` entry, including
   when the subprocess fails or times out.
7. A consult exceeding `advisor.timeout_seconds` terminates and exits non-zero
   with a timeout reason rather than hanging.
8. `check_floor("claude-code", "haiku", "claude-code", "opus")` returns
   `violation`; `ll-advise` refuses the consult. The same mismatch across hosts
   returns `advisory` and the consult proceeds with a warning on stderr.
9. `rank_model` returns the same rank for `"opus"` and its concrete ID from
   `MODEL_ALIASES`; an unknown/dated model returns `None` and `check_floor`
   returns `unknown` (warn, proceed) — never a silent pass.
10. `ll-doctor` reports advisor host reachability and emits a warning (not an
    error) when the floor is `advisory` or `unknown`; exit code is unaffected by
    an advisory-only finding.
11. `advisor` block round-trips through `BRConfig` and merges correctly from
    `.ll/ll.local.md` (arrays replace, nested deep-merge, `null` removes).
12. `advisor.host` values outside the registry enum fail schema validation.
13. `evaluate_llm_structured` behavior is unchanged after migrating onto
    `run_blocking_json` — existing FSM evaluator tests pass without edits.
14. Advisor consults are excluded from FSM resume/replay input hashing and are
    never cache-marked.
15. `python -m pytest scripts/tests/`, `ruff check scripts/`, and
    `python -m mypy scripts/little_loops/` all pass.

## Why not subagents / detached sessions?

- Subagents are **same-host, same-model-family** and lack the model-override +
  structured-verdict-back-into-transcript contract. The advisor's point is a
  *different, stronger, possibly different-provider* model.
- A detached session is fire-and-forget; the advisor is **synchronous and
  in-band** — the verdict must return before the primary continues.
- The consult must be signal-cited and (from Slice 2) budget-counted. Ad-hoc
  subagent spawns are neither.

Reuse the *transport*; the advisor is a thin accountable layer on top.

## Out of Scope (follow-up slices)

Each later slice has its own issue; this one blocks all three.

- **FEAT-3038 (Slice 2)** — wire `confidence_gate` (readiness score <
  `commands.confidence_gate.readiness_threshold`, currently 85) and `pre_done`
  (Stop hook on the final diff) to auto-consult; add `max_consults_per_task`
  plus the per-task counter that makes it enforceable.
- **FEAT-3039 (Slice 3)** — FSM stall escalation consuming `evaluate_diff_stall`
  / `evaluate_score_stall` verdicts (routed through the normal transition table
  — there is no `on_stall` key in the FSM schema today); an `advisor_consult`
  evaluator whose verdict is routable.
- **FEAT-3040 (Slice 4)** — log consults to `.ll/history.db` for `ll-ctx-stats`
  analytics.

Also unresolved and deferred:

- **Overlap with `/ll:go-no-go`.** That skill already *is* an adversarial
  second opinion. Decide in Slice 2 whether the advisor becomes go-no-go's
  different-model engine or stays a separate surface; do not ship both as
  competing "get a second opinion" entry points without a stated distinction.
- **Context assembly** — Slice 1 uses an explicit, caller-authored payload
  (`--context-file`), never an auto-slurp of the working tree.
- **Cross-host auth** — a `codex`/`gemini` advisor needs that host
  authenticated. Headless/cron runs may lack interactive auth; `ll-doctor`
  surfaces it and the consult fails soft.

## Impact

- **Priority**: P3 — a capability gap, not a defect. Nothing is broken without
  it; it unlocks the signal-gated escalation pattern the harness rules already
  argue for.
- **Effort**: Medium — the transport, config plumbing, and doctor-check patterns
  all exist and are copied, but three genuinely new pieces land here:
  per-call host resolution, the extracted `run_blocking_json` helper (which
  touches an FSM hot path), and the capability-rank table.
- **Risk**: Medium — refactoring `evaluate_llm_structured` onto a shared helper
  touches every `check_semantic` / `llm_structured` FSM state. Mitigated by
  keeping the refactor behavior-preserving and gated on existing evaluator
  tests. The advisor surface itself is additive and off by default.
- **Breaking Change**: No — `advisor` is absent by default; all existing
  `resolve_host()` call sites are untouched.

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — MR-1, self-evaluation bias.
- `docs/reference/HOST_COMPATIBILITY.md#orchestration-cli` — host abstraction.
- `docs/reference/API.md#little_loopshost_runner`

## Status

**Open** | Created: 2026-08-03 | Priority: P3
