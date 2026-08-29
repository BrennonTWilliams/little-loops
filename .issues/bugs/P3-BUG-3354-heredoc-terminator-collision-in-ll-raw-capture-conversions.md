---
id: BUG-3354
type: BUG
title: Heredoc terminator collision in LL_RAW capture conversions
priority: P3
status: open
discovered_by: manual-review
discovered_date: '2026-08-28'
captured_at: '2026-08-28T00:00:00Z'
parent: EPIC-3336
relates_to:
- BUG-3341
- ENH-3347
verify_verdict: PROPOSAL_UNSOUND
confidence_score: 85
outcome_confidence: 42
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 0
---

# BUG-3354: Heredoc terminator collision in LL_RAW capture conversions

## Summary

The BUG-3341 conversions render `${captured.*.output}` inside
`cat > ... << 'LL_RAW_9F3C1A7E_EOF'` heredocs. The terminator
`LL_RAW_9F3C1A7E_EOF` is a **fixed, public string** (checked into this repo's
loop YAMLs). A captured output containing that exact line terminates the
heredoc early, and everything after it in the captured payload executes as
shell — the same class of injection BUG-3341 fixed, surviving through the fix's
own delimiter.

Found during ENH-3347 review (2026-08-28). ENH-3347's case 2 covers `"""` +
newline payloads only; its scope boundary ("representative, not exhaustive")
explicitly does not cover terminator collision, and no other issue tracks it.

## Current Behavior

Every converted class-B site uses the same literal terminator, e.g.
`scripts/little_loops/loops/loop-router.yaml:208-210`:

```bash
cat > "${context.run_dir}/parse_project_score-project_score.txt" << 'LL_RAW_9F3C1A7E_EOF'
${captured.project_score.output}
LL_RAW_9F3C1A7E_EOF
```

Captured output is LLM-produced text. An output containing a line that is
exactly `LL_RAW_9F3C1A7E_EOF` (plausible adversarially, since the marker is
public; conceivable accidentally if a loop ever captures output that quotes a
loop YAML — e.g. a loop-authoring or loop-auditing state) closes the heredoc at
that line, and the remainder of the payload is parsed as shell commands.

## Expected Behavior

Captured-output rendering is injection-proof regardless of payload content —
no fixed delimiter whose presence in the payload changes parsing. Candidate
directions considered:

1. **Per-render unique terminator**: interpolation-time generated marker
   (e.g. UUID-suffixed) guaranteed absent from the payload — requires engine
   support since actions are static YAML text.
2. **Engine-level safe binding**: a first-class FSM mechanism that writes
   captured output to a file *before* shell rendering (sidestepping heredocs
   entirely), with the action referencing the file path.
3. **Detect-and-refuse**: interpolation fails loudly if the rendered payload
   contains the terminator line — turns silent injection into a hard error.

**Decided 2026-08-28 (unparented-issues review): this issue's scope is
option 3** — interpolation fails loudly (hard error, run halts at that state)
when a rendered payload contains a line equal to the heredoc terminator of the
site being rendered. That turns silent arbitrary shell execution into a
deterministic, attributable failure at Small effort with no touch to the ~145
converted sites. Options 1/2 remain the candidate structural fix; file a
follow-up (child of EPIC-3336) only if the hard-error path fires in practice.

## Steps to Reproduce

1. Run a loop through any of the converted class-B heredoc sites named in
   this issue — e.g. `loop-router.yaml`'s `parse_project_score` state
   (`scripts/little_loops/loops/loop-router.yaml:208-210`), which renders
   `${captured.project_score.output}` inside
   `cat > "..." << 'LL_RAW_9F3C1A7E_EOF'`.
2. Arrange for the state whose output is captured beforehand to produce a
   payload containing a line that is exactly `LL_RAW_9F3C1A7E_EOF` (the
   marker is public — checked into this repo's loop YAMLs — so this is
   directly reproducible by hand: feed a captured-output-producing state a
   response that includes that exact line, followed by arbitrary shell
   commands on subsequent lines), then let the FSM proceed to
   `parse_project_score`.
3. Observe: `interpolate()` (`scripts/little_loops/fsm/interpolation.py:274`)
   substitutes the payload into the heredoc body unexamined, and the shell
   runner (`bash -c`) closes the heredoc at the first line matching the
   marker rather than at the real trailing `LL_RAW_9F3C1A7E_EOF` line the
   YAML declares — every payload line after the injected marker line is then
   parsed and executed as shell, not written to the intended capture file.

## Root Cause

- **File**: `scripts/little_loops/fsm/interpolation.py`
- **Anchor**: `in function interpolate()` (`interpolation.py:274-341`)
- **Cause**: `interpolate()` does whole-template substitution —
  `VARIABLE_PATTERN.sub(replace_var, result)` (`:336`) — over the entire
  multi-line `state.action` string in one pass. A heredoc terminator line
  (e.g. `LL_RAW_9F3C1A7E_EOF`) is literal YAML text, not a `${...}` token, so
  it passes through the substitution untouched and unexamined. The function
  returns the fully rendered bash body with no check that a substituted
  `${captured.*.output}` value's content contains a line equal to that
  terminator. The caller (`FSMExecutor._run_action()`, `executor.py:2171`)
  hands the returned string straight to the shell runner — a captured payload
  line that reads exactly `LL_RAW_9F3C1A7E_EOF` (or `LL_STDERR_EOF` at the
  widened sites) closes the heredoc early, and every subsequent payload line
  executes as shell.

