---
id: BUG-3286
type: BUG
title: 'Priority read from filename prefix only: frontmatter priority: is write-only
  and drifts on re-prioritization'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T17:37:01Z'
labels:
- parser
- frontmatter
- planning-hub
- multi-repo
- mcp
---

# BUG-3286: Priority read from filename prefix only: frontmatter priority: is write-only and drifts on re-prioritization

## Summary

`IssueParser` resolves an issue's priority exclusively from the `P<n>-` filename prefix; the frontmatter `priority:` key is written on every created issue but never read by any code path, so prefix-less issue files silently flatten to P5 and the two sources drift with no reconciliation.

## Current Behavior

Priority has two sources of truth in little-loops and only one of them is ever read.

**The write side.** `ll-issues create` writes `priority` into the frontmatter dict at `scripts/little_loops/cli/issues/create.py:311` and builds the filename with the same value at `create.py:454`. Both are in sync at creation.

**The read side.** `IssueParser.parse_file` sets priority from `self._parse_priority(filename)` at `scripts/little_loops/issue_parser.py:2767` and nothing else. Two lines later it calls `parse_frontmatter(content)` and pulls a dozen fields off it — `discovered_by`, `epic`, `size`, `effort`, `impact`, `confidence_score`, `outcome_confidence`, `score_*`, `testable`, `decision_needed` — but never `priority`. `_parse_priority` at `issue_parser.py:2927-2939` does a bare `filename.startswith(f"{p}-")` scan over the priority list from `BRConfig.issue_priorities` (`scripts/little_loops/config/core.py:714`) and falls through to its last element (P5) when no prefix matches. `_ANCHORED_FILENAME_RE` at `issue_parser.py:58` likewise makes the priority group optional and yields `None`.

A grep of every `"priority"` read site across `scripts/little_loops/` confirms the frontmatter key is **write-only**: no module consumes it. In this repo's own `.issues/`, 2,083 files carry a frontmatter `priority:` that no code has ever read.

**Consequence 1 — prefix-less repos flatten to P5.** Reproduced in a throwaway project outside this repo (see Steps to Reproduce) whose sole issue file has no `P<n>-` prefix and a frontmatter `priority: P1`:

```
ENH-279-foo.md -> 'P5'  priority_int=5
```

**Consequence 2 — the two sources drift in this repo already.** `ll-issues prioritize --apply` renames the file and never opens it: `apply_priorities` at `scripts/little_loops/cli/issues/prioritize.py:132-143` computes `new_name`, calls `git_mv_with_fallback(path, new_path)`, and returns. The frontmatter copy goes stale on every re-prioritization. Four live mismatches in `.issues/` today (filename prefix vs. frontmatter):

| File | Filename says | Frontmatter says |
|---|---|---|
| `P3-BUG-3109-loop-info-show-effective-scope.md` | P3 | P4 |
| `P2-ENH-2746-f3-compaction-shrink-ratio-outside-gate-band.md` | P2 | P3 |
| `P2-ENH-2988-expand-skill-ships-documentation-shaped-prompts-with-no-directive-to-act.md` | P2 | P3 |
| `P2-ENH-3047-confidence-check-consume-claim-and-parity-gaps.md` | P2 | P3 |

**Consequence 3 — two readers disagree on the same input.** `ll-issues show` does not use `IssueParser`; it carries its own filename regex at `scripts/little_loops/cli/issues/show.py:79-81` and yields `None` when there is no prefix, where the parser yields `P5`. Same file, two different wrong answers.

## Expected Behavior

- Priority resolution consults the frontmatter `priority:` key when the filename carries no `P<n>-` prefix, and defaults to P5 only when neither source specifies one.
- When a filename prefix and a frontmatter value disagree, the filename wins (see Decision Rules) — deliberately, and documented.
- `ll-issues prioritize --apply` updates the frontmatter `priority:` alongside the rename, so the two sources stop diverging.
- A format-check rule reports filename↔frontmatter priority disagreement, and the four existing mismatches are reconciled.
- `ll-issues show` and `IssueParser` agree on the resolved priority for any given file.

## Motivation

Priority is the core planning signal. Every consumer downstream of it — `ll-issues next-issue`, `ll-sprint` sequencing, `backlog_snapshot.by_priority`, ll-mcp `issues_query` summary cards — silently produces meaningless output when every issue ties at P5. There is no crash and no data loss, so the failure is invisible until someone notices the ordering is arbitrary.

Two motivations, not one:

<!-- ll-private-ok: external planning hub demonstrates issue scope -->
1. **Multi-repo generalization.** Any repo using the frontmatter-priority convention without a filename prefix (the ll-product planning hub today, any future planning-hub or convention repo) gets a dead priority ordering.
2. **Internal correctness.** Even in this repo, where the prefix convention holds, little-loops maintains two priority sources, syncs them only at creation, and has no reconciliation or lint between them. Fixing only (1) formalizes a field that goes stale on every re-prioritization — it would make a known-unreliable source authoritative for one class of repo.

