---
id: ENH-2530
type: ENH
priority: P3
status: open
captured_at: '2026-07-07T21:00:00Z'
discovered_date: '2026-07-07'
discovered_by: audit-loop-run
relates_to:
- ENH-2533
decision_needed: false
labels:
- loops
- observability
---

# ENH-2530: rn-remediate — manual_review_handoff_<id>.md with decision_context

## Summary

When `emit_needs_manual_review` in
`scripts/little_loops/loops/rn-remediate.yaml` parks an issue, write a
per-issue handoff markdown that states the specific reason and recommended
next action, pulling `decision_context` from issue frontmatter when
`decision_needed: true` is the proximate cause.

## Source

Audit of an rn-implement run in a downstream project
(`AUDIT-rn-implement-2026-07-07T201030.md`, proposals 2 and 3). Two parked
issues surfaced only "requires human decision before automation can proceed" —
too vague to act on. The operator had to re-read `events.jsonl` and the issue
files to learn that one needed TTL options enumerated and the other a refactor
scope decision.

## Current Behavior

`emit_needs_manual_review` writes a one-line token to
`subloop_outcome_<ID>.txt` (`MANUAL_REVIEW_NEEDED` or
`MANUAL_REVIEW_RECOMMENDED`, distinguished per ENH-2443) and the parent appends
one line to `blocked.txt`. Nothing captures *which* decision is needed, the
score gap, or the remediation next step.

## Expected Behavior

`emit_needs_manual_review` additionally writes
`${context.run_dir}/manual_review_handoff_<ID>.md` containing:

