---
id: BUG-2827
type: BUG
priority: P3
status: done
captured_at: '2026-07-26T06:40:00Z'
discovered_date: 2026-07-26
discovered_by: capture-issue
completed_at: '2026-07-26T16:28:07Z'
labels:
- loops
- shell
- autodev
- summary
relates_to:
- BUG-2826
confidence_score: 96
outcome_confidence: 80
score_complexity: 20
score_test_coverage: 18
score_ambiguity: 20
score_change_surface: 22
---

# BUG-2827: `grep -c ... || echo 0` yields a two-line count, breaking every summary counter

## Summary

Across 7 built-in loops (25 sites) counters are computed as:

```bash
COUNT=$(echo "$IDS" | grep -c '[^[:space:]]' || echo 0)
```

`grep -c` **prints its count and then exits 1 when the count is zero**. The
`|| echo 0` therefore fires *in addition to* grep's own `0`, and the variable is
assigned the two-line string `"0\n0"` rather than `0`. Every downstream use of
that variable then fails: `printf '%d'` rejects it as an invalid number, and
`[ "$COUNT" -gt 0 ]` errors with `integer expected`.

The `|| echo 0` was presumably written for the missing-file case — and there it
works, because `grep -c` on a nonexistent file prints nothing and exits 2. It is
the *empty-but-valid* case, which is the common one, that produces the double
value.

## Current Behavior

From the `finalize_done` state of run `.loops/runs/autodev-20260726T011116/`
(stderr captured in the run's events JSONL):

```
bash: line 29: printf: 0
0: invalid number
bash: line 31: [: 0
0: integer expected
bash: line 34: [: 0
0: integer expected
bash: line 37: [: 0
0: integer expected
```

The summary still rendered — `Passed (0)` / `Skipped (1)` — because `printf`
emits the first line before erroring and the failing `[` tests are inside `if`
guards whose sections happened to be empty anyway. So the defect is currently
**latent**: noisy stderr, and three conditional sections whose guards evaluate
by accident rather than by arithmetic.

Affected files and site counts:

| File | Sites |
|---|---|
| `scripts/little_loops/loops/recursive-refine.yaml` | 13 |
| `scripts/little_loops/loops/autodev.yaml` | 5 |
| `scripts/little_loops/loops/auto-refine-and-implement.yaml` | 2 |
| `scripts/little_loops/loops/rn-build.yaml` | 2 |
| `scripts/little_loops/loops/dead-code-cleanup.yaml` | 1 |
| `scripts/little_loops/loops/rn-refine.yaml` | 1 |
| `scripts/little_loops/loops/rl-coding-agent.yaml` | 1 |

Two variants exist and fail differently:

- `echo "$VAR" | grep -c ...` — broken whenever `$VAR` is empty (i.e. whenever
  the bucket is empty), which is the normal case for most buckets.
- `grep -c ... FILE 2>/dev/null || echo 0` — correct when the file is *missing*
  (exit 2, no stdout), broken when the file exists with no matching lines.

## Root Cause

- **File**: `scripts/little_loops/loops/autodev.yaml` (representative; same shape at all 25 sites listed above)
- **Anchor**: `finalize_done` state, lines 1601-1605 — `PASSED_COUNT`, `SKIPPED_COUNT`, `INFRA_SKIPPED_COUNT`, `GATE_BLOCKED_COUNT`, `DECISION_UNRESOLVED_COUNT`
- **Cause**: `grep -c` prints the match count to stdout *and* exits 1 when that count is zero (both BSD and GNU grep). The `|| echo 0` fallback is written for the "no output at all" case (missing file, exit 2) but also fires on the exit-1/zero-match case, where `grep -c` already wrote `0`. The variable is assigned an embedded-newline two-line value (`"0\n0"`) rather than a single token. Downstream, `printf '%d' "$COUNT"` and `[ "$COUNT" -gt 0 ]` (lines 1616-1624) then fail arithmetically — and per `ENH-2825`'s new `on_error: failed` route on `finalize_done` (line 1634), a shell error surfaced here can now flip a run's summary state from `done` to `failed`, which is the opposite of BUG-2825's intent.

## Steps to Reproduce

```bash
$ EMPTY=""
$ COUNT=$(echo "$EMPTY" | grep -c '[^[:space:]]' || echo 0)
$ printf '%d\n' "$COUNT"
bash: printf: 0
0: invalid number
$ printf '%q\n' "$COUNT"
$'0\n0'
```

Or observe it end-to-end: run `ll-loop run autodev <ID>` on any issue that does
not populate every bucket and read the `finalize_done` stderr in the run's
events JSONL.

## Expected Behavior

Counters hold a single integer in every case — file missing, file empty, file
populated — so `printf '%d'` and `[ -gt ]` behave arithmetically rather than by
accident, and no spurious stderr is emitted.

## Impact

Currently latent: spurious stderr on most loop runs, and three `if` guards in
`autodev.yaml`'s summary whose conditions error rather than evaluate (a failing
`[` is treated as false, which happens to match the intended behaviour for an
empty bucket). No data loss and no wrong exit codes observed. The cost is
mainly that the reporting path is arithmetically unsound and the idiom is
replicated 25 times, so it propagates into every new loop written by example.

