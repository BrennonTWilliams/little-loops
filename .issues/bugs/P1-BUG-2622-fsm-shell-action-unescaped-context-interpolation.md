---
id: BUG-2622
type: BUG
priority: P1
status: in_progress
labels:
- fsm
- interpolation
- shell
- security
relates_to:
- BUG-2362
confidence_score: 100
outcome_confidence: 77
score_complexity: 9
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# FSM shell actions paste `${context.*}` raw into bash — values with `"`/`$`/`` ` ``/`\` break tokenizing and misroute loops

## Summary

`little_loops.fsm.interpolation.interpolate()` does a bare `str(value)` substitution
of `${namespace.path}` placeholders (interpolation.py:253-257) with **no shell
escaping**. `_run_action()` (executor.py:1470) calls it identically for `shell`,
`prompt`, and `mcp` actions. When a `action_type: shell` body interpolates a
user-controlled value (`${context.input}`, `${context.goal}`, …) into a position
where bash parses it as a token — e.g. `[ -z "${context.input}" ]` — any `"`, `$`,
`` ` ``, `\`, or `!` in the value either breaks bash parsing (action exits non-zero)
or, from an untrusted source, injects commands.

Both manifestations look identical to the runner: the expected sentinel is absent,
the evaluator routes to `on_error`/`on_no`, and the loop dies in a terminal state
that **misattributes** the failure to "input was empty" when it was actually
malformed. Adjacent precedent: BUG-2362 (recursive-refine bare shell-var crash).

## Current Behavior

`interpolate()` substitutes `${context.*}` placeholders into `shell` action bodies
with a bare `str(value)` (interpolation.py:257) and no shell escaping. When the
placeholder sits in a bash token position (e.g. `[ -z "${context.input}" ]`), any
`"`, `$`, `` ` ``, `\`, or `!` in the interpolated value breaks bash tokenizing —
the action exits non-zero or, from an untrusted source, executes injected commands.
The evaluator then routes to `on_error`/`on_no` and misattributes the failure to
"input was empty" rather than "input was malformed".

## Expected Behavior

Values interpolated into a shell token position should be safe against shell
metacharacters: either the four Tier-1 builtin loops write the value through a
quoted heredoc (immune to all shell metacharacters) as already fixed in this
branch, or an author opts a placeholder into `shlex.quote()`-style escaping via
the planned `${context.x:shell}` suffix (Tier 3). A value containing `"`, `$`,
`` ` ``, `\`, or `!` must not break tokenizing or misroute the loop.

## Impact

- **Priority**: P1 - shell metacharacters in free-text input silently misroute
  builtin loops (`rlhf-animated-svg`, `prompt-across-issues`) to an incorrect
  terminal state, and the same bare-substitution path is a command-injection
  vector for any `action_type: shell` body fed untrusted `${context.*}` values.
- **Effort**: Medium - Tier 1 (loop rewrites) is done in this branch; Tiers 2-4
  (lint rule, engine `:shell` suffix, regression tests) are scoped with concrete
  anchors in the Integration Map but not yet implemented.
- **Risk**: Low - Tier 1 changes are isolated to four loop YAML files and already
  pass the full test suite; Tiers 2-4 are additive (new lint rule, new suffix
  grammar, new tests) with no behavior change to existing safe interpolations.
- **Breaking Change**: No

## Steps to Reproduce

1. Run `ll-loop run rlhf-animated-svg "$(printf 'Create a "side-by-side" diagram')"`
   — a free-text input containing an embedded `"`.
2. Observe: `Loop completed: input_missing (0.0s)`, despite `context.input` being
   set to the (malformed-for-bash) string.

```bash
ll-loop run rlhf-animated-svg "$(printf 'Create a "side-by-side" diagram')"
# Before fix → Loop completed: input_missing (0.0s), despite context.input being set
```

Root cause verified via probe: after interpolation the body becomes
`if [ -z "Create a "side-by-side" diagram" ]; then` — the inner `"` terminates the
outer quoted string and bash mis-tokenizes.

## Scope — this ships in core builtin loops

Grep for `action_type: shell` bodies interpolating user-controlled context into a
bash **token** position:

