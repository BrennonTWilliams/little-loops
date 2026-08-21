---
id: BUG-3287
type: BUG
title: locate_enumerable_options lets a tier match preempt Pattern E, and its bullet
  tier cannot see bold-wrapped markers
priority: P2
status: open
parent: EPIC-3290
discovered_by: bug-3278-pre-implementation-review
discovered_date: '2026-08-21'
captured_at: '2026-08-21T19:30:00Z'
labels:
- issue-parser
- decide-issue
- decision-needed
- pipeline
relates_to:
- BUG-3278
- BUG-3279
---

# BUG-3287: locate_enumerable_options lets a tier match preempt Pattern E, and its bullet tier cannot see bold-wrapped markers

## Summary

`locate_enumerable_options` (`issue_parser.py:2134`) resolves a document to **one** option set by
running `_OPTION_PATTERNS` tiers 1–4 first and falling back to the Pattern E directive heuristic
`_locate_directive_alternatives` (`:2062`) only when **all four tiers miss document-wide**. Two
defects follow from that chain:

1. **Pattern E preemption (live today).** Any tier match anywhere in the resolved section hides a
   co-located prose decision directive. Measured over the live `.issues/` corpus: **6 issues** carry
   a Pattern E directive that a tier match preempts right now, with no code change required.
2. **The `bullet` tier cannot match a bold-wrapped marker.** `_OPTION_PATTERNS[3]` requires the
   `(a)` marker to sit immediately after the dash, so `- **(a) Make the override real.**` — the
   idiomatic option shape in this repo's issues — matches **zero** tiers. It is not out-competed;
   it is unreachable.

Split out of BUG-3278 at pre-implementation review. BUG-3278 fixes both defects *inside its own
new group iterator* (which probes directives in addition to tiers, under
`include_approximate_tiers=True`); this issue fixes them in the shared precedence chain that
`check-decidable`, `locate-options`, `count_enumerable_options`, and `/ll:decide-issue` Phase 2.5
all sit on. The two are independent — neither blocks the other.

## Current Behavior

`locate_enumerable_options` walks sections in precedence order (`## Proposed Solution`, then
`_OPTION_FALLBACK_SECTIONS`, then a whole-document H2 sweep), handing each section body to
`_locate_options_in_text` (`:1967`), which **returns on the first `_OPTION_PATTERNS` tier with
≥1 match**. `_locate_directive_alternatives` is reached only after every section and every tier
has missed.

### Defect 1 — a tier match preempts a Pattern E directive

Because the directive probe is a *fallback* rather than an *additional* probe, a document holding
both an enumerated option set and a separate prose decision directive reports only the former.
Reproduced over the live corpus:

```python
import pathlib
from little_loops.issue_parser import locate_enumerable_options, _locate_directive_alternatives
for p in pathlib.Path('.issues').rglob('*.md'):
    c = p.read_text()
    loc, d = locate_enumerable_options(c), _locate_directive_alternatives(c)
    if d is not None and loc.pattern not in (None, 'provisional_e'):
        print(p.name, loc.count, loc.pattern, '| hidden directive in', d.heading, 'line', d.options[0].start_line)
```

Six live issues, e.g.:

| Issue | Reported | Hidden directive |
|---|---|---|
| BUG-1183 | `count 2`, `bold_label` | `## Proposed Solution`, line 55 |
| ENH-2446 | `count 2`, `bullet` | `## Proposed Solution`, line 123 |
| ENH-2873 | `count 2`, `bold_label` | `## Proposed Change`, line 84 |
| ENH-2239 | `count 2`, `bold_label` | `## Scope Boundaries`, line 49 |
| ENH-3275 | `count 2`, `section_header` | `## Proposed Solution`, line 73 |
| FEAT-2339 | `count 2`, `bold_label` | `## Proposed Solution`, line 128 |

`/ll:decide-issue` Phase 3 scores the tier options, Phase 7b clears `decision_needed`, and the
directive is never surfaced.

### Defect 2 — the bullet tier cannot see a bold-wrapped marker

```python
from little_loops.issue_parser import _OPTION_PATTERNS
s = "- **(a) Make the documented override real.**"
[i for i, p in enumerate(_OPTION_PATTERNS) if p.search(s)]   # -> []  (no tier matches)
```

`_OPTION_PATTERNS[3]` is `r"^[-*]\s+(?:\([a-z0-9]\)\s+|\*{0,2}Option\s+[A-Za-z0-9])"` — the
`\*{0,2}` bold-tolerance applies only to the `Option X` alternative, never to the `(a)` marker,
and the marker alternative additionally requires `\s+` after the closing paren.