## Status

Open — not started. Root cause confirmed (`grep -c` prints `0` *and* exits 1 on
no matches) and all 25 call sites enumerated; no fix attempted.

## Motivation

Individually harmless, but it is a correctness landmine sitting in the reporting
path of the loops operators rely on to know what happened. The guards it breaks
(`INFRA_SKIPPED_COUNT`, `GATE_BLOCKED_COUNT`, `DECISION_UNRESOLVED_COUNT` in
`autodev.yaml`) are exactly the ones that surface *actionable* buckets — a `[`
that errors is treated as false, so a populated bucket could be suppressed if the
count string were ever malformed for a non-zero value. It also trains the pattern
into new loops: 25 copies already exist, and each one is a template for the next.

## Proposed Solution

Replace the idiom with one that cannot emit two values. Options, cheapest first:

1. **Count lines, don't grep-count**, e.g.
   `COUNT=$(printf '%s\n' "$IDS" | grep -c '[^[:space:]]' || true)` still has the
   dual-write problem — instead assign unconditionally and normalize:
   `COUNT=$(grep -c '[^[:space:]]' <<<"$IDS"); COUNT=${COUNT:-0}` with the
   pipeline's exit status ignored rather than branched on.
2. **Prefer a form whose exit status is irrelevant**, such as
   `COUNT=$(printf '%s' "$IDS" | grep -c '[^[:space:]]' 2>/dev/null); : "${COUNT:=0}"`.
3. Whatever form is chosen, apply it to **all 25 sites** — a one-file fix leaves
   the pattern alive and copy-pasted.
4. Consider a `ll-loop validate` lint for `grep -c ... || echo` so the idiom
   cannot re-enter the codebase, in the spirit of the existing MR-* shell rules
   (MR-7/MR-9/MR-10 already police shell shapes in loop YAML).

