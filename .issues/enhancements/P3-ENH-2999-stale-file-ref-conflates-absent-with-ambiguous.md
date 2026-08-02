---
id: ENH-2999
status: open
priority: P3
captured_at: "2026-08-02T14:05:00Z"
discovered_date: 2026-08-02
discovered_by: capture-issue
relates_to: [ENH-2983, ENH-2971, ENH-2946]
testable: true
---

# `stale_file_ref` reports ambiguous multi-match references as drift

## Summary

`classify_file_ref()` returns `stale` for a reference that suffix-matches more
than one tracked file. Declining to resolve is correct — a silent pick would be
worse — but `stale` tells the reader the file moved or vanished, when the truth
is "this path matches two real files; disambiguate the reference." Wrong verdict
class for a correct decision. **86 instances** across `.issues/`.

## Current Behavior

`scripts/little_loops/text_utils.py` — `resolve_ref_path()` returns `None` for
both "no match" and "more than one match", and `classify_file_ref()` collapses
both into `stale`:

```python
matches = [p for p in candidates if p.endswith(suffix)]
if len(matches) == 1:
    return matches[0]
non_mirror = [p for p in matches if not p.startswith(_mirror_prefixes())]
return non_mirror[0] if len(non_mirror) == 1 else None   # 0 matches and 3 matches
                                                          # are indistinguishable here
```

Worked examples from the corpus:

| Reference | Matches | Reported |
|---|---|---|
| `issues/anchor_sweep.py` | `scripts/little_loops/cli/issues/anchor_sweep.py`, `scripts/little_loops/issues/anchor_sweep.py` | `stale` |
| `agents/openai.yaml` | 66 tracked `skills/*/agents/openai.yaml` files | `stale` |

