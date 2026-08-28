---
id: BUG-3349
type: BUG
title: loop-router finalize_present_result parses model output unanchored and interpolates
  it into Python literals
priority: P2
status: done
discovered_by: split-from-BUG-3334
discovered_date: '2026-08-28'
captured_at: '2026-08-28T00:00:00Z'
completed_at: '2026-08-28T01:46:12Z'
decision_needed: false
confidence_score: 96
outcome_confidence: 84
score_complexity: 22
score_test_coverage: 15
score_ambiguity: 22
score_change_surface: 25
---

# BUG-3349: loop-router finalize_present_result parses model output unanchored and interpolates it into Python literals

## Summary

Spun out of BUG-3334 (Proposed Solution item 1, "Item 1 covers the whole block")
so it can land independently of the fencing design work. It fixes the only
defect in BUG-3334 that silently flips a pass/fail outcome.

`loop-router.yaml`'s `finalize_present_result` state (lines 509-558, a
`python3 << 'PYEOF'` quoted heredoc) contains **four** unanchored parses over
model output and **two** raw triple-quoted interpolations of model output into
Python string literals. All six sit within one 50-line block and are one edit.

## Current Behavior

| Line | Construct | Defect |
|---|---|---|
| 522 | `proposal_out = """${captured.new_loop_proposal.output:default=}"""` | raw `"""`-literal interpolation of model output — a `"""` in the value is a `SyntaxError` |
| 523 | `review_out = """${captured.review_result.output:default=}"""` | same shape, same consequence |
| 524 | `has_proposal = 'PROPOSED_NAME:' in proposal_out` | bare substring test over model output that **selects the entire result branch** — the widest consequence of the six |
| 527 | `_field()`: `re.search(key + r':(.*)', proposal_out)` | unanchored first-match over model output, for every `PROPOSED_*` field |
| 544 | `re.search(r'REVIEW_SUCCESS:(true|false)', review_out, re.IGNORECASE)` | unanchored first-match — the verdict flip |
| 545 | `re.search(r'REVIEW_SUMMARY:(.*)', review_out)` | unanchored first-match |

## Steps to Reproduce

Verdict flip, line 544:

1. Run `loop-router` with any goal that dispatches to a sub-loop.
2. Have the sub-loop's output contain the literal text `REVIEW_SUCCESS:false`
   anywhere — it need not be adversarial; a loop that *discusses* the router
   protocol, echoes a prior run, or quotes an issue file produces it
   incidentally.
3. The `review` state summarises a stream containing that token. If the model
   quotes or restates any part of the stream in `REVIEW_SUMMARY`, the token
   appears in `review_result`.
4. The unanchored `re.search` takes the **first** match anywhere in the text.
   An echoed token earlier in the output beats the model's actual verdict line.

## Expected Behavior

