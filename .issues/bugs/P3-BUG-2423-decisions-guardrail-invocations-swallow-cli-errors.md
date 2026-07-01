---
id: BUG-2423
title: Decisions-check invocations swallow CLI errors via `2>/dev/null || true`, silently
  disabling the guardrail
type: BUG
priority: P3
status: done
captured_at: '2026-07-01T02:24:04Z'
completed_at: '2026-07-01T03:42:34Z'
discovered_date: 2026-07-01
discovered_by: capture-issue
labels:
- bug
- decisions
- skills
- error-handling
- silent-failure
relates_to:
- BUG-2026
- BUG-372
decision_needed: false
confidence_score: 100
outcome_confidence: 74
score_complexity: 14
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
---

# BUG-2423: Decisions-check invocations swallow CLI errors via `2>/dev/null || true`, silently disabling the guardrail

## Summary

Five skill/command files invoke the decisions guardrail as
`ll-issues decisions list … 2>/dev/null || true`. That pattern collapses two
distinct outcomes into one: a **legitimate empty result** (exit 0, no matching
rules) and a **command failure** (exit 2, e.g. an unrecognized flag) both
produce empty stdout and are treated as "no rules to enforce." As a result, any
drift between the flags a skill passes and the flags the CLI actually accepts
**silently disables the decisions guardrail** with no error, no log, and no
non-zero exit code.

This was not hypothetical: every call site passed `--enforcement required`,
which `ll-issues decisions list` never accepted (the flag existed only on `add`
/`promote`). The command exited 2 on every invocation; `2>/dev/null || true`
hid it, so `format-issue`, `ready-issue`, and `verify-issues` never actually
ran their decisions check. The concrete flag was fixed separately (added
`--enforcement` to the `list` subparser); **this issue tracks the swallowing
pattern that let the breakage go undetected**, which will mask the next arg
drift just as effectively.

## Steps to Reproduce

1. Note a decisions-check call site, e.g. `skills/format-issue/SKILL.md` Step
   2.6: `ll-issues decisions list --type rule --enforcement required --active-only 2>/dev/null || true`.
2. Introduce (or already have) any flag the CLI does not accept — the real case
   was `--enforcement` missing from the `list` subparser.
3. Run the skill. The subcommand exits 2 with an argparse usage error on stderr.
4. **Observe:** `2>/dev/null` discards the usage error and `|| true` forces exit
   0, so the caller sees empty output and concludes "no required rules → skip."
   The guardrail is silently inert; nothing signals that the query never ran.

## Current Behavior

The decisions-check invocations cannot distinguish command failure from an empty
result. Affected call sites (all wrap the query in `2>/dev/null || true` or the
`--format json` equivalent):

- `skills/format-issue/SKILL.md:187` — `--enforcement required`
- `commands/ready-issue.md:189` — `--enforcement required`
- `commands/verify-issues.md:69` — `--enforcement required`
- `skills/improve-claude-md/SKILL.md:273` — `--enforcement advisory`
- `skills/go-no-go/SKILL.md:413` — `--enforcement=advisory`

Because the check emits `[DECISIONS]` findings only when the query returns rows,
a failed query yields zero findings — indistinguishable from a clean pass.

### Codebase Research Findings

_Added by `/ll:refine-issue` — the call-site inventory above is partly stale; verified against the current tree:_

**Guardrail `decisions list` queries that swallow (the sites this bug actually targets):**
- `skills/format-issue/SKILL.md:187` — `list --type rule --enforcement required --active-only` (required-rule guardrail).
- `skills/format-issue/SKILL.md:190` — `list --type exception` (companion suppressor lookup, same `2>/dev/null || true`) — **omitted from the original list**.
- `commands/ready-issue.md:189` — `list --type rule --enforcement required --active-only --format json`.
- `commands/ready-issue.md:192` — `list --type exception` (companion) — **omitted from the original list**.
- `commands/verify-issues.md:69` — `list --type rule --enforcement required --active-only`.
- `skills/improve-claude-md/SKILL.md:231` — `list --type rule 2>/dev/null | grep -i … || true` (dedup lookup, not the required-rule guardrail). **The issue cited line 273, but 273 is a `decisions add`, not a `list` query — the correct target in this file is line 231.**