Consequence: `check-decidable` reports such a document as having nothing to decide, routing
`resolve-decision.yaml`'s `check_decision_decidable` (`:47-67`) to `refine` instead of `decide`.

## Steps to Reproduce

**Defect 1** (no fixture needed — reproduces on committed files):

1. Run the corpus script above against `.issues/`.
2. Observe six issues where `_locate_directive_alternatives` finds a directive that
   `locate_enumerable_options` does not report.
3. `ll-issues locate-options ENH-2446 --json` → `pattern: "bullet"`, no mention of the
   `## Proposed Solution` directive at line 123.

**Defect 2**:

1. Author an issue whose `## Proposed Solution` holds only `- **(a) …**` / `- **(b) …**` bullets.
2. `ll-issues locate-options <ID> --json` → `count 0`, `pattern: null`.
3. `ll-issues check-decidable <ID>` → exit 1 ("nothing to decide"), despite a decision being
   plainly present.

## Expected Behavior

- A Pattern E directive is reported even when a tier also matches — the document holds two decision
  points and the precedence chain must not silently pick one.
- A bold-wrapped `- **(a) …**` marker matches the `bullet` tier.
- No document that matches a tier today stops matching, and no document's reported `count` drops.

## Motivation

Both defects hide decision points from the deterministic layer that FSM loops gate on. Defect 1 is
live on six committed issues; defect 2 makes the repo's own idiomatic option shape invisible to
`check-decidable`, so a decidable issue takes a pointless `/ll:refine-issue` detour and, in the
worst case, has `decision_needed` cleared against an option set that was never seen.

This is also the precondition for BUG-3278's coverage to be complete: BUG-3278's group iterator
fixes both defects for its own new probe, but leaves the shared chain — and therefore
`check-decidable`, Phase 2.5, and `count_enumerable_options` — untouched.

## Proposed Solution

Two parts. **Part 1 must land with or before part 2** — part 2 materially widens part 1's blast
radius, and shipping part 2 alone introduces a new false-clear (see *Ordering constraint*).

### Part 1 — probe directives in addition to tiers

In `locate_enumerable_options`, call `_locate_directive_alternatives` alongside the tier scan
rather than only after it. When both produce a result, the returned `LocatedOptions` must express
both. Two viable shapes; pin one during implementation:

- **Merge** — return the tier result with the directive's `LocatedOption` appended and
  `pattern` set to the tier name, `count` incremented. Cheapest, but `pattern` then lies about one
  of the entries.
- **Precedence-preserving with a flag** — return the tier result unchanged plus a new
  `residual_directive: LocatedOption | None` field on `LocatedOptions`. Keeps `count`/`pattern`
  contracts byte-identical for every existing consumer, and gives Phase 3 / `check-decidable`
  something explicit to branch on. **Recommended** — the `count` field feeds
  `/ll:decide-issue` Phase 3's `count == 1` branch (which clears `decision_needed` outright), so
  mutating `count` is the higher-risk shape.

### Part 2 — widen `_OPTION_PATTERNS[3]`

```python
r"^[-*]\s+\*{0,2}(?:\([a-z0-9]\)\s*|Option\s+[A-Za-z0-9])"   # MULTILINE | IGNORECASE
```

Hoists `\*{0,2}` out of the `Option` alternative so it covers the `(a)` marker too, and relaxes
the post-marker `\s+` to `\s*`.

### Ordering constraint

Part 2 without part 1 **introduces a new false-clear**. Verified against BUG-3229:

| | `count` | `pattern` | section |
|---|---|---|---|
| today | 2 | `provisional_e` | Proposed Solution |
| part 2 alone | **1** | `bullet` (label `(i)`) | Proposed Solution |

A stray `- (i)` bullet becomes a tier-4 match, preempts the real 2-alternative directive, and
collapses the result to `count 1` — which is `/ll:decide-issue` Phase 3's *"Only one option present
— no decision required. Clearing `decision_needed` if set"* branch (`SKILL.md:187`). Part 1 keeps
the directive visible, so the count does not collapse.

### Blast radius

Measured by applying part 2 to every file in `.issues/` and diffing `locate_enumerable_options`
output: **22 of the live corpus change**. Two change in ways a regex-level superset check does not
predict, because tier precedence and *section* precedence both shift:

| Issue | Before | After | Why it matters |
|---|---|---|---|
| BUG-3229 | `2`, `provisional_e` | `1`, `bullet` | count **drops**; hits the `count == 1` clear branch — the case part 1 exists to prevent |
| ENH-3264 | `1`, `numbered`, §Confidence Check Notes | `2`, `bullet`, §**Proposed Solution** | the winning **section** changes, not just the tier |

The remaining 20 are `count 0 → N`, `pattern null → bullet` — the intended correction.

Affected consumers:

- `ll-issues check-decidable` (`cli/issues/check_decidable.py:19-52`) — only tests `count >= 1`, so
  `0 → N` flips it to decidable and `2 → 1` is inert. Live routing change in
  `resolve-decision.yaml:47-67` (`refine` → `decide`).
- `ll-issues locate-options` — `count`/`pattern`/`heading` all move on the 22.
- `count_enumerable_options` — scoring/gap heuristics; "no options" documents become "has options".
- `/ll:decide-issue` Phase 2.5 (`SKILL.md:110-146`) — fewer `OPTIONS_MISSING` exits.

### Verified match matrix (part 2)

Strict superset at the regex level — every previously-matching shape still matches:

| Shape | today | after |
|---|---|---|
| `- (a) foo` | ✓ | ✓ |
| `* Option B: x` | ✓ | ✓ |
| `- **Option B** x` | ✓ | ✓ |
| `- **(a) foo**` | ✗ | **✓** |
| `- *(a)* foo` | ✗ | **✓** |
| `- (a)foo` | ✗ | **✓** |
| `- (a): text` | ✗ | **✓** |
| `- (a)` | ✗ | **✓** |
| `- some bullet` | ✗ | ✗ |
| `- optional extras` | ✗ | ✗ |
| `- **Options** are` | ✗ | ✗ |
| `1. (a) foo` | ✗ | ✗ |
| `  - (a) indented` | ✗ | ✗ |
| `-(a) foo` | ✗ | ✗ |

Note the last four newly-matching rows come from the `\s+`→`\s*` relaxation, not the bold
widening. A bare `- (a)` in unrelated prose is now a `bullet`-tier match — intended (a marker-only
bullet is still an option label), but it is why the corpus differential below is a required test,
not an optional one.

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_parser.py` — `locate_enumerable_options` directive-probe ordering
  (+ `LocatedOptions.residual_directive` if the recommended shape is taken), `_OPTION_PATTERNS[3]`

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/issues/check_decidable.py:19-52` — `count >= 1` gate
- `scripts/little_loops/cli/issues/locate_options.py:19-38` — `--json` payload
- `scripts/little_loops/issues/fold_research_findings.py:178` — prose reference to
  `count_enumerable_options`
- `scripts/little_loops/loops/oracles/resolve-decision.yaml:47-67` (`check_decision_decidable`)
- `skills/decide-issue/SKILL.md:110-146` (Phase 2.5), `:160-190` (Phase 3 extraction + the
  `count == 1` branch at `:187`)
- `commands/refine-issue.md:524` — cites `count_enumerable_options()`/`count_unresolved_options()`

### Similar Patterns

- `locate_unresolved_options` (`issue_parser.py:2240`) mirrors the same *section* precedence but
  its own block iterator; it does **not** read `_OPTION_PATTERNS` and is unaffected by part 2

### Tests

- `scripts/tests/test_issue_parser_unresolved.py` — the match matrix above as a table-driven case;
  a new `TestDirectiveNotPreempted` covering a document with both a tier match and a directive
- **Corpus differential (required):** a test that applies `locate_enumerable_options` across
  `.issues/` and asserts no file's `count` decreases and no file's resolved `heading` changes.
  This is the only check that would have caught BUG-3229 and ENH-3264; the 14-shape regex matrix
  passes both.
- `scripts/tests/test_issues_locate_options.py` — a case asserting `- **(a) …**` reports
  `pattern: "bullet"`
- `scripts/tests/test_ll_issues_check_decidable.py` — a case asserting the same document is
  decidable, and one asserting a tier+directive document still reports the directive

### Documentation

- `docs/reference/API.md:987-1032` — `locate_enumerable_options` precedence prose and the
  documented `bullet` shape; `count_enumerable_options` wrapper note
- `docs/reference/CLI.md:1945` (`check-decidable` Pattern E coverage sentence), `:2023`
  (`locate-options` precedence framing and worked example)
- `docs/guides/DECISIONS_LOG_GUIDE.md:198` — states Pattern E is reached when formal option blocks
  are absent; becomes false under part 1

### Configuration

N/A

## Program Design

### Types

- `LocatedOptions.residual_directive: LocatedOption | None` — new optional field (recommended
  shape), default `None` so every existing constructor call and `to_dict()` consumer is unaffected

### Signatures

- `locate_enumerable_options(content: str) -> LocatedOptions` —
  `scripts/little_loops/issue_parser.py:2134` — unchanged signature; the directive probe moves from
  terminal fallback to an additional probe
- `_locate_directive_alternatives(content: str) -> LocatedOptions | None` —
  `scripts/little_loops/issue_parser.py:2062` — unchanged