Note the FSM interpolates the whole action string before bash sees it, so any
replacement must keep `${...}` escaping consistent with the surrounding lines.
`grep`/`-c`/`||`/`echo 0` do not collide with the FSM `${...}` token grammar, so
the fix itself needs no new escaping — but if the replacement introduces a bash
parameter expansion like `${COUNT:-0}`, that must be written `$${COUNT:-0}` in
the YAML action string (per MR-7 / BUG-2346), since `COUNT` is not one of the
FSM's resolvable namespaces (`context`, `captured`, `prev`, `result`, `state`,
`loop`, `env`, `messages`, `param`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Existing correct precedent, already in-tree**: `scripts/little_loops/loops/rn-refine.yaml:511-514` (`synth_dispatch` state) already carries the fix, with an explanatory comment:
  ```bash
  # grep -c prints the count AND exits 1 when zero, so guard with || true and
  # normalize an empty (missing-file) result rather than relying on exit code.
  QN=$(grep -c '[^[:space:]]' "$SQ" 2>/dev/null || true)
  [ -z "$QN" ] && QN=0
  ```
  This is the cleanest fix shape: `|| true` (not `|| echo 0`) suppresses only the nonzero exit without writing a second stdout line, then `[ -z "$VAR" ] && VAR=0` normalizes the missing-file case. Note `rn-refine.yaml`'s *own* remaining site at line 213 (`echo "RECONCILED $(grep -c ... || echo 0)"`) still uses the buggy form four lines away from the fix — it needs the same treatment.
- **Alternative correct precedent (no grep at all)**: `scripts/little_loops/loops/auto-refine-and-implement.yaml:704-707` defines a reusable `count()` helper: `count() { awk 'NF{c++} END{print c+0}' "$RUN_DIR/$1" 2>/dev/null || echo 0; }` — `awk`'s `END{print c+0}` always emits exactly one normalized line regardless of match count, sidestepping the grep dual-write hazard entirely. The *same file* still has the broken idiom at lines 889-895 (`INPUT_SIZE=$(... | grep -c '[^[:space:]]' 2>/dev/null || echo 0)`), one of the 25 enumerated sites, sitting right next to its own fix.
- **A third, related-but-distinct broken variant** (not in the 25-site count, found during research): `scripts/little_loops/loops/general-task.yaml:412` — `UNCHECKED_PLAN=$(grep -c '...' "$PLAN" || true)` uses `|| true` but has no `[ -z ... ]` normalization, so it can leave the variable *empty* (not `0`) rather than double-valued. Worth the same normalization treatment if this file is touched.
- **Exact 25 call sites with line numbers** (supersedes the file-level counts above):
  - `recursive-refine.yaml`: 117, 118, 149, 418, 708, 796, 797, 798, 799, 800, 801, 802, 803
  - `autodev.yaml`: 1601, 1602, 1603, 1604, 1605 (`finalize_done` state)
  - `auto-refine-and-implement.yaml`: 891, 894
  - `rn-build.yaml`: 105, 147
  - `dead-code-cleanup.yaml`: 35
  - `rn-refine.yaml`: 213
  - `rl-coding-agent.yaml`: 76
- **Unguarded variant found outside the 25-site count** (separate hazard, same root cause, not scoped to this fix unless expanded): `scan-and-implement.yaml:62` and `canvas-sketch-generator.yaml:311` use bare `grep -c` with no `|| echo 0`/`|| true` guard at all — these will hard-fail (nonzero exit, no fallback) rather than silently double-write.
- **Idiom also taught in docs/skills** (relevant to Proposed Solution option 4 — "prevent re-entry"): the same `grep -c ... || echo 0` pattern appears as an authoring example in `docs/generalized-fsm-loop.md:1012,1229,1262`, `docs/guides/LOOPS_GUIDE.md:483`, and `skills/create-loop/loop-types.md:415`. A lint-only fix leaves these teaching the broken idiom to new loop authors by example.
- **Lint rule precedent for `scripts/little_loops/fsm/validation.py`**: existing MR-7/MR-9/MR-10 rules (regex constants ~lines 116-147, validator functions ~lines 1924-2140, wired into `validate_fsm()` around line 1370) follow a consistent shape — a module-level regex, a `_validate_*()` function taking the `FSMLoop` and returning `list[ValidationError]`, guarded to `shell`-type actions, and a top-level `<flag>_ok: true` suppression key. A new rule would follow the same shape and needs a corresponding test class in `scripts/tests/test_fsm_validation.py` (see `TestMR7BashDefaultInterpolation`/`TestMR9OverescapedShell` for the pattern: fires-on-bad, does-not-fire-on-good, suppressed-by-flag, integrates-with-validate_fsm).
- **Regression test precedent for `scripts/tests/test_builtin_loops.py`**: `test_no_bare_bash_variable_in_shell_actions` (lines 234-289, class `TestBuiltinLoopFiles`, fixture `builtin_loops` at lines 31-37 iterating `BUILTIN_LOOPS_DIR.rglob("*.yaml")`) is the structural template — loop over builtin loops, filter `action_type == "shell"` states, regex-scan the `action` string, assert an empty violations list with a `f"{loop_file.name}/{state_name} ..."` message. A new `test_no_grep_c_or_echo_fallback_in_shell_actions` should mirror this shape.