The docstring already documents the *decision* ("ambiguous matches must not
silently resolve") — this issue is about the *label*, not the resolution policy.

Note the mirror tie-break added alongside this issue's capture handles the
specific case where the ambiguity is a generated host-adapter copy
(`.codex/`, `.gemini/`, `.kimi-code/`) shadowing its source. The 86 above are
the residue: genuine same-name ambiguity between two real source paths.

## Expected Behavior

An ambiguous reference is reported as its own thing, with the candidate paths
named so the reader can disambiguate:

```
  ambiguous_file_ref: issues/anchor_sweep.py (matches 2: scripts/little_loops/cli/issues/…, scripts/little_loops/issues/…)
```

`stale_file_ref` then means what it says: a `/`-qualified path matching nothing.

## Motivation

The two conditions call for opposite fixes. `stale` says "find where this moved
or delete the reference"; ambiguous says "add the missing path prefix." Reporting
both under one label sends the reader after the wrong fix, and — because 86 of
them sit inside a 3,331-finding pile — makes the pile marginally less trustworthy
in a way that discourages acting on any of it.

## Proposed Solution

Add `ambiguous` to `RefStatus` (`text_utils.py:111`) and return it when the
suffix-match set has more than one member after the mirror tie-break.

Three consumers must be updated in the same change — this is why it is not a
narrow fix:

1. **`issue_parser.check_format_gaps()`** (`issue_parser.py:528`) — decide
   whether `ambiguous` gets its own `FormatGaps` field (recommended: it is
   separately actionable) or folds into `stale_file_ref`'s list with a
   distinguishing suffix.
2. **`cli/issues/format_check.py:154`** — print the candidate paths, not just
   the ref. The count is the actionable part.
3. **`issues/research_triage.py:186`** — `qualified_ref_count()` gates on
   `in ("resolved", "stale")`. Decide deliberately whether an ambiguous ref
   counts toward ENH-2971's ≥80% axis-coverage denominator. It probably should
   (the author did cite a real file), but leaving the tuple untouched silently
   drops it.

## Program Design

The resolution *policy* is unchanged; only the return channel widens so callers
can tell the two failure modes apart. `resolve_ref_path` currently returns
`str | None`, collapsing "no match" and "many matches" into `None`.

### Signatures

```python
RefStatus = Literal["resolved", "stale", "unresolvable_form", "planned_new", "ambiguous"]

@dataclass(frozen=True)
class RefResolution:
    path: str | None = None            # the single resolved path, else None
    candidates: tuple[str, ...] = ()   # >1 when ambiguous, empty when absent

def resolve_ref(ref: str, index: RefIndex) -> RefResolution: ...
def resolve_ref_path(ref: str, index: RefIndex) -> str | None: ...  # kept as a wrapper
```

`classify_file_ref` maps the resolution: `path` set → `resolved`; `candidates`
non-empty → `ambiguous`; both empty → `stale`. The candidate list is what makes
the report actionable, so it must survive to the CLI rather than being reduced
to a boolean at the classifier boundary.

`resolve_ref_path` stays as a thin wrapper returning `resolution.path` — ENH-2971's
call sites want the target path, not the ambiguity detail, and keeping it spares
them a change.

### Call Path

`classify_issue_refs` → `classify_file_ref` → `resolve_ref` (new; wraps the
existing suffix-match body), then out to the two consumers:

- `check_format_gaps` → `main_format_check` — gains an `ambiguous` bucket in
  `FormatGaps` and prints the candidates
- `qualified_ref_count` — decide explicitly whether `ambiguous` joins
  `resolved`/`stale` in the coverage denominator

## Integration Map

### Files to Modify

- `scripts/little_loops/text_utils.py` — `RefStatus`, `resolve_ref_path`,
  `classify_file_ref`, and the numbered resolution-order docstring
- `scripts/little_loops/issue_parser.py` — `FormatGaps` field + population
- `scripts/little_loops/cli/issues/format_check.py` — reporting
- `scripts/little_loops/issues/research_triage.py` — denominator membership
- `.claude/CLAUDE.md` § CLI Tools — the `format-check` gap-class list enumerates
  every class by name and would go stale

### Dependent Files

- `scripts/tests/test_text_utils.py` — `test_ambiguous_suffix_match_does_not_resolve`
  deliberately asserts the loose `!= "resolved"`, so it stays green; tighten it
  to assert `== "ambiguous"` as part of this change
- `scripts/tests/test_ll_issues_format_check.py`

### Conventions in Force

- `resolve_ref_path()` is the single resolution path shared by `format-check`
  and `research-triage` — evidence: its docstring states the two must not drift.
  Any new status must be introduced there, not branched per consumer.

## Implementation Steps

1. `RefStatus` gains `ambiguous`; `resolve_ref_path` distinguishes the zero-match
   and many-match cases (returning the candidates, or a sentinel, rather than a
   bare `None`).
2. Each of the three consumers handles the new member explicitly — no silent
   fall-through to an `else` branch.
3. Corpus re-measurement shows ~86 findings moving `stale` → `ambiguous` and no
   ref changing `resolved` → anything else.
4. `python -m pytest scripts/tests/` passes.

## Impact

- **Effort**: Small-Medium — the classifier change is a few lines; the cost is
  the three consumers and deciding the research-triage denominator question.
- **Risk**: Low — additive status; the resolution policy does not change.
- **Breaking Change**: `RefStatus` is a public `Literal`. Any external consumer
  exhaustively matching it would need the new member, though there are none in
  this repo outside the three listed.

## Scope Boundaries

- **In scope**: the verdict label and its propagation to the three consumers.
- **Out of scope**: changing *whether* ambiguous refs resolve. Declining is
  correct and stays.
- **Out of scope**: untracked-by-design directories reporting `stale` — that is
  a separate root cause with its own issue.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/text_utils.py` | The classifier and its resolution-order contract |
| `.claude/CLAUDE.md` | § CLI Tools enumerates `format-check`'s gap classes |

## Session Log
- `/ll:capture-issue` - 2026-08-02

## Status

- **Status**: open