- `_locate_options_in_text(content: str, body: str, body_offset: int) -> LocatedOptions | None` —
  `scripts/little_loops/issue_parser.py:1967` — unchanged; still first-tier-wins within a section
- `_OPTION_PATTERNS: tuple[re.Pattern, ...]` — `scripts/little_loops/issue_parser.py:1891` —
  element 3 widened

### Call Path

`ll-issues check-decidable` / `ll-issues locate-options` -> `cmd_check_decidable`
(`cli/issues/check_decidable.py:34`) / `cmd_locate_options` (`cli/issues/locate_options.py:38`) ->
`locate_enumerable_options` (`issue_parser.py:2134`) -> `_locate_options_in_text` (`:1967`) **and**
`_locate_directive_alternatives` (`:2062`) -> `LocatedOptions`

### Decision Rules

One decision remains, scoped and enumerable — the return shape for part 1:

**Option A — merge into `count`/`options`.** Append the directive's `LocatedOption`; increment
`count`. Simplest diff, no dataclass change. Costs: `pattern` misdescribes one entry, and `count`
moves for the 6 live preemption cases — which perturbs Phase 3's `count == 1` branch and
`check-decidable`'s threshold on documents that are not otherwise changing.

**Option B — `residual_directive` field.** Leave `count`/`pattern`/`options` byte-identical;
surface the directive on a new optional field. Costs: one dataclass field and a `to_dict()` entry;
consumers must opt in to see it, so `check-decidable` needs an explicit `or residual_directive`
clause to benefit.

Recommendation: **Option B**, because `count` is load-bearing for a branch that clears
`decision_needed` outright, and Option A moves it on documents this issue is not otherwise
touching.

## Implementation Steps

1. **Part 1 first.** Restructure `locate_enumerable_options` so `_locate_directive_alternatives`
   runs in addition to the tier scan; pin the return shape per *Decision Rules*. Add
   `TestDirectiveNotPreempted` and assert the six live corpus cases now surface their directive.
2. Land the corpus differential test (no `count` decreases, no `heading` changes) **before**
   part 2, so it fails loudly if part 2 regresses a file.
3. **Part 2.** Widen `_OPTION_PATTERNS[3]`. Add the 14-shape match matrix as a table-driven test.
4. Add the `locate-options` and `check-decidable` cases pinning the newly-reachable
   `- **(a) …**` shape as `bullet`/decidable — these are behavior changes to existing consumers
   and must be pinned by test, not left implicit.
5. Re-run the corpus differential; confirm BUG-3229 holds at `count 2` and ENH-3264's resolved
   section is stable.
6. Update the four documentation sites in *Integration Map → Documentation*.

**Out of scope**: `locate_unresolved_options` and `_iter_option_blocks` (`:2210-2240`) — they do not
read `_OPTION_PATTERNS`, and widening their conservatism is a loop-gate change with its own blast
radius (the ENH-2446 comment at `:2225` is a deliberate choice). BUG-3278 covers the decision-group
layer built over them.

## Impact

- **Priority**: P2 — defect 1 is live on six committed issues and silently hides a decision point;
  defect 2 makes the repo's own idiomatic option shape invisible to the decidability gate. Neither
  is a common-path break, which is what keeps it off P1.
- **Effort**: Medium — two small, well-bounded edits to one module, but the test burden is real:
  a corpus differential plus pinning tests for three existing consumers.
- **Risk**: Medium. `_OPTION_PATTERNS` is module-level state on the shared precedence chain; 22
  live issues change output, and two of them change in ways the obvious regex-superset check does
  not predict. Bounded by the ordering constraint (part 1 before part 2) and the corpus
  differential, which is the only test that catches the count-drop and section-shift classes.
- **Breaking Change**: No — no signature or CLI contract changes under the recommended shape.

## Root Cause

- **File**: `scripts/little_loops/issue_parser.py`
- **Anchor**: `in function locate_enumerable_options()` and `_OPTION_PATTERNS[3]`
- **Cause**: The precedence chain treats `_locate_directive_alternatives` as a terminal fallback
  reached only when every tier misses document-wide, so a tier match masks a co-located prose
  directive. Separately, `_OPTION_PATTERNS[3]`'s `\*{0,2}` bold-tolerance was scoped to the
  `Option X` alternative only, leaving `- **(a) …**` unreachable by any tier.

## Related Key Documentation

- `docs/guides/DECISIONS_LOG_GUIDE.md:198` — documents the Pattern E fallback semantics this
  issue changes
- `docs/reference/CLI.md:1945` — documents `check-decidable`'s Pattern E coverage
- BUG-3278 — the sibling this was split out of; fixes the same two defects inside its own new
  decision-group iterator, leaving the shared chain to this issue

## Status

**Open** | Created: 2026-08-21 | Priority: P2