## Proposed Solution

Three coordinated changes. (1) alone closes the reported symptom; (2) and (3) prevent the fix from resting on a field that silently rots.

**1. Frontmatter fallback in the parser.** Give priority resolution access to the parsed frontmatter and consult it when the filename anchor yields nothing:

```python
def _resolve_priority(self, filename: str, frontmatter: dict[str, Any]) -> str:
    """Resolve priority: filename prefix wins, frontmatter is the fallback."""
    for priority in self.config.issue_priorities:
        if filename.startswith(f"{priority}-"):
            return priority
    fm_priority = frontmatter.get("priority")
    if isinstance(fm_priority, str) and fm_priority.upper() in self.config.issue_priorities:
        return fm_priority.upper()
    return self.config.issue_priorities[-1] if self.config.issue_priorities else "P3"
```

`parse_file` already reads content and calls `parse_frontmatter` — the resolution call moves below that, so no extra file read. `ll-issues show` (`show.py:79-81`) gains the same fallback so the two readers agree.

**2. Keep frontmatter in sync on rename.** `apply_priorities` calls `update_frontmatter` on the renamed file to set `priority` to the new value, so the copies cannot diverge going forward.

**3. Drift lint + one-time reconciliation.** A `format-check` rule reporting filename↔frontmatter disagreement, plus a pass over the four existing mismatches to bring them into agreement.

## Integration Map

| File | Change |
|---|---|
| `scripts/little_loops/issue_parser.py` | `_parse_priority` → `_resolve_priority`; call site moves below `parse_frontmatter` |
| `scripts/little_loops/cli/issues/show.py` | Same fallback so `show` agrees with the parser (currently yields `None`) |
| `scripts/little_loops/cli/issues/prioritize.py` | `apply_priorities` updates frontmatter after `git_mv_with_fallback` |
| `scripts/little_loops/cli/issues/format_check*.py` | New drift gap kind |
| `docs/reference/ISSUE_TEMPLATE.md` | Document the frontmatter `priority:` field and the precedence rule |
| `scripts/tests/test_issue_parser*.py` | Fallback, precedence, and regression coverage |
| `.issues/` (4 files) | Reconcile existing mismatches |

## Program Design

### Types

No new types. `IssueInfo.priority` (`str`) and `IssueInfo.priority_int` (`int`) keep their current shapes and semantics.

### Signatures

- `IssueParser._resolve_priority(self, filename: str, frontmatter: dict[str, Any]) -> str` — replaces `_parse_priority`; filename prefix first, frontmatter `priority:` second, `issue_priorities[-1]` last.
- `apply_priorities(config: BRConfig, mapping: dict[str, str]) -> list[RenameResult]` — unchanged signature; body gains an `update_frontmatter` call after the rename so the frontmatter copy tracks the new prefix.
- `update_frontmatter(path: Path, updates: dict[str, Any]) -> None` — existing helper, reused by the sync step.

### Call Path

- `IssueParser.parse_file` → `parse_frontmatter` → `IssueParser._resolve_priority` → `IssueInfo`
- `apply_priorities` → `git_mv_with_fallback` → `update_frontmatter`
- `find_issues` → `IssueParser.parse_file` (unchanged; picks up the corrected priority transitively)

### Decision Rules

**Precedence rule.** When both a filename `P<n>-` prefix and a frontmatter `priority:` are present and they disagree, the **filename prefix wins**.

- Inputs: the issue filename and the parsed frontmatter dict.
- Rationale, evidence-backed rather than convention-backed: `apply_priorities` writes the filename and leaves the frontmatter untouched, so for all four existing mismatches in this repo the filename is by construction the fresher signal. Filename-wins also preserves byte-identical behavior for every currently-prefixed repo.
- Frontmatter is consulted only when the filename anchor yields no priority.
- A frontmatter value outside `config.issue_priorities` (malformed, e.g. `priority: high`) is ignored, falling through to the P5 default rather than raising.
- Escape hatch: none needed — the rule is total and has a defined result for every input.

**Drift rule (new format-check gap kind).** Report a gap when a file has both a filename prefix and a frontmatter `priority:` whose values differ. Scoped to the file's own name and frontmatter — no cross-file comparison. Dismissal follows the existing format-check dismissal mechanism; no new opt-out key.

## Implementation Steps

