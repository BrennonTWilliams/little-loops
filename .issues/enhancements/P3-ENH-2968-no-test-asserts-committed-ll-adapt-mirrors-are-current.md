---
id: ENH-2968
title: No test asserts committed ll-adapt host mirrors are current
type: ENH
priority: P3
status: open
captured_at: '2026-08-01T16:02:14Z'
discovered_date: 2026-08-01
discovered_by: capture-issue
relates_to:
- FEAT-2916
- BUG-2956
testable: true
labels:
- adapters
- tests
---

# ENH-2968: No test asserts committed `ll-adapt` host mirrors are current

## Summary

`.kimi-code/` and `.gemini/` hold `ll-adapt`-generated mirrors of
`skills/*/SKILL.md` and `commands/*.md`, checked into the repo. Nothing
verifies they match what `ll-adapt` would produce from the current canonical
sources. A canonical skill edit that skips `ll-adapt --apply` leaves non-Claude
hosts silently running stale logic, and no test fails.

## Current Behavior

Editing `skills/confidence-check/SKILL.md` without re-running
`ll-adapt --host kimi-code --apply` / `--host gemini --apply` leaves
`.kimi-code/skills/confidence-check/SKILL.md` and
`.gemini/skills/confidence-check/SKILL.md` describing the previous logic. The
suite passes.

There *are* adapter tests, but they cover a different thing — worth stating
precisely so this issue is not mistaken for a duplicate:

- `scripts/tests/test_adapt_golden_corpus.py` (ENH-2883) runs
  `CodexEmitter`/`GeminiEmitter` over a **synthetic corpus**
  (`scripts/tests/fixtures/adapt/{skill,command,agent}_cases.json`) and writes
  into `tmp_path` (`L89`, `L148`). It asserts byte-identity of the
  *transform* across a refactor.
- `test_kimi_adapter.py`, `test_codex_adapter.py`, `test_adapters.py`,
  `test_adapt_skills_for_codex.py`, `test_adapt_agents_for_codex.py` likewise
  exercise emitter behavior against fixtures.

None of them reads the committed `.kimi-code/` or `.gemini/` trees. Testing
that the transform is correct is orthogonal to testing that the checked-in
output of that transform is current.

### Confirmed: the mirrors are already stale (2026-08-01)

The Impact section below listed "discovering the committed mirrors are already
stale" as a risk. It is not a risk; it is the current state, and there is a
second defect underneath it.

Running `ll-adapt --host gemini --only refine-issue --apply` after editing
`commands/refine-issue.md` regenerated **two** files: the intended
`refine-issue.toml`, and `.gemini/commands/help.toml`, which shrank by 368
lines. `commands/help.md` is 19 lines; the committed mirror held a ~370-line
copy of a long-superseded version. Nothing had regenerated it in the interim
and nothing flagged it.