## Motivation

The BUG-3341 fix converted ~145 sites to this pattern; all share one public
delimiter. The failure mode is silent arbitrary shell execution inside
automation runs. Likelihood is low (requires the exact marker line in captured
output) but the marker's public visibility makes it a standing adversarial
target, and loops that read/quote loop YAMLs raise the accidental odds above
zero.

## Program Design

### Types

**Decided 2026-08-29 (post-verify redesign)**: one new exception type in
`interpolation.py`:

- `class HeredocCollisionError(InterpolationError)` — raised only when a
  substituted value's content collides with the enclosing heredoc's
  terminator line (the Decision Rules gate below). Nothing else may raise
  it.

The subclass is the load-bearing design element. The prior plan — raise the
existing `InterpolationError` and carve *that type* out of `on_error`
routing — was rejected as PROPOSAL_UNSOUND by `/ll:verify-issues`: base
`InterpolationError` is already raised for unrelated, legitimate reasons
(missing variable, malformed `:default=`, bad `namespace.path`), an existing
test (`scripts/tests/test_fsm_executor.py:4337`,
`test_interpolation_error_routes_to_on_error_when_set`) locks in
on_error-catches-`InterpolationError` behavior, and a type-based carve-out
would silently reverse `on_error` semantics across every loop YAML in the
repo, contradicting this issue's "Low risk / no breaking change" claim. A
failure-mode-scoped subclass changes routing for the collision case only;
all existing `InterpolationError` behavior (including `:4337`) is untouched.

Subclassing `InterpolationError` (rather than a sibling type) is deliberate:
`run()`'s existing typed handler (`executor.py:876-883`) remains a backstop
if any path misses the new dedicated handler, and external callers catching
`InterpolationError` keep working.

### Signatures

No changed public signatures. The function that houses the guard keeps its
signature:

- `interpolate(template: str, ctx: InterpolationContext) -> str`

`interpolation.py:274` — the one function in the call chain that holds both
the raw `template` (carrying each heredoc's literal opener and marker
declaration) and the fully substituted `result` string, before either
reaches a shell runner. Whatever function performs the collision check, it
needs both of these values at once; `interpolate()` is where they already
coexist. It raises `HeredocCollisionError` for the collision case (and base
`InterpolationError` for all existing cases, unchanged).

### Call Path

`FSMExecutor._run_action` (`executor.py:2171`) -> `interpolate()`
(`interpolation.py:274`) -> shell runner (`bash -c`).

**Correction (remediation pass, 2026-08-29)**: `_execute_with_baseline`
(`executor.py:3132-3172`) contains two `interpolate()` calls against
`state.action`, not a single "second call site," and they have different
propagation mechanics:
- `executor.py:3160` (`action_text = interpolate(state.action, ctx)`, used
  only to extract `baseline_skill_name` via `_extract_skill_from_action`)
  runs **synchronously in the calling thread**, four lines before
  `with ThreadPoolExecutor(max_workers=2) as pool:` opens at `:3164`. An
  `InterpolationError` here surfaces as an ordinary synchronous exception out
  of `_execute_with_baseline` (itself called synchronously from
  `_execute_state` at `:1914`) — it never touches `harness_future`.
- The call that actually runs inside a worker thread and propagates via
  `harness_future.result()` (`:3171`) is the one inside `_run_action`
  (`:2171`), reached via `pool.submit(self._run_action, ...)` (`:3165-3167`)
  — i.e. the same primary call site already named above, not a distinct one.

**A guard inside `interpolate()` alone does not reach the decided hard-halt
behavior at either propagation path**, because neither of `interpolate()`'s
two actual callers for a converted heredoc site routes an `InterpolationError`
to `FSMExecutor.run()`'s top-level handler (`:876-883`) uniformly:
- `_run_action_or_route` (`executor.py:3313-3337`) — the immediate caller of
  `_run_action` for every standard shell/prompt state, invoked from `run()`
  at `:1918` and `:1849` — wraps the call in `except Exception as exc: if
  state.on_error: ...; return None, interpolate(state.on_error, ctx)`. This
  bare `except Exception` has no `InterpolationError` carve-out: whenever
  `state.on_error` is set, the new error is silently rerouted to that
  on_error target instead of propagating to `:876-883`. Every heredoc site
  this issue names sets `on_error` (`loop-router.yaml`'s `parse_project_score`
  — `on_error: finalize_failed` at `:236`; `autodev.yaml`'s `init` —
  `on_error: finalize_done`; `prompt-across-issues.yaml`'s `init` —
  `on_error: diagnose_error`; `recursive-refine.yaml`'s `parse_input` —
  `on_error: diagnose`; `rlhf-animated-svg.yaml`'s `validate_input` —
  `on_error: input_missing`; `refine-to-ready-issue.yaml`'s
  `write_failure_evidence` — `on_error: classify_terminal`), so the fix as
  currently scoped (guard inside `interpolate()`, no `executor.py` change)
  would silently reroute the run at each of these instead of halting it.