1. Add `_resolve_priority` with the frontmatter fallback; move the call in `parse_file` below `parse_frontmatter`. Cover with tests for fallback, prefix-wins precedence, malformed frontmatter, and the no-priority-anywhere P5 default.
2. Apply the same fallback in `show.py` so `ll-issues show` and `IssueParser` agree; add a test asserting agreement on a prefix-less file.
3. Extend `apply_priorities` to update frontmatter after the rename; test that a re-prioritized file has matching filename and frontmatter.
4. Add the format-check drift rule with tests for the matching and mismatching cases.
5. Reconcile the four existing `.issues/` mismatches; confirm the new rule reports clean afterwards.
6. Update `docs/reference/ISSUE_TEMPLATE.md` to document the field and precedence.

## Impact

<!-- ll-private-ok: external planning hub impact assessment -->
**Priority: P2.** Silent corruption of the core planning signal, no crash and no data loss. It fully disables priority ordering for any prefix-less repo (ll-product: 125 open issues all reading P5) and leaves a latent two-sources-of-truth defect in every repo including this one. Not P1 — the prefix convention means little-loops' own ordering is currently correct in practice, and the four drifts are cosmetic today.

**Effort: 2 (medium).** Six files, mostly small and well-isolated. The parser change is a few lines; the format-check rule and its tests are the bulk of it.

**Risk: low-to-medium.** The precedence choice makes the parser change byte-identical for every prefixed file, so existing repos see no behavior change. The real risk is step 3: `apply_priorities` currently never opens files, and adding a content write makes it a heavier, more failure-prone operation — worth checking interaction with `git_mv_with_fallback` ordering and staging.

<!-- ll-private-ok: external planning hub scope documentation -->
**Verification claim.** The reproduction above and the mismatch scan were both executed against this checkout at capture time; the P5 result, the 2,083 write-only frontmatter fields, and the four named mismatches are observed, not inferred. The ll-product figures cited in the originating report (`{P5: 125}`, the `P3:118, P2:109, P4:38, P1:20, P0:13, P5:4` frontmatter spread, the ll-mcp summary cards) are from an external repo and were **not** independently verified here; they match the predicted symptom of the confirmed mechanism.

## Steps to Reproduce

```bash
mkdir -p /tmp/pritest/.issues/enhancements && cd /tmp/pritest
printf -- '---\nid: ENH-279\npriority: P1\nstatus: open\n---\n\n# Test\n' \
  > .issues/enhancements/ENH-279-foo.md
python -c "
from pathlib import Path
from little_loops.issue_parser import IssueParser
from little_loops.config import BRConfig
p = IssueParser(BRConfig(Path('.')))
i = p.parse_file(Path('.issues/enhancements/ENH-279-foo.md'))
print(i.priority, i.priority_int)
"
# actual:   P5 5
# expected: P1 1
```

For the drift half, from this repo's root:

```bash
python3 - <<'EOF'
import re, pathlib
for p in pathlib.Path('.issues').rglob('*.md'):
    m = re.search(r'^priority:\s*(P[0-5])', p.read_text(errors='ignore'), re.M)
    fm = re.match(r'^(P[0-5])-', p.name)
    if m and fm and fm.group(1) != m.group(1):
        print('MISMATCH', p.name, '-> frontmatter', m.group(1))
EOF
```

## Root Cause

`IssueParser.parse_file` (`scripts/little_loops/issue_parser.py`) treats the filename as the sole priority source. `_parse_priority` has no access to the file's frontmatter — it takes a `filename: str`, not a path or parsed content — so the fallback to `issue_priorities[-1]` fires for any file whose name lacks the prefix, regardless of what the frontmatter says.

The drift half has a separate proximate cause: `apply_priorities` in `scripts/little_loops/cli/issues/prioritize.py` performs a pure path operation (`git_mv_with_fallback`) and never reads or rewrites file content, so the frontmatter copy written at creation is never updated on re-prioritization.

The two share a root: priority is stored twice with no designated authority and no invariant enforcing agreement.

## Location

- `scripts/little_loops/issue_parser.py:58` — `_ANCHORED_FILENAME_RE`, optional priority group
- `scripts/little_loops/issue_parser.py:2767` — `parse_file` call site, sole priority source
- `scripts/little_loops/issue_parser.py:2927-2939` — `_parse_priority` and the P5 fallback
- `scripts/little_loops/cli/issues/create.py:311` — writes frontmatter `priority` (write-only today)
- `scripts/little_loops/cli/issues/prioritize.py:132-143` — renames without touching frontmatter
- `scripts/little_loops/cli/issues/show.py:79-81` — independent filename regex, yields `None` not P5

## Related Key Documentation

- `docs/reference/ISSUE_TEMPLATE.md` — issue frontmatter reference; does not currently document `priority:`
- `.claude/CLAUDE.md` § Issue File Format — filename convention `P[0-5]-[TYPE]-[NNN]-description.md`

## Status

**Open** | Created: 2026-08-21 | Priority: P2


## Session Log
- `/ll:capture-issue` - 2026-08-21T17:37:13 - `0c91fc4e-e09c-41b9-a77b-d05fa80fd5b1.jsonl`
