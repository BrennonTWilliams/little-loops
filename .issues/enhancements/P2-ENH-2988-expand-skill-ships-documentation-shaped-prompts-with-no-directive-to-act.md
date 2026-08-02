---
id: ENH-2988
title: expand_skill ships documentation-shaped prompts with no directive to act
type: ENH
priority: P3
status: open
captured_at: '2026-08-02T00:00:00Z'
discovered_date: 2026-08-02
discovered_by: capture-issue
relates_to:
- ENH-2989
labels:
- automation
- resilience
- skill-expander
testable: true
confidence_score: 95
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-2988: expand_skill ships documentation-shaped prompts with no directive to act

## Summary

`skill_expander.expand_skill` turns a skill/command Markdown file into a
self-contained prompt by substituting `$ARGUMENTS` in place. For most skills
that token sits in a trailing `## Arguments` reference section, so the expanded
prompt reads as *documentation of a command* rather than a request to run it —
the only actionable content is a bare ID hundreds of lines in, followed by
`## Examples` and `## Integration` boilerplate.

A model can, and demonstrably does, read that as reference material and decline
to act. Append an imperative execution tail when args are present, so every
pre-expanded skill states plainly what it is asking for.

## Current Behavior

`expand_skill` (`scripts/little_loops/skill_expander.py:99-136`) returns the
substituted body verbatim. Nothing is appended.

For `ready-issue`, `$ARGUMENTS` is at `commands/ready-issue.md:489` of 546 —
alone under `## Arguments`, with 57 further lines of examples and integration
notes after it. The expanded prompt is 25,611 chars and opens with a
`# Ready Issue` heading.

Observed consequence, run `.loops/runs/autodev-20260801T214427/`: `ll-auto`
Phase 1 sent that prompt and the model replied, in full:

> I don't see an actual request in your message — just system context. What
> would you like me to help with?

Exit 0, seven seconds, no tool calls (session
`aaf47f73-e638-4d68-acb7-13fe44e851a1`). The verdict parsed to `UNKNOWN` and a
14m17s / $1.33 autodev run was discarded at its final step.

The failure is probabilistic, not deterministic: a byte-identical prompt shape
21 minutes earlier (session `3aed3356`, also exactly 25,611 chars, `BUG-2985`
in place of `ENH-2971`) worked correctly with 11 tool calls.

Every other `expand_skill` caller ships the same prompt shape. `ready-issue` is
simply the one with a verdict parser sensitive enough to notice.

## Expected Behavior

When `args` is non-empty, `expand_skill` appends a short imperative tail naming
the target, so the expanded prompt cannot be mistaken for reference material.

Callers that pass no args are unaffected.

## Program Design

The change is a pure string transform at the tail of one function. No model
call, no new I/O.

### Signatures

```python
# scripts/little_loops/skill_expander.py — existing, unchanged signature
def expand_skill(name: str, args: list[str], config: BRConfig) -> str | None

# new module-level helper in skill_expander.py
def _append_execution_directive(body: str, name: str, args: list[str]) -> str

# scripts/little_loops/ready_issue.py — becomes a re-export
IMPERATIVE_TAIL: str
```

### Call Path

`expand_skill` (`scripts/little_loops/skill_expander.py:99-136`) currently ends
with `body = _substitute_arguments(body, args)` then `return body`. The new
helper slots in immediately after `_substitute_arguments`, mirroring the
existing `_substitute_config` / `_substitute_relative_refs` /
`_substitute_arguments` chain — same shape, same failure semantics (the whole
function is already wrapped in `except Exception: return None`).

Callers, all unchanged: `issue_manager.process_issue_inplace`
(`scripts/little_loops/issue_manager.py:725`, ready-issue), the manage-issue
expansion later in the same function, and
`ready_issue.build_retry_command` (`scripts/little_loops/ready_issue.py:51-68`),
which stops appending its own tail once `expand_skill` does it.

`_substitute_arguments` returns the body unchanged when `args` is empty, so the
`args`-empty guard belongs in the new helper, not the caller.

### Open questions for refinement

