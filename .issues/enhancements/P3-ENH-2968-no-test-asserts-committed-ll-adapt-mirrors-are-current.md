---
id: ENH-2968
title: No test asserts committed ll-adapt host mirrors are current
type: ENH
priority: P3
status: cancelled
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
closed_reason: superseded
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

**Update (2026-08-03):** the `.gemini/commands/help.toml` symptom cited above
was independently fixed by `e8ed3ca3` ("regenerate gemini/kimi-code mirrors
for help and normalize-issues", 2026-08-01), which regenerated both
`help.toml` and `normalize-issues.toml` for `.gemini` and `.kimi-code`. That
was a manual, one-off `ll-adapt --apply` run, not a test — the underlying gap
this issue exists to close (nothing *catches* the next drift automatically)
is unaffected. Treat the specific `help.toml` example above as historical;
the skip-predicate defect and the missing regeneration-diff test are still
live.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

Both open decisions from the list above are now resolved:

- **Hosts in scope**: three trees are committed, not two.
  `git ls-files .kimi-code .gemini .codex` confirms `.codex/` is also
  committed — but only `.codex/agents/*.toml` (9 files). No
  `.codex/skills/` or `.codex/commands/` exist. `.kimi-code/` and `.gemini/`
  each carry skills, commands, and agents. `omp` has no committed tree at
  all (`.omp/` does not exist), consistent with the existing
  out-of-scope note. So the test is parametrized over
  `(host, artifact_kind)` pairs, not just `host` — Codex only contributes
  an `agents` case.
- **Skip-predicate defect scope**: narrower than "the skip predicate," a
  Codex-specific presence-only check.
  `CodexEmitter.emit_command` (`adapters/codex.py:307`) skips on
  `out_skill_md.exists() and out_openai_yaml.exists()` — no content
  comparison. `CodexEmitter.emit_skill`'s sidecar check (`yaml_exists`,
  `codex.py:260`) is the same. `GeminiEmitter.emit_skill`/`emit_command`
  (`adapters/gemini.py:94,134`) and all three `KimiEmitter` methods
  (`adapters/kimi.py:71,111,144`) already skip on
  `out_path.exists() and out_path.read_text() == new_content` — full
  content comparison. The BUG-2956-adjacent "skip predicate is the cause"
  finding applies to Codex only.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

The seam does **not** already exist, and it needs to be added inconsistently
across three different surfaces — this is not a one-line parameter thread:

- **`process_agents()`** (`adapters/core.py:409`) already accepts a real
  `output_dir` parameter, threaded into `agent_meta["output_dir"]` and
  honored by every emitter. This one is a genuine, reusable seam today.
- **`process_commands()`** (`adapters/core.py:336`) accepts `output_dir` too,
  but only `CodexEmitter.emit_command` (`codex.py:287,303`) reads it.
  `GeminiEmitter.emit_command` (`gemini.py:128`) and
  `KimiEmitter.emit_command` (`kimi.py:106`) ignore the parameter entirely
  and self-derive the plugin root from `cmd_path.parent.parent`.
- **`process_skills()`** (`adapters/core.py:279`) has no `output_dir`
  parameter at all. `skill_meta` carries only `skill_path`/`content`/`fm`/
  `apply`/`quiet`. `GeminiEmitter.emit_skill` (`gemini.py:88-90`) and
  `KimiEmitter.emit_skill` (`kimi.py:66-67`) both derive
  `plugin_root = skill_path.parent.parent.parent` and hardcode
  `.gemini/skills/...` / `.kimi-code/skills/...` off of it;
  `CodexEmitter.emit_skill` co-locates its `openai.yaml` sidecar next to
  `skill_path` (`codex.py:242`) rather than under any output root.
- `main_adapt()` (`cli/adapt.py:31`) never exposes an override for
  `plugin_root`/`_find_plugin_root()` either, so even the one working seam
  (`process_agents`) isn't reachable from the CLI today — only from calling
  `core.py` functions directly in Python.
- `test_adapt_golden_corpus.py`'s `tmp_path` isolation is not this seam: it
  places the *synthetic input* fixture under `tmp_path` so Gemini/Kimi's
  self-derived `plugin_root` happens to land there too
  (`_make_skill_file`, line 38), and it calls emitter classes directly —
  never `core.py`'s `process_skills`/`process_commands`/`process_agents` or
  `main_adapt()`. It does not prove a reusable output-root parameter exists.

Net: the Program Design signature `emit_host_artifacts(host, project_root,
output_root)` needs new production code, not just a rename — a skills-level
`output_dir` param mirroring `process_agents()`'s, plus fixing
`GeminiEmitter`/`KimiEmitter.emit_command` to honor the `output_dir` they
already receive but currently discard.

### Call Path

`test_mirrors_are_current` → (existing adapt emit path, target=`tmp_path`) →
walk committed tree + regenerated tree → diff → assert empty

`scripts/little_loops/adapters/core.py` drives traversal from the ENH-2873
capability map (per ENH-2883); `adapters/{kimi,gemini,codex,omp}.py` are the
per-host emitters. The test should enter at the same level `--apply` does.

## Integration Map

### Files to Modify
- `scripts/tests/test_adapt_mirror_staleness.py` — new.
- `scripts/little_loops/adapters/core.py` — `process_skills()` (`L279`) needs
  an `output_dir` parameter added (currently has none); `process_commands()`
  (`L336`) already threads `output_dir` through.