- `_flush_pending_shell_state` (`executor.py:2871-2897`, reached from `:574`
  and `:633` for the BUG-1226 timeout-flush race) wraps
  `self._run_action(state.action, state, ctx)` in a bare
  `try/except Exception: pass` — a total, silent swallow with no rerouting
  and no signal at all, worse than the on_error case.

This means Implementation Step 1's original "should not need new plumbing
in `executor.py`" does not hold: `_run_action_or_route` and
`_flush_pending_shell_state` both need a carve-out (bypass on_error routing
/ bypass the swallow) for the decided hard-halt behavior to actually occur
at the sites this issue names. **Resolved (2026-08-29 redesign): the
carve-out is keyed on `HeredocCollisionError` only — never on base
`InterpolationError`** (see Program Design → Types for why a type-based
carve-out on the base class was rejected as PROPOSAL_UNSOUND). Both sites
re-raise `HeredocCollisionError` before their generic `except Exception`
handling; base `InterpolationError` continues to route to `on_error` /
be swallowed exactly as today.

### Decision Rules

- **Gate condition**: the fully rendered action body contains a line, within
  a heredoc body region, that is exactly equal to that heredoc's own
  terminator marker.
- **Heredoc region**: opened by a redirect matching quoted (`<<'MARKER'`,
  `<<-"MARKER"`) or unquoted (`<<MARKER`) forms, closed by the first
  subsequent line whose content (stripped of leading tabs only for a `<<-`
  opener; unstripped for plain `<<`) equals MARKER. This is the same
  open/close shape already implemented twice in this codebase as static
  scanners — see Integration Map → Conventions in Force.
- **Marker scope**: keyed on the site's own terminator string, whatever the
  literal text is — not hardcoded to an `LL_RAW_*` prefix. This is required
  by the Scope Widening note below (`LL_STDERR_EOF` sites must be caught by
  the same mechanism).
- **Routing carve-out scope**: keyed on the `HeredocCollisionError` subclass
  only. Base `InterpolationError` routing/swallow behavior in
  `_run_action_or_route`, `_flush_pending_shell_state`, and every other
  broad handler is byte-for-byte unchanged;
  `test_fsm_executor.py::test_interpolation_error_routes_to_on_error_when_set`
  (`:4337`) must pass unmodified.
