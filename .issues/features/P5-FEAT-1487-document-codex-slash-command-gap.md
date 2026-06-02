---
id: FEAT-1487
type: FEAT
priority: P5
status: done
captured_at: '2026-05-15T23:00:00Z'
discovered_date: 2026-05-15
discovered_by: manage-issue
parent: EPIC-1463
decision_needed: false
testable: false
confidence_score: 90
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
completed_at: '2026-05-16T05:35:16Z'
---

# FEAT-1487: Update HOST_COMPATIBILITY.md Codex Slash-Command Entry

## Summary

Research in FEAT-1483 confirmed that Codex has no `.codex/prompts/` slash-command
surface — the prior `[^cmds]` footnote in `HOST_COMPATIBILITY.md` was speculative.
The Codex Skills API (`~/.codex/skills/`) covers both "skill" and "command"
use-cases. This issue updates the parity matrix and footnote to accurately reflect
the research outcome, and documents the gap as "skills only — no separate
slash-command registration."

## Current Behavior

`docs/reference/HOST_COMPATIBILITY.md` footnote `[^cmds]` references
`.codex/prompts/` as the Codex slash-command path. This path does not exist on
the Codex CLI. The "Slash-command discovery" row shows `✗` for Codex with
misleading guidance about `.codex/prompts/`.

## Expected Behavior

After this issue:
- `[^cmds]` footnote references `~/.codex/skills/` (not `.codex/prompts/`), notes
  that no separate slash-command surface exists, and points to FEAT-1486 for skill
  adaptation work.
- The "Slash-command discovery" parity matrix cell for Codex is updated to reflect
  "skills-only — no separate command surface; see FEAT-1486" (remains `✗` until
  a full skill bridge lands in FEAT-1486, or is documented as N/A).
- `hooks/adapters/codex/README.md` "Out of scope" note is updated to reflect the
  research outcome.

## Use Case

**Who**: Maintainer or contributor checking `HOST_COMPATIBILITY.md` for Codex slash-command support

**Context**: After FEAT-1483 confirmed Codex has no separate slash-command surface (only `~/.codex/skills/`), a developer looking up how to register commands on Codex finds `.codex/prompts/` referenced — a path that does not exist

**Goal**: Find accurate documentation so they route slash-command work through `~/.codex/skills/` and understand the FEAT-1486 scope for skill bridging

## Acceptance Criteria

- [ ] `docs/reference/HOST_COMPATIBILITY.md` `[^cmds]` footnote references
      `~/.codex/skills/` instead of `.codex/prompts/`
- [ ] The footnote mentions that no separate slash-command surface exists and
      points to FEAT-1486 for skill discovery work
- [ ] `hooks/adapters/codex/README.md` "Out of scope" line references
      `thoughts/research/codex-command-discovery.md` and notes the Skills API is confirmed

## API/Interface

N/A — documentation only; no public API or interface changes.

## Motivation

The `[^cmds]` footnote references `.codex/prompts/` — a path that does not exist on the Codex CLI. This misleads anyone looking up Codex slash-command support. FEAT-1483 already produced the research confirming `~/.codex/skills/` is the correct surface. Updating two files closes the accuracy gap at zero runtime risk.

## Proposed Solution

1. In `docs/reference/HOST_COMPATIBILITY.md`, locate the `[^cmds]` footnote definition and replace `.codex/prompts/` with `~/.codex/skills/`; add a sentence: "No separate slash-command surface exists; see FEAT-1486 for skill-bridge work."
2. Check the "Slash-command discovery" parity matrix row for Codex and ensure the `✗` cell note is consistent with the updated footnote.
3. In `hooks/adapters/codex/README.md`, update the "Out of scope" bullet referencing slash-commands to cite `thoughts/research/codex-command-discovery.md` and note the Skills API path is confirmed.

## Integration Map

### Files to Modify

- `docs/reference/HOST_COMPATIBILITY.md` — `[^cmds]` footnote revision; "Slash-command discovery" parity matrix cell note
- `hooks/adapters/codex/README.md` — "Out of scope" line update
- `thoughts/research/codex-command-discovery.md` — "Gating recommendation" section: mark FEAT-1487 as completed, following the same pattern as the FEAT-1486 `COMPLETED` annotation at line 143 [Wiring pass added by `/ll:wire-issue`]

### Dependent Files (Callers/Importers)

- N/A — documentation only; no runtime code references these footnotes

### Similar Patterns

- N/A — no other footnotes reference CLI paths that need verification

### Tests

- N/A — documentation change; `ll-check-links` can verify no broken anchors are introduced
- `scripts/tests/test_feat1483_doc_wiring.py` — existing wiring-test pattern (checks FEAT-1483 research artifacts exist and reference correct surfaces); provides the model for any analogous FEAT-1487 verification test
- `scripts/tests/test_feat1462_doc_wiring.py` — existing test covering `HOST_COMPATIBILITY.md`; `TestHostCompatibilityWiring.test_codex_skills_path_present` asserts `"codex/skills" in content`; currently passes, no update needed [Wiring pass added by `/ll:wire-issue`]
- `scripts/tests/test_feat1487_doc_wiring.py` — **new test file to write**, following the FEAT-1483 pattern; classes: `TestHostCompatibilitySlashCommandFootnote` (assert `"no separate slash-command surface"` in `HOST_COMPATIBILITY.md`, assert `FEAT-1486` and `FEAT-1487` referenced), `TestCodexReadmeFeat1487Reference` (assert `FEAT-1487` in `hooks/adapters/codex/README.md`); all assertions already pass against current file state — green confirmation test [Wiring pass added by `/ll:wire-issue`]