- Whether the tail should be uniform across skills or parameterized per skill
  (some skills' bodies already end imperatively and would read oddly).
- Whether a skill can opt out via frontmatter, for bodies where a trailing
  directive would conflict with the documented output contract.
- Whether appending changes any existing golden-prompt test expectations —
  `scripts/tests/test_skill_expander.py` asserts on expanded bodies.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Two more call sites than listed above, same shape.** `process_issue_inplace`
  (`scripts/little_loops/issue_manager.py:619`) calls `expand_skill` four times,
  not two: `issue_manager.py:725` (ready-issue initial attempt, cited above),
  `issue_manager.py:792` (ready-issue path-mismatch retry fallback, not
  previously listed), `issue_manager.py:957` (`decide-issue` — a caller not
  previously listed at all), and `issue_manager.py:1053` (manage-issue, cited
  above as "the manage-issue expansion later in the same function"). All four
  pass the return value straight to `run_claude_command`/`run_with_continuation`
  with no local tail-appending logic, so all four are equally in scope and
  equally safe as unmodified callers.
- **`_substitute_arguments`'s empty-args behavior is not "unchanged."**
  `_substitute_arguments("Args: $ARGUMENTS", [])` returns `"Args: "` — the
  token is replaced with an empty string, not left as-is (confirmed by
  `test_empty_args`, `scripts/tests/test_skill_expander.py:159-161`, and
  exercised end-to-end via `expand_skill(..., [], config)` in
  `TestExpandSkill`, `test_skill_expander.py:210-250`). The args-empty guard
  for `_append_execution_directive` therefore needs to branch on `args` itself
  (`if not args: return body`), not on whether `$ARGUMENTS` substitution
  produced a change — those are different conditions.
- **Double-append confirmed, not just anticipated.** If
  `_append_execution_directive` moves into `expand_skill`, `build_retry_command`
  (`scripts/little_loops/ready_issue.py:65-68`) must stop concatenating its own
  `IMPERATIVE_TAIL` — verified by tracing the retry path: today it is the one
  caller that already appends a tail after `expand_skill` returns, so leaving
  its `+ IMPERATIVE_TAIL.format(target=target)` in place after the move would
  stack two directives on every retry prompt.
- **Frontmatter opt-out precedent exists and directly answers the second open
  question above.** `disable-model-invocation` is the codebase's one existing
  per-skill boolean opt-out flag, read via `parse_skill_frontmatter()`
  (`scripts/little_loops/frontmatter.py:371`) and checked identically at five
  call sites (`cli/verify_skill_prose.py:168-170`,
  `cli/generate_skill_descriptions.py:110`, `doc_counts.py:365,414`,
  `cli/doctor_trim.py:162` inverted, `adapters/core.py:187`) via
  `fm.get("disable-model-invocation", "").lower() in ("true", "yes", "1")`.
  No shared helper factors this out — each site repeats the tuple literal.
  Note `expand_skill` currently discards frontmatter entirely (calls
  `strip_frontmatter(raw)` and never `parse_skill_frontmatter`/
  `parse_frontmatter`), so wiring a comparable opt-out here would require
  parsing frontmatter from `raw` before stripping it.
- **No pipeline abstraction to extend.** The `_substitute_config` /
  `_substitute_relative_refs` / `_substitute_arguments` chain is three
  hardcoded sequential reassignments of `body` (`skill_expander.py:131-133`),
  not a list-driven transform pipeline — a codebase-wide grep for a
  `TRANSFORMS = [...]` / `for transform in ...` idiom found none. Adding
  `_append_execution_directive` as a fourth sequential call after
  `_substitute_arguments` (before `return body` at `skill_expander.py:134`)
  matches the only pattern present; introducing a pipeline abstraction here
  would be a novel shape, not a consistency improvement.
- **Test suite won't collide, mostly answering the third open question.**
  Every `expand_skill`-level assertion in `test_skill_expander.py` is a
  substring/absence check (`"$ARGUMENTS" not in result`, `"..." in result`),
  never full-string equality — only the isolated pure-transform functions
  (`_substitute_config`, `_substitute_arguments`, etc.) are asserted with
  `==`. Appending trailing content to `expand_skill`'s composed output is
  unlikely to break existing `TestExpandSkill`/
  `TestExpandSkillAgainstRealManageIssue` assertions structurally.
- **Re-export convention for `IMPERATIVE_TAIL`.** This codebase's established
  shape for "symbol moved, old location re-exports" pairs a `# noqa: F401`
  import with a short prose comment stating the reason (wording varies —
  "for backward compatibility", "for tests/lint" — but the pairing is
  consistent). Examples: `adapters/codex.py:14-18`,
  `cli/sprint/__init__.py:8-9,28`, `cli/loop/info.py:27,38`,
  `fsm/executor.py:58`, `cli/__init__.py:155`.
- **Sampled skill bodies show no pre-existing imperative to double up
  against.** `commands/ready-issue.md:487-499` and
  `skills/manage-issue/SKILL.md:491-497` both end their `## Arguments` section
  in reference prose, not a directive. `skills/decide-issue/SKILL.md` has no
  literal `$ARGUMENTS` token at all (only pseudocode references at
  `SKILL.md:73-81`), so `_substitute_arguments` is a no-op there — the new
  directive would still need to append for this caller, since the append
  condition is "args is non-empty," independent of whether `$ARGUMENTS` itself
  was present in the body.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

1. Update `scripts/tests/test_ready_issue_retry.py` — fix the three mocked-`expand_skill`-return-value tests (`TestBuildRetryCommand.test_expanded_body_gets_the_imperative_tail`, `TestRunReadyIssueWithRetry.test_retry_command_is_differentiated`, `TestIssueManagerWiring.test_phase1_recovers_and_reaches_phase2`) so their mock return values already include the appended directive.
2. Add `TestAppendExecutionDirective` to `scripts/tests/test_skill_expander.py`, following the `TestSubstituteArguments` pattern.
3. Update `docs/reference/API.md`'s `expand_skill` and `build_retry_command` doc sections to describe the appended directive and the collapsed re-export.

## Integration Map

_Wiring pass added by `/ll:wire-issue`:_

### Dependent Files (Callers/Importers)

- `scripts/little_loops/parallel/worker_pool.py` — second production consumer of the changed prompt shape, via `little_loops.ready_issue.run_ready_issue_with_retry` (imported line 27, invoked ~line 450) → `build_retry_command` → `expand_skill`. No code change needed (it consumes the return value opaquely), but it's in the blast radius alongside `issue_manager.py`'s four call sites already listed in Codebase Research Findings.

### Tests

- `scripts/tests/test_ready_issue_retry.py` — **will break**, must be updated:
  - `TestBuildRetryCommand.test_expanded_body_gets_the_imperative_tail` (~line 236-240) mocks `little_loops.skill_expander.expand_skill` to `return_value="# Ready Issue\nbody"` (no tail), then asserts `build_retry_command`'s output ends with `IMPERATIVE_TAIL`. Once `build_retry_command` stops appending its own tail (per Scope Boundaries), this mock bypasses the real `_append_execution_directive` call site and the assertion fails. Update the mock's `return_value` to already include the appended tail, matching what the real `expand_skill` will now produce.
  - `TestRunReadyIssueWithRetry.test_retry_command_is_differentiated` (~line 91-107) and `TestIssueManagerWiring.test_phase1_recovers_and_reaches_phase2` (~line 292-326) both patch `little_loops.skill_expander.expand_skill` at the whole-function level and assert the imperative-tail text appears in the resulting retry command/commands. Same fix: update mocked `return_value`s to include the directive text, since the mock never calls the real `_append_execution_directive`.
  - `TestBuildRetryCommand.test_falls_back_to_plain_slash_without_the_tail` and `test_real_expansion_targets_the_issue` are unaffected (unmocked or None-fallback paths).
- `scripts/tests/test_skill_expander.py` — new `TestAppendExecutionDirective` class needed, placed directly after `TestSubstituteArguments` (~line 150-161), importing `_append_execution_directive` alongside the other private helpers in the `from little_loops.skill_expander import (...)` block (lines 10-17). Follow the `TestSubstituteArguments` shape: token-present case, args-empty no-op case.
  - `TestExpandSkillAgainstRealManageIssue.test_manage_issue_expansion_has_no_raw_tokens` (~line 256-276) calls `expand_skill("manage-issue", ["bug", "implement", "BUG-001"], config)` with non-empty args — it will now exercise the new directive-append path end-to-end against a real skill file. No existing assertion contradicts an appended tail, but worth a manual check after the change lands.

### Documentation

- `docs/reference/API.md` — § `little_loops.skill_expander` → `expand_skill` prose describes the transform chain (frontmatter strip, config substitution, relative-ref conversion, `$ARGUMENTS` substitution) with no mention of an appended directive; needs a new sentence/bullet for `_append_execution_directive`. § `little_loops.ready_issue` → `build_retry_command` currently documents it as "the pre-expanded skill body plus `IMPERATIVE_TAIL`" — stale once the append moves inside `expand_skill` and `build_retry_command` becomes a passthrough re-export consumer.

## Scope Boundaries

- **In scope**: appending an execution directive in `expand_skill` when `args`
  is non-empty; collapsing `ready_issue.IMPERATIVE_TAIL` to a re-export.
- **Out of scope**: changing `$ARGUMENTS` placement in individual
  `commands/*.md` bodies; the retry mechanism itself (already shipped in
  `little_loops.ready_issue`); any change to slash-command invocation, which
  never goes through `expand_skill`.

## Impact

Removes a whole class of silent automation failure — a non-compliant model turn
discarding a long, expensive run — rather than containing it one caller at a
time. Cheap: a few lines in one function.

## Status

open


## Session Log
- `/ll:confidence-check` - 2026-08-02T05:03:59 - `14443915-f99b-4803-a617-1a2c459ff606.jsonl`
- `/ll:wire-issue` - 2026-08-02T05:00:22 - `fe6a935b-97e2-4705-b250-8a27aff90aeb.jsonl`
- `/ll:refine-issue` - 2026-08-02T04:52:58 - `fe6a935b-97e2-4705-b250-8a27aff90aeb.jsonl`
