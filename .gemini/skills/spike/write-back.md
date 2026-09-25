# Refuted write-back (BUG-3592)

Companion to `SKILL.md` Phase 6. Applies **only** to a `REFUTED` verdict.

`/ll:decide-issue` finds options through `issue_parser.locate_enumerable_options`
(`### Option` headers, bold labels, numbered/bullet items). A free-text Open Questions
item gives it nothing, and the refuted approach would still sit in `## Proposed
Solution` where decide-issue could select it again. So on a refuted verdict:

1. Rewrite `## Proposed Solution` into **`### Option <X>: <title>` header blocks only**.
   The existing proposal body moves verbatim under `### Option A: <refuted approach>`;
   each alternative named in `## Spike Findings` becomes `### Option B…`. Header blocks
   are mandatory: an original Proposed Solution usually holds numbered design steps, and
   without headers the locator would read those steps as `numbered` options.
2. Add one numbered item under `## Open Questions` (created before `## Status` /
   `## Session Log` if absent) in exactly this shape:

   ```markdown
   1. **Refuted option**: Option A — /ll:spike 2026-09-24: `assert result.ready is True`. Which remaining option replaces it?
   ```

   Quote the failing assertion from the classifier cause. The trailing `?` is deliberate:
   it makes the marker count as an open question, keeping `check-open-questions`
   blocking until a replacement is chosen. The label (`Option A`) must equal the
   refuted option's `### Option` label.
3. Set `decision_needed: true` in the frontmatter.

`ll-issues locate-options` / `check-unresolved-decisions` then mark the refuted option
`eligible: false` deterministically, so decide-issue never re-selects it — even when it
is the only option left (`ALL_OPTIONS_REFUTED`).

Residual, accepted: an AC `AssertionError` caused by a bug in the spike's own code reads
as refuted; the Findings entry quotes the assertion so a human can tell.