**Mislabeled in the original list (these are `decisions add` *writes*, not guardrail `list` *reads*) — OUT OF SCOPE, DO NOT TOUCH:**
- `skills/improve-claude-md/SKILL.md:267-273` — `decisions add --enforcement advisory` (recording; locator reports **no** `2>/dev/null || true` on this one).
- `skills/go-no-go/SKILL.md:407-414` — `decisions add --enforcement=advisory … 2>/dev/null || true`, **already wrapped in an `[ -f .ll/decisions.yaml ]` gate** (lines 406-416), so its absent-skip is already correct; only the inner `|| true` still swallows a real failure. **This site is explicitly OUT OF SCOPE for this bug — leave it unchanged.** It is a tail-of-skill bookkeeping *write* (records the go/no-go verdict), not the required-rule guardrail *read* this bug targets; hardening it yields no correctness benefit here, and go-no-go is an expensive LLM skill invoked directly from FSM loops, so it is not a site to churn casually. Editing it would also break a live test assertion (`test_feat1896_skill_bridges.py:84`, see Integration Map → Tests). If the inner-`|| true`-on-`add`-writes concern is ever pursued, it belongs in a separate follow-on ENH alongside `improve-claude-md:267-273`, not here.

**Broader swallow family outside skills/commands (same hygiene class; candidate for a follow-on, not necessarily this bug's scope):**
- `.loops/distill-decisions.yaml:14,44` — `decisions list --format json 2>/dev/null | python3 -c …` (count queries piped to Python with a bare `except`; same swallow class, and these are `list` *reads*, not `extract-from-completed`). **Not in the original inventory** — surfaced by the 2026-06-30 re-verification pass. [Agent 1 finding]
- `.loops/distill-decisions.yaml:34,36` — `decisions extract-from-completed … 2>/dev/null || true`.
- `hooks/scripts/issue-completion-log.sh:77` — `decisions extract-from-completed --issue … >/dev/null 2>&1`.

_Wiring pass added by `/ll:wire-issue`:_
- `skills/wire-issue/static-coupling-layer.md:13,20` — `decisions list --type=coupling … 2>/dev/null` (Phase 3.5 coupling read used by `/ll:wire-issue` itself). No `|| true`, but the effect is identical: stderr is blackholed and the downstream logic keys only on empty/`[]` stdout, so an argparse exit 2 collapses into the "no coupling entries → skip to Phase 4" path — the same silent-failure class this bug targets. **Not in the refine-pass inventory.** Same-class candidate; belongs with the broader-family follow-on, not the core required-rule guardrail scope. [Agent 1 finding]

Net: the core fix touches **6 swallowing `list` invocations across 4 files** (format-issue ×2, ready-issue ×2, verify-issues ×1, improve-claude-md ×1), not "five `list` sites." The two `add` writes (go-no-go, improve-claude-md:267-273) are **out of scope — do not touch them in this bug**; they are a separate, lower-severity concern for a possible follow-on ENH.

_Re-verified 2026-06-30 (`/ll:refine-issue --auto`): all 6 in-scope `list` sites confirmed at their cited lines with **zero drift** — `format-issue/SKILL.md:187,190`, `ready-issue.md:189,192`, `verify-issues.md:69`, `improve-claude-md/SKILL.md:231`. The out-of-scope `add` writes and the `wire-issue/static-coupling-layer.md:13,20` same-class reads are likewise unchanged. `tradeoff-review-issues.md` in fact has **two** gated `add` writes (`296-304` and `348-356`) — both out of scope, noted only so the follow-on ENH counts them. One broader-family inventory addition is noted above (`distill-decisions.yaml:14,44`)._

## Expected Behavior

A decisions-check invocation must treat "the command errored" differently from
"the command succeeded and returned no rules":

1. A non-zero exit from `ll-issues decisions list` should surface (a warning to
   the operator and/or a non-suppressed finding), not be laundered into a clean
   pass.
2. `stderr` should not be blackholed to `/dev/null` when it may carry an
   argparse/usage error that indicates the guardrail didn't run.
3. The genuinely-optional case (decisions log absent) should still be a quiet,
   graceful skip — that behavior is correct and must be preserved.

## Motivation

The decisions guardrail is a correctness gate: it is supposed to catch when an
issue's proposed approach conflicts with an active required rule. A gate that
silently turns itself off on the first flag mismatch provides false assurance —
skills report "no decisions conflicts" while never having checked. The failure
is invisible precisely because it happens in the automation path where no human
inspects the intermediate command. This is the same silent-failure family as
[[BUG-2026]] (an invalid `--format` flag silently misrouted every EPIC) and
[[BUG-372]] (bare `except` swallowed GitHub query failures) — and the loop-side
`ll-loop validate` rule MR-10 already codifies "don't swallow parse failures and
exit 0." The skill invocation layer lacks the equivalent guard.

## Root Cause

The shell idiom `<cmd> 2>/dev/null || true` used at each decisions-check call
site is lossy by construction:

- `2>/dev/null` discards the diagnostic that would reveal a bad invocation.
- `|| true` normalizes every non-zero exit (including argparse exit 2) to 0.

The downstream logic keys only on whether stdout is empty, so a hard failure and
a legitimately empty result are the same signal. No call site inspects the exit
code or preserves stderr.

### Codebase Research Findings

_Added by `/ll:refine-issue` — the CLI exit-code contract (`scripts/little_loops/cli/issues/decisions.py`) is what makes the swallow recoverable once the caller stops discarding it:_

- **Argparse error** (unknown/malformed flag) → exit **2** with a usage message on **stderr**. This is raised inside `main_issues()` at `parser.parse_args()` (`cli/issues/__init__.py:733`), *before* `_cmd_list()` ever runs — there is no `try/except` around it, so `SystemExit(2)` propagates to the process boundary.
- **Any successful `list` path** → exit **0**. `_cmd_list()` (`decisions.py:334-382`) has no non-zero return of its own.
- **Missing `.ll/decisions.yaml`** → `load_decisions()` returns `[]` (`decisions.py:275-276`) → exit **0**, empty output (`(no entries)` in text, `[]` in json).

Consequence: at the CLI's own level, "file absent" and "zero matches" are *already* indistinguishable (both exit 0 / empty) — the **only** distinguishing signal is the argparse **exit 2 + stderr**, which is exactly what `2>/dev/null || true` collapses into the exit-0 case. Therefore a fix that (a) gates on `[ -f .ll/decisions.yaml ]` and (b) runs the query *without* `|| true` inside the gate makes any remaining non-zero exit unambiguously a real error, because the sole "clean empty" case (absent file) has already been handled by the gate.

The `--enforcement` flag fix referenced above has landed: `list` now registers `--enforcement` (`choices=["required","advisory"]`) at `decisions.py:71-76`, regression-tested by `scripts/tests/test_cli_decisions.py::TestDecisionsCLIList::test_list_filter_enforcement`.

_Re-verified 2026-06-30 (`/ll:refine-issue --auto`): every CLI-contract citation above is still exact — `parse_args()` at `cli/issues/__init__.py:733`, `_cmd_list()` at `cli/issues/decisions.py:334-382` (all paths `return 0`), `--enforcement` at `decisions.py:71-76`, regression at `test_cli_decisions.py:201-264`. **One disambiguation:** `load_decisions()`'s absent-file `return []` lives in the **data** module `scripts/little_loops/decisions.py:272-282` (the `if not resolved.exists(): return []` check is at `275-276`), not the identically-named CLI module `cli/issues/decisions.py` — the bare `decisions.py:275-276` citation resolves correctly but is ambiguous between the two same-named files. Also confirmed: `SystemExit(2)` from argparse propagates **uncaught** to the process boundary (`main_issues()` wraps its body in `cli_event_context`, which re-raises unmodified), so exit 2 + stderr remains the sole real-failure signal the hardened callers must key on. [Agent 2 finding]_

## Proposed Solution

Harden the 6 in-scope `decisions list` guardrail call sites (across 4 files) so a
command error is distinguishable from an empty result. Options, roughly in order of
preference:

1. **Capture status + stderr explicitly.** Replace `… 2>/dev/null || true` with a
   form that keeps the exit code, e.g. run the query, branch on `$?`: exit 0 →
   parse rows; exit ≠ 0 and decisions log present → emit an operator warning
   ("decisions check could not run: <stderr>") rather than a clean pass; skip
   only when `.ll/decisions.yaml` is genuinely absent.
2. **Distinguish "absent" up front.** Gate the query on `[ -f .ll/decisions.yaml ]`
   first (the legitimate skip), then run the query *without* `|| true` so a real
   error propagates instead of being masked.
3. **Prevention lint (optional, broader).** Add a check that validates the flags
   each skill/command passes to `ll-issues …` against the CLI's actual argparse
   definitions, so flag drift fails loudly in CI. Broader than this bug; could be
   split into its own ENH if pursued.

Apply the same pattern across all 6 in-scope `list`-read call sites (4 files) so
the fix lands consistently. The `add`-write sites (go-no-go, improve-claude-md:267-273)
are **out of scope — do not touch**; see "Explicitly OUT OF SCOPE" under Integration Map.

### Codebase Research Findings

_Added by `/ll:refine-issue` — options 1 and 2 are not really alternatives; the codebase evidence says to combine them:_

- **The house-style gate already exists.** The `[ -f .ll/decisions.yaml ]; then … fi` structural gate (option 2) is the established idiom for the sibling `decisions add` call sites: `commands/tradeoff-review-issues.md:296-306`, `skills/go-no-go/SKILL.md:406-416`, `skills/capture-issue/SKILL.md:309-319`, `skills/decide-issue/SKILL.md:373-383`. The `list` guardrail sites should converge on the same idiom rather than invent a new one.
- **Subtlety that forces the combination:** those gated `add` blocks *still keep* `2>/dev/null || true` **inside** the gate. The file gate alone (option 2) satisfies "distinguish absent up front" but does **not** stop a real failure from being swallowed — the inner `|| true` must *also* be dropped and the exit status branched on (option 1's substance). **Recommended fix = gate on file presence, run the query without `|| true`, and on non-zero exit emit an operator warning instead of a clean pass.**

> **Selected:** Combined Option 1 + Option 2 — gate each call site on `[ -f .ll/decisions.yaml ]` first (the legitimate skip), then run the `decisions list` query *without* `|| true` inside the gate and branch on `$?`, surfacing a non-zero exit as an operator warning instead of a clean pass. Per the stated recommendation above.

- **Best exit-branching model to copy:** `skills/confidence-check/rubric.md:126-137` captures stdout into a variable, checks `$?`, and treats "command failed" (`status=missing`) as a branch distinct from "succeeded with no data" — precisely the two-way distinction this bug needs.
- **Option 3 (prevention lint) has no existing test precedent.** No test under `scripts/tests/` cross-checks markdown `ll-issues …` flags against the CLI argparse. If pursued as its own ENH, the concrete templates are: the loop-side MR-10 guard `_validate_parse_swallow` (`scripts/little_loops/fsm/validation.py:1755-1801`; regexes at `123-130`; suppression flag `parse_swallow_ok` wired at `fsm/schema.py:1011`), and the markdown-regex-scan structure of `scripts/tests/test_ready_issue_lint.py`.

Options 1+2 collapse into one recommended fix (selected above) and are the scope of this bug. Option 3 (prevention lint) is explicitly separable and out of scope here — split into a follow-on ENH if pursued. Decided by `/ll:decide-issue` on 2026-06-30.

## Integration Map

### Files to Modify (in scope — the swallowing `decisions list` *reads* only)
- `skills/format-issue/SKILL.md` (Step 2.6, lines 187 & 190),
  `commands/ready-issue.md` (lines 189 & 192), `commands/verify-issues.md`
  (line 69), `skills/improve-claude-md/SKILL.md` (line 231) — the 6 swallowing
  `decisions list` guardrail invocations across these 4 files.

### Explicitly OUT OF SCOPE — do not touch
- `skills/go-no-go/SKILL.md:407-414` and `skills/improve-claude-md/SKILL.md:267-273`
  are `decisions **add**` *writes* (tail-of-skill bookkeeping), not the guardrail
  *reads* this bug targets. They are already file-gated, hardening them yields no
  correctness benefit to this bug, and `go-no-go` is an expensive LLM skill invoked
  directly from FSM loops — not a site to churn casually. Leave both unchanged.
  Any "drop the inner `|| true` on `add` writes" cleanup belongs in a separate
  follow-on ENH, where the `test_feat1896_skill_bridges.py` assertions (below) would
  be updated alongside it.

_Wiring pass added by `/ll:wire-issue`:_
- `skills/improve-claude-md/SKILL.md:231` is **not a drop-in swap** — it pipes the query straight into `grep`: `ll-issues decisions list --type rule 2>/dev/null | grep -i "${TOPIC_EXCERPT}" || true`. Under a plain (non-`pipefail`) pipeline `$?` reflects `grep`'s exit, not `list`'s, so the fix must capture the `decisions list` output into a variable *before* piping to `grep` and branch on that captured status. The other five sites are structurally uniform and map cleanly onto the capture-then-`$?` idiom. [Agent 2 finding]
- `skills/go-no-go/SKILL.md` (lines 407-414) is **out of scope for this bug — do not modify it** (see "Explicitly OUT OF SCOPE" above). For the record, dropping its inner `|| true` would also break a live assertion (`test_feat1896_skill_bridges.py:84`, see Tests below), which is one more reason to defer it to a dedicated follow-on rather than fold it in here. [Agent 3 finding]

### Dependent Files (Callers/Importers)
- `ll-issues decisions list` (`scripts/little_loops/cli/issues/decisions.py`) is
  the invoked CLI; its exit codes (0 = success, 2 = argparse error) are the
  contract the hardened invocations must key on.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_feat1896_skill_bridges.py:84` — `TestGoNoGoDecisionsBridge.test_graceful_degradation` asserts `"2>/dev/null || true" in body` for `skills/go-no-go/SKILL.md`. Because go-no-go is **out of scope here (do not touch)**, this test stays green in this bug — it is documented only as a tripwire for any *future* follow-on that hardens the `add`-write sites: that follow-on must update this assertion in the same change. Its three sibling assertions (lines 120/155/197) target `decide-issue`, `tradeoff-review-issues`, `capture-issue` — also `decisions add` writes, all out of scope — and likewise stay green. [Agent 3 finding]
- `skills/wire-issue/SKILL.md:125` loads `static-coupling-layer.md` (the additional same-class swallow site noted under Current Behavior); if that site is later hardened, `scripts/tests/test_wire_issue_static_layer.py` is the test that exercises it. [Agent 1 finding]
- Reference model for the exit-branch idiom: `skills/confidence-check/rubric.md` captures `result=$(ll-learning-tests check "$target" 2>/dev/null)` then branches on `if [ $? -eq 0 ] && [ -n "$result" ]` — the exact capture-then-`$?` shape the five uniform sites should copy. [Agent 2 finding, corroborates issue's Proposed Solution]

### Similar Patterns
- [[BUG-2026]] (invalid `--format` flag → silent misrouting) and [[BUG-372]]
  (bare-except swallowing) are the same silent-failure class in other paths.
- Loop-side rule MR-10 (`parse_swallow_ok`) in `.claude/CLAUDE.md` is the
  precedent guard for "don't swallow failures and exit 0"; the skill layer wants
  an analogous discipline.

### Tests
- No direct unit test surface for skill markdown. If the prevention lint (option
  3) is pursued, add a test under `scripts/tests/` asserting every documented
  `ll-issues …` invocation uses only real flags.

_Wiring pass added by `/ll:wire-issue` — the "no direct unit test surface" claim is only partly true; there is an established, idiomatic harness for exactly this kind of markdown-string assertion:_

**No test breaks in this bug's scope** (the four in-scope `list`-read files have no asserting test — confirmed by Agent 3):
- `scripts/tests/test_feat1896_skill_bridges.py:84` asserts `"2>/dev/null || true" in body` for `skills/go-no-go/SKILL.md`, but go-no-go is **out of scope / do not touch**, so this test stays green here. It is recorded only as a tripwire for a future `add`-write follow-on. See Dependent Files. [Agent 3 finding]

**New test to write (locks the fix — lightweight, idiomatic route):**
- `scripts/tests/test_wiring_skills_and_commands.py` — add parametrized rows to its existing `DOC_STRINGS_ABSENT` table (asserted via `test_string_absent_from_doc`, session-scoped `project_root` fixture from `conftest.py`) forbidding the decisions-list swallow needle (scope it specifically, e.g. `--active-only 2>/dev/null || true`, to avoid catching unrelated future `2>/dev/null || true` usage) in the four target files, tagged `BUG-2423`; optionally mirror with `DOC_STRINGS_PRESENT` rows asserting the `[ -f .ll/decisions.yaml ]` gate is now present. This is the shift-left guard that stops the next flag/arg drift silently — the concrete, low-cost form of the issue's Option 3. [Agent 3 finding]

**Heavier alternative (only if Option 3 becomes a real regex validator):** model on `scripts/tests/test_fsm_validation.py::TestParseSwallow` (positive-fire / variant / clean / suppression-flag / wired-into-`validate_fsm` shape) with regexes styled after `_validate_parse_swallow` (`scripts/little_loops/fsm/validation.py:123-130,1755-1801`) and fence-scoping from `_CODE_FENCE`/`_FILE_LINE` in `little_loops/issues/anchor_sweep.py` (as used by `scripts/tests/test_ready_issue_lint.py:54-91`). [Agent 3 finding]

**No coverage today:** `skills/improve-claude-md/SKILL.md:231` — `scripts/tests/test_improve_claude_md_skill.py` has zero references to `decisions` or `2>/dev/null`, so that call site is entirely untested. [Agent 3 finding]

**Historical prose (no update needed):** `scripts/tests/test_cli_decisions.py:214` mentions the old idiom inside a docstring describing the original regression — not a live content assertion, will not break. [Agent 3 finding]

_Re-verified 2026-06-30 (`/ll:refine-issue --auto`) — exact current anchors for the new test (zero drift from the wire-issue pass): the `DOC_STRINGS_ABSENT` table is at `test_wiring_skills_and_commands.py:208-233`, asserted by `test_string_absent_from_doc` (`:236-242`); the optional `DOC_STRINGS_PRESENT` mirror is at `:20-194`, asserted by `test_string_present_in_doc` (`:197-203`); the session-scoped `project_root` fixture is at `conftest.py:118-121`. Copy-paste model for a new ABSENT row (`:210`): `("agents/codebase-analyzer.md", "file:line", "ENH-1299")` — a `(doc_rel, needle, issue_id)` 3-tuple. [Agent 3 finding]_

### Documentation
- N/A — the change is to invocation hygiene inside skill/command bodies; no
  user-facing doc describes the swallowing behavior.

_Wiring pass added by `/ll:wire-issue`:_
- Confirmed clean (no change needed): `docs/reference/CLI.md` (`ll-issues decisions` section), `docs/guides/DECISIONS_LOG_GUIDE.md`, `docs/reference/COMMANDS.md`, and `docs/reference/API.md` all document `decisions list`/`add` usage but contain **no** `2>/dev/null || true` idiom — no shipped doc teaches the swallow pattern, so none need editing. [Agent 2 finding]
- FYI only (do not edit — completed/historical issue): `.issues/features/P3-FEAT-1893-decisions-log-validation-autogen-tests-docs.md` is the origin design doc that introduced these six call sites and explicitly recommends `ll-issues decisions list … 2>/dev/null || true` as the "graceful degradation" pattern, with exact `format-issue`/`ready-issue` snippets. Per project convention completed issues aren't retroactively edited, but it's the one place a future contributor could copy the anti-pattern from (via `ll-session`/`ll-history-context`), which reinforces the value of the prevention-lint above. [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified integration surface:_

- **Files to modify (corrected):** `skills/format-issue/SKILL.md` (lines 187 **and** 190), `commands/ready-issue.md` (lines 189 **and** 192), `commands/verify-issues.md` (line 69), `skills/improve-claude-md/SKILL.md` (line **231**, not 273). See the corrected inventory under **Current Behavior**. **Out of scope — do not touch:** the `add`-write sites `skills/go-no-go/SKILL.md:407-414` and `skills/improve-claude-md/SKILL.md:267-273` (deferred to a possible follow-on ENH; see "Explicitly OUT OF SCOPE" under Files to Modify).
- **Test/lint surface for option 3:** existing producer-side regression `scripts/tests/test_cli_decisions.py::TestDecisionsCLIList::test_list_filter_enforcement` proves the `--enforcement` flag is accepted but does **not** lint the caller markdown. A consumer-side flag-drift lint does not yet exist; `scripts/tests/test_ready_issue_lint.py` (markdown-regex scan) is the nearest structural template, and MR-10's `_validate_parse_swallow` (`scripts/little_loops/fsm/validation.py:1755-1801`) is the loop-side precedent for shifting a swallow guard left.

## Impact

- **Priority**: P3 — the guardrail was fully dormant across the 6 in-scope `list`
  call sites, but real-world impact was nil because all active rules are `advisory`
  and the check only flags `required` rules (of which there are currently zero).
  The risk is latent recurrence: the next flag/arg drift will silently disable the
  gate again. Not P2 because nothing is being missed today; not P4 because it
  defeats a correctness gate by design.
- **Effort**: Small — a mechanical, repeated edit across the 6 in-scope `list`
  markdown call sites in 4 files (plus an optional, separable lint). The `add`-write
  sites (go-no-go, improve-claude-md:267-273) are explicitly excluded. No production
  Python change required for the core fix.
- **Risk**: Low — the change only makes existing failures visible; the graceful
  "decisions log absent" skip must be preserved so quiet no-op remains the
  behavior when the feature is genuinely off.

## Confidence Check Notes

_Re-verified by `/ll:confidence-check` on 2026-07-01 (post refine-issue/wire-issue/decide-issue passes) — all six in-scope call sites and CLI-contract citations confirmed at their stated lines with zero drift; scores unchanged from the prior check._

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- Broad enumeration across 6 call sites in 4 files (format-issue ×2, ready-issue ×2, verify-issues ×1, improve-claude-md ×1) — each needs the same file-gate + branch-on-`$?` treatment applied consistently; the improve-claude-md:231 site pipes into `grep`, which needs its own captured-then-piped variant so a non-`pipefail` shell doesn't mask the `decisions list` exit code.
- The 4 in-scope files have no dedicated regression test for this behavior today; the fix should land its own test extension (`test_wiring_skills_and_commands.py` `DOC_STRINGS_ABSENT`/`DOC_STRINGS_PRESENT` rows, per the issue's Tests section) in the same change so the swallow pattern can't silently reappear.

## Resolution

_Resolved 2026-07-01 via `/ll:manage-issue` (TDD mode)._

Hardened all **6 in-scope `decisions list` guardrail reads across 4 files** to the
combined Option 1 + Option 2 idiom (per `/ll:decide-issue`): gate on
`[ -f .ll/decisions.yaml ]` (the sole legitimate clean-empty case), then run the query
**without `|| true`** and **without blackholing stderr**, branching on `$?` so a
non-zero exit surfaces as an operator `⚠ [DECISIONS]` warning instead of a clean pass.

- `skills/format-issue/SKILL.md` (Step 2.6) — required-rule read + companion exception lookup.
- `commands/ready-issue.md` (Decisions Gate) — required-rule read (`--format json`) + exception lookup; failure now maps to a `Decisions | WARN` row, not a silent PASS.
- `commands/verify-issues.md` (Step B.5) — required-rule read.
- `skills/improve-claude-md/SKILL.md` (Step CT-1) — dedup lookup; special-cased the piped-into-`grep` site by capturing `decisions list` output into a variable **before** piping, so a non-`pipefail` shell doesn't mask the query's exit code.

**Explicitly untouched (out of scope):** the `decisions add` *writes* at
`skills/go-no-go/SKILL.md:407-414` and `skills/improve-claude-md/SKILL.md:267-273`
(deferred to a possible follow-on ENH); the `test_feat1896_skill_bridges.py:84` tripwire
that asserts go-no-go still contains `2>/dev/null || true` stays green.

**Regression guard (shift-left):** added 10 parametrized rows to
`scripts/tests/test_wiring_skills_and_commands.py` tagged `BUG-2423` — 6
`DOC_STRINGS_ABSENT` rows forbidding each scoped swallow needle, 4 `DOC_STRINGS_PRESENT`
rows requiring the `[ -f .ll/decisions.yaml ]` gate. Validated Red (10 fail on
unmodified files) → Green (10 pass after fix). Full suite: 13295 passed, 23 skipped;
the single failure (`test_enh494_skill_companions.py` — `manage-issue/SKILL.md` at 523
lines) is **pre-existing and unrelated** (that file was 523 at HEAD, untouched here).

## Session Log
- `/ll:manage-issue` - 2026-07-01T03:42:34Z - `cbb70290-2b30-4d37-91f5-4b7f426bbf3d.jsonl`
- `/ll:ready-issue` - 2026-07-01T03:16:01 - `b1d80d1f-950b-4ab3-8971-1af05b6c69db.jsonl`
- `/ll:confidence-check` - 2026-07-01T03:13:40Z - `f5cfb802-e8d7-4866-bd77-17b0c742c10a.jsonl`
- `/ll:refine-issue` - 2026-07-01T03:09:46 - `c697f748-585d-498e-adef-1039d691c458.jsonl`
- `/ll:confidence-check` - 2026-06-30T00:00:00Z - `55bf24de-5192-4d0e-ba1f-250ed1f1abb1.jsonl`
- `/ll:wire-issue` - 2026-07-01T02:52:20 - `3e394fcf-f454-4f27-83c8-04afb80965f0.jsonl`
- `/ll:decide-issue` - 2026-07-01T02:43:18 - `457ad308-c7c0-49a8-936f-f80f8ed18900.jsonl`
- `/ll:refine-issue` - 2026-07-01T02:39:12 - `30fa61b7-db73-4b9c-a30e-09f0a8263487.jsonl`
- `/ll:format-issue` - 2026-07-01T02:28:06 - `405ec4c6-0c9e-4416-a7e8-50f7289cc53e.jsonl`
- `/ll:capture-issue` - 2026-07-01T02:24:04Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/94f01e4a-8995-4dd3-9a06-d06181dd9822.jsonl`

## Status

**Done** | Created: 2026-07-01 | Completed: 2026-07-01 | Priority: P3