- `scripts/little_loops/adapters/gemini.py` — `emit_skill` (`L88-90`) and
  `emit_command` (`L128`) self-derive `plugin_root` instead of honoring a
  passed output root; need to accept and use one.
- `scripts/little_loops/adapters/kimi.py` — same defect, `emit_skill`
  (`L66-67`) and `emit_command` (`L106`).
- `scripts/little_loops/adapters/codex.py` — `emit_skill`'s sidecar
  (`L242`) co-locates rather than using an output root; `emit_command`'s
  skip check (`L307`) is presence-only and needs a content comparison to
  match Gemini/Kimi's existing pattern.
- `scripts/little_loops/cli/adapt.py` — `main_adapt()` (`L31`) never exposes
  an output-root override at all; needed if the test drives the CLI path
  rather than calling `core.py` functions directly.

### Dependent Files
- `.kimi-code/skills/`, `.kimi-code/commands/`, `.kimi-code/agents/`,
  `.gemini/skills/`, `.gemini/commands/`, `.gemini/agents/`,
  `.codex/agents/` — the committed trees under test. `.codex/` has **no**
  committed `skills/`/`commands/` (agents only) — confirmed via
  `git ls-files .codex`.
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Both `ll-verify-cli-allowlist` (`cli/verify_cli_allowlist.py:84-106`) and
  `ll-verify-docs` (`doc_counts.py:133-195`) share one convention worth
  matching: compute the canonical/ground-truth value independently of the
  artifact under test, compute the artifact's declared value the same way,
  diff to an *itemized* list (not a single bool), map any non-empty diff to
  exit 1, and print each discrepancy with enough detail (file:line, or
  tool name) to fix it directly — never a generic "drift detected."
- The skip-gracefully convention (`test_policy_builder_node_gate.py:45-71`)
  is specifically `shutil.which(...)` presence check + a version probe,
  each branch calling `pytest.skip("<reason>")` with an explicit string —
  not `pytest.mark.skipif` or `pytest.importorskip`. When the dependency is
  present, enforcement is unconditional (no soft-fail path).
- `test_adapt_golden_corpus.py`'s named-exclusion convention is two things
  together, not one: a module-docstring `**Named exclusions**` section
  naming each excluded case and why, *plus* a dedicated test function
  (`test_omp_and_gemini_agent_excluded_from_byte_identity_claim`, lines
  196-215) that asserts the exclusion still holds (e.g.
  `pytest.raises(AdapterError)` for `omp`). A skip/exclusion list alone,
  without the paired assertion, would not match this codebase's convention.
- No `filecmp.dircmp` or generic tree-diff helper exists anywhere in the
  repo (zero matches for `dircmp|filecmp`). Every drift gate found
  (`verify_cli_allowlist.py`, `doc_counts.py`) implements its own bespoke
  comparison inline. The new test should do the same rather than expect a
  reusable helper to import.

## Implementation Steps

1. Test scope covers `(kimi-code, {skills,commands,agents})`,
   `(gemini, {skills,commands,agents})`, and `(codex, agents)` only — `.codex/`
   has no committed `skills/`/`commands/` tree to diff against (confirmed via
   `git ls-files .codex`).
2. `process_skills()` (`adapters/core.py:279`) gains an `output_dir`
   parameter; `GeminiEmitter`/`KimiEmitter`'s `emit_skill`/`emit_command`
   are changed to honor a passed output root instead of self-deriving
   `plugin_root` from `skill_path`/`cmd_path` — this is new production code,
   not a rename, per the Program Design findings above.
3. Write the regeneration-diff test calling the fixed `core.py` traversal
   (not the emitter classes directly, unlike `test_adapt_golden_corpus.py`);
   make the failure message name the drifted paths and the fixing command.
4. Run it against current `main` — the committed mirrors are *already*
   stale (`.gemini/commands/help.toml` confirmed drifted); fix that drift in
   the same change so the gate lands green.
5. Fix `CodexEmitter.emit_command`'s presence-only skip check (`codex.py:307`)
   and `emit_skill`'s sidecar `yaml_exists` check (`codex.py:260`) to compare
   content, matching the pattern `GeminiEmitter`/`KimiEmitter` already use
   (`out_path.exists() and out_path.read_text() == new_content`).
6. Handle `omp` with an explicit, named skip/exclusion, following
   `test_adapt_golden_corpus.py`'s paired docstring-note +
   assertion-that-the-exclusion-holds convention (not a bare skip list).

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
- `/ll:audit-issue-conflicts` - 2026-08-06T05:57:00 - `b806aadf-1033-4656-b34d-bd948c43350c.jsonl`
- `/ll:refine-issue` - 2026-08-01T20:09:21 - `844dd8a3-cedc-47e7-8eb3-e4133f298428.jsonl`
- `/ll:capture-issue` - 2026-08-01T16:20:51 - `15f4582a-2df6-4315-9f84-3f5730f550e5.jsonl`

---

## Status

**Open** | Created: 2026-08-01 | Priority: P3

---

## Resolution

- **Completed**: 2026-08-06
- **Reason**: Superseded by ENH-3062 via conflict resolution audit
- **Proposed change**: Consolidate the mirror-staleness gate into ENH-3062's simpler dry-run parametrized-test approach (no new production seam required), absorbing this issue's Codex presence-only skip-check defect finding as scope on ENH-3062.
