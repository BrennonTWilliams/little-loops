---
id: ENH-2945
title: 'll-issues size: deterministic size scoring for issue-size-review'
type: ENH
priority: P2
status: done
discovered_by: skill-audit
discovered_date: 2026-07-31
completed_at: '2026-08-01T09:35:49Z'
parent: EPIC-2938
epic: EPIC-2938
relates_to:
- FEAT-2947
labels:
- cli
- issues
- sizing
confidence_score: 96
outcome_confidence: 87
score_complexity: 22
score_test_coverage: 25
score_ambiguity: 20
score_change_surface: 20
---

# ENH-2945: `ll-issues size <id> --json` — deterministic size scoring

## Summary

`skills/issue-size-review/SKILL.md` (466 lines) Phases 1–3 are a fully countable scoring rubric the LLM computes by hand; Phase 6 is ID/file scaffolding. Move both into `ll-issues size`; the skill keeps Phases 4–5 (split-decision judgment).

## Current Behavior

- Phase 1 (L82–110): glob type dirs / resolve sprint IDs via `ll-issues path`.
- Phase 2 (L114–126): the scoring table — +2 file-path count patterns, +2 sections >300 words, +3 multiple `##` subsections, +2 cross-issue references, +2 >800 words total; max 11.
- Phase 3 (L128–174): score→label mapping (0–2 Small … 8+ Very Large), `Edit` of `size:` frontmatter, `git add`.
- Phase 6 (L272–330): `next-id`, filename templating, session-log JSONL hunting (L282–289), parent `status: done`, staging.

## Expected Behavior

`ll-issues size <id|--all|--sprint NAME> [--write] --json` — computes the Phase 2 signals and total, maps to the label, emits `{id, score, label, signals:{...}}`; `--write` stamps `size:` frontmatter. The skill becomes: run CLI → for Large/Very Large, do Phase 4 (sub-task identification, independently-shippable test, never-split-by-artifact-type and TDD-wiring rules, sequential-vs-parallel judgment) and Phase 5 → child creation via FEAT-2947's `create`/`finalize-decomposition` once available (session-log via `ll-issues append-log`, per ENH-2939).

## Integration Map

### Files to Modify
- `skills/issue-size-review/SKILL.md` — Phase 1 (L82–110, glob/sprint resolution), Phase 2 (L112–126, the scoring table), and Phase 3 (L128–174, label mapping + frontmatter write-back) replaced with a call to `ll-issues size`; Phase 6's mechanical parts (L272–339, `next-id`/filename templating, session-log JSONL-hunting fallback, parent `status: done`) slimmed per the Scope Boundaries note below.
- `scripts/little_loops/cli/issues/size.py` (new) — `SizeScore` dataclass, `SIZE_SIGNAL_WEIGHTS` module constant, `compute_size()`, `label_for()`, `write_size()`, `add_size_parser()`, `cmd_size()`.
- `scripts/little_loops/cli/issues/__init__.py` — four-touchpoint wiring identical to `normalize.py`'s ENH-2944 pattern: local import inside `main_issues()`, `add_size_parser(subs)` call, `if args.command == "size": return cmd_size(config, args)` dispatch branch, and an epilog/`Examples:` entry.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/autodev.yaml` — guard2 path consumes `issue-size-review --auto` output; confirm the slimmed skill still emits whatever guard2's verdict regex expects (BUG-2752 already tracks that regex's fragility — don't widen its blast radius here).
- `docs/reference/CLI.md` — needs a new `ll-issues size` entry alongside the other `ll-issues` subcommands.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/recursive-refine.yaml:626` — `action: "/ll:issue-size-review ${captured.input.output} --auto"`; the skill's `--auto` invocation contract and observable output must stay stable across the Phase 1-3 replacement.
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:388` — same `/ll:issue-size-review ... --auto` invocation on the not-ready-confidence exit path.
- `scripts/little_loops/loops/rn-decompose.yaml:76` — same invocation; `test_rn_decompose.py` asserts on this action string directly (see Tests below).
- `scripts/little_loops/loops/rn-implement.yaml:1218,1288` — comments reference `SIZE_REVIEW_FAILED` diagnostic emitted when `/ll:issue-size-review` errors or is inconclusive; the slimmed skill must still be able to signal that failure mode.