### Documentation

- `thoughts/research/codex-command-discovery.md` — primary research source confirming `~/.codex/skills/` and absence of `.codex/prompts/`

### Configuration

- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**⚠️ Critical finding: Acceptance criteria appear already satisfied.**

All three acceptance criteria were verified against the live files during refinement:

1. `docs/reference/HOST_COMPATIBILITY.md` lines 53–61 — `[^cmds]` footnote already reads:
   - "Codex has no `.codex/prompts/` slash-command path (that reference in prior footnotes was speculative — no such surface exists in the current Codex CLI)"
   - Names `~/.codex/skills/<name>/SKILL.md` as the correct surface
   - Cites `thoughts/research/codex-command-discovery.md` (FEAT-1483) and FEAT-1486
2. `docs/reference/HOST_COMPATIBILITY.md` lines 50–51 — parity matrix Codex column already reads:
   - Slash-command discovery: `✗ — no separate slash-command surface; Skills API covers both[^cmds]`
   - Skill discovery: `✓ — ~/.codex/skills/<name>/SKILL.md; all ll skills adapted by ll-adapt-skills-for-codex (FEAT-1486)[^cmds]`
3. `hooks/adapters/codex/README.md` lines 162–167 — "Out of scope" bullet already reads:
   - "**Codex Skills API is confirmed stable** (`~/.codex/skills/`);"
   - "see `thoughts/research/codex-command-discovery.md` (FEAT-1483) and FEAT-1486 (skill adaptation) / FEAT-1487 (parity matrix update)"

**Remaining `.codex/prompts/` references** (none require action): the string appears only in issue files (intentional history), completed issue files, test assertions that check it is mentioned only to negate it, and the research doc itself — all appropriate usages.

**Recommendation**: Before implementing, verify these file states are still current (`grep -n "codex/prompts" docs/reference/HOST_COMPATIBILITY.md`). If the content matches, the issue is already done and should be closed.

## Implementation Steps

1. Update `[^cmds]` footnote in `docs/reference/HOST_COMPATIBILITY.md` (`.codex/prompts/` → `~/.codex/skills/`)
2. Add inline note to the "Slash-command discovery" Codex cell referencing the footnote
3. Update `hooks/adapters/codex/README.md` "Out of scope" bullet
4. Grep for remaining `.codex/prompts/` references and update any stragglers

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `thoughts/research/codex-command-discovery.md` "Gating recommendation" section — mark FEAT-1487 as completed (same pattern as FEAT-1486 annotation at line 143: "COMPLETED — ...")
6. Write `scripts/tests/test_feat1487_doc_wiring.py` — doc-wiring verification test following the `test_feat1483_doc_wiring.py` pattern (two classes: `TestHostCompatibilitySlashCommandFootnote` and `TestCodexReadmeFeat1487Reference`; all assertions are green against current file state)

## Impact

- **Priority**: P5 — documentation accuracy fix; no runtime behavior change
- **Effort**: Small — two file edits, no code changes
- **Risk**: Low — documentation-only; no tests required
- **Breaking Change**: No

## Labels

codex, docs, host-compat

## Status

**Closed - Already Fixed** | Created: 2026-05-15 | Closed: 2026-05-16 | Priority: P5

All three acceptance criteria were verified as already satisfied in live files during `/ll:ready-issue` validation. No implementation required.


## Session Log
- `/ll:ready-issue` - 2026-05-16T05:34:57 - `7f57340e-a102-4af2-83c4-aa87c1c90b24.jsonl`
- `/ll:confidence-check` - 2026-05-16T00:00:00Z - `bfcdb563-da12-4eda-a615-ec5c3c36f292.jsonl`
- `/ll:wire-issue` - 2026-05-16T05:29:57 - `68b8d7ac-7611-418f-b1ab-8f6237162b76.jsonl`
- `/ll:refine-issue` - 2026-05-16T05:26:06 - `1590f00d-ff0d-42a0-8087-d447e25a51a1.jsonl`
- `/ll:format-issue` - 2026-05-16T03:55:05 - `604904cc-0700-49df-ba1a-c56e52eb7fa1.jsonl`
- `/ll:format-issue` - 2026-05-16T03:45:34 - `b0311cf7-493f-4a79-bc9d-67419d002020.jsonl`


---

## Resolution

- **Status**: Closed - Already Fixed
- **Closed**: 2026-05-16
- **Reason**: already_fixed
- **Closure**: Automated (ready-issue validation)

### Closure Notes
Issue was automatically closed during validation.
The issue was determined to be invalid, already resolved, or not actionable.