The second defect: `ll-adapt` reported `SKIP  ll-<name>: already adapted` for
96 of 98 entries in that same run. The skip predicate keys on the output
file's **presence**, not on whether its content still matches the source. An
`--apply` run over a fully-drifted tree therefore reports success while
changing nothing — which is why the drift survived. A test asserting mirror
currency (this issue's subject) would have caught the symptom; the skip
predicate is the cause and should be fixed alongside it, or the test will fail
on a tree that `--apply` claims is already correct.

(The `help.toml` regeneration was reverted rather than committed, to keep it
out of an unrelated change. The drift is still present on `main`.)

## Expected Behavior

A test regenerates each host's artifacts from the canonical sources into a
temp dir and diffs against the committed tree, failing with the exact paths
that drifted and the `ll-adapt` command that fixes them.

## Motivation

The mirrors exist so Codex/Gemini/Kimi users get the same skills Claude Code
users do. When they drift, those users get *silently wrong* behavior — not a
missing feature or an error, but stale instructions presented as current. That
is the worst failure shape for a generated artifact, and the one a staleness
check is cheapest to prevent.

The drift is also easy to cause: the canonical file is the one a contributor
naturally edits, `ll-adapt --apply` is a separate manual step, and nothing in
the commit path prompts for it. This session's BUG-2956 wiring pass flagged
exactly this (*"these are generated artifacts, not hand-maintained… nothing
currently tests their sync"*), and the finding was carried forward when that
issue was closed as not-reproducible.

This is the same class as `ll-verify-docs` (documented counts vs. actual) and
`ll-verify-cli-allowlist` (entry points vs. allowlist) — generated-or-derived
artifact vs. its source, enforced by the local suite.

## Proposed Solution

Add a regeneration-diff test, per the project's CI policy (the pytest suite
*is* CI; no hosted runner).

Shape:

1. For each host with committed mirrors, run the same emit path
   `ll-adapt --host <h> --apply` uses, targeting a temp dir.
2. Walk the committed tree and the regenerated tree; diff file sets and
   contents.
3. On mismatch, fail with the drifted paths and the exact remediation command.

Two decisions to settle during implementation:

- **Which hosts are in scope.** `.kimi-code/` and `.gemini/` are committed;
  confirm whether Codex artifacts are committed too, or generated on demand.
  Only committed trees can drift.
- **Skip vs. fail when a host emitter is unavailable.** `omp`'s emitters raise
  `AdapterError` unconditionally (a 28-line stub, per
  `test_adapt_golden_corpus.py`'s named exclusions). Follow the established
  convention of skipping gracefully rather than hard-failing contributors, and
  make the skip explicit and named, not silent.

Prefer driving the real emit path over reimplementing it — a test that
reimplements emission can pass while `ll-adapt --apply` produces something
different.

## Program Design

### Types

**No new types.** The test consumes existing emitter/CLI machinery.

### Signatures

- `emit_host_artifacts(host: str, project_root: Path, output_root: Path) -> list[Path]`
  — the seam the test needs: run the same traversal-and-emit `--apply` runs,
  but rooted at an arbitrary `output_root`, returning the paths written.
  **Confirm whether this already exists before adding it** — `main_adapt()`
  (`scripts/little_loops/cli/adapt.py:31`) is the CLI entry and
  `adapters/core.py` holds the traversal, so the parameter may already be
  threaded through under another name. If so, no production change is needed
  and this issue is test-only.
- `test_committed_mirrors_match_regenerated(host: str, tmp_path: Path) -> None`
  — parametrized over the committed hosts; calls the seam, diffs both trees.

The rule: factor the output root out of the existing apply path. Do **not**
reimplement traversal in the test — a test with its own traversal can pass
while `ll-adapt --apply` writes something different, which is the exact
failure this issue exists to catch.

### Call Path

`test_mirrors_are_current` → (existing adapt emit path, target=`tmp_path`) →
walk committed tree + regenerated tree → diff → assert empty

`scripts/little_loops/adapters/core.py` drives traversal from the ENH-2873
capability map (per ENH-2883); `adapters/{kimi,gemini,codex,omp}.py` are the
per-host emitters. The test should enter at the same level `--apply` does.

## Integration Map

### Files to Modify
- `scripts/tests/test_adapt_mirror_staleness.py` — new.
- `scripts/little_loops/cli/adapt.py` — only if the apply path needs an
  output-root seam (`main_adapt()` at `L31`).

### Dependent Files
- `.kimi-code/skills/`, `.kimi-code/commands/`, `.gemini/skills/`,
  `.gemini/commands/` — the committed trees under test.
- `skills/*/SKILL.md`, `commands/*.md`, `agents/*.md` — canonical sources.

### Similar Patterns
- `ll-verify-docs` — documented counts vs. actual file counts; same
  derived-artifact-vs-source family.
- `ll-verify-cli-allowlist` (BUG-2764) — `pyproject.toml` entry points vs.
  two other artifacts, exit 1 on drift.
- `scripts/tests/test_policy_builder_node_gate.py` (FEAT-2390) — the
  established pattern for a gate that skips gracefully when its external
  dependency is absent while still enforcing wherever available. Directly
  applicable to the unavailable-emitter question above.
- `test_adapt_golden_corpus.py` — the *contrast* case; read its docstring for
  how named exclusions are documented rather than silently dropped.

## Implementation Steps

1. Determine which host trees are committed and in scope; confirm whether
   Codex artifacts are committed.
2. Find or create the seam that lets the apply path emit to an arbitrary root.
3. Write the regeneration-diff test; make the failure message name the drifted
   paths and the fixing command.
4. Run it against current `main` — if the committed mirrors are *already*
   stale, fix that drift in the same change so the gate lands green.
5. Handle unavailable emitters with an explicit, named skip.

## Scope Boundaries

**In scope:**
- A test asserting committed host mirrors match current `ll-adapt` output.
- The minimal production seam needed to emit to a temp root.

**Out of scope:**
- Changing emitter behavior or output format.
- Adding new hosts or new adapted artifact kinds.
- Auto-regenerating mirrors in a hook or on commit — this issue only detects
  drift. Auto-fixing is a separate decision with its own tradeoffs.
- `omp`'s stub emitters (no output to compare).

## Impact

- **Priority**: P3 — silent wrongness for non-Claude hosts, but bounded to
  those hosts and only when a contributor forgets a step. P3 rather than P2
  because the blast radius excludes the primary host.
- **Effort**: Small-Medium — the test is straightforward; the unknown is
  whether an output-root seam already exists.
- **Risk**: Low — additive test. The one real risk is discovering the
  committed mirrors are already stale, which enlarges the change (step 4).
  That is a benefit disguised as a risk.
- **Breaking Change**: No.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Session Log
- `/ll:capture-issue` - 2026-08-01T16:20:51 - `15f4582a-2df6-4315-9f84-3f5730f550e5.jsonl`

---

## Status

**Open** | Created: 2026-08-01 | Priority: P3