### Similar Patterns
- `scripts/little_loops/cli/issues/normalize.py` — most recent "move skill mechanics into a deterministic CLI" precedent (ENH-2944): module-level weight/keyword constants (`_SIGNAL_KEYWORDS`, `TYPE_MISMATCH_THRESHOLD` at L27–70), a `@dataclass` finding with `.to_dict()` for `--json`, a pure `scan_*(config) -> list[Finding]` compute function decoupled from IO, a separate `apply_*(findings)` writer, and self-contained `add_normalize_parser(subs)`/`cmd_normalize(config, args)` entry points.
- `scripts/little_loops/cli/issues/set_scores.py` (57 lines) — closest sibling for the write flow to model `write_size()` on: `_resolve_issue_id(config, issue_id)` → `content = path.read_text()` → `update_frontmatter(content, {"size": score.label})` → `path.write_text(new_content)`. Its `confidence_score`/`score_ambiguity`/etc. fields are a wholly separate rubric (confidence-check's outcome-confidence dimensions) — no overlap or reuse beyond the write idiom.
- `scripts/little_loops/cli/deps.py:66–77` — `issue_id nargs="?"` + `--all` mutually-exclusive argparse shape for the `id|--all` targeting mode.
- `scripts/little_loops/cli/deps.py:320–352` — the only in-repo Python-level `--sprint NAME` resolution (vs. shelling out to `ll-issues path` per ID as the skill's Phase 1 currently does): `Sprint.load(sprints_dir, name)` from `little_loops.sprint`, with `sprints_dir` resolved from `config.sprints.sprints_dir`; returns `None` on missing sprint, `.issues: list[str]` gives the bare-ID list to filter `find_issues(config, ...)` results against.
- `scripts/little_loops/cli/issues/deferred_triage.py:15–34` (`_REASON_RANK: dict[str, int]` with inline per-key comments) — closest existing convention for `SIZE_SIGNAL_WEIGHTS: dict[str, int]`.
- `scripts/little_loops/issue_parser.py` — `_section_body(content, heading)` (L205) already extracts a `## Heading` section's raw text (used by `normalize.py`'s `_classification_text()`), which is what the ">300 words in Proposed Solution/Implementation" signal needs; `IssueInfo.size: str | None` (L1134) is the already-present-but-unused frontmatter field this issue starts writing to. `find_issues(config, ..., only_ids=...)` (L1718) accepts an ID set, matching `--sprint`'s resolved-ID-list shape.
- `scripts/little_loops/frontmatter.py:439` — `update_frontmatter(content, updates)` is the write target.

### Tests
- `scripts/tests/test_ll_issues_normalize.py` (235 lines) — direct template: `_write_issue()`/`_run()` fixtures, a `TestScanNormalize`-style class exercising `compute_size()` directly, a `TestWriteSize`-style class asserting on-disk mutation + idempotency, and a `TestCheckModeExitCode`-style class driving the full CLI via `main_issues()` + `--json` output assertions.
- New: `scripts/tests/test_ll_issues_size.py` — fixture issues at each signal (file-path patterns, >300-word section, multiple `##` subsections, cross-issue refs, >800 words total) and each label boundary (score 2/3, 4/5, 7/8); `--write` idempotency.
- `scripts/tests/test_issue_size_review_skill.py` — currently asserts SKILL.md prose (phase headings, guard phrases like `score_ambiguity ≥ 18`); will need updating once Phase 1–3 text is replaced with a CLI-call instruction.
- Note: `scripts/tests/test_skill_size_checker.py` is unrelated — it tests SKILL.md line-count linting (`doc_counts.check_skill_sizes()`, the ENH-494 500-line gate), not issue-size scoring. Don't confuse it with the new test file.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_session_log_prose_sweep.py` (ENH-2939) — parametrized over `skills/issue-size-review/SKILL.md` among others; asserts the file does NOT contain `~/.claude/projects` and DOES contain `ll-issues append-log`. This is the exact contract that Phase 6's "no JSONL session-log hunting" acceptance criterion must satisfy — run this test after slimming, don't just eyeball the prose.
- `scripts/tests/test_wiring_skills_and_commands.py` — `DOC_STRINGS_PRESENT`/`DOC_STRINGS_ABSENT` tuples pin exact substrings in `skills/issue-size-review/SKILL.md`: `parent: [PARENT-ID]` must remain present (currently at SKILL.md L216 and L281, inside the Phase 6 child-creation draft template — i.e. inside the region this issue's Scope Boundaries says may get slimmed), and `parent_issue:` must remain absent. If Phase 6's child-creation template text is edited or deleted, update these tuples in the same change or the test fails on stale anchors.
- `scripts/tests/test_builtin_loops.py:5172,6581` — asserts `/ll:issue-size-review` (and, separately, the `--auto` flag) literally appear in `autodev.yaml`'s `run_size_review`/`breakdown_issue` state actions. Confirms the CLI-backed skill must still be invoked via the same `/ll:issue-size-review <id> --auto` slash-command surface, not a direct `ll-issues size` call, from loop YAML.
- `scripts/tests/test_rn_decompose.py:66-70` — same invocation-contract assertion (`"/ll:issue-size-review" in rsr["action"]`) for `rn-decompose.yaml`'s `run_size_review` state.
- `scripts/tests/test_autodev_loop.py` (BUG-2752) — regression test for `check_guard2_verdict`'s verdict regex against real `issue-size-review --auto` output; the Integration Map above already flags the regex-fragility risk qualitatively, but this is the concrete test file to run to catch a break.

## Proposed Solution

Word/section/reference counting over `issue_parser.parse_file` output; label table as data. `--write` via `frontmatter.update_frontmatter`. Keep the signal weights in one place (module constant) so `issue-size-review --auto` (used by autodev's guard2 path) and the CLI can't diverge.

**Ordering (soft dep on FEAT-2947)**: Phase 6's child-creation mechanics can only be deleted once `ll-issues create` exists. Land FEAT-2947 first within Wave 2; if this issue ships earlier, scope it to Phases 1–3 only and leave Phase 6's slimming to a follow-up rather than half-converting it.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- No Python module currently computes issue size — the scoring today is 100% hand-executed by the LLM reading `skills/issue-size-review/SKILL.md`'s prose table; `scripts/tests/test_issue_size_review_skill.py` confirms this by only asserting the markdown text, never exercising Python logic.
- Verbatim signal weights to port from `skills/issue-size-review/SKILL.md` L116–124 (`SIZE_SIGNAL_WEIGHTS`): `file_count: +2` (file-path patterns like `src/`, `.py`, `.ts`, `.md`), `section_complexity: +2` (Proposed Solution/Implementation section >300 words), `multiple_concerns: +3` (multiple `##` subsections, or phrases like "additionally"/"also need to"), `dependency_mentions: +2` (references to other `BUG-`/`FEAT-`/`ENH-`/`EPIC-` IDs or "depends on"/"blocked by"), `word_count: +2` (>800 words total). Max 11. Label thresholds (L428–435): `0–2 Small`, `3–4 Medium`, `5–7 Large`, `8+ Very Large`.
- `scripts/little_loops/cli/issues/set_scores.py` writes a differently-named rubric (`confidence_score`, `score_ambiguity`, etc.) — verified no key collision with `size:` frontmatter, so `write_size()` can reuse its `update_frontmatter` idiom without namespace conflict.

## Implementation Steps

1. Implement scoring + label mapping + `--write`.
2. Slim `skills/issue-size-review/SKILL.md` Phases 1–3 and the mechanical parts of Phase 6.
3. Tests: fixture issues hitting each signal and each label boundary; `--write` idempotency.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Step 1 concretely: create `scripts/little_loops/cli/issues/size.py` following `normalize.py`'s shape (module constants → dataclass with `to_dict()` → pure `compute_size()` → `write_size()` → `add_size_parser()`/`cmd_size()`), then wire it into `scripts/little_loops/cli/issues/__init__.py` at the same four touchpoints `normalize.py` uses (local import, `add_size_parser(subs)`, dispatch branch, epilog/`Examples:` entry).
- `--sprint NAME` should resolve via `little_loops.sprint.Sprint.load(sprints_dir, name)` (Python-level, per `scripts/little_loops/cli/deps.py:320–352`) rather than shelling out to `ll-issues path` per ID as the skill's Phase 1 currently does — cheaper and avoids N subprocess calls.
- Step 3 concretely: model `scripts/tests/test_ll_issues_size.py` on `scripts/tests/test_ll_issues_normalize.py`'s `_write_issue()`/`_run()` fixture helpers and its `TestScanNormalize`/`TestApplyNormalize`/`TestCheckModeExitCode` class split (pure-function tests, write/mutation tests, full-CLI exit-code tests).

## Program Design

### Types

- `SizeScore: dataclass`
  - `id: str`
  - `score: int`
  - `label: str`  (Small | Medium | Large | Very Large)
  - `signals: dict[str, int]`
- `SIZE_SIGNAL_WEIGHTS: dict[str, int]` — module constant, single source for skill + CLI

### Signatures

- `compute_size(issue: IssueInfo, body: str) -> SizeScore` — file-path counts, >300-word sections, `##` subsection count, cross-issue refs, >800-word total
- `label_for(score: int) -> str` — 0–2 Small / 3–4 Medium / 5–7 Large / 8+ Very Large
- `write_size(issue_path: Path, score: SizeScore) -> None` — `frontmatter.update_frontmatter`

### Call Path

- `compute_size()` -> `find_issues()` (existing, `issue_parser.py`)
- `write_size()` -> `update_frontmatter()` (existing, `frontmatter.py`)

## Scope Boundaries

- In scope: scoring/label/`--write` subcommand; slimming Phases 1–3 and mechanical Phase 6 steps of issue-size-review.
- Out of scope: Phase 4–5 split judgment (stays LLM), child-issue creation (FEAT-2947), autodev routing changes that consume the score.

## Impact

- **Priority**: P2 - Feeds autodev's guard2/size-review path with a deterministic score instead of hand-counted signals
- **Effort**: Small - Countable signals over parsed issues
- **Risk**: Low - Read-only by default; `--write` stamps one frontmatter key

## Status

**Open** | Created: 2026-07-31 | Priority: P2

## Acceptance Criteria

- [x] `ll-issues size --json` reproduces the skill's scoring table exactly (fixtures at boundaries 2/3, 7/8)
- [x] Skill retains only Phase 4–5 judgment + child-creation orchestration _(Phases 1-3 slimmed; Phase 6 explicitly deferred below — FEAT-2947 hasn't landed yet)_
- [ ] No JSONL session-log hunting remains in the skill _(deferred with Phase 6, below)_
- [x] Phase 6's ID/filename templating is either deleted in favor of `ll-issues create` (FEAT-2947 landed) or explicitly deferred — never left half-converted
- [x] pytest coverage in `scripts/tests/`

## Resolution

- **Status**: Done
- **Completed**: 2026-08-01
- Implemented `ll-issues size <id|--all|--sprint NAME> [--write] [--json]`
  (`scripts/little_loops/cli/issues/size.py`): `SIZE_SIGNAL_WEIGHTS`, `compute_size()`,
  `label_for()`, `write_size()`, wired into `cli/issues/__init__.py` at the standard
  four touchpoints.
- Slimmed `skills/issue-size-review/SKILL.md` Phases 1–3 into a single CLI-call section;
  Phase 4 (decomposition proposal) through Phase 6 (execution) are unchanged.
- **Explicit deferral (per this issue's own Ordering/Scope Boundaries note)**: FEAT-2947
  (`ll-issues create`) has not landed, so Phase 6's ID/filename templating and JSONL
  session-log-hunting fallback are left as-is rather than half-converted. Follow-up once
  FEAT-2947 ships.
- Tests: `scripts/tests/test_ll_issues_size.py` (compute/write/CLI, boundary fixtures at
  scores 2/3 and 7/8); updated `scripts/tests/test_issue_size_review_skill.py` for the new
  Phase 1-3 heading.

## Session Log
- `/ll:manage-issue` - 2026-08-01T09:35:18 - `bb48669c-8ebf-461c-bb4b-030fb283d72e.jsonl`
- `/ll:ready-issue` - 2026-08-01T09:21:24 - `34f64ce0-62dd-40fe-89ee-c3b0b73688ec.jsonl`
- `/ll:confidence-check` - 2026-08-01T09:20:08 - `1f818b7a-4487-4aa3-88bf-cfd2a03fdd58.jsonl`
- `/ll:wire-issue` - 2026-08-01T09:18:47 - `7f201a7c-1370-4a14-b861-d83eeb0fc069.jsonl`
- `/ll:refine-issue` - 2026-08-01T09:16:04 - `019a7d71-f331-466d-9226-eb4d3e08e97c.jsonl`