- **Escape hatch**: none. Closed decision, not deferred — Option 3 as decided
  (2026-08-28) is an unconditional hard error with no per-site suppression
  flag; unlike MR-9/MR-11's `_ok: true` opt-outs, this issue deliberately
  introduces no equivalent. If practice later surfaces a legitimate false
  positive requiring one, that is new scope for a follow-up issue (child of
  EPIC-3336, per the Expected Behavior section's follow-up clause) — it is
  not a gap in this issue's implementation-readiness.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- `interpolate()` has at least 13 other call sites beyond the two analyzed
  above (executor.py:2171 and :3160), each wrapped in a broad
  `except InterpolationError:` handler built for a different purpose —
  silently falling back when a variable/path is simply missing, not for
  heredoc payloads: `evaluators.py:856`, `:866`, `:1759`, `:1972`, `:1985`,
  `:2005` (all interpolating small variable/path/prompt templates, e.g.
  `${{{key}}}`, `history_file`, `prompt` — none of which carry heredoc
  syntax today) and `executor.py:908` (`state.loop`), `:1807`/`:1888` (an
  `on_error`/`on_no` route target), `:2684` (`state.evaluate.source`, which
  falls back to `raw_output` on any `InterpolationError`), plus the
  `on_error`-reroute catch documented in the Call Path correction above
  (`:3336`). Because the decided guard lives inside `interpolate()` itself —
  applying to every template it is asked to render, not only `state.action`
  — this issue has not audited whether any of these pre-existing catches
  would silently absorb a terminator-collision `InterpolationError` as an
  ordinary missing-variable fallback if a future site ever passes a
  heredoc-shaped string through one of these other templates. None of the
  templates these call sites currently interpolate contain heredoc syntax as
  of this pass, so no fix is required now — but an implementer changing
  which templates route through these calls should re-check this list.
  (2026-08-29 redesign note: since `HeredocCollisionError` subclasses
  `InterpolationError`, these broad catches *would* absorb it if a
  heredoc-shaped template ever flowed through them — the conclusion is
  unchanged because none does today, but the re-check obligation now applies
  to the subclass specifically.)

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **Clarifying the Decision Rules' Gate condition/Heredoc region ambiguity
  (remediation pass, 2026-08-29)**: the Gate condition's wording ("the fully
  rendered action body contains a line, within a heredoc body region...")
  is ambiguous about whether region boundaries are computed against the RAW
  (pre-substitution) `template` or the RENDERED (post-substitution) `result`
  string — and applying the stated close rule ("closed by the first
  subsequent line ... equal to MARKER") to the rendered body is
  self-defeating: a scan over rendered text would stop at the very first
  line matching MARKER, which is exactly the attacker-controlled collision
  line, and treat it as the legitimate close — reproducing in the detector
  the same first-match-wins ambiguity that causes the vulnerability, so it
  could never observe the violation it exists to catch. The required
  reading: region boundaries (open redirect, close-line position) are
  computed from the RAW template, where every terminator declaration is
  literal YAML text with no attacker-controlled content and no ambiguity;
  the check then examines only the SUBSTITUTED VALUE that lands at each
  `${...}` token position falling inside that raw-computed region, testing
  whether any of its lines equals the region's MARKER — it does not re-scan
  the fully rendered body with the raw close rule. `interpolate()` already
  holds both `template` and `result` per the existing Signatures note above,
  so both are available to whichever function houses this check.
- **Correcting the "at least 13 other call sites... each wrapped in a broad
  except InterpolationError: handler" claim above (remediation pass,
  2026-08-29)**: verified false for two of the cited sites.
  `executor.py:1807` (`return interpolate(state.on_error, ctx)`) sits
  *inside* the body of the `except (FileNotFoundError, ValueError,
  InterpolationError):` block it is attributed to (`Try` node spans
  1803-1808, confirmed by AST parse) — a new `InterpolationError` raised by
  that specific call is not caught by the handler it executes inside of
  (Python does not re-enter a handler for exceptions raised within it); it
  propagates normally. `executor.py:1888` (`return interpolate(state.on_error,
  ctx)`, inside the `if state.next:` / `result.exit_code < 0` branch) has no
  enclosing `try`/`except` at all — confirmed by an AST scan finding zero
  `Try` nodes spanning that line. Both propagate uncaught up through
  `_execute_state` to `run()`'s top-level `except InterpolationError` handler
  (`executor.py:876-883`) — i.e. these two sites already reach the intended
  halt path today and are not part of the unaudited-swallow risk the
  surrounding paragraph describes.
- **Correcting the "at least 13" call-site count itself (remediation pass,
  2026-08-29)**: a full count finds 33 total `interpolate()` call sites in
  `executor.py` (31 beyond the two already analyzed at `:2171`/`:3160`) plus
  10 in `evaluators.py`, for 41 un-analyzed call sites, not ~13. Two
  additional silent-swallow sites exist in the same failure class as
  `_run_action_or_route`/`_flush_pending_shell_state` but were not
  previously inventoried: `executor.py:1338`
  (`excluded.add(interpolate(raw_excl, ctx))` under a bare `except Exception:
  pass`) and `executor.py:1345` (`resolved = interpolate(raw_path, ctx)`
  under `except Exception: continue`), both in the repeated-failure
  circuit-breaker path-resolution logic (`self.fsm.circuit.repeated_failure`
  exclude/progress path resolution). Neither currently interpolates a
  heredoc-shaped template, so — consistent with the original note's
  conclusion — no fix is required now, but this list (not the "~13" figure)
  is the one an implementer should re-check before routing new templates
  through any of these calls.

## Implementation Steps

1. **Guard in `interpolation.py`**: add
   `class HeredocCollisionError(InterpolationError)` (see Program Design →
   Types). `interpolate()` raises it — instead of returning the colliding
   string — when a substituted value's content contains a line equal to the
   enclosing heredoc's terminator, per Decision Rules (regions computed from
   the RAW template; only substituted values landing inside a region are
   tested). Its message names the state (if available via ctx) and the
   literal terminator marker, and uses no "missing"/"undefined" variable
   language.
2. **Executor carve-outs, subclass-scoped**:
   - `_run_action_or_route` (`executor.py:3313-3337`): re-raise
     `HeredocCollisionError` before the `if state.on_error:` reroute (e.g.
     an `except HeredocCollisionError: raise` clause ahead of the bare
     `except Exception`), so it propagates to `run()`'s top-level handling.
   - `_flush_pending_shell_state` (`executor.py:2871-2897`): re-raise
     `HeredocCollisionError` instead of the silent `except Exception: pass`
     swallow.
   - Base `InterpolationError` behavior is unchanged at both sites;
     `test_fsm_executor.py:4337`
     (`test_interpolation_error_routes_to_on_error_when_set`) passes
     unmodified.
3. **Dedicated halt message (Step-2 fork resolved as option (a))**: add an
   `except HeredocCollisionError` clause in `FSMExecutor.run()` *ahead of*
   the existing `except InterpolationError` clause (`executor.py:876-883`),
   producing a `_finish("error", ...)` whose message names the state and the
   terminator marker and does **not** carry the "Missing context variable in
   state" prefix (that prefix stays as-is for base `InterpolationError`). A
   test asserts the composed run-result error string contains the literal
   terminator and does not contain "Missing context variable".