| Loop | Line(s) | Input | Exposure |
|------|---------|-------|----------|
| `rlhf-animated-svg.yaml` | 58 | free-text description | **HIGH** (repro) |
| `prompt-across-issues.yaml` | 50 | free-text prompt | **HIGH** |
| `autodev.yaml` | 46, 57 | comma-sep issue IDs | med (defense-in-depth) |
| `recursive-refine.yaml` | 74, 79 | comma-sep issue IDs | med (defense-in-depth) |
| `loop-composer{,-adaptive}.yaml`, `loop-router.yaml` | echo `${context.goal}` fallback | free-text goal | LOW (not yet fixed) |

`prompt`-action interpolation of `${context.input}` is **safe** — the string is sent
as an LLM content payload, not parsed by a shell.

## Fix (tiered)

### Tier 1 — fix the loops (DONE in this branch)

Rewrote the four token-position states to write `context.input` to a file via a
**quoted heredoc** (`<<'LL_INPUT_EOF'`), then validate/split from the file. The
quoted-heredoc body is read literally by bash, so it is immune to *every* shell
metacharacter — including `"`, which the report's originally-suggested
`printf '%s' "${context.input}"` pattern does **not** handle (the value is still
pasted raw inside the surrounding `"..."`).

Note the indentation trap: a `<<'EOF'` terminator must sit at column 0 after YAML
block-scalar dedent, so in `recursive-refine` the heredoc write lives at the
action's base indent (before the `if/else`), not inside the nested queue-mode branch.

Verified: interpolated bodies pass `bash -n` with adversarial input; valid input
still routes to the success sentinel; empty/whitespace-only still detected via
`grep -q '[^[:space:]]'`; comma-split loops preserve tokens verbatim. Full suite
(1323 tests across builtin-loops/fragments/outer-loop-eval) green.

### Tier 2 — MR-lint rule (TODO)

Add an `ll-loop validate` WARN when an `action_type: shell` body interpolates a
user-controlled `${context.*}` (`input`/`goal`/`description`/`task`/`prompt`/
`query`/`topic`) outside a safe position (single-quoted string, quoted heredoc,
`:shell` suffix, or file-write target). Suppress with a top-level flag, matching
the existing MR-3/MR-7 conventions. This is the gate that should have caught it.

### Tier 3 — engine escape syntax (TODO)

Extend the suffix grammar in `interpolation.py` (which already parses `:default=`,
`?`, and `$${}` escaping) with **`${context.input:shell}`** → emits `shlex.quote()`
output, used *without* surrounding quotes. Author-controlled, backward-compatible,
no `action_mode` plumbing needed. Chosen over the report's `${shell:context.input}`
*prefix* form because a suffix composes with the existing parser instead of adding
a second namespace-like grammar.

Rejected: transparent auto-`shlex.quote()` in shell mode — every affected loop
already wraps the placeholder in `"..."`, so `shlex.quote('a"b')` → `'a"b'` placed
inside those quotes produces `"'a"b'"` and is still broken. Correct auto-quoting
would require the engine to detect whether each placeholder already sits inside
quotes — too fragile — and `interpolate()` is shared with prompt/mcp actions where
raw substitution is correct.

### Tier 4 — regression coverage (TODO)