- issue ID and title
- specific reason: outcome vs threshold (e.g. "outcome_confidence=70,
  threshold=75"), convergence delta and remediation pass count when available
- `decision_context` frontmatter verbatim when `decision_needed: true`
  (fallback to the generic sentence only when the field is absent)
- recommended next action: `/ll:refine-issue <ID>` for options-missing,
  `/ll:explore-api <target>` for learning gates
- captured pre/post scores

## Integration Map

_Added by `/ll:refine-issue` — codebase-derived file/caller/test surface._

### Files to Modify
- `scripts/little_loops/loops/rn-remediate.yaml:793–805` — extend
  `emit_needs_manual_review`'s shell action to write the markdown artifact
  alongside the existing `subloop_outcome_<ID>.txt` token. No structural
  YAML changes; only the `action:` body grows. Existing token write must
  remain unchanged.

### Files to Read (no modification)
- `scripts/little_loops/loops/rn-implement.yaml:360–457` — `check_blocked_by`
  is the **canonical parser pattern** to mirror (try `yaml.safe_load` with
  `re.match(r'^([\w-]+):\s*(.*)', line)` regex fallback; walk
  `.issues/{bugs,features,enhancements,epics}/*.md`; extract frontmatter
  with `re.match(r'^---\n(.*?)\n---', content, re.DOTALL)`; fail-open via
  `sys.exit(0)` at each parse step).
- `scripts/little_loops/loops/rn-implement.yaml:1222–1240` — `mark_blocked`
  and `mark_blocked_options_missing` are the parent-side analogs. The new
  handoff's per-issue detail supplements the parent's one-line diagnostic
  in `blocked.txt`.

### Sidecar Producers (already exist; handoff consumes them)
- `scripts/little_loops/loops/rn-remediate.yaml:158` — `verify_scores_persisted`
  writes `pre_scores_<ID>.json`.
- `scripts/little_loops/loops/rn-remediate.yaml:628` — `verify_re_assess_scores`
  writes `post_scores_<ID>.json`.
- `scripts/little_loops/loops/rn-remediate.yaml:683, 689, 695` —
  `check_convergence` increments `remediation_count_<ID>.txt` and writes
  `convergence_<ID>.json`.
- `scripts/little_loops/loops/rn-remediate.yaml:165` — `verify_scores_persisted`
  writes `complexity_band_<ID>.txt` (MINIMAL / ABOVE_MINIMAL; useful but
  not required by the issue's expected-behavior list).
- `scripts/little_loops/loops/rn-remediate.yaml:307` — `decide_options_deposited`
  writes the ENH-2443 marker that distinguishes MANUAL_REVIEW_RECOMMENDED
  from MANUAL_REVIEW_NEEDED. The handoff must branch on this same marker.

### Callers (states that route into `emit_needs_manual_review`)
- `scripts/little_loops/loops/rn-remediate.yaml:486` — `decide.on_no`
  (when `/ll:decide-issue --auto` returns nothing scorable).
- `scripts/little_loops/loops/rn-remediate.yaml:728` —
  `check_convergence` route `NEEDS_MANUAL_REVIEW` (when `decision_needed=true`
  and convergence stalls; BUG-2193).

### Consumers (today, only the human operator)
- The parent `rn-implement.yaml` does NOT read the handoff markdown. The
  existing `subloop_outcome_<ID>.txt` token is the only routing signal.
  Adding a markdown consumer is out of scope for this issue.
- The new handoff is a **terminal diagnostic artifact** for human
  operators; no FSM routing change.

### Similar Patterns to Follow
- `scripts/little_loops/loops/lib/common.yaml:326–347` —
  `subloop_rate_limit_diagnostic` fragment: an "outcome-token-emitter"
  state shape that the extended `emit_needs_manual_review` parallels.
- `scripts/little_loops/loops/cua-agent-desktop.yaml:412–418` —
  quoted-heredoc raw-output write pattern (`<< 'EOF'` to prevent shell
  expansion of dynamic markdown bodies).
- `scripts/little_loops/loops/hitl-md.yaml:255` — adjacent per-issue
  markdown artifact pattern in a different loop; demonstrates that
  top-level (non-`run_dir`) discoverability is the alternative convention
  if run_dir-only discovery proves insufficient later.

### Tests to Extend (existing pattern coverage)
- `scripts/tests/test_rn_remediate.py:308–327` — `TestManualReviewRecommendedToken`:
  add tests asserting the markdown write references both sidecar formats
  and the existing token write is preserved (token-preservation assertion
  is the regression guard).
- `scripts/tests/test_rn_remediate.py:1187–1195` —
  `test_mr3_run_dir_used_for_writes`: confirm no `.loops/tmp/` literal
  appears in the extended action.
- `scripts/tests/test_rn_remediate.py:1307–1320` — `TestEmitTokensWrittenToRunDir`:
  extend the expected-states dict or add a sibling test for the handoff
  markdown path.
- `scripts/tests/test_rn_remediate.py:1939–1943` — `TestSubloopSidecarContract`:
  add a per-state regex check that `manual_review_handoff_` substring
  appears in `emit_needs_manual_review.action`.

### Documentation to Update
- `docs/guides/LOOPS_REFERENCE.md:593–608` — `emit_needs_manual_review`
  description; add a paragraph noting the new handoff artifact and its
  MR-3 location.
- `docs/guides/RECURSIVE_LOOPS_GUIDE.md` — cross-reference the new handoff
  if the recursive-loops section mentions manual review semantics.
- `docs/reference/COMMANDS.md` — no change expected (commands don't
  reference the handoff; only `/ll:refine-issue` and `/ll:decide-issue`
  are recommended next-actions).

### Decisions Log
- `.ll/decisions.yaml` — consider adding a rule entry for the new
  handoff artifact convention (parallel to the existing
  `MANUAL_REVIEW_NEEDED` / `MANUAL_REVIEW_RECOMMENDED` rule entries
  mentioned by ENH-2443). Optional but consistent with project
  conventions.

### Related Issues (sibling context)
- `ENH-2533` (relates_to: ENH-2530) — sibling from same audit: per-issue
  `summary.json` outcomes.
- `ENH-2534` (sibling) — `check_blocked_by` unresolved-token artifact
  pattern (likely mirrors what this issue does for `check_convergence`).
- `ENH-2443` (done) — the predecessor that introduced
  `MANUAL_REVIEW_RECOMMENDED`; the canonical reference for the
  `decide_options_deposited_<ID>.txt` marker.

## Proposed Solution

- Extend the `emit_needs_manual_review` shell action with an inline python3
  heredoc that reads the issue frontmatter (mirror check_blocked_by's
  yaml-with-regex-fallback parser) plus `pre_scores_<ID>.json` /
  `convergence_<ID>.json` sidecars and renders the handoff file.
- Keep the existing token write unchanged (parent routing depends on it).
- Per MR-3, the handoff lives under `${context.run_dir}/` — already the
  convention here.
- If refine-issue does not yet reliably populate `decision_context`, note the
  fallback path in the handoff rather than blocking on it.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Target state to extend**: `emit_needs_manual_review` at
  `scripts/little_loops/loops/rn-remediate.yaml:793–805`. Action currently
  is a 4-line shell block that branches on the `decide_options_deposited_<ID>.txt`
  marker (line 307) to write either `MANUAL_REVIEW_RECOMMENDED` or
  `MANUAL_REVIEW_NEEDED`. Routes to `failed` (terminal).
- **Parser pattern to mirror** (verified exact match to issue text):
  `check_blocked_by` heredoc at `scripts/little_loops/loops/rn-implement.yaml:360–457`.
  Same `_parse_yaml` regex fallback shape is inlined in `select_next` (`:202–323`),
  `re_enqueue_unblocked` (`:763–836`), `check_learning_ready` (`:502–611`), and
  `prove_rem_learning_gate` (`:961–1060`) — this is the loop-wide convention.
- **Sidecar readers needed** (all under `${context.run_dir}/`):
  - `pre_scores_<ID>.json` — written by `verify_scores_persisted:158`.
    JSON keys: `.confidence`, `.outcome`, `.score_complexity`,
    `.score_ambiguity`, `.score_change_surface`, `.decision_needed`,
    `.missing_artifacts`.
  - `post_scores_<ID>.json` — written by `verify_re_assess_scores:628`.
    Same shape as pre-scores.
  - `convergence_<ID>.json` — written by `check_convergence:689`. Shape:
    `{id, pre_confidence, post_confidence, pre_outcome, post_outcome,
    delta_confidence, delta_outcome, delta_complexity, delta_ambiguity,
    total_delta}`. **Refreshed every convergence check** (the deltas are
    pass-over-pass, not initial-vs-final).
  - `remediation_count_<ID>.txt` — incremented at `check_convergence:683, 743`.
    Use this for "remediation pass count" in the handoff body.
- **Distinguishing MANUAL_REVIEW_RECOMMENDED vs NEEDED in the handoff body**:
  mirror the existing `if [ -f "...decide_options_deposited_..." ]` branch
  (ENH-2443). When the marker exists, the issue already exhausted the
  `/ll:refine-issue --auto` retry once; recommended next-action text should
  suggest `/ll:refine-issue <ID>` (manual, not auto). When the marker is
  absent, this is a fresh decision requirement.
- **`decision_context` field status** (load-bearing for the fallback clause):
  the field **does not exist anywhere in the codebase yet** — only mentioned
  in this issue and ENH-2443 (where it was named but not implemented). No
  producer writes it. The handoff writer MUST fall back to a generic sentence
  (e.g. "Issue requires human decision; see convergence data and issue
  frontmatter for context") until `/ll:refine-issue` or `/ll:decide-issue`
  are extended to populate it. Adding the producer is out of scope for this
  issue — track separately if desired.
- **Quoted heredoc required**: the markdown body will contain dynamic strings
  (issue title, decision_context body with potential `:` and `'` characters,
  score values). Use `python3 << 'PYEOF'` (quoted delimiter) to prevent shell
  expansion. Pattern precedent: `cua-agent-desktop.yaml:412–418` for `<< 'EOF'`
  on raw LLM output writes.
- **MR-3 lint**: `test_rn_remediate.py:1187–1195` (`test_mr3_run_dir_used_for_writes`)
  will fail the loop if any state writes to `.loops/tmp/`. Confine the new
  artifact to `${context.run_dir}/` — the issue's proposal already does.
- **Parent-side aftermath is unchanged**: `mark_blocked` (`:1222–1228`) and
  `mark_blocked_options_missing` (`:1230–1240`) already log distinct
  diagnostic lines to `blocked.txt`. The new handoff is **additive terminal
  diagnostic** — does not change FSM routing. The handoff's "next action"
  recommendation should mirror the parent's diagnostic phrasing where
  applicable (`run /ll:refine-issue <ID> manually to deposit options` is
  already a pattern the parent uses).
- **Failure mode**: if any sidecar is missing, fail-open to writing a
  handoff with whatever data is available plus a "(data unavailable)" note.
  The parent has no `manual_review_handoff_<ID>.md` reader today — the only
  consumer is the human operator — so partial data is better than no file.
  Wrap each sidecar read in a `try/except` block (mirrors the
  fail-open semantics in `check_blocked_by:379–446`).

## Implementation Steps

_Added by `/ll:refine-issue` — concrete code-level steps referencing real anchors._

### Phase 1: Extend `emit_needs_manual_review`

1. **Open** `scripts/little_loops/loops/rn-remediate.yaml` and locate the
   `emit_needs_manual_review` state (lines 793–805).

2. **Preserve** the existing `if [ -f "...decide_options_deposited..." ]`
   branch (the ENH-2443 token disambiguation must remain — parent's
   longest-prefix-first routing at `rn-implement.yaml:860–881` depends on
   it).

3. **Append** an inline `python3 << 'PYEOF'` heredoc to the existing
   `action:` block (quoted delimiter is required — see
   `cua-agent-desktop.yaml:412–418` for the pattern). The heredoc:
   - Defines `_parse_yaml(text)` exactly as in `check_blocked_by:379–407`
     (try `yaml.safe_load`, fall back to `re.match(r'^([\w-]+):\s*(.*)', line)`
     line-by-line).
   - Resolves the issue file by walking
     `.issues/{bugs,features,enhancements,epics}/*.md` and matching
     `re.match(r'P\d-([A-Z]+-\d+)-', p.name)` against `${context.issue_id}`
     (same as `check_blocked_by:411–422`).
   - Reads frontmatter with `re.match(r'^---\n(.*?)\n---', content, re.DOTALL)`
     → `_parse_yaml(...)`. Wraps in `try/except` with `sys.exit(0)`
     (fail-open — empty `decision_context` triggers the generic fallback
     message).
   - Reads `${context.run_dir}/convergence_<ID>.json` with `try/except` —
     on failure, sets `convergence = None` and the handoff writes
     "(convergence data unavailable)".
   - Reads `${context.run_dir}/pre_scores_<ID>.json` and
     `post_scores_<ID>.json` with `try/except` — same pattern.
   - Reads `${context.run_dir}/remediation_count_<ID>.txt` (line-count
     integer with `try/except`).
   - **Branches on `${context.run_dir}/decide_options_deposited_<ID>.txt`**
     presence to set `next_action = "/ll:refine-issue <ID>"` (manual, when
     marker exists) vs `next_action = "/ll:refine-issue <ID> --auto"` or
     a generic decision prompt (when marker absent — see Issue §
     `decision_context` field status below).
   - Renders the markdown body to
     `${context.run_dir}/manual_review_handoff_<ID>.md` via `Path.write_text`.

4. **Markdown body template** (minimum content per Issue § Expected Behavior):
   ```markdown
   # Manual Review Handoff: <ID>

   - **Issue**: <title>
   - **Token**: MANUAL_REVIEW_NEEDED | MANUAL_REVIEW_RECOMMENDED
   - **Reason**: outcome_confidence=<post.outcome>, threshold=<config threshold>; remediation pass <N> of <max>
   - **Convergence delta**: total_delta=<conv.total_delta> (Δconfidence=<conv.delta_confidence>, Δoutcome=<conv.delta_outcome>)
   - **Decision needed**: <decision_context verbatim, or generic fallback sentence>
   - **Recommended next action**: <next_action>

   ## Diagnostic Data
   - Pre-scores: confidence=<pre.confidence>, outcome=<pre.outcome>
   - Post-scores: confidence=<post.confidence>, outcome=<post.outcome>
   - Complexity band: <pre.score_complexity> (ambiguity=<pre.score_ambiguity>)
   ```

### Phase 2: Verification

1. **Lint**: `python -m pytest scripts/tests/test_rn_remediate.py -v`
   should pass. The MR-3 lint at `test_rn_remediate.py:1187–1195` will
   catch any `.loops/tmp/` literal that creeps into the action.
2. **Sidecar contract**: the existing
   `TestSubloopSidecarContract` (`test_rn_remediate.py:1939–1943`)
   continues to assert `subloop_outcome_` is in the action — preserve
   that line.
3. **Manual smoke test**: run `ll-loop run rn-remediate <issue-with-decision-needed>`
   on a real `decision_needed: true` issue; verify
   `.loops/runs/<run>/manual_review_handoff_<ID>.md` exists, has the
   expected sections, and `blocked.txt` is unchanged in shape.
4. **Token preservation**: confirm `subloop_outcome_<ID>.txt` still
   contains `MANUAL_REVIEW_NEEDED` or `MANUAL_REVIEW_RECOMMENDED` —
   parent routing at `rn-implement.yaml:860–881` depends on this.

### Phase 3: Test Additions (no fixtures required)

1. **Add to `TestManualReviewRecommendedToken`** (`test_rn_remediate.py:308–327`):
   ```python
   def test_writes_manual_review_handoff_markdown(self) -> None:
       data = _load_loop()
       action = data["states"]["emit_needs_manual_review"]["action"]
       assert "manual_review_handoff_${context.issue_id}.md" in action
       assert "${context.run_dir}" in action  # MR-3 conformance
   ```

2. **Add to `TestEmitTokensWrittenToRunDir`** (`test_rn_remediate.py:1307–1320`):
   extend the existing dict-driven loop to also assert the handoff path
   for `emit_needs_manual_review`, OR add a sibling test class.

3. **Add to `TestSubloopSidecarContract`** (`test_rn_remediate.py:1939–1943`):
   ```python
   def test_manual_review_emits_handoff_md(self) -> None:
       data = _load_loop()
       action = data["states"]["emit_needs_manual_review"]["action"]
       assert "manual_review_handoff_" in action
   ```

### Phase 4: Documentation

1. Update `docs/guides/LOOPS_REFERENCE.md:593–608` — add a paragraph
   noting the new `manual_review_handoff_<ID>.md` artifact, its MR-3
   location (`${context.run_dir}/`), and that it supplements (does not
   replace) the `subloop_outcome_<ID>.txt` token.
2. No CHANGELOG entry expected at this stage (the project uses
   `[X.Y.Z] - DATE` sections per repo convention — leave for release
   prep).

### Out of Scope (explicit)
- Adding a `decision_context` frontmatter producer in
  `/ll:refine-issue` or `/ll:decide-issue`. Until that lands, the handoff
  falls back to a generic sentence (per Issue § Proposed Solution bullet 4).
- Adding a parent-side reader for the new handoff. The handoff is a
  human-only terminal diagnostic today.
- Touching `rn-decompose.yaml` or `rn-refine.yaml` — sibling sub-loops
  have analogous `*_needs_manual_review` patterns but the issue scopes
  the change to `rn-remediate.yaml:793–805` only.

## Impact

- **Severity**: Medium (turns post-hoc audits into one-click handoffs)
- **Effort**: Small–Medium
- **Risk**: Low (additive artifact; no routing changes)


## Session Log
- `/ll:refine-issue` - 2026-07-07T22:51:38 - `06cf831f-8243-472a-958e-6e4b821c6604.jsonl`