4. `scripts/tests/test_builtin_loops.py::TestEnh3347RouterInjection` (from
   `:18786`) already runs the `interpolate(action, ctx)` + `bash -c` harness
   against `loop-router.yaml`'s real converted actions, including a BUG-3341
   red/green pair (`test_triple_quote_capture_with_newline_no_longer_crashes`,
   `:18842`) with the exact shape a new terminator-collision test would
   follow: red demonstrates today's silent execution of a payload line equal
   to `LL_RAW_9F3C1A7E_EOF`, green demonstrates `interpolate()` raising before
   `bash -c` ever runs.
5. `scripts/tests/test_fsm_interpolation.py` holds `interpolate()`'s
   unit-level contract; the new raise path needs direct unit coverage there,
   not only the end-to-end bash harness in `test_builtin_loops.py`.
6. `python -m pytest scripts/tests/test_fsm_interpolation.py
   scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_executor.py
   -v` passes, including whatever new test(s) cover this gate and the
   unmodified `:4337` on_error-routing test.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add a collision-test fixture against the `LL_INPUT_EOF` family (e.g.
  `scripts/little_loops/loops/autodev.yaml:56-58`) alongside the
  `LL_RAW_*_EOF`/`LL_STDERR_EOF` cases — see Integration Map → Tests for the
  four sites and why this family is the most attacker-controlled of the
  three.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **Resolving the Call Path correction's open fork (remediation pass,
  2026-08-29)**: the fork is resolved toward closing the routing gap, not
  narrowing Expected Behavior — Expected Behavior's "hard error, run halts
  at that state" stands unchanged. Concrete, checkable bar: for each of the
  six heredoc sites this issue names (`loop-router.yaml` `parse_project_score`,
  `autodev.yaml` `init`, `prompt-across-issues.yaml` `init`,
  `recursive-refine.yaml` `parse_input`, `rlhf-animated-svg.yaml`
  `validate_input`, `refine-to-ready-issue.yaml` `write_failure_evidence`),
  an `InterpolationError` raised by the new guard for a colliding action
  must reach `FSMExecutor.run()`'s top-level halt handler
  (`executor.py:876-883`) and produce a `_finish("error", ...)` outcome —
  not a reroute to `state.on_error` and not a silent drop. That requires an
  explicit carve-out — **scoped to the `HeredocCollisionError` subclass, not
  base `InterpolationError` (2026-08-29 redesign; see Program Design →
  Types)** — in both call paths the Call Path correction identified as
  swallowing it: `_run_action_or_route` (`executor.py:3313-3337`)'s bare
  `except Exception as exc:` must let `HeredocCollisionError` propagate past
  the `if state.on_error:` reroute instead of being caught by it, and
  `_flush_pending_shell_state` (`executor.py:2871-2897`)'s bare
  `except Exception: pass` must do the same instead of swallowing it. A
  test exercising each of the six named
  sites (or a representative subset reachable via the existing
  `TestEnh3347RouterInjection` harness) with a colliding payload must assert
  the run ends in `_finish("error", ...)`, never at the site's `on_error`
  target and never with the shell state silently dropped.
- **Correction to Step 2's message-wording bar (remediation pass,
  2026-08-29)**: verified at `executor.py:876-882` — the operator-facing
  string is composed as `f"Missing context variable in state
  '{self.current_state}': {exc}. Run with: ll-loop run..."`; the literal
  prefix `"Missing context variable in state"` is not itself touched by this
  issue (Step 2 says so explicitly), so it appears verbatim ahead of `{exc}`
  for every terminator-collision halt regardless of what the inner
  `InterpolationError` message says. A unit test asserting only that the
  raised `InterpolationError`'s own message contains the terminator string
  and omits "missing" does not close this gap: that composed prefix still
  reads "Missing context variable" to the operator. Closing it requires
  either (a) a distinct halt-message path for this guard that bypasses the
  `:880-881` prefix, or (b) accepting the prefix as a known, unresolved
  wording wart and scoping Step 2's AC to the inner exception message only.
  **Resolved (2026-08-29 redesign): option (a)** — the dedicated
  `except HeredocCollisionError` clause in `run()` (Implementation Step 3)
  is that distinct halt-message path; the `:880-881` prefix is untouched and
  continues to apply to base `InterpolationError` only.

## Scope Boundaries

**In scope:** the delimiter-collision failure mode of the `LL_RAW_*_EOF`
heredoc pattern across converted sites; a behavioral test demonstrating the
break; the option-3 detect-and-refuse guard (decided above).

**Scope widening (2026-08-28, refine-to-ready-issue review):** the same
collision class exists under a *second* fixed marker, `LL_STDERR_EOF` —
e.g. `refine-to-ready-issue.yaml`'s `write_failure_evidence` uses four
`cat <<'LL_STDERR_EOF'` data-sink blocks carrying genuinely untrusted
payloads (`${captured.*.stderr?}`, `${prev.output?}`). The option-3 guard
must key on the *site's own terminator line*, whatever the marker string,
not on the `LL_RAW_*` prefix specifically.