1. Unit: interpolate a shell-action body with a value containing `"`/`$`/`` ` ``/`\`,
   assert the result passes `bash -n`.
2. Integration: fixture loop with a shell validator + adversarial input, assert the
   loop reaches the success path (not the empty-input terminal).
3. Static: walk all builtin loops, assert every `${context.<user>}` in a shell
   action is in a documented safe position.

## Integration Map

_Added by `/ll:refine-issue` — concrete anchors for the remaining Tier 2–4 TODOs, from codebase research._

### Tier 3 — engine `:shell` suffix (`interpolation.py`)

Files to modify:
- `scripts/little_loops/fsm/interpolation.py`
  - `interpolate()` → `replace_var()` closure (`interpolation.py:221`). Suffix parsing is the `if ":default=" ... elif full_path.endswith("?") ...` chain at **lines 227–241**, run *before* the namespace/path split at line 251. Add a third branch here that detects a `:shell` flag suffix (shape it like the `?` case — `full_path.endswith(":shell")` + strip — not like `:default=`, since `:shell` carries no `=value` payload) and threads a `shell_quote: bool` into the substitution step.
  - Success-path substitution is the try-block at **lines 253–257**; line 257 `return str(value)` is the exact bare-substitution point. Change it to `return shlex.quote(str(value))` when the shell flag is set. Add `import shlex` at the top.
  - Reuse the existing "Ambiguous suffix" `InterpolationError` message shape (`interpolation.py:234-237`) to reject `:shell` combined with `:default=`/`?`.
  - **Free coverage**: `interpolate_dict()` (`interpolation.py:273`) and `_interpolate_list()` (`interpolation.py:303`) both funnel string values back through `interpolate()`, so `state.params` dict values used by `mcp_tool` actions (`executor.py:1504`) inherit the suffix with no extra wiring.
- **Why suffix, not action-mode auto-quote** (confirms the Tier 3 rationale): `_run_action()` (`executor.py:1452`) calls `interpolate(action_template, ctx)` at **line 1470** *before* it computes `self._action_mode(state)` at line 1471, and never re-passes the mode back into `interpolate()`. There is no choke point where the executor could gate escaping on shell-vs-prompt, so escaping must be author-declared per-placeholder via the suffix.

### Tier 2 — MR-lint rule (`validation.py`)

Model the new rule on **MR-9 `_validate_overescaped_shell()` (`validation.py:1840`)** — the closest analog because it already gates to shell actions via `if state.action_type not in ("shell", None): continue` (line 1868) and skips slash-command actions (line 1870). MR-7 (`_validate_bash_default_interpolation`, `validation.py:1805`) uses the two-function `_find_* + _validate_*` split (`_find_bash_default_tokens`, `validation.py:1789`) worth following if the safe-position detection gets complex.

Files to modify:
- `scripts/little_loops/fsm/validation.py`
  - Add a module-level detector regex near the other MR regexes (**lines 108–123**, alongside `_SHARED_TMP_PATH_RE`/`_BASH_DEFAULT_RE`/`_OVERESCAPED_SHELL_RE`) for a user-controlled `${context.<input|goal|description|task|prompt|query|topic>}` in a shell body. The rule must treat these as **safe positions** (no warning): single-quoted string, quoted heredoc `<<'EOF'`, the new `:shell` suffix, or a file-write target.
  - Add `_validate_unsafe_context_interpolation(fsm)` (WARN severity → `ValidationSeverity.WARNING`), first statement `if fsm.<suppress_flag>: return []`.
  - Register it in `validate_fsm()` alongside the other shell rules at **validation.py:1255–1257** (`errors.extend(...)`).
  - Add the suppress-flag name to `KNOWN_TOP_LEVEL_KEYS` (**validation.py:196–213**) so it isn't reported as an unknown top-level key.
- `scripts/little_loops/fsm/schema.py`
  - Declare the suppress flag on `FSMLoop` with default `False` near the other `*_ok` flags (**lines 1135–1139**).
  - Serialize conditionally in `to_dict()` (**lines 1231–1240**) and parse in `from_dict()` (**lines 1327–1331**).
- WARN severity lands in `struct_warnings` (**validation.py:2810**), so it advises without blocking load — matches the requested Tier 2 behavior. Pick the next free `MR-N` id and add a row to the CLAUDE.md + `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` rule tables.

### Tier 4 — regression tests

- `scripts/tests/test_fsm_interpolation.py` — **no existing test pipes `interpolate()` through `bash -n`**; this is net-new. Use `subprocess.run(["bash", "-n", "-c", result])`; model the input/output assertion shape on `test_escape_bash_default_value` (`test_fsm_interpolation.py:379`). Also add `:shell` suffix positive tests (value with `"`/`$`/`` ` ``/`\` → shlex-quoted, passes `bash -n`) and the mutual-exclusivity `pytest.raises(InterpolationError)` case (model on `test_bash_default_operator_raises_interpolation_error`, line 241).
- `scripts/tests/test_fsm_validation.py` — add a rule test class modeled on `TestOverescapedShell` (**~lines 3304–3404**): should-fire (raw token position), should-not-fire (single-quoted / quoted-heredoc / `:shell`-suffixed / `action_type: prompt` gate), suppress-flag, wired-into-`validate_fsm`, and a `test_<flag>_recognized_as_top_level_key` case (writes real YAML, asserts no "Unknown top-level" warning).
- `scripts/tests/test_fsm_schema.py` — round-trip serialization test for the new suppress flag, modeled on the MR-7 `bash_default_ok` tests (**~lines 3650–3684**).
- Static walk — `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles` (**lines 28–54**, `test_all_validate_as_valid_fsm`) and the permissive-context guard `scripts/tests/test_builtin_loop_interpolation.py` (BUG-2362 regression) already exercise every builtin loop; the Tier 4 "static: all `${context.<user>}` in a shell action is in a safe position" check belongs here.
- Fixture — model a minimal single-purpose loop on `scripts/tests/fixtures/fsm/assess-pid-corruption.yaml`.

