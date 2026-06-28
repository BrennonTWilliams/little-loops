---
status: done
completed_at: 2026-06-27T23:23:45Z
relates_to:
- ENH-2359
---
# P3-ENH-2360: rn-remediate format guard — ensure required sections before assess

## Summary
Added a format guard as the entry point of the `rn-remediate` FSM loop
(`scripts/little_loops/loops/rn-remediate.yaml`). Before the issue is scored, the
loop deterministically checks that all required template sections are present and,
only when a required section is missing, runs `/ll:format-issue --auto` to repair
it. This prevents `/ll:confidence-check` (the `assess` state) from scoring a
malformed issue and mis-routing the downstream `diagnose → remediate → converge`
chain on unreliable scores (garbage-in).

## Current Pain Point
`rn-remediate`'s first action was `assess` (`/ll:confidence-check --auto`), and the
entire dimensional-routing chain keys on the scores it produces. A malformed issue
(missing required sections such as acceptance criteria) yields unreliable
confidence/outcome scores, which then mis-route remediation. There was no guard
ensuring an issue was structurally complete before it was assessed.

## Current Behavior
- `initial: assess` — the loop scored the issue immediately, with no structural
  precondition.
- Malformed issues reached `confidence-check` and produced low-fidelity scores that
  fed `diagnose` / `check_convergence`.

## Expected Behavior
- `initial: ensure_formatted` — a cheap, deterministic `exit_code` shell gate runs
  first.
- `ensure_formatted` reads the required section titles from `ll-issues sections
  <type>` (`common_sections.required == true` plus `type_sections.level ==
  "required"`) and greps the issue file for each `## <title>`.
  - All present → route to `assess` (no LLM cost on the common, already-formatted
    path).
  - Any missing → route to `format_issue`.
  - Fail-open on every tooling error (unresolved file, unparseable template,
    unreadable issue) so a glitch never blocks remediation.
- `format_issue` runs `/ll:format-issue <id> --auto` via the
  `with_rate_limit_handling` fragment and routes **unconditionally to `assess`** on
  every verdict (`on_yes`/`on_no`/`on_partial`/`on_error`), with
  `on_rate_limit_exhausted: rate_limit_diagnostic`. Routing straight to `assess`
  (never back to the gate) bounds it to at most one format pass — no oscillation,
  and immune to template-title mismatch.

## Impact
- Confidence scoring (and the whole diagnose/converge chain) now operates on
  structurally complete issues, improving routing fidelity.
- Guard lives in `rn-remediate` (not `rn-implement`), so both the orchestrated
  (`rn-implement → run_remediation`) and standalone (`ll-loop run rn-remediate
  "<id>"`) paths are covered, and per-issue domain logic stays out of the queue
  orchestrator — consistent with `rn-implement`'s stated architecture.
- Common (already-formatted) path stays cheap: the gate is non-LLM and only pays
  for `/ll:format-issue` when a required header is actually absent.

## Scope Boundaries
- The deterministic gate catches **missing** required headers only. It does not
  catch renamed, empty, or boilerplate-only sections; those still reach `assess`.
  If malformed-but-not-missing issues later skew scores, the documented follow-on is
  to swap the gate body for a `/ll:format-issue --check` slash_command pre-pass
  (that mode already exists, purpose-built for FSM evaluators: exit 1 on any gaps).
- No changes to `rn-implement.yaml`; the guard was intentionally placed in the
  sub-loop, not the orchestrator.
- No backlog sweep was performed. Older issues missing required sections will each
  trigger one format pass on entry (intended behavior); an optional one-time
  `/ll:format-issue --all --auto` sweep would raise the gate's fast-path hit rate.

## Implementation Notes
- File: `scripts/little_loops/loops/rn-remediate.yaml`
  - Changed `initial: assess` → `initial: ensure_formatted`.
  - Added `ensure_formatted` (shell, `evaluate: exit_code`) and `format_issue`
    (slash_command, `with_rate_limit_handling`) as a new "Phase 0: Format Guard".
- Heredoc-stdin gotcha: a `python3 << EOF` heredoc owns stdin, so the template JSON
  is passed via the `SECTIONS_JSON` env var rather than piped into the python block
  — mirroring the no-stdin pattern used by `select_next` in `rn-implement.yaml`.
- No meta-loop rules (MR-1…MR-7) apply: `rn-remediate` is `category: planning`
  operating on issue *data*, not harness artifacts, and the new gate is `exit_code`.

## Verification
- `ll-loop validate rn-remediate` → valid (39 states, `Initial: ensure_formatted`).
- Smoke-tested the gate's shell/python against real issues: `ENH-2359` (current
  template) passes cheaply; older issues (`BUG-001`, `FEAT-020`, `ENH-206`)
  correctly route to formatting with the specific missing sections named.
- `python -m pytest scripts/tests/test_builtin_loops.py` → 945 passed. The 2
  failures (`test_deterministic_warning_categories_do_not_regrow` on
  `sprint-build-and-validate`; `test_list_shows_builtin_tag`) are pre-existing on
  `main`, confirmed via `git stash`, and unrelated to this change.

## Progress (2026-06-27)
**Completed:**
- Designed and implemented the format guard at the top of `rn-remediate`.
- Validated the loop and smoke-tested the gate logic against real issues.
- Confirmed the two failing builtin-loop tests are pre-existing and unrelated.
</content>
</invoke>


## Session Log
- `hook:posttooluse-status-done` - 2026-06-27T23:24:29 - `620351c4-3563-489a-a8e6-df580087960a.jsonl`