**Out of scope:** options 1/2 (per-render unique terminator; engine-level safe
binding) — the structural fix, deferred to a follow-up if ever needed;
re-litigating the BUG-3341 conversion pattern itself; ENH-3347's four
behavioral cases; non-captured interpolation classes (BUG-3339/3340
territory).

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/interpolation.py` — houses `interpolate()`
  (`:274`), the only function in the call chain holding both the raw
  template (with its literal heredoc terminator declarations) and the fully
  rendered output before either reaches a shell runner.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/fsm/executor.py:2171` — `FSMExecutor._run_action()`,
  the primary call site (`action = interpolate(action_template, ctx)`), used
  for every shell/prompt action.
- `scripts/little_loops/fsm/executor.py:3160` —
  `FSMExecutor._execute_with_baseline()`, a second call site that runs
  `interpolate()` inside a `ThreadPoolExecutor` worker; an `InterpolationError`
  raised there propagates correctly via `harness_future.result()` (`:3171`).
  > Correction (remediation pass, 2026-08-29) — this call at `:3160`
  > actually runs synchronously in the calling thread, before the
  > `ThreadPoolExecutor` block opens at `:3164`; see Program Design → Call
  > Path correction above for the corrected propagation mechanics.
- `scripts/little_loops/fsm/executor.py:876-885` — `FSMExecutor.run()`'s
  top-level `except InterpolationError` / catch-all `except Exception`, the
  existing halt mechanism Option 3 relies on (see Program Design → Decision
  Rules and Implementation Steps above).
- `scripts/little_loops/fsm/validation/shell_safety.py` — imports
  `interpolation.py` (`InterpolationError`, `parse_interpolation_suffixes`);
  its MR-11 check (`_find_unsafe_context_interpolations`, `:149-198`) already
  walks `state.action` line-by-line tracking a `heredoc_marker` via
  `_QUOTED_HEREDOC_START_RE = re.compile(r"<<-?\s*['\"](\w+)['\"]")` (`:42`).
- `scripts/little_loops/fsm/interp_sweep.py` — a second, independent
  heredoc-marker walker (`:140-165`) with a more general opener regex,
  `_HEREDOC_OPEN_RE = re.compile(r"(?<!<)<<(?!<)(-)?\s*(?:['\"](\w+)['\"]|(\w+))")`
  (`:37`, corrected from `:35` — remediation pass, 2026-08-29), which also
  matches unquoted `<<EOF` and distinguishes `<<-`'s tab-only terminator
  indent from plain `<<`.
- `scripts/little_loops/fsm/types.py` — imports `interpolation.py`; import
  edge only, not yet inspected for further relevance.
- `scripts/little_loops/fsm/executor.py:3313-3337` —
  `FSMExecutor._run_action_or_route()`, the immediate caller of `_run_action`
  for every standard shell/prompt state; its bare `except Exception` reroutes
  to `state.on_error` when set, which would silently absorb the new guard's
  `InterpolationError` at every converted heredoc site this issue names
  (each one sets `on_error`) instead of propagating to the halt handler at
  `:876-883`. See Program Design → Call Path correction above.
- `scripts/little_loops/fsm/executor.py:2871-2897` —
  `FSMExecutor._flush_pending_shell_state()` (reached from `:574`/`:633` for
  the BUG-1226 timeout-flush race), whose bare `try/except Exception: pass`
  around `self._run_action(...)` would silently and totally swallow the new
  guard's `InterpolationError` with no signal at all. See Program Design →
  Call Path correction above.

### Conventions in Force

- Heredoc-marker line-tracking (open on `<<[-]['"]MARKER['"]`/`<<[-]MARKER`,
  close on the first line whose stripped content equals MARKER) is already
  implemented twice in this codebase as static, pre-execution text scanners
  — `shell_safety.py`'s MR-11 check and `interp_sweep.py`'s A/B/C classifier
  — establishing the line-walk shape as the convention for this problem
  class. Neither existing implementation runs against a *rendered*
  (post-interpolation) string; both scan the raw YAML action text only, so
  this issue's runtime guard is the first of its kind rather than a copy of
  either.
- `InterpolationError` is the established exception type for every hard-
  failure path already in `interpolation.py` and is the type
  `FSMExecutor.run()`'s top-level handler already expects. This issue's
  guard raises the new `HeredocCollisionError` subclass (see Program Design
  → Types) so the collision case is distinguishable from missing-variable
  failures in routing decisions while still inheriting that handler as a
  backstop.

### Tests

- `scripts/tests/test_builtin_loops.py::TestEnh3347RouterInjection`
  (`:18786` onward) — end-to-end `interpolate()` + `bash -c` harness against
  `loop-router.yaml`'s real converted actions; `:18842`'s
  `test_triple_quote_capture_with_newline_no_longer_crashes` is the closest
  sibling (same BUG-3341 lineage) as a shape reference, not a file to edit.
- `scripts/tests/test_fsm_interpolation.py` — unit-level coverage for
  `interpolate()` (`TestInterpolate`, `TestSafeInterpolation`,
  `TestShellSuffix`, etc.); the guard's raise-vs-pass-through contract
  belongs here too.

