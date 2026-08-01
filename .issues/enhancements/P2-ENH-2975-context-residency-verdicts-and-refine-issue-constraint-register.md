---
id: ENH-2975
title: Context-residency verdicts (ll-doctor --trim) and refine-issue constraint register
type: ENH
status: done
priority: P2
completed_at: 2026-08-01 17:31:18+00:00
discovered_date: 2026-08-01
discovered_by: research-review
relates_to:
- ENH-2970
- ENH-2971
- ENH-2972
testable: true
labels:
- context
- doctor
- refine-issue
- cli
---

# ENH-2975: Context-residency verdicts (`ll-doctor --trim`) and refine-issue constraint register

## Summary

Two changes shipped directly during a review of the Boris Cherny / Claude Code
workflow talk (`2026-08-01-claude-code-creators-greatest-tip-for-using-ai-agents.md`),
without a prior issue. Captured retroactively so the design decisions and their
rationale are recoverable.

1. **`ll-doctor --trim`** — a context-residency report answering "is this
   component earning the context it costs?", distinct from the rest of
   `ll-doctor`'s "is this component broken?".
2. **`/ll:refine-issue` register change** — the command now deposits
   constraints and conventions rather than recipes and templates.

Sibling issues ENH-2971 and ENH-2972 were captured in the same session for the
work *not* done here.

## Current Behavior

_(pre-change)_

**Residency.** Nothing in little-loops expired. The setup accumulated
monotonically — ~40 skills, 29 commands, a ~10,300-token `.claude/CLAUDE.md` —
and no pass asked whether a given line still earned its place. The component
signals existed but were not joined to that question: `ll-logs dead-skills`
ranked usage without cost, `ll-ctx-stats` reported cost without per-component
usage, and `ll-doctor` checked only install health.