### Remaining Tier 1 (last open AC)

`echo "${context.goal}"` fallbacks not yet converted to a safe pattern:
- `scripts/little_loops/loops/loop-composer.yaml`
- `scripts/little_loops/loops/loop-composer-adaptive.yaml`
- `scripts/little_loops/loops/loop-router.yaml`

### Precedent / related lint rules
- MR-7 (`ENH-2348`, `BUG-2346`): bash `:-` default interpolation lint — the pattern this rule extends.
- MR-9 (`BUG-2368`): over-escaped `$$` PID lint — closest structural analog.
- `BUG-2362`: bare shell-var crash — adjacent precedent (already linked in frontmatter).
- `BUG-2553`: default-suffix false-positive in a pre-run validator — a cautionary reference for keeping the new safe-position detection from over-flagging.

### Documentation

_Wiring pass added by `/ll:wire-issue`: the MR-rule table is duplicated across **five** files, not the two named above — every one needs the new MR-N row (and `:shell` suffix example)._

- `.claude/CLAUDE.md` — § Loop Authoring MR table (already noted) [Agent 2]
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — § "The Design Rules (MR-1…MR-10)" table (lines 92–105) **plus** the section heading (line ~85) and TOC entry (line ~26) that hard-code the "MR-1…MR-10" range → bump to the new top id [Agent 2]
- `docs/reference/CLI.md` — `#### ll-loop validate` prose bullet list (MR bullets at lines 672–686) + the suppression-flag summary sentence at line 683 (append the new `*_ok` flag) [Agent 2]
- `docs/reference/API.md` — `validate_fsm()` "Checks performed" bullets (MR-7/MR-9 at lines 5370–5372, add new bullet) + `FSMLoop` field-comment block (alongside `bash_default_ok` line 4689 / `shell_pid_ok` line 4691) + `interpolate()` docstring example block (lines 5297–5320 — add a `:shell` example next to the existing `:default=`/`?` examples) [Agent 2]
- `skills/review-loop/reference.md` — MR-rule table (lines 40–48) used by `/ll:review-loop`. **Note: this table is already stale (stops at MR-8, missing MR-9/MR-10)** — adding the new rule here means also backfilling the MR-9/MR-10 gap, or the review skill keeps under-reporting [Agent 2]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestValidatorWarningBudget` (class at line 9337; `CATEGORY_PATTERNS` line 9347, `ALLOWLIST` line 9366) — **ratchet test, most likely to fire.** If the new WARN rule matches any builtin loop (including any `${context.*}` shell interpolation Tier 1 leaves unconverted, or any other loop), `test_deterministic_warning_categories_do_not_regrow` (line 9412) fails until the loop is fixed or an `ALLOWLIST` entry citing BUG-2622 is added; the new category must also be registered in `CATEGORY_PATTERNS`. Conversely, if Tier 1's `${context.goal}` fix removes an already-allowlisted warning, `test_allowlist_entries_are_not_stale` (line 9426) fails and needs allowlist pruning [Agent 3]
- `scripts/tests/test_loop_composer.py` (`TestLoopComposerFile`, `REQUIRED_STATES`) — covers `loop-composer.yaml`; asserts state names/fields only, so the Tier 1 rewrite is unlikely to break it, but re-run to confirm [Agent 3]
- `scripts/tests/test_loop_composer_adaptive.py` — same shape for `loop-composer-adaptive.yaml` [Agent 3]
- `scripts/tests/test_loop_router.py` (`TestLoopRouterFile`, `TestLoopRouterStates`; `test_dispatch_with_binding_references_derived_params` line 181) — covers `loop-router.yaml` [Agent 3]
- New `:shell` suffix tests: model on `TestSafeInterpolation` (`test_fsm_interpolation.py:553`) which already exercises a full new-suffix family (per-namespace resolution, no-suffix-still-raises, `$${...}` pass-through combo, `interpolate_dict` propagation) — mirror it but assert `shlex.quote()` output [Agent 3]

### Callers / consumers (context for Tier 3 grammar change)

_Wiring pass added by `/ll:wire-issue`: `interpolate()` has callers beyond `executor.py`; the `:shell` suffix is self-contained inside `interpolate()` so none need code changes, but two are behavior-sensitive:_
- `scripts/little_loops/fsm/evaluators.py` — interpolates evaluator config; inherits the new suffix for free [Agent 1]
- `scripts/little_loops/cli/loop/testing.py` — `ll-loop simulate`/`test` runs `interpolate()` against synthetic contexts; a template that previously contained literal `:shell` text now has it consumed as a flag (behavior change to spot-check) [Agent 2]
- `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_validate` (the `ll-loop validate` entry point) calls `load_and_validate()`; the new WARN rule surfaces here with no extra wiring [Agent 1]
- `scripts/little_loops/config-schema.json` — confirmed it does **not** enumerate FSM suppress flags (`bash_default_ok` etc. absent); no change needed for the new `*_ok` flag (loop-YAML top-level key, governed by `KNOWN_TOP_LEVEL_KEYS`/`FSMLoop` only) [Agent 2]

## Acceptance criteria

- [x] `rlhf-animated-svg` / `prompt-across-issues` / `autodev` / `recursive-refine`
      no longer misroute on inputs containing shell metacharacters.
- [ ] `ll-loop validate` warns on the unsafe pattern (Tier 2).
- [ ] `${context.x:shell}` shlex-quote escape available in the engine (Tier 3).
- [ ] Regression tests per Tier 4 added and gating.
- [ ] `loop-composer{,-adaptive}` / `loop-router` `echo "${context.goal}"` fallbacks
      converted to a safe pattern.
- [ ] New MR-N row + `:shell` suffix documented in **all five** MR-table sites
      (CLAUDE.md, HARNESS_OPTIMIZATION_GUIDE.md, CLI.md, API.md, review-loop/reference.md),
      and `TestValidatorWarningBudget` (`test_builtin_loops.py`) stays green
      (`CATEGORY_PATTERNS`/`ALLOWLIST` updated if the new rule fires on any builtin loop).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Register the new WARN rule's category in `scripts/tests/test_builtin_loops.py` `CATEGORY_PATTERNS` (line 9347) and add a BUG-2622 `ALLOWLIST` entry (line 9366) if it fires on any builtin loop — otherwise `test_deterministic_warning_categories_do_not_regrow` (line 9412) breaks.
2. Add the new MR-N row to **all five** table sites (not just CLAUDE.md + HARNESS_OPTIMIZATION_GUIDE.md): `docs/reference/CLI.md` (bullets 672–686 + suppression sentence line 683), `docs/reference/API.md` (`validate_fsm()` bullets 5370–5372, `FSMLoop` field comment ~4689, `interpolate()` example block 5297–5320), and `skills/review-loop/reference.md` (lines 40–48, backfilling its stale MR-9/MR-10 gap).
3. Bump the "MR-1…MR-10" range in `HARNESS_OPTIMIZATION_GUIDE.md` heading (~line 85) + TOC (~line 26).
4. Spot-check `scripts/little_loops/cli/loop/testing.py` (`ll-loop simulate`) for any template with literal `:shell` text now consumed as a flag by the Tier 3 grammar change.
5. Re-run `test_loop_composer.py` / `test_loop_composer_adaptive.py` / `test_loop_router.py` after the Tier 1 `${context.goal}` rewrite to confirm no structural assertion broke.

## Status

**In Progress** | Created: 2026-07-13 | Priority: P1

## Session Log
- `/ll:ready-issue` - 2026-07-13T00:21:14 - `af64d3b3-b8cf-4b8d-86fb-f34d7b26b01f.jsonl`
- `/ll:confidence-check` - 2026-07-13T00:18:23 - `ad641d10-ec71-4e00-8362-c23466a87d83.jsonl`
- `/ll:wire-issue` - 2026-07-13T00:16:10 - `574636e3-3d15-47b4-adff-896e7a79fe1e.jsonl`
- `/ll:refine-issue` - 2026-07-13T00:08:51 - `ac47afd1-540a-4d52-b4ec-c15e4e0d98f6.jsonl`