_Wiring pass added by `/ll:wire-issue`:_
- A third fixed-terminator family exists beyond the two named in Scope
  Widening: `<<'LL_INPUT_EOF'` at `scripts/little_loops/loops/autodev.yaml:56-58`,
  `prompt-across-issues.yaml:59-61`, `recursive-refine.yaml:61-63`, and
  `rlhf-animated-svg.yaml:63-65` — each renders `${context.input}` (raw
  CLI-supplied user text, not LLM output) inside the heredoc body. This is
  the most directly attacker-controlled of the three families (a user can
  type the terminator line verbatim as CLI input, no LLM cooperation
  needed). The guard's marker-agnostic Decision Rule already covers it with
  no additional code change, but the new collision test suite should
  include at least one `LL_INPUT_EOF` fixture (in addition to the
  `LL_RAW_*_EOF`/`LL_STDERR_EOF` cases already implied by Scope Widening) to
  prove the marker-agnostic guarantee holds, not just assume it. Verified:
  `grep -rn "<<[-]\?['\"]" scripts/little_loops/loops/*.yaml` found no other
  fixed-terminator families carrying dynamic content — `PLANNING_PROMPT_EOF`
  (`rn-plan.yaml:45-57`) wraps only static guidance text with no
  interpolated tokens, so it is out of scope.

### Documentation

`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` MR-11 (this repo's own
CLAUDE.md-referenced, authoritative rule table for shell/heredoc-safety in
loop YAMLs) already documents "quoted heredoc (`<<'EOF'`)" as a *recommended
safe position* for interpolating untrusted `${context.*}` values
(`HARNESS_OPTIMIZATION_GUIDE.md:104`), but says nothing about the terminator
itself colliding with payload content — this issue's failure mode is
adjacent to, and not contradicted by, that guidance. No update is required
for implementation-readiness of this issue, but once Option 3 lands, MR-11's
row (or the guide's narrative text) is the natural place for a one-line
addendum noting that the hard-error guard now backstops this collision case
engine-wide; left as an operator follow-up, not part of this issue's scope.

### Configuration

N/A — no config files affected.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **Correction to the Wiring Phase "Verified" grep claim above (remediation
  pass, 2026-08-29)**: `grep -rn "<<[-]\?['\"]" scripts/little_loops/loops/*.yaml`
  requires the opening quote to immediately follow `<<`/`<<-` with no space,
  so it misses every heredoc opener written as `<< 'MARKER'` (space before
  the quote) — the exact style used at all `LL_RAW_9F3C1A7E_EOF`/`LL_STDERR_EOF`
  sites this issue is about (e.g. `loop-router.yaml:208`:
  `<< 'LL_RAW_9F3C1A7E_EOF'`). A space-tolerant scan
  (`grep -rn "<<-\?[[:space:]]*['\"]" scripts/little_loops/loops/*.yaml`) finds
  7 more fixed-terminator families wrapping dynamic/captured content, none
  previously named in this issue: `LL_PLAN_RAW_EOF`
  (`loop-composer.yaml:99-101`, `loop-composer-adaptive.yaml:101-103` —
  `${captured.plan_json.output}`); `LL_STEP_OUTPUT_EOF`
  (`loop-composer.yaml:303-305`/`371-373`,
  `loop-composer-adaptive.yaml:312-314`/`381-383` —
  `${captured.step_output.output}`); `LL_REASSESS_EOF`
  (`loop-composer-adaptive.yaml:516-518`/`566-568` —
  `${captured.reassess_decision.output}`); `RAWEOF` (`brainstorm.yaml:162-164`
  — `${captured.round_ideas.output}`); `PLANEOF`
  (`cua-agent-desktop.yaml:421-423` — `${captured.plan_output.output}`);
  `DIAGEOF` (`cua-agent-desktop.yaml:1087-1092` — `${context.description}`,
  `${state.iteration}`); and `__END_CUA_DESCRIPTION__`
  (`cua-agent-desktop.yaml:78-80` — `${context.description}`). All 7 verified
  by direct read against current file content. `PLANNING_PROMPT_EOF`
  (`rn-plan.yaml:45-57`) remains correctly out of scope — verified it wraps
  only static guidance text with no interpolated tokens. The option-3 guard's
  marker-agnostic Decision Rule already covers all 7 with no additional code
  change (same reasoning already applied to the `LL_INPUT_EOF` family in the
  Wiring Phase note above), but the collision-test suite named in
  Implementation Steps and the Wiring Phase note should include at least one
  fixture from this set to prove the marker-agnostic guarantee holds for
  `${captured.*}`-carrying families beyond `LL_RAW_*_EOF`/`LL_STDERR_EOF`, not
  just assume it from those two.

_Added by `/ll:refine-issue` — 2026-08-29 — based on codebase analysis:_

- **Documentation touchpoint missed by the Documentation subsection
  (remediation pass, 2026-08-29)**: `docs/reference/API.md` — the
  authoritative Python module reference this repo's CLAUDE.md lists as an
  Important File — documents `interpolate()`'s exception contract with a
  runnable example containing the comment "Unsuffixed references still
  raise InterpolationError on missing paths" (`docs/reference/API.md:6287`,
  verified). A heredoc-terminator collision is a distinct, non-missing-path
  trigger for the same `InterpolationError` on the same public function; once
  this guard lands, that comment's framing ("on missing paths") reads as
  incomplete for the new raise condition. This is a second documentation
  touchpoint beyond the `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` MR-11
  note already recorded under Documentation above; neither blocks
  implementation-readiness, but both are follow-up doc updates once Option 3
  lands.

