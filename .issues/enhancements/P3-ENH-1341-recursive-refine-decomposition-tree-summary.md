---
id: ENH-1341
type: ENH
priority: P3
status: done
discovered_date: 2026-05-02
completed_at: 2026-05-03T18:39:24Z
discovered_by: research-synthesis
decision_needed: false
confidence_score: 98
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
relates_to: ['ENH-1340']
---

# ENH-1341: Render Decomposition Tree in `recursive-refine` `done` Summary

## Summary

`recursive-refine`'s `done` state emits two flat lists (passed, skipped) but no structural view of *how* the work decomposed. With moderately deep runs (root → children → grandchildren), the user has no easy way to see "ENH-1100 was split into ENH-1200/1201, and ENH-1201 further split into ENH-1300/1301." Render an indented tree (or simple `parent → [children]` adjacency block) at the end of the run, sourced from the decomposition record proposed in ENH-1340.

## Motivation

2026 research on long-horizon agents converges on observability — particularly *structured* observability over flat logs — as a precondition for trusting agent autonomy:

- "From Agent Loops to Structured Graphs" argues for explicit structured-graph framing of agent execution to enable post-hoc analysis ([arXiv 2604.11378, 2026](https://arxiv.org/html/2604.11378v1)).
- The 2026 multi-agent failure literature emphasizes that without structural visibility, "loop drift" and "procedural drift" go undetected ([fixbrokenaiapps 2026](https://www.fixbrokenaiapps.com/blog/ai-agents-infinite-loops); [Cogent 2026](https://cogentinfo.com/resources/when-ai-agents-collide-multi-agent-orchestration-failure-playbook-for-2026)).
- This is also the natural input for `/ll:assess-loop` and `/ll:analyze-loop` — they currently operate on event history, not on decomposition shape.

A flat skip list buries the difference between "abandoned" and "successfully decomposed."

## Current Behavior

- `done` (lines 494–527 of `recursive-refine.yaml`) prints:
  ```
  Passed  (N): ID1,ID2,...
  Skipped (M): ID3,ID4,...
  ```
- No parent-child relationships rendered.
- A reader looking at `Skipped: ENH-1100` cannot tell whether it was abandoned or decomposed into the issues that appear in `Passed`.

## Expected Behavior

- `done` emits an additional block:
  ```
  === Decomposition Tree ===
  ENH-1100 [decomposed by size-review]
    ├── ENH-1200 (passed, conf=92, outcome=78)
    └── ENH-1201 [decomposed by sub-loop]
          ├── ENH-1300 (passed, conf=95, outcome=82)
          └── ENH-1301 (skipped: budget)
  ENH-1102 (passed, conf=91, outcome=80)
  ```
- Roots that were not decomposed appear as single lines.
- Decomposed parents appear with their reason in brackets and an indented child list.
- Final scores pulled from `ll-issues show <id> --json`.
- If ENH-1340 (decomposition record) is not yet implemented, fall back to reconstructing the tree from `recursive-refine-original-queue.txt`, `recursive-refine-passed.txt`, `recursive-refine-skipped.txt`, and a one-pass `find .issues -path '*completed/*' -name '*-<parent>-*'` lookup using the `Decomposed from` annotation.

## Proposed Solution

1. Depend on ENH-1340 ideally — read its `recursive-refine-decomposition.tsv` to drive the tree.
2. Add a python helper inline in `done`'s action body that:
   - Loads the original queue (roots).
   - Loads passed/skipped IDs and their reasons.
   - Loads the decomposition record (or reconstructs from `Decomposed from` annotations).
   - Walks each root depth-first, emitting indented lines.
   - Calls `ll-issues show <id> --json` for each leaf to fetch confidence/outcome scores.
3. Place the tree block *between* the existing `Passed` / `Skipped` summary and the closing newline, gated behind a context flag `tree_summary: true` (default true) so it can be disabled for noisy multi-root runs.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**ENH-1340 is not yet implemented** — `recursive-refine-decomposition.tsv` does not exist anywhere in the current loop. The fallback reconstruction path is required for initial implementation.

**Fallback reconstruction algorithm (definitive):**
- `recursive-refine-depth-map.txt` has `<id> <depth>` per line for every queued ID — useful to know depths but contains NO parent-child edge information.
- `recursive-refine-new-children.txt` is **overwritten each iteration** (not cumulative) — cannot be used for tree reconstruction.
- The only persistent parent-child edge source is the `parent_issue: PARENT_ID` frontmatter field in child issue files (written by the `issue-size-review` skill, Phase 3). The body annotation `Decomposed from [PARENT-ID]: [Title]` is also present but frontmatter is cleaner to grep.
- Reconstruction: for each ID in the union of passed + skipped, run `grep -r "^parent_issue: $ID$" .issues/` to find its children. One pass over all issue files suffices.

**`${context.tree_summary}` in action body:** Use `[ "${context.tree_summary}" != "false" ]` as the shell gate. `$${VAR:-none}` is the YAML escape for shell `${VAR:-none}` — the FSM interpolation engine converts `$${}` → `${}` before shell execution (see `interpolation.py:186`).

**`ll-issues show --json` field names:** `confidence` (from `confidence_score` frontmatter) and `outcome` (from `outcome_confidence`) are both `str|None`. Access pattern: `int(d.get('confidence') or 0)`. See `recursive-refine.yaml:check_passed` and `recheck_scores` for the existing call pattern.

**Inline Python in shell action:** Use the `| python3 -c "..."` heredoc pattern established in `refine-to-ready-issue.yaml:121` and `recursive-refine.yaml:check_passed`. The tree-walk Python can be a self-contained multi-line string embedded in the shell action body.

## Acceptance Criteria

- [ ] `done` summary now includes a `=== Decomposition Tree ===` block by default.
- [ ] Roots without children render as a single line with their final scores.
- [ ] Decomposed parents render with their reason and indented children.
- [ ] Leaf entries show `(passed, conf=X, outcome=Y)` or `(skipped: <reason>)`.
- [ ] Falls back gracefully when no decomposition occurred (omits the block, or shows roots-only).
- [ ] `context.tree_summary: false` disables the block.
- [ ] Test: synthetic run with 1 root that decomposes into 2 children (one of which decomposes further) produces a 3-level tree.

## Scope Boundaries

- **In scope**: textual tree rendering at end of run, scoring annotations, on/off flag.
- **Out of scope**: graphical (mermaid) rendering — mermaid output belongs in a follow-up if/when `/ll:assess-loop` consumes the tree.
- **Out of scope**: streaming the tree during the run (only at `done`).

## Depends On

- ENH-1340 — decomposition record file is the cleanest input. Without it the tree can be reconstructed from `Decomposed from` annotations, but with higher cost.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/recursive-refine.yaml` — extend `done` action body with the tree renderer and add `tree_summary` flag to `context:`.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — actual FSM loop runner that executes the YAML action bodies.
- `scripts/little_loops/cli/loop/_helpers.py` — `resolve_loop_path()` and `run_foreground()` load and launch the loop; no code change required but receives the updated YAML.
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor` executes the `done` state action body and manages `tree_summary` context; no code change required.
- `scripts/little_loops/cli/issues/show.py:_parse_card_fields()` — implements `ll-issues show <id> --json`; `confidence` maps from `confidence_score` frontmatter, `outcome` from `outcome_confidence`; both returned as `str|None`.
- `scripts/little_loops/fsm/interpolation.py:interpolate()` — processes `${context.tree_summary}` references; `$${VAR:-default}` in YAML → `${VAR:-default}` in shell.
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — calls `recursive-refine` with `context_passthrough: true`; child's `tree_summary: true` default wins over any parent value; no code change required.
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — same `context_passthrough: true` pattern; same no-change note.
- `skills/issue-size-review/SKILL.md` — writes `parent_issue:` frontmatter to child issues; this is the data source the tree renderer greps; no change required.
- `/ll:assess-loop` and `/ll:analyze-loop` skills — likely future consumers of the rendered tree.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/_helpers.py` — `resolve_loop_path()` loads `recursive-refine.yaml` [Agent 1 finding]
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor.run()` executes the `done` state and merges `tree_summary` context [Agent 1 finding]
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — `context_passthrough: true`; child context wins [Agent 2 finding]
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — same `context_passthrough: true` pattern [Agent 2 finding]
- `skills/issue-size-review/SKILL.md` — source of `parent_issue:` frontmatter used by tree reconstruction [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/loops/autodev.yaml:459` — closest parallel: `done` state with identical `printf`-based structured summary using `$${VAR:-none}` escaping; the direct template to follow.
- `scripts/doc_scraper.py:824 _print_sitemap()` — recursive depth-first tree renderer using `├──`/`└──`; the tree-walk logic to adapt inline.
- `scripts/little_loops/cli/sprint/_helpers.py:154` — single-level `├──`/`└──` rendering using Unicode code points (`├──`, `└──`, `│`) for reference on the exact characters.

### Tests
- `scripts/tests/test_loops_recursive_refine.py:597 TestDoneSummary` — existing test class for the `done` action body shell script; extend with a new test method using the same `_bash(script, cwd=tmp_path)` helper and `tmp_path / ".loops/tmp"` fixture layout. The new test must write `recursive-refine-original-queue.txt`, `passed.txt`, `skipped.txt`, and stub issue files with `parent_issue:` frontmatter to simulate a 3-level decomposition.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_loops_recursive_refine.py:600 TestDoneSummary._DONE_SCRIPT` — verbatim copy of the `done` action body; **must be updated** when the YAML done state is extended, otherwise the class constant diverges silently from the real YAML [Agent 2 + 3 finding]
- `scripts/tests/test_loops_recursive_refine.py:633` — 6 existing `TestDoneSummary` test methods (depth-cap, cycle, budget lines); may need `recursive-refine-original-queue.txt` written in fixture setup once tree renderer is added to `_DONE_SCRIPT`; tree renderer must gracefully skip when the file is absent or all 6 existing tests require the new fixture file [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles.test_all_parse_as_yaml` — parses every loop YAML including `recursive-refine.yaml`; will break if inline Python block has YAML syntax errors [Agent 3 finding — may break]
- `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles.test_all_validate_as_valid_fsm` — runs FSM schema validation on every loop YAML; will break on schema errors in the extended done state [Agent 3 finding — may break]
- `scripts/tests/test_fsm_fragments.py::TestBuiltinLoopMigration.test_builtin_loops_load_after_migration` — explicitly loads `recursive-refine.yaml` via `load_and_validate`; will break on YAML/FSM errors [Agent 3 finding — may break]
- `scripts/tests/test_enh1341_doc_wiring.py` — **new test file** following the pattern in `test_enh1345_doc_wiring.py`; assert `tree_summary` is present in the LOOPS_GUIDE.md context variables table and `=== Decomposition Tree ===` is present in the summary output example [Agent 3 finding — new]

### Documentation
- `docs/reference/loops/recursive-refine.md` — **does not exist**; skip this target.
- `docs/guides/LOOPS_GUIDE.md` — **primary doc target** (file confirmed present). Two changes required: (1) add `tree_summary` row to the "Required context variables" table under `recursive-refine`; (2) update the "Summary output" rendered example to show the `=== Decomposition Tree ===` block. [Agent 2 finding]

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — add `tree_summary` to context vars table; update summary output example [Agent 2 finding]

### Configuration
- N/A — `tree_summary` lives in the loop's `context:`; no `.ll/ll-config.json` change required.

## Implementation Steps

1. Confirm dependency on ENH-1340's decomposition record (or implement the fallback reconstruction path if not yet available).
2. Add `tree_summary: true` to `recursive-refine.yaml` `context:`.
3. Extend the `done` state's action body with a Python helper that loads roots / passed / skipped / decomposition record and walks each root depth-first.
4. Fetch leaf scores via `ll-issues show <id> --json`.
5. Emit the tree block between the existing `Passed` / `Skipped` lines and the closing newline.
6. Honor `tree_summary: false` to disable the block.
7. Add the synthetic 3-level test fixture.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Confirm fallback path is required**: ENH-1340 is Open/unimplemented. Use `parent_issue:` frontmatter grep across `.issues/` for tree reconstruction. Do NOT rely on `recursive-refine-new-children.txt` (overwritten each iteration).
2. **Add `tree_summary: true` to `context:` block** (`recursive-refine.yaml:24`): insert after the existing `max_depth: 3` line.
3. **Extend `done` state at `recursive-refine.yaml:494`**: model the shell structure on `autodev.yaml:459`. Add a gate: `[ "${context.tree_summary}" != "false" ]`. Embed an inline Python script (following the `| python3 -c` pattern from `check_passed`) that:
   a. Reads `recursive-refine-original-queue.txt` for roots.
   b. Collects all IDs from `passed.txt` + `skipped.txt` + their sub-files.
   c. Builds `parent→children` map by running `grep -rl "^parent_issue: $id" .issues/` for each ID.
   d. Walks each root depth-first, emitting `├──`/`└──` lines (adapt `doc_scraper.py:824 _print_sitemap()` logic; use Unicode code points from `sprint/_helpers.py:154`).
4. **Fetch leaf scores**: `subprocess.run(['ll-issues', 'show', leaf_id, '--json'], capture_output=True, text=True)` then `int(json.loads(r.stdout).get('confidence') or 0)`. Only call for leaf nodes (no children) to minimize subprocess count.
5. **Emit tree block** between the `Passed`/`Skipped` printf lines and the closing `printf '\n'`.
6. **Honor `tree_summary: false`**: wrap entire tree block in `if [ "${context.tree_summary}" != "false" ]; then ... fi`.
7. **Test in `TestDoneSummary`** (`test_loops_recursive_refine.py:597`): add a new method that writes `original-queue.txt`, `passed.txt`, `skipped.txt` and creates stub `.issues/` files with `parent_issue:` frontmatter under `tmp_path`. Use `_bash(self._TREE_SCRIPT, tmp_path)` where `_TREE_SCRIPT` is a class-level raw string of the extended `done` action body.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `TestDoneSummary._DONE_SCRIPT` in `scripts/tests/test_loops_recursive_refine.py:600` — keep the class constant in sync with the extended `done` action body; failing to do so causes the class to silently test a stale script.
9. Add `recursive-refine-original-queue.txt` to the fixture setup of all 6 existing `TestDoneSummary` test methods — required once tree renderer reads that file; or ensure the renderer silently no-ops when the file is absent and document this graceful-skip in the gate logic.
10. Update `docs/guides/LOOPS_GUIDE.md` — add `tree_summary` row to the "Required context variables" table and extend the "Summary output" rendered example to show the decomposition tree block.
11. Write `scripts/tests/test_enh1341_doc_wiring.py` — new test file following the `test_enh1345_doc_wiring.py` pattern; assert `tree_summary` appears in LOOPS_GUIDE context table and `=== Decomposition Tree ===` appears in the output sample.

## Impact

- **Priority**: P3 — Pure observability win; raises the floor for trusting recursive runs.
- **Effort**: Small — One inline Python helper in `done`; reuses existing tracking files.
- **Risk**: Low — Output-only change; flag-gated for noisy runs.
- **Breaking Change**: No — Additive summary block.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `recursive-refine`, `fsm-loops`, `observability`

## Status

**Open** | Created: 2026-05-02 | Priority: P3

## References

- `scripts/little_loops/loops/recursive-refine.yaml:494` (`done` state, lines 494–527).
- 2026 research: [Structured Graphs for Agent Execution](https://arxiv.org/html/2604.11378v1), [AI Agent Loops research](https://www.fixbrokenaiapps.com/blog/ai-agents-infinite-loops).

## Resolution

Implemented fallback tree reconstruction using `parent_issue:` frontmatter grep (ENH-1340 not yet available). Added `tree_summary: true` context variable to `recursive-refine.yaml`, extended the `done` state with an inline Python depth-first tree renderer, updated `TestDoneSummary._DONE_SCRIPT` and added 3 new tree tests, updated `LOOPS_GUIDE.md` context table and summary example, and added `test_enh1341_doc_wiring.py`.

## Session Log
- `/ll:ready-issue` - 2026-05-03T18:28:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c073749a-0a8f-468e-b646-4a3878f4c8b1.jsonl`
- `/ll:confidence-check` - 2026-05-03T19:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ccd162c-559d-45b4-8072-deaaeb589fb9.jsonl`
- `/ll:wire-issue` - 2026-05-03T18:23:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4d906b4c-4829-4094-a674-e4103fda9dc4.jsonl`
- `/ll:refine-issue` - 2026-05-03T18:15:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8c5899e6-a66d-4aa4-877c-73b8f4a247c6.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:20:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:format-issue` - 2026-05-03T04:41:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a41e2fe5-b6da-449b-8d60-6b8ddd06d97c.jsonl`
