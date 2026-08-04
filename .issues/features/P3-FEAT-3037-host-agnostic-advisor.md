---
id: FEAT-3037
title: Host-agnostic advisor
type: FEAT
parent: EPIC-3041
priority: P3
status: done
testable: true
discovered_date: 2026-08-03
verify_verdict: NON_VALID
blocks:
- 3038
- 3039
- 3040
labels:
- planning-hub
size: Very Large
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-04 — based on codebase analysis:_

- Line-reference corrections: `evaluate_llm_structured` spans `fsm/evaluators.py:1083-1268` (not 1083-1270); `config/core.py`'s `to_dict()` `"orchestration"` key starts at line 786, not "near line 782" (782 is inside the preceding `refine_status` block).
- `ll-action` / `ll-harness` (the cited CLI-shape precedent) both wrap their entire body in `cli_event_context(DEFAULT_DB_PATH, "ll-<name>", sys.argv[1:])`, dispatch to `cmd_<subcommand>(args) -> int` functions that return ints rather than raising or calling `sys.exit`, and use `with suppress(Exception):` around best-effort side-writes so a non-critical failure never changes the CLI's own exit code (`cli/action.py:262-277`) — `ll-advise`'s "fails soft, no traceback" requirement (AC #4, #7) should follow this same shape: catch host/timeout errors at the `cmd_*` boundary and return a nonzero int, never let them propagate.
- `CheckResult.severity: Literal["error", "informational"]` (`cli/doctor.py:54-73`) is the existing mechanism for "warn but don't fail" — `_exit_code_for` (`doctor.py:124-127`) only fails the overall exit code on `severity == "error" and status == "unsupported"`. `_advisor_check` should set `severity="informational"` for `advisory`/`unknown` floor results to satisfy AC #10 without new plumbing, mirroring the existing `_ADVISORY_CAPABILITIES` frozenset pattern (`doctor.py:95`).

_Added by `/ll:refine-issue` — 2026-08-04 — based on codebase analysis:_

- `evaluate_llm_structured`'s error-handling order (`fsm/evaluators.py:1083-1268`) is check-order-dependent and must be preserved exactly by `run_blocking_json()`: `subprocess.TimeoutExpired` → `FileNotFoundError` → `proc.returncode != 0` (reports stderr) → **then** the empty-stdout-with-exit-0 guard (`:1155-1164`, only reached when `returncode == 0`) → JSON envelope parse. A non-zero exit with empty stdout hits the returncode branch, not the empty-output branch — collapsing these checks or reordering them changes which error message a caller sees for the same failure, breaking AC #13's "behavior is unchanged" bar even though tests may not always catch message-text drift.
- `_structured_output_args` (`evaluators.py:159-172`) appends both `--json-schema <schema>` **and** `--no-session-persistence` when `invocation.capabilities.structured_output` is true — `run_blocking_json()` must carry over both flags, not just `--json-schema`.
- The JSON envelope extraction inside `evaluate_llm_structured` (`:1171-1235`) has a specific fallback priority `run_blocking_json()` needs to replicate: whole-string `json.loads`, then last-non-blank-line JSONL fallback on `JSONDecodeError`; `subtype == "error_max_structured_output_retries"` and legacy `is_error` are checked before result extraction; result extraction tries `structured_output` dict field first, then `result` field (dict as-is, or string re-parsed via `json.loads`, falling back to `_extract_tagged_structured_output()` only on that inner `JSONDecodeError` and re-raising only if the tag fallback also returns `None`), then a bare `"verdict" in envelope` fallback, else an error with a 300-char `raw_preview`.
- Evidence-coercion (`:1246-1248`) forces `verdict = "no"` specifically when `schema is None` (the *default* schema, not any caller-supplied schema) and evidence is blank and verdict isn't already `"error"` — this is schema-conditional behavior a shared `run_blocking_json()` must not apply unconditionally, since the advisor always supplies its own schema.
- `apply_host_cli_from_config()` (`host_runner.py:1612-1637`) has three early-return guards that make it a no-op: `os.environ.get("LL_HOST_CLI")` already truthy, `config.orchestration.host_cli` raising `AttributeError` (e.g. test doubles), or `host_cli` falsy. Its one production call site is `cli/doctor.py:1050`, immediately before `resolve_host()` — confirming the advisor's "must not call this" constraint is a plain grep-absence check against `advisor.py`/`cli/advise.py`, not a runtime behavior to special-case around.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-04 — based on codebase analysis:_

- `MODEL_ALIASES` (`host_runner.py:79-96`) has 4 entries, not 3: `fable → claude-fable-5`, `opus → claude-opus-5`, `sonnet → claude-sonnet-5`, `haiku → claude-haiku-4-5` (case-insensitive, whitespace-stripped lookup; unknown values pass through unchanged). `MODEL_RANKS`/`rank_model()` should account for `fable` alongside `opus`/`sonnet`/`haiku` if it's meant to be exhaustive over the alias table.
- `OrchestrationConfig.from_dict` (`config/orchestration.py:62-103`, the cited pattern for `AdvisorConfig.from_dict`) does no enum validation itself — `host_cli`/`request_path` are accepted as bare strings; enum enforcement lives entirely in `config-schema.json`. `AdvisorConfig.from_dict` should follow the same division of labor (schema validates `host`, the dataclass just reads it).
- `BRConfig.to_dict()` has no generic dataclass serializer — every block, including `orchestration`, is hand-rolled field-by-field (`config/core.py:786-803`, tracked as a known gap under BUG-3012). `AdvisorConfig`'s `to_dict()` entry will need the same manual field listing, not a shared helper.
- `.ll/ll.local.md` merge (arrays replace, nested deep-merge, `null` removes) is one shared, generic `deep_merge()` (`config/core.py:57-84`) applied once over the whole raw config in `hooks/session_start.py:145` — `advisor`'s merge behavior is automatic once the block is added to the raw config dict; no per-block merge code is needed.

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/__init__.py` — add `AdvisorConfig` to the
  `from little_loops.config.orchestration import (...)` block (lines 79-84) and
  to `__all__` (starts line 86); without this, `from little_loops.config import
  AdvisorConfig` fails even though `config/orchestration.py` defines it.
- `skills/configure/areas.md` — add `ll-advise` to the "All ll- commands"
  preset-tools list.
- `scripts/little_loops/init/writers.py` — add `"Bash(ll-advise:*)"` to
  `_LL_PERMISSIONS` (line ~61-115). **Test-enforced**: `ll-verify-cli-allowlist`
  (BUG-2764) fails `scripts/tests/test_verify_cli_allowlist.py::TestRun::test_clean_state_returns_zero`
  if any `pyproject.toml` `[project.scripts]` entry is missing from either this
  tuple or `areas.md` — adding the `ll-advise` entry point without these two
  updates breaks the local pytest suite (this repo's CI gate).

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

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_advise.py` (new) — the repo's own convention splits
  CLI-argparse-contract tests from core-logic tests into a separate file per
  CLI (`cli/harness.py` → `test_cli_harness.py`; `cli/action.py` →
  `test_action.py`). `test_advisor.py` should cover `consult`/`rank_model`/
  `check_floor` only; `main_advise(argv) -> int` contract tests (required-arg
  `SystemExit`, `--json` output via `capsys`) belong in this new file, modeled
  on `TestMainHarness` (`test_cli_harness.py:739`) and
  `TestMainAction.test_no_subcommand_exits_with_error` (`test_action.py:714`).
- **Correction**: the issue's own Codebase Research Findings (line 383) call
  the codex `--output-schema`/`cleanup_paths` branch "dormant" and imply it's
  untested. It is not — `scripts/tests/test_host_runner.py`'s `CodexRunner`
  test class already has real-tempfile coverage (`ENH-1530`):
  `test_build_blocking_json_json_schema_writes_temp_file` (~line 348),
  `test_build_blocking_json_json_schema_returns_cleanup_paths` (~line 361),
  `test_build_blocking_json_no_schema_cleanup_paths_empty` (~line 383). The
  gap is genuinely "no *production caller* exercises this path yet," not "no
  test exists" — `test_advisor.py`/`test_host_runner.py` additions should
  extend this existing block, not write it from scratch.
- `scripts/tests/test_cli_doctor.py` — model `_advisor_check`'s "informational
  severity never fails exit code" behavior after
  `test_exit_code_ignores_informational_unsupported` (~line 699), and use the
  save/clear/restore-`_CHECKS` isolation pattern from
  `test_register_check_appends_and_runs` (~line 682) /
  `test_mixed_severity_registered_check_affects_exit_code_via_main_doctor`
  (~line 715) if `_advisor_check` needs a fake-check test double.
- `scripts/tests/test_config.py` — mirror `TestOrchestrationConfig` (~line 3404)
  and `TestBRConfigOrchestration` (~line 3474) exactly for `AdvisorConfig`'s
  defaults/override/`.ll/ll.local.md`-merge coverage (AC #11); the `deep_merge`
  arrays-replace/nested-merge/`None`-removes cases are already tested generically
  starting ~line 3315 and don't need advisor-specific duplicates.

### Documentation

- `docs/reference/CLI.md` — `ll-advise`.
- `docs/reference/API.md` — `little_loops.advisor`, new `host_runner` exports.
- `docs/reference/HOST_COMPATIBILITY.md` — advisor host support matrix; explicit
  note that cross-host capability floors are **advisory, not enforced**.
- `.claude/CLAUDE.md` — add `/ll:advise` to the command list.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/writers.py` — `_LL_COMMANDS` (lines 137-199), the
  one-line-description tuple that renders the "little-loops" section of
  *consuming projects'* generated `CLAUDE.md`/`AGENTS.md`. Not test-enforced
  (unlike `_LL_PERMISSIONS` above), but omitting `ll-advise` here means every
  downstream project's generated docs silently miss it. Distinct from the
  `.claude/CLAUDE.md` item above, which is this repo's own file.

### Configuration

- `.ll/ll-config.json` — new optional `advisor` block (absent = disabled).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-04 — based on codebase analysis:_

- `resolve_host()` (`host_runner.py:1564`) already accepts an optional `env: dict[str, str] | None` param (defaults to `dict(os.environ)`) — `resolve_host_named(name)` is a trivial one-line wrapper (`resolve_host({"LL_HOST_CLI": name})`); no signature change to `resolve_host` itself is needed.
- `apply_host_cli_from_config()` has exactly one production call site today: `cli/doctor.py:1050`, immediately before `resolve_host()` inside `main_doctor`. The advisor's "must not call this" constraint is a plain grep check against `advisor.py`/`cli/advise.py`.
- `CodexRunner.build_blocking_json`'s `--output-schema <tmpfile>` / `cleanup_paths` branch (`host_runner.py:664-698`) is dormant in production: none of the 9 existing `build_blocking_json` call sites pass `json_schema=`, so `cleanup_paths` is always `()` today and no caller anywhere unlinks it (repo-wide grep for `cleanup_paths` returns only the dataclass field + this one assignment site). The advisor is the first caller that will exercise this path — AC #5/#6 are new *exercised* behavior, not a fix to something already running.
- `_structured_output_args` and `_extract_tagged_structured_output` (`fsm/evaluators.py:159`, `:111`) are both currently module-private to `evaluators.py` and unused elsewhere — relocating/exporting them for `run_blocking_json()` is a clean move, no other caller depends on their current location.
- Two other `build_blocking_json` call sites in `evaluators.py` (`evaluate_blind_comparator` ~line 1314, a third judge call ~line 1566) duplicate `evaluate_llm_structured`'s subprocess-and-parse loop but lack its tag-fallback safety net — an existing asymmetry worth deciding whether `run_blocking_json()` should also backfill for those two callers, or intentionally leave them un-migrated in this slice.
- `dispatch_anthropic_request` (`host_runner.py:1879-1936`) is SDK-based (calls `anthropic.Anthropic().messages.create()` directly, no subprocess) and returns `ActionResult`, not `EvaluationResult`/a verdict shape — it does not share reusable logic with the planned `run_blocking_json()` beyond living in the same module; treat them as two independent functions, not a refactor target for each other.
- No existing `@register_check` in `cli/doctor.py` pings a host CLI for reachability — the closest analog, `_capability_check_results()` (`doctor.py:98-113`), is deliberately *not* `@register_check`-registered because it needs the resolved `HostRunner` at call time (comment at `doctor.py:76-80`); `_advisor_check` will need to follow that same non-`@register_check` pattern (or resolve the advisor host inside a thin `@register_check` wrapper) rather than the standard zero-arg registered-check shape.
- `config-schema.json`'s `orchestration.host_cli` enum (`:1558-1562`) is a bare inline literal array, not a shared `$ref`'d definition — there is no existing precedent in the schema for two properties validating against one shared enum. `advisor.host`'s enum will need to duplicate the same 7-value array rather than reference it.
- Existing tests always patch `resolve_host` at the *calling* module (e.g. `little_loops.fsm.evaluators.resolve_host`, `little_loops.runner_spec.resolve_host`), never at `little_loops.host_runner.resolve_host` where it's defined — `test_advisor.py`'s mocking should patch `little_loops.advisor.resolve_host_named`/`resolve_host` (or wherever `advisor.py` imports it into its own namespace), matching this convention.

_Wiring pass added by `/ll:wire-issue`:_
- **Correction**: the `CodexRunner.build_blocking_json` `--output-schema`/`cleanup_paths` branch (line 437 above) is *not* untested, contrary to "dormant in production" implying no coverage — `scripts/tests/test_host_runner.py`'s `CodexRunner` test class already has real-tempfile tests for it (`ENH-1530`): `test_build_blocking_json_json_schema_writes_temp_file` (~line 348), `test_build_blocking_json_json_schema_returns_cleanup_paths` (~line 361), `test_build_blocking_json_no_schema_cleanup_paths_empty` (~line 383). "No production caller exercises this path" is accurate; "untested" is not — new tests should extend this block, not originate it.
- **Implementation constraint for AC #13**: `evaluate_llm_structured` does a module-level `import subprocess` in `fsm/evaluators.py:32` and calls `subprocess.run(...)` directly; `scripts/tests/test_fsm_evaluators.py` patches this at ~15 call sites via `patch("little_loops.fsm.evaluators.subprocess.run")`. `host_runner.py` currently has zero `subprocess.run`/`Popen` calls — `run_blocking_json()` will be the first. For `evaluate_llm_structured`'s existing test patches to keep working unmodified per AC #13, either `run_blocking_json()` must still bottom out at a patchable `evaluators.subprocess.run` call (i.e. `evaluators.py` keeps doing the actual `subprocess.run` and `run_blocking_json` takes the already-completed result), or the tests need updating to patch `host_runner.subprocess.run` instead — which would contradict "existing FSM evaluator tests pass without edits" as currently worded. Decide which explicitly during implementation.
- **AC #14 clarification** — no new exclusion code is needed. `derive_input_hash` (`cli/loop/_helpers.py:1395`) only seeds `context["input_hash"]` from FSM loop-launch input; `decide_cache_marking` (`cache_marking_oracle.py:76`) is only invoked from `dispatch_anthropic_request` (the SDK path), never from `build_blocking_json`/subprocess-transport code. `ll-advise`/`consult()` uses the subprocess transport exclusively, so it structurally never touches either mechanism — AC #14 is satisfied by construction. Worth a one-line comment in `advisor.py` noting this is deliberate, so a future FSM-integrated advisor state (Slice 3, FEAT-3039) doesn't accidentally wire a consult into either path.

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

## Verification Notes

_Added by `/ll:verify-issues` — 2026-08-04:_

Verdict: **NEEDS_UPDATE**. This is a pre-implementation proposal, so most content
describes code that doesn't exist yet (correctly, per grep: `advisor.py`,
`cli/advise.py`, `skills/advise/SKILL.md`, `test_advisor.py`,
`test_cli_advise.py`, the `ll-advise` pyproject entry, and `AdvisorConfig` in
`config/__init__.py` are all still absent). Of the 29 checkable claims about
**existing** code (line numbers, function signatures, test names), 27 matched
exactly; two issues found:

- **Factual error** (Codebase Research Findings, "Existing tests always patch
  `resolve_host` at the *calling* module... never at
  `little_loops.host_runner.resolve_host`"): false. `test_cli_doctor.py` and
  `test_cli_doctor_full.py` patch `little_loops.host_runner.resolve_host`
  directly at ~10 call sites (e.g. `test_cli_doctor.py:74,92,120,153,...`).
  Only `test_fsm_evaluators.py:933` patches at the caller namespace. Fix before
  using this claim to guide `test_advisor.py`'s mocking strategy.
- **Minor line-range drift**: `config/orchestration.py:62-103` cited for
  `OrchestrationConfig.from_dict` — the class starts at 62 (docstring/fields),
  but the `from_dict` method body itself is lines 96-103. Not blocking.
- **Dependency backlink inconsistency**: `blocks: [3038, 3039, 3040]` uses bare
  integers, unlike every other `blocks:` list in `.issues/` (which use full IDs,
  e.g. `'FEAT-2847'`). More substantively, none of FEAT-3038/3039/3040 declare
  `blocked_by: [FEAT-3037]` — the repo convention for a `blocks` reciprocal
  (confirmed via `link.py:190`'s `blocked_by`↔`blocks` reciprocal-field mapping,
  and via working examples like FEAT-1808→FEAT-1809/`blocked_by`). Instead they
  each declare `depends_on: [3037]`, a separate, non-reciprocal field. Consider
  adding `blocked_by: [FEAT-3037]` to FEAT-3038/3039/3040 (or switching
  FEAT-3037's `blocks` entries to full-ID form) so `ll-issues show` renders the
  dependency consistently with the rest of the backlog.

Everything else — the extensive line-number citations against
`host_runner.py`, `fsm/evaluators.py`, `config/core.py`,
`config/orchestration.py`, `hooks/session_start.py`, `cli/doctor.py`,
`config-schema.json`, `init/writers.py`, and the various test files — checked
out exactly. `MODEL_ALIASES` has the claimed 4 entries; `apply_host_cli_from_config`'s
three guards and sole call site (`doctor.py:1050`) are accurate;
`cleanup_paths` is confirmed genuinely unexercised by any production caller
today.

No active required decision-log rules to check (decisions log has no entries).
Dependency refs to FEAT-3038/3039/3040 all resolve to real, open issues.

## Related Key Documentation

- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — MR-1, self-evaluation bias.
- `docs/reference/HOST_COMPATIBILITY.md#orchestration-cli` — host abstraction.
- `docs/reference/API.md#little_loopshost_runner`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-08-04
- **Reason**: Issue scored Very Large (11/11) on `ll-issues size` and covers
  three architecturally separable concerns.

### Decomposed Into
- FEAT-3042: Advisor transport - shared run_blocking_json helper
- FEAT-3043: Advisor configuration - AdvisorConfig block
- FEAT-3044: Advisor core - ll-advise CLI, capability floor, and ll-doctor check

## Status

**Done** | Created: 2026-08-03 | Priority: P3


## Session Log
- `/ll:issue-size-review` - 2026-08-04T20:47:21 - `b57cebec-46d2-436b-b650-9a1afa94ec18.jsonl`
- `/ll:verify-issues` - 2026-08-04T20:42:53 - `97441ea7-5d7e-47f5-8c5d-364991183913.jsonl`
- `/ll:refine-issue` - 2026-08-04T20:37:26 - `650434bc-d789-4e46-80af-5ca27b0d0f91.jsonl`
- `/ll:verify-issues` - 2026-08-04T20:33:27 - `305bc37e-8d57-4c74-8cd3-5f3bd246d78c.jsonl`
- `/ll:wire-issue` - 2026-08-04T20:29:14 - `9a232634-c75e-4ea0-9ef9-0d29e428f8df.jsonl`
- `/ll:refine-issue` - 2026-08-04T20:18:49 - `de4d07bc-db46-48c5-9174-010f6f16478c.jsonl`