## Impact

- **Priority**: P3 — real injection class, low trigger likelihood, no known
  in-the-wild occurrence.
- **Effort**: Small — option 3 only (interpolation-layer guard plus tests);
  the Medium engine rework belongs to the deferred 1/2 follow-up.
- **Risk**: Low — detect-and-refuse adds a hard error on a payload shape that
  today executes as shell; no rendering change at the converted sites.
- **Breaking Change**: No.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-29_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 42/100 → LOW

### Concerns
- **Superseded** — the Call Path fork this section previously flagged as
  unresolved ("both need an `InterpolationError` carve-out ... or the issue's
  Expected Behavior needs to be narrowed") was resolved by the subsequent
  `/ll:refine-issue` pass (15:39:58): Program Design → Codebase Research
  Findings now states the fork is "resolved toward closing the routing gap"
  with a concrete bar naming both call sites
  (`_run_action_or_route`/`executor.py:3313-3337`,
  `_flush_pending_shell_state`/`executor.py:2871-2897`) and the required test
  assertion (`_finish("error", ...)` at all six named sites, never an
  `on_error` reroute or silent drop).
- That resolution, however, lives only in a "Codebase Research Findings"
  prose block appended after Implementation Steps — the numbered
  Implementation Steps list itself still shows only Step 1 marked
  "Superseded" with no replacement step added for the two executor.py
  carve-outs. An implementer reading Implementation Steps in isolation would
  miss this required work; it is present but only inferable from the research
  findings, not stated as an actionable step.
- Step 2's message-wording fork remains genuinely unresolved: "Closing it
  requires either (a) a distinct halt-message path ... or (b) accepting the
  prefix as a known, unresolved wording wart ... whichever direction is
  taken, the AC must state which of the two it is" — no decision has been
  recorded between (a) and (b).
- `verify_verdict: PROPOSAL_UNSOUND` (frontmatter, from `/ll:verify-issues` at
  2026-08-29T15:27:51) predates the Call Path fork's resolution
  (15:39:58) and has not been re-confirmed by a fresh verify pass against the
  corrected plan.
- The guard as decided lives inside `interpolate()` itself (applies to every
  template it renders, not only `state.action`). The issue's own Codebase
  Research Findings count 41 total un-analyzed `interpolate()` call sites
  (33 in `executor.py`, 10 in `evaluators.py`) wrapped in broad
  `except InterpolationError`/`except Exception` handlers built for
  missing-variable fallback, explicitly flagged as unaudited for whether they
  would silently absorb a terminator-collision error the same way (though
  none currently interpolate heredoc-shaped templates, so no fix is required
  now).

### Outcome Risk Factors
- Moderate cross-cutting complexity beyond the original single-file scope: the
  executor.py propagation fix (bypassing `on_error` routing and the
  `_flush_pending_shell_state` swallow) touches shared exception-routing
  behavior used by many loop states, not a mechanical/local change confined to
  `interpolation.py`.
- Broad, unaudited blast radius: `interpolate()` has 41 other call sites with
  pre-existing broad exception handlers that could silently absorb the new
  failure mode differently than intended; the issue explicitly flags this as
  unaudited rather than verified safe.
- No test coverage yet exists for the executor.py carve-out (direction now
  decided, but no test authored) — only the interpolation.py-level guard has
  a clear test story (`test_fsm_interpolation.py`, `test_builtin_loops.py`).

## Status

**Open** | Created: 2026-08-28 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-08-29T15:54:29 - `e1f51e56-4700-4629-9064-1d81eae9d21d.jsonl`
- `/ll:refine-issue` - 2026-08-29T15:39:58 - `48e9d546-94fd-4111-9bec-ae917ba67439.jsonl`
- `/ll:confidence-check` - 2026-08-29T15:32:50 - `3452bd7a-6500-48f4-9258-6b5f0bb307e9.jsonl`
- `/ll:verify-issues` - 2026-08-29T15:27:51 - `3452bd7a-6500-48f4-9258-6b5f0bb307e9.jsonl`
- `/ll:refine-issue` - 2026-08-29T15:20:03 - `3452bd7a-6500-48f4-9258-6b5f0bb307e9.jsonl`
- `/ll:confidence-check` - 2026-08-29T15:10:51 - `3452bd7a-6500-48f4-9258-6b5f0bb307e9.jsonl`
- `/ll:wire-issue` - 2026-08-29T14:59:33 - `3452bd7a-6500-48f4-9258-6b5f0bb307e9.jsonl`
- `/ll:refine-issue` - 2026-08-29T14:51:59 - `e1f51e56-4700-4629-9064-1d81eae9d21d.jsonl`