- **Lines 524/527/544/545**: anchor to line start with `re.MULTILINE`
  (`has_proposal` becomes an anchored `re.search`, not an `in` test), first
  match throughout.

  **Anchor + first match is the required form; last-match is strictly worse**
  (per BUG-3334's review pass): the state's required output is
  `REVIEW_SUCCESS:` on line 1 and `REVIEW_SUMMARY:` on line 2, and the echo
  risk lives *inside the summary* — so an echoed token is precisely the last
  match in the text. Last-match would prefer the echo over the real verdict in
  exactly the scenario this issue fixes.
- **Lines 522-523**: bind the captures to environment variables and read them
  via `os.environ` rather than interpolating into a Python literal. The
  `:shell` interpolation modifier (`interpolation.py:254`, shlex-quotes the
  resolved value) **already exists on the current tree** — this fix does not
  need BUG-3340 to land first; it applies BUG-3340's idiom locally:

  ```yaml
  action: |
    LL_PROPOSAL_OUT=${captured.new_loop_proposal.output:shell:default=} \
    LL_REVIEW_OUT=${captured.review_result.output:shell:default=} \
    python3 << 'PYEOF'
    import os
    proposal_out = os.environ.get('LL_PROPOSAL_OUT', '')
    review_out   = os.environ.get('LL_REVIEW_OUT', '')
    ...
  ```

  (Exact spelling at implementation time; the requirement is that no captured
  model output appears inside a Python string literal.)

- **Prerequisite: `interpolation.py` must allow `:shell` to compose with a
  missing-path fallback.** On the current tree, `:shell` is mutually
  exclusive with both `:default=` and `?` (`interpolation.py:242-250`), and
  a bare `:shell` on a missing path propagates `InterpolationError` — the
  `except` clause at `interpolation.py:275-280` only rescues when
  `default_value` or `nullable` is set. This matters because the two
  captures live on **mutually exclusive branches**: `review_result` is
  captured only on the dispatch path (`loop-router.yaml:438`) and
  `new_loop_proposal` only on the propose path (line 478), so exactly one
  of them is always missing when `finalize_present_result` runs — that is
  why the current code carries `:default=`. A bare-`:shell` binding as
  originally drafted here would raise on **every** run, and since
  interpolation happens before bash executes, the Python-side
  `os.environ.get(..., '')` default never gets a chance; the action would
  fail wholesale and route to `finalize_failed`.

  Required change: support the combined form `${...:shell:default=<v>}` in
  `interpolation.py` — resolve the path; on a missing path substitute `<v>`;
  shlex-quote whatever value is emitted (resolved or fallback). Parsing note:
  the existing `:default=`-first split already sees `var_part` ending in
  `:shell` and raises "Ambiguous suffix" (`interpolation.py:242-248`) —
  that branch becomes the legal combined form. Bare `:shell` on a missing
  path stays an error (unchanged). The unsafe alternative — a double-quoted
  bash assignment with `?` — is rejected: `$(...)`/backticks in model output
  would execute.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- **Files to Modify**: `scripts/little_loops/loops/loop-router.yaml` — `finalize_present_result` state, lines 509-558 (confirmed unchanged from issue's cited range); `scripts/little_loops/fsm/interpolation.py` — suffix parser in `replace_var()` (lines 230-280) gains the `:shell:default=` combined form (see Expected Behavior prerequisite)
- **Dependent Files (Callers/Importers)**: `scripts/tests/test_loop_router.py` — `TestLoopRouterStates.REQUIRED_STATES` (lines 76-97) exercises `loop-router.yaml` states but does not currently include `finalize_present_result`; `scripts/little_loops/fsm/executor.py:2864` — `action_type == "shell"` execution path that runs this heredoc
- **Convention**: every other captured-model-output parse site in this codebase uses the same unanchored first-match `re.search` shape this issue fixes (`loop-router.yaml:202-205,270-273`; `lib/rubric-router.yaml:77`; `lib/policy-router.yaml:88`; `goal-cluster.yaml:210,567,643`; `loop-composer-adaptive.yaml:527,579`; `apply-research.yaml:171,309`; `rn-build.yaml:534,537,641`). This issue's fix would be the first `re.MULTILINE`-anchored parse of captured model output anywhere in the codebase — the sole existing `re.MULTILINE` hit (`autodev.yaml:417`) parses static issue-body markdown, not model/loop output.
- **Convention**: the `:shell` interpolation modifier (`scripts/little_loops/fsm/interpolation.py:254-256`; mutual exclusivity with `:default=` enforced at lines 242-250) is used at 11+ sites across loop YAMLs, always binding `${context.*}` values (task/description/config strings). No existing site applies `:shell` to a `${captured.*}` reference — this fix's `${captured...:shell}` usage has no direct precedent confirming the combination works, though nothing in `interpolation.py` restricts `:shell` to the `context` namespace.
- **Convention**: the `os.environ.get(...)` heredoc-read idiom has independent precedent (`auto-refine-and-implement.yaml:783`, `autodev.yaml:408`, `rn-refine.yaml:922-931`, `oracles/generator-evaluator-flux.yaml:93-99`) but is always fed by bash-local or `context.*`-derived variables, never by a `captured.*:shell` binding directly.
- A sibling raw-literal-interpolation site exists at `loop-router.yaml:201` (`output = """${captured.project_score.output}"""`, in `parse_project_score`) — same defect shape as this issue's lines 522-523, explicitly out of scope per the issue's own Scope boundary section.
- **Tests**: `scripts/tests/test_builtin_loops.py` — the issue's cited "`TestClassifyTerminal._run_classify_terminal`" precedent is actually `TestRefineToReadyIssueSubLoop._run_classify_terminal` (staticmethod, lines 2120-2139), which tests `refine-to-ready-issue.yaml`'s `classify_terminal` state — there is no class literally named `TestClassifyTerminal`. The technique it uses (substituting `${captured.*}` refs via a generic regex + dict lookup) is unique to this one helper; no shared/importable action-extraction utility exists in the file — every test site inlines `data["states"][...]["action"]`.
- `scripts/tests/test_loop_router.py` — `TestLoopRouterStates.REQUIRED_STATES` (lines 76-97) does not currently include `finalize_present_result`.
- **Documentation**: `docs/reference/API.md`, `docs/reference/CLI.md`, `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` reference the `:shell` modifier generally; none document a `captured.*:shell` pattern.

## Program Design

### Types

No new types; `finalize_present_result` is a `python3 << 'PYEOF'` heredoc
embedded in `loop-router.yaml`'s `action:` field, not a standalone Python
module.

### Signatures

- `_field(key: str) -> str` — existing helper inside the heredoc
  (`loop-router.yaml:~527`); its internal search becomes
  `re.search('^' + key + r':(.*)', proposal_out, re.MULTILINE)` — the `^`
  anchor is required alongside the flag (`re.MULTILINE` without `^` changes
  nothing).
- `interpolate()` / `replace_var()` (`scripts/little_loops/fsm/interpolation.py:230-280`)
  — the suffix parser gains the combined `:shell:default=<v>` form: on the
  `:default=` split, a `var_part` ending in `:shell` no longer raises
  "Ambiguous suffix"; instead it sets both `shell_quote` and
  `default_value`, and the fallback value is shlex-quoted on emission the
  same as a resolved value. `?` + `:shell` remains unsupported; bare
  `:shell` on a missing path remains an error.
- Module-level heredoc statements (not functions) change shape:
  - `has_proposal = bool(re.search(r'^PROPOSED_NAME:', proposal_out, re.MULTILINE))`
    replaces the current `'PROPOSED_NAME:' in proposal_out` substring test.
  - `re.search(r'^REVIEW_SUCCESS:(true|false)', review_out, re.IGNORECASE | re.MULTILINE)`
    replaces the current unanchored form.
  - `re.search(r'^REVIEW_SUMMARY:(.*)', review_out, re.MULTILINE)` replaces
    the current unanchored form.
  - `proposal_out = os.environ.get('LL_PROPOSAL_OUT', '')` and
    `review_out = os.environ.get('LL_REVIEW_OUT', '')` replace the
    `"""${captured...}"""` literal interpolations.

### Call Path

`loop-router.yaml` FSM executor -> `finalize_present_result` state's
`action:` bash block -> `LL_PROPOSAL_OUT`/`LL_REVIEW_OUT` env vars (bound via
`${captured...:shell}`) -> embedded `python3` heredoc -> `_field()` /
inline `re.search` calls -> printed JSON consumed by the state's
`evaluate:`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-28 — based on codebase analysis:_

- **Call Path correction**: `finalize_present_result` has **no `capture:` and
  no `evaluate:` key** — the Call Path description above ("printed JSON
  consumed by the state's `evaluate:`") does not match current behavior. The
  state's `python3` heredoc prints JSON to stdout only; the state routes
  unconditionally via `next: present_result` (line 557) to the terminal
  `present_result` state (lines 559-560, no action of its own).
  `on_error: finalize_failed` (line 558) is the only alternate route, taken
  only if the `python3` invocation itself exits non-zero — not based on the
  printed JSON's content. Confirmed via
  `scripts/little_loops/loops/loop-router.yaml:509-560`.
- **MR-11 validation gap** (relevant to Acceptance Criteria's
  `ll-loop validate` check): `scripts/little_loops/fsm/validation/shell_safety.py`'s
  MR-11 rule (`_UNSAFE_CONTEXT_INTERP_RE`, lines 33-35) only matches
  `${context.(input|goal|description|task|prompt|query|topic)...}` tokens —
  it never matches `${captured.*}`, the namespace this issue's six defect
  sites actually use. Separately, `_find_unsafe_context_interpolations`
  (lines 148-188) treats a quoted heredoc (`<<'PYEOF'`) as a safe position
  and skips scanning inside it entirely. Net effect: `ll-loop validate` did
  not flag these six sites before the fix and will not validate the fix's
  correctness after — it only confirms the file still parses/lints, not that
  the anchoring or env-var binding is correct. The Acceptance Criteria's
  `ll-loop validate` check is a schema/lint gate, not evidence of this bug's
  fix.

## Tests

No test loads or executes `finalize_present_result` today (0 hits in
`scripts/tests/test_builtin_loops.py`). Write one from scratch following the
`TestRefineToReadyIssueSubLoop._run_classify_terminal` precedent
(`test_builtin_loops.py:2120-2139`): extract the state's raw `action:` text,
substitute `${captured.*}` refs with synthetic values, run via
`subprocess.run(["bash", "-c", script], ...)`, assert on the printed JSON.

**Substitution must mirror runtime quoting**: after this fix the refs carry
`:shell:default=`, so the test's substitution regex must match that suffix
and replace each ref with the `shlex.quote()`d synthetic value (missing
capture → `shlex.quote('')`). Substituting raw unquoted text would make the
triple-quote case pass for the wrong reason — at runtime the value reaches
Python via the env var, and the test only exercises that path if its
substitution quotes the same way interpolation does.

Cases to cover at minimum:

1. **Decoy verdict**: `review_result.output` containing a decoy
   `... REVIEW_SUCCESS:false ...` inside the summary text after a real
   line-anchored `REVIEW_SUCCESS:true` — asserts `success: true`.
2. **Triple-quote survival**: `new_loop_proposal.output` containing `"""` —
   asserts the block runs without `SyntaxError` (fails on the current tree).
3. **Branch selection**: `PROPOSED_NAME:` appearing mid-line inside prose in
   `review_result`-era proposal output does not select the `propose_new`
   branch; a line-anchored `PROPOSED_NAME:` does.
4. **Missing-capture interpolation** (unit tests in
   `scripts/tests/test_fsm_interpolation.py`, alongside the existing
   `:shell` suite at ~line 845): `${captured.x.output:shell:default=}` on a
   missing path emits `''` (shlex-quoted empty); on a present path emits the
   shlex-quoted value; bare `:shell` on a missing path still raises
   `InterpolationError`. This case cannot be covered by the heredoc-extraction
   test — the failure mode lives at interpolation time, before bash runs.

## Acceptance Criteria

- [ ] All four parses (lines 524, 527, 544, 545) are line-start-anchored with
      `re.MULTILINE`, first match.
- [ ] Neither `${captured.new_loop_proposal.output}` nor
      `${captured.review_result.output}` appears inside a Python string
      literal; both reach Python via environment variables.
- [ ] `interpolation.py` supports `${...:shell:default=<v>}` (shlex-quoted
      fallback on missing path); bare `:shell` on a missing path still raises;
      unit tests in `test_fsm_interpolation.py` cover both (Tests case 4).
- [ ] A regression test executes the heredoc with the three synthetic-input
      cases above and passes, substituting refs with shlex-quoted values.
- [ ] `ll-loop validate` passes on `loop-router.yaml`.
- [ ] Full suite (`python -m pytest scripts/tests/`) shows no new failures.

## Scope boundary

This issue owns `loop-router.yaml:509-558` only. Sibling unanchored-`re.search`
sites elsewhere (`lib/rubric-router.yaml:77`, `lib/policy-router.yaml:88`,
`loop-router.yaml:202-205,270-273`, `goal-cluster.yaml:210,567,643`,
`loop-composer-adaptive.yaml:527,579`, `apply-research.yaml:171,309`) extract
scores/plans/IDs rather than a boolean verdict — recorded in BUG-3334's wiring
pass, deliberately not folded in here.

Fencing of the prompts that *produce* these captures is BUG-3334 (items 2
onward). Same source values, different sink, different remedy.

## Dependencies

- **BUG-3334** — parent; its Proposed Solution item 1 is this issue in full.
  BUG-3334's Dependencies research established no other open issue owns lines
  522-523 (BUG-3331 cancelled; BUG-3339 cites this block as an already-safe
  example, not a target).
- **BUG-3340** — file-level contention only: it edits `loop-router.yaml` at
  lines 34, 53, 192, 252, 345 — outside this block. No sequencing requirement;
  the `:shell` idiom it standardises already exists in `interpolation.py`.
  Note: this issue now also edits `interpolation.py` (the `:shell:default=`
  combined form) — a capability addition BUG-3340's standardisation can reuse,
  but a second file-level contention point to be aware of if both run in
  parallel.

## Impact

- **Priority**: P2 — an incidentally-echoed token silently flips a success
  verdict; blast radius is a wrong success/failure summary, not data loss.
- **Effort**: Small — one heredoc block, a ~10-line suffix-parser change in
  `interpolation.py`, and two new test additions.
- **Risk**: Low.
- **Breaking Change**: No.

## Status

**Open** | Created: 2026-08-28 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-28T01:45:55 - `55433ce7-efd7-423d-a202-3e46531f233e.jsonl`
- `/ll:confidence-check` - 2026-08-28T01:34:41 - `e8e3b913-2614-4686-b293-63402787dd9d.jsonl`
- `/ll:confidence-check` - 2026-08-28T01:28:58 - `286a27cf-122d-45a3-9474-592c93a3cfca.jsonl`
- `/ll:refine-issue` - 2026-08-28T01:20:27 - `7cbe469c-9cbd-4824-b712-5ef6f08221f0.jsonl`
- `/ll:format-issue` - 2026-08-28T01:14:44 - `52d1fdcc-59ae-4471-83fd-cc9439286464.jsonl`