## Integration Map

| File | Change |
|---|---|
| `scripts/little_loops/loops/recursive-refine.yaml:117,118,149,418,708,796-803` | replace 13 counter sites |
| `scripts/little_loops/loops/autodev.yaml:1601-1605` (`finalize_done`) | replace 5 counter sites |
| `scripts/little_loops/loops/auto-refine-and-implement.yaml:891,894` | replace 2 counter sites (in-file `count()` helper at 704-707 is the model) |
| `scripts/little_loops/loops/rn-build.yaml:105,147` | replace 2 counter sites |
| `scripts/little_loops/loops/rn-refine.yaml:213` | replace 1 counter site (in-file fixed precedent at 511-514 is the model) |
| `scripts/little_loops/loops/dead-code-cleanup.yaml:35` | replace 1 counter site |
| `scripts/little_loops/loops/rl-coding-agent.yaml:76` | replace 1 counter site |
| `scripts/little_loops/fsm/validation.py` (~lines 116-147 regex, ~1924-2140 validators, ~1370 wiring) | optional new MR-* lint rule for the idiom |
| `scripts/tests/test_fsm_validation.py` | test class for the new lint rule, if added |
| `scripts/tests/test_builtin_loops.py` (model: `test_no_bare_bash_variable_in_shell_actions`, lines 234-289) | assert no loop YAML contains `grep -c` piped into `|| echo` |
| `docs/generalized-fsm-loop.md:1012,1229,1262`, `docs/guides/LOOPS_GUIDE.md:483`, `skills/create-loop/loop-types.md:415` | optional: update authoring examples that teach the broken idiom |

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_loops_recursive_refine.py` — contains **hand-copied Python-string bash fixtures**, not loaded from the YAML, that independently embed the identical buggy idiom and will silently drift out of sync unless edited in lockstep with `recursive-refine.yaml`: `_DONE_SCRIPT` (line ~714, class `TestDoneSummary`, 6 occurrences at lines 728-733, exercised by `test_depth_cap_line_shows_capped_ids` and siblings), `_DEQUEUE_NEXT_SCRIPT` (line ~1234, 3 occurrences at lines 1250-1252, asserted via `result.stderr` checks at lines 1345-1346), `_ENQUEUE_CHILDREN_PEEK_SCRIPT` (line ~1393, 1 occurrence at line 1395) and `_ENQUEUE_OR_SKIP_PEEK_SCRIPT` (line ~1407, 1 occurrence at line 1410), plus `_check_depth_script()` helper (line ~245). None of these tests currently assert on the buggy stderr itself, so nothing blocks the fix — but the constants must be updated to match whatever replacement idiom lands in `recursive-refine.yaml`, or the mirror goes stale.
- `scripts/tests/test_rn_remediate.py:1616-1631` — `test_emit_implemented_uses_quiet_grep_for_dedup`, a directly analogous prior fix/test pair for the same bug class in `rn-remediate.yaml`'s `emit_implemented` state (BUG-2170: `grep -cxF ... || echo 0` → `grep -qxF`), asserting `"grep -qxF" in action` / `"grep -cxF" not in action`. Useful as a second test-shape template alongside the `test_no_bare_bash_variable_in_shell_actions` model already cited, if per-site (rather than only cross-file-scan) assertions are wanted.
- `scripts/little_loops/loops/general-task.yaml:412` — already noted in Codebase Research Findings as a related-but-out-of-scope broken variant (`|| true` with no `[ -z ... ]` normalization, leaves the var empty rather than double-valued); confirmed by this pass as a real site, still explicitly not part of the 25-site count unless this issue's scope is expanded to include it.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `skills/create-loop/reference.md:910` — teaches the idiom in a "Capture metric output and use it in the fix action" example (`ruff check src/ 2>&1 | grep -c 'error' || echo 0`); distinct from `skills/create-loop/loop-types.md:415` already flagged — `create-loop` has the idiom in two of its files.
- `skills/review-loop/reference.md:795` — teaches the idiom in a `count_errors` before/after example (`grep -c 'ERROR' build.log 2>/dev/null || echo 0`); not previously flagged for any file in `review-loop`.

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- If a new MR-* suppression flag (e.g. `grep_c_echo_ok`) is added alongside a new lint rule, it must be registered in **`scripts/little_loops/fsm/schema.py`**, not just `validation.py`: the `LoopConfigOverrides` dataclass field declarations (~lines 1253-1275), its `to_dict()` serialization (~lines 1360-1394), its `from_dict()` parsing (~lines 1481-1497), and `KNOWN_TOP_LEVEL_KEYS` (~lines 214-268) where existing flags like `bash_default_ok`/`shell_pid_ok`/`parse_swallow_ok` are listed. Per MR-7/9/10 precedent, no corresponding entry in `fsm-loop-schema.json` is required for parity — those three flags are dataclass-only, not JSON-schema-declared.
- `.claude/CLAUDE.md` MR-* table (Loop Authoring section) — if a new rule lands, add a row matching the existing 4-column shape (`| Rule | Sev | Catches | Suppress with |`), slotting after the `MR-12` row per the file's current numeric-then-named ordering.


## Resolution

Replaced all 25 `grep -c ... || echo 0` sites (across `recursive-refine.yaml`,
`autodev.yaml`, `auto-refine-and-implement.yaml`, `rn-build.yaml`,
`dead-code-cleanup.yaml`, `rn-refine.yaml`, `rl-coding-agent.yaml`) with the
in-tree precedent shape from `rn-refine.yaml`'s `synth_dispatch` state:
`VAR=$(grep -c ... || true)` followed by `[ -z "$VAR" ] && VAR=0`. This
suppresses only the nonzero exit without a second stdout write, so `printf
'%d'` and `[ -gt ]` behave arithmetically in every case (missing file, empty
file, populated file). Added a regression test,
`test_no_grep_c_or_echo_fallback_in_shell_actions` in
`scripts/tests/test_builtin_loops.py`, mirroring the
`test_no_bare_bash_variable_in_shell_actions` structural-scan template so the
idiom cannot silently re-enter any built-in loop YAML. Did not add a new MR-*
lint rule or touch the docs/skills authoring examples — those were flagged as
optional in the Proposed Solution; the regression test already closes the
"re-enters via new loops" risk for in-repo loops, and lint-rule/schema wiring
plus docs updates can be split into a follow-up if desired.

## Session Log
- `/ll:confidence-check` - 2026-07-26T00:00:00Z - `262ceca1-b394-406a-8957-4f35e40daddb.jsonl`
- `/ll:wire-issue` - 2026-07-26T16:11:25 - `da324ba0-fa3b-47d4-9721-f97b1900609c.jsonl`
- `/ll:refine-issue` - 2026-07-26T16:03:32 - `9164b4f4-31b4-4697-be2c-47ab37bc317f.jsonl`
- `/ll:manage-issue` - 2026-07-26T16:27:38Z - `1311a2f9-a7cd-4961-9aa9-e43f9068e123.jsonl`
