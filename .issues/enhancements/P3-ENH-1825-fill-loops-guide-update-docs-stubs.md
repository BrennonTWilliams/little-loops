---
id: ENH-1825
title: Fill update-docs stubs in LOOPS_GUIDE.md
type: ENH
priority: P3
captured_at: '2026-05-31T00:00:00Z'
discovered_date: '2026-05-31'
discovered_by: audit-docs
status: open
labels:
- enhancement
- documentation
- loops
---

# ENH-1825: Fill update-docs stubs in LOOPS_GUIDE.md

## Summary

`docs/guides/LOOPS_GUIDE.md` contains 9 unfilled `<!-- TODO: update-docs stub -->` blocks written between April and May 2026. Each represents a feature or behaviour change that was implemented but never documented. Filling them completes the guide and removes stale debt markers.

## Current Behavior

Nine stubs exist (line numbers as of 2026-05-31 audit):

| Line | Stub tag | Topic |
|------|----------|-------|
| 71 | `dd260362` | Safety limits section |
| 548 | `write-back + apply commands` | rn-refine write-back + apply |
| 768 | `git change 4e692df0` | scan-and-implement expansion |
| 1165 | `base64 image embedding` | base64 image embedding in hitl-compare |
| 1416 | `cli-anything-bootstrap` | cli-anything-bootstrap FSM flow, context vars, examples |
| 1449 | `MR-3` | Per-run artifact isolation rule text (partially filled inline) |
| 1472 | `BUG-1815` | exit-code short-circuit for non-exit-code evaluators |
| 1645 | `ENH-1678` | `retryable_exit_codes` field description (partial inline content exists) |
| 2584 | `ENH-1293` | server-error automatic retry section |

Each stub is a `<!-- TODO: update-docs stub … -->` HTML comment. Some are standalone placeholders; others are inline within partially written paragraphs (lines 1449 and 1645).

## Expected Behavior

All 9 stubs are replaced with complete prose. No `<!-- TODO: update-docs stub -->` comments remain in the file. Each replacement:
- Follows the surrounding document style (same heading levels, code-block format, table columns)
- Is sourced from the implementing code, the referenced git commit/issue, or existing CLAUDE.md/ARCHITECTURE.md content
- Does not change surrounding content except to remove the stub comment

## Motivation

Discovered during 2026-05-31 docs audit. Stubs have been open for 5–35 days with no progress. Several reference shipped features (`BUG-1815` exit-code short-circuit, `ENH-1678` retryable_exit_codes, `ENH-1293` server-error retry) that users need to understand to configure loops correctly. The guide is the primary reference; stub sections silently omit real behaviour.

## Proposed Solution

Work through each stub in document order:

1. **Line 71 — Safety limits (dd260362)**: Read git commit `dd260362` for context; write a prose section explaining whatever safety limit was introduced.
2. **Line 548 — rn-refine write-back + apply**: Check `loops/rn-refine.yaml` for write-back state names and commands; document the write-back mechanism and `apply` command.
3. **Line 768 — scan-and-implement (4e692df0)**: Read git commit `4e692df0`; document the scan-and-implement expansion.
4. **Line 1165 — base64 image embedding in hitl-compare**: Read `loops/hitl-compare.yaml` for how base64 embedding works; write a note or bullet.
5. **Line 1416 — cli-anything-bootstrap**: Read `loops/cli-anything-bootstrap.yaml` for FSM flow, context variables, and usage examples; write a `### cli-anything-bootstrap` section.
6. **Line 1449 — MR-3 per-run artifact isolation**: The surrounding paragraph already has content; remove the inline stub comment, clean up the sentence.
7. **Line 1472 — BUG-1815 exit-code short-circuit**: Find the BUG-1815 issue or commit; document the short-circuit behaviour for non-exit-code evaluators.
8. **Line 1645 — ENH-1678 retryable_exit_codes**: The table cell has a partial description; expand it to a complete description and remove the stub delimiters.
9. **Line 2584 — ENH-1293 server-error automatic retry**: Find ENH-1293 or related commits; write the server-error retry section.

## Success Metrics

- [ ] `grep -c 'TODO: update-docs stub' docs/guides/LOOPS_GUIDE.md` returns `0`
- [ ] Each previously stubbed section contains prose that accurately reflects the implemented feature
- [ ] No markdown link errors introduced (run `ll-check-links docs/guides/LOOPS_GUIDE.md`)
- [ ] No regressions in surrounding content (spot-check each edited section)

## Scope Boundaries

- Only `docs/guides/LOOPS_GUIDE.md` is modified.
- Do not refactor or rewrite surrounding sections — fill stubs and nothing else.
- If a stub references a feature that was never implemented or was reverted, replace it with a one-line note explaining that and remove the stub comment.

## Implementation Steps

1. Read `docs/guides/LOOPS_GUIDE.md` in full to understand surrounding context for each stub.
2. For git-commit-tagged stubs (dd260362, 4e692df0): run `git show <hash> --stat --oneline` to identify files changed, then read the diff for content.
3. For issue-tagged stubs (BUG-1815, ENH-1678, ENH-1293): read the corresponding `.issues/` file for motivation and implementation notes.
4. For loop-file stubs (cli-anything-bootstrap, rn-refine, hitl-compare): read the YAML loop file.
5. Draft replacements for all 9 stubs, then apply them in a single editing pass to avoid line-number drift.
6. Run `grep 'TODO: update-docs stub' docs/guides/LOOPS_GUIDE.md` to confirm zero remaining stubs.
7. Run `ll-check-links docs/guides/LOOPS_GUIDE.md` (or equivalent) to verify no broken links.

## Integration Map

### Files to Modify
- `docs/guides/LOOPS_GUIDE.md` — replace 9 stub comments with prose

### Reference Files (Read Only)
- `scripts/little_loops/loops/cli-anything-bootstrap.yaml` — FSM, context vars, usage
- `scripts/little_loops/loops/rn-refine.yaml` — write-back states
- `scripts/little_loops/loops/hitl-compare.yaml` — base64 embedding
- `.issues/bugs/` and `.issues/enhancements/` — BUG-1815, ENH-1678, ENH-1293
- Git: `git show dd260362`, `git show 4e692df0`

## Impact

- **Priority**: P3 — existing features go undocumented until filled
- **Effort**: Medium — 9 stubs, most requiring reading source material; no code changes
- **Risk**: Low — documentation only
- **Breaking Change**: No