**refine-issue.** `commands/refine-issue.md` deposited an ordered recipe into
`## Implementation Steps` ("1. Modify `parser.py:parse_args()` to handle new
flag") and pointed the implementer at exemplar files to reproduce
(`### Similar Patterns` — "`path/to/similar.py:100` — similar implementation to
follow"). The `codebase-pattern-finder` prompt asked for "test patterns to
model after."

## Expected Behavior

`ll-doctor --trim` reports per-component residency cost joined against recorded
usage, with a verdict whose confidence matches the evidence behind it.
`/ll:refine-issue` deposits ground truth and invariants; the route stays the
implementer's call.

## Motivation

From the source talk, two claims drove this:

- **§1** — a setup is mostly corrections for things models used to get wrong;
  on a capable model the hand-holding is what gets in the way. The measurement
  has to exist before that judgment can be applied to anything.
- **§3** — telling the model *how* caps the result at your own approach, and
  anything concrete handed over gets copied rather than learned from.

The second claim does not transfer wholesale: `refine-issue`'s output is
consumed by headless automation with no human present, and the issue is the
durable artifact across context boundaries. The talk assumes a live human
prompting a fresh session. So the applicable cut was the *register* of what
gets written, not the sections it gets written to — Integration Map, Root
Cause, and callers/dependents are exactly the constraints an implementer
cannot cheaply rediscover, and stay.

Separately, the trim report immediately produced the evidence for ENH-2972:
three `CLAUDE.md` sections account for ~6,900 of ~10,300 resident tokens.

## Proposed Solution

_(as implemented)_

**`--trim` verdict vocabulary**, split by whether the evidence is decidable
from cost + usage alone:

| Verdict | Meaning | Decidable? |
|---|---|---|
| `trim` | resident cost > 0, zero invocations in window | Yes — it demonstrably returned nothing for what it charged |
| `review` | costly but rarely used, **or** a memory section (no per-line usage signal exists) | No — a pointer at what deserves judgment, not a recommendation to cut |
| `keep` | used often enough to have earned residency | Yes |

**Design decision — the CLI does not answer the talk's own question.** "Would
the model have worked this out on its own?" is not computable from cost and
usage. For memory files the tool reports section-level cost and defers; a
`CLAUDE.md` section is never auto-verdicted `trim`. The alternative — having
the CLI guess — produces confident garbage on exactly the sections where
being wrong is most expensive.

**Design decision — absent telemetry is not evidence of disuse.** A missing
`.ll/history.db`, or one without a `skill_events` table, yields
`usage_available: false` and scores nothing as `trim`. Without this a fresh
install would score its entire catalog dead. A *present but empty* table is
real evidence and does score.

**Design decision — `--trim` is advisory.** It never affects the exit code. An
unused skill is a cost signal, not a broken install; folding it into the exit
code would fail every project that ships more of the catalog than it happens
to use.

## Program Design

### Signatures

```python
Verdict = Literal["keep", "trim", "review"]

@dataclass(frozen=True)
class TrimComponent:
    name: str
    kind: Literal["memory", "skill", "command"]
    scope: str
    resident_tokens: int
    invocations: int | None   # None == no usage signal applies, != recorded 0
    verdict: Verdict
    rationale: str

@dataclass(frozen=True)
class TrimReport:
    components: tuple[TrimComponent, ...]
    window_days: int
    usage_available: bool
    sessions_observed: int

def collect_trim_report(root: Path | None = None, *, window_days: int = 90) -> TrimReport
def render_trim_report(report: TrimReport) -> None
```

### Call Path

- `main_doctor` → `collect_trim_report` → `render_trim_report`
- `collect_trim_report` → `_memory_components` and `_catalog_components`
- `_usage_counts` reads `skill_events` read-only; mirrors the aggregation in
  `_aggregate_skill_stats`
- `_estimate_tokens` follows the repo-wide convention in `check_skill_budget`

`--trim` results are deliberately excluded from the `results` list that
`_exit_code_for` grades.

## Integration Map

### Files Modified

- `scripts/little_loops/cli/doctor_trim.py` — new module
- `scripts/little_loops/cli/doctor.py` — `--trim` / `--trim-window-days`
  flags, JSON key, render call, exit-code exclusion comment
- `scripts/tests/test_cli_doctor_trim.py` — new, 25 tests
- `commands/refine-issue.md` — register section, pattern-finder prompt,
  Integration Map template, Implementation Steps template
- `.gemini/commands/refine-issue.toml` — regenerated mirror
- `.claude/CLAUDE.md` — `--trim` documented on the `ll-doctor` entry

### Conventions in Force

- Token estimation is `len(text) // 4` throughout — evidence:
  `doc_counts.check_skill_budget`, `cache_marking_oracle`
- Doctor checks are frozen dataclasses with closed status vocabularies —
  evidence: `CheckResult`, `FindingDetail` in `doctor.py`
- History DB reads that must not create the file open `mode=ro` after an
  explicit existence probe — evidence: `_history_db_data` in `doctor.py`

### Tests

- `scripts/tests/test_cli_doctor_trim.py` — section splitting (including that
  section bodies cover the whole file, so costs sum to real residency), usage
  verdicts, absent-telemetry handling, memory-never-trims, report aggregates,
  and exit-code isolation

## Implementation Steps

_(completed — stated as the outcomes verified)_

1. `ll-doctor --trim` reports per-section memory cost and per-entry catalog
   cost joined against `skill_events` usage. **Verified** against this repo.
2. No memory section is ever verdicted `trim`. **Verified** by
   `test_memory_never_verdicts_trim`.
3. Absent or table-less telemetry scores nothing as `trim`; an empty table
   does. **Verified** by `TestAbsentTelemetry`.
4. `--trim` does not change the exit code. **Verified** by
   `test_trim_findings_do_not_affect_exit_code`.
5. `refine-issue` no longer instructs the pattern-finder to find things to
   "model after," and no longer templates an imperative recipe.
6. `python -m pytest scripts/tests/` passes (17,621 passed, 42 skipped);
   `ruff check scripts/` and `python -m mypy scripts/little_loops/` clean.

## Scope Boundaries

- **In scope**: the measurement, and the register of what `refine-issue`
  writes.
- **Out of scope**: acting on the measurement (ENH-2972), and gating
  `refine-issue`'s subagent fan-out (ENH-2971).
- **Out of scope**: the user-level `~/.claude/CLAUDE.md`.
- **Deliberately not done**: making `--trim` auto-apply anything. Every
  verdict is advisory; nothing is deleted, and no `--fix` mode exists.

## Impact

- **Effort**: Medium — one new module, one prose rewrite.
- **Risk**: Low. `--trim` is additive and advisory. The refine-issue change
  carries the only real risk: register guidance is prose and therefore
  unenforced, so drift back toward recipe-writing would be silent. No test
  covers it.
- **Breaking Change**: No.

## Resolution

**`ll-doctor --trim`** (`scripts/little_loops/cli/doctor_trim.py`, new):
joins `len(text)//4` residency cost against `skill_events` usage from
`.ll/history.db` over a `--trim-window-days` window (default 90), emitting
`trim`/`review`/`keep` per component. Memory files are split at H2 boundaries
and cost-reported only. Wired into `ll-doctor` behind `--trim`, present in
`--json` output under a `trim` key, excluded from the exit code.

Against this repo it reports ~10,400 resident tokens, of which three
`CLAUDE.md` sections hold ~6,900 (`## CLI Tools` 3,695; `## Loop Authoring`
1,939; `## Issue File Format` 1,268), plus 354 tokens/session across 16
never-invoked catalog entries. That output is the evidence base for ENH-2972.

**`/ll:refine-issue`** (`commands/refine-issue.md`): added a
`## Register: Constraints, Not Recipes` section with a write-this/not-this
table, then changed the three places it binds — the `codebase-pattern-finder`
prompt now asks for *the rule the examples share* with the file cited as
evidence (and to report both sides when two examples disagree, rather than
silently picking one), the Integration Map's `### Similar Patterns` became
`### Conventions in Force`, and the Implementation Steps template moved to
outcome-plus-verification phrasing with a note that imperative sequencing is
for genuinely forced orderings only.

### Incidental findings (not fixed here)

- **`ll-adapt` skips on presence, not content.** Regenerating the
  `refine-issue` mirror also rewrote `.gemini/commands/help.toml`, shrinking it
  368 lines against a 19-line `commands/help.md`; the same run reported
  `SKIP: already adapted` for 96 of 98 entries. An `--apply` over a fully
  drifted tree reports success and changes nothing. Appended as confirmed
  evidence to ENH-2968, which had listed this only as a hypothetical risk. The
  `help.toml` regeneration was reverted to keep it out of an unrelated change,
  so **the drift is still present on `main`**.
- **A fenced code block inside `## Program Design` breaks anchor extraction.**
  `_BACKTICKED` in `program_design.py:105` treats a triple-backtick fence as a
  single backtick pair, swallowing the block and mis-pairing every backtick
  after it, so `Call Path` anchors following a fence fail to resolve. Worked
  around by using plain bullets; not filed.
- `program_design_not_applicable: true` is honored by `format-check`, which
  may make BUG-2956 narrower than its title suggests.

## Related Key Documentation

- `.claude/CLAUDE.md` — `ll-doctor` entry documents `--trim`
- Source: `docs/research/inputs/2026-08-01-claude-code-creators-greatest-tip-for-using-ai-agents.md` (ll-product repo)

## Session Log
- `hook:posttooluse-status-done` - 2026-08-01T17:32:32 - `bdc3763a-d563-49bc-9770-c94f54d36615.jsonl`
- direct implementation - 2026-08-01T17:31:18Z

---

## Status

**Done** | Created: 2026-08-01 | Completed: 2026-08-01 | Priority: P2
