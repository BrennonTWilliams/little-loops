---
id: BUG-3164
type: BUG
title: ll-adapt kimi-code, gemini, and omp mirrors omit skill companion files
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-13'
captured_at: '2026-08-13T22:23:42Z'
parent: EPIC-2257
---

# BUG-3164: ll-adapt kimi-code, gemini, and omp mirrors omit skill companion files

## Summary

Follow-up to BUG-3163 (qwen surface, EPIC-3154): the identical single-file mirror gap exists in the other SKILL.md-mirroring emitters. `KimiEmitter.emit_skill` (`scripts/little_loops/adapters/kimi.py:57`) writes only `.kimi-code/skills/<name>/SKILL.md`, `GeminiEmitter.emit_skill` (`scripts/little_loops/adapters/gemini.py:80`) writes only `.gemini/skills/<name>/SKILL.md`, and `OmpEmitter.emit_skill` (`scripts/little_loops/adapters/omp.py:52`) writes only `.omp/skills/<name>/SKILL.md`. None copy the ENH-494 companion files, and their skip checks compare SKILL.md only, so companion drift is never repaired by re-runs.

**Observed state**: `.kimi-code/skills/` (46 tracked files) and `.gemini/skills/` (18 tracked files) contain SKILL.md files only. The same 23 companion files BUG-3163 restored for qwen — across wire-issue (6), audit-issue-conflicts (4), create-loop (3), confidence-check (2), configure (2), and capture-issue, decide-issue, format-issue, manage-issue, spike, verify-issue-loop (1 each) — are absent from both mirrors. No `.omp/skills` mirror is tracked in this repo yet, but the emitter carries the same gap.

**Impact**: on Kimi Code and Gemini CLI hosts, adapted skills that read companions dangle at the mirror path; in end-user projects without the `skills/` source tree there is no glob-recovery, so affected skills hard-fail. Same deterministic failure mode BUG-3163 documented for qwen (11 of 18 mirrored skills).

**Fix path is paved**: BUG-3163 landed the shared `_sync_skill_companions` helper in `scripts/little_loops/adapters/core.py`. Rather than pasting the same one-call wiring into three more emitters, hoist the whole mirrored-skill emission into a shared `core.py` helper that all four mirror emitters delegate to (see Proposed Solution) — the four `emit_skill` bodies are already token-identical apart from the host directory name. Then mirrors regenerate via `ll-adapt --host kimi-code --apply` / `--host gemini --apply`, and BUG-3163's wiring parity test (`test_qwen_skill_mirrors_carry_companions`) is parametrized over the mirror roots.


## Current Behavior

`ll-adapt --host kimi-code|gemini|omp --apply` writes only `.kimi-code/skills/<name>/SKILL.md`, `.gemini/skills/<name>/SKILL.md`, or `.omp/skills/<name>/SKILL.md` per eligible skill. ENH-494 companion files living beside the source SKILL.md are never copied into the mirror, but adapted SKILL.md bodies reference them with relative paths — so those reads dangle at the mirror path. Each emitter's skip check compares SKILL.md content only and returns early, so re-runs never repair companion drift either.

## Expected Behavior

Each SKILL.md-mirroring emitter mirrors the full skill directory: SKILL.md plus every companion file (excluding the codex-only `agents/` subtree), with re-runs repairing drift and pruning stale mirror companions — identical to the BUG-3163 behavior for `QwenEmitter`. A wiring parity test guards `.kimi-code/skills/` and `.gemini/skills/` the way `test_qwen_skill_mirrors_carry_companions` guards `.qwen/skills/`. The omp surface has no tracked `.omp/skills/` mirror in this repo, so the parity test cannot cover it — omp's guarantee comes from the emitter unit tests instead (see Tests).

## Motivation

Same deterministic failure mode BUG-3163 fixed for qwen, live on two more hosts: 11 mirrored skills reference 23 companion files that are absent from both `.kimi-code/skills/` and `.gemini/skills/`. End-user projects without the `skills/` source tree have no glob-recovery path, so those skills hard-fail. Also keeps the three mirror emitters from drifting further apart now that the shared helper exists.

## Proposed Solution

**Consolidate rather than triplicate.** `KimiEmitter.emit_skill` (`kimi.py:57`), `QwenEmitter.emit_skill` (`qwen.py:61`), and `OmpEmitter.emit_skill` (`omp.py:52`) are token-identical apart from the host directory literal (`.kimi-code` / `.qwen` / `.omp`); `GeminiEmitter.emit_skill` (`gemini.py:80`) differs only in using `_prepare_skill_content` instead of `_select_frontmatter_fields`. Adding three independent `_sync_skill_companions` calls fixes today's bug while leaving four copies of the same method to drift again.

Instead, add a shared emission helper to `scripts/little_loops/adapters/core.py`:

```python
def _emit_mirrored_skill(skill_meta: dict, host_dir: str, prepare: Callable[[str, str], tuple[str, ...]]) -> str
```

that derives `plugin_root / host_dir / "skills" / skill_name / "SKILL.md"`, prepares content via the injected callable, calls `_sync_skill_companions` **even when SKILL.md is unchanged**, and returns `"skipped"` only when SKILL.md *and* companions are all in sync. All four mirror emitters (`qwen`, `kimi`, `gemini`, `omp`) become one-line delegations; the qwen wiring BUG-3163 landed refactors into it unchanged in behavior (guarded by the existing `TestQwenEmitterSkillCompanions` cases).

Then regenerate mirrors (`ll-adapt --host kimi-code --apply`, `ll-adapt --host gemini --apply`) and parametrize the BUG-3163 wiring parity test over the mirror roots. Two constraints on that test:

- `.kimi-code/skills/` also contains 28 command-bridged `ll-*` skills with no `skills/` source directory — skip any mirror dir with no source `skills/<name>/SKILL.md` rather than flagging it as an offender (the current qwen test appends `"no source skill directory"`, which would fire 28 times).
- `.omp/skills/` does not exist in this repo, so globbing it yields nothing and the assertion passes vacuously. Guard on `mirror_root.exists()` and rely on the emitter unit tests for omp's real coverage — do not let the vacuous pass read as verification.

## Integration Map

### Files to Modify
- `scripts/little_loops/adapters/core.py` — new shared `_emit_mirrored_skill(skill_meta, host_dir, prepare)` helper wrapping path derivation + `_sync_skill_companions` + skip decision
- `scripts/little_loops/adapters/kimi.py` — `KimiEmitter.emit_skill` delegates to it (`.kimi-code`, `_select_frontmatter_fields`)
- `scripts/little_loops/adapters/gemini.py` — `GeminiEmitter.emit_skill` delegates to it (`.gemini`, `_prepare_skill_content`)
- `scripts/little_loops/adapters/omp.py` — `OmpEmitter.emit_skill` delegates to it (`.omp`, `_select_frontmatter_fields`)
- `scripts/little_loops/adapters/qwen.py` — `QwenEmitter.emit_skill` refactored onto the shared helper (behavior unchanged; BUG-3163 wiring absorbed)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/adapters/core.py` `process_skills()` — sole caller of `emit_skill`; no signature change
- `.kimi-code/skills/*/`, `.gemini/skills/*/` — mirrors regenerated by `ll-adapt --host <host> --apply` (~46 newly git-tracked companion files: 23 per host)
- `scripts/little_loops/adapters/codex.py`, `claude_code.py` — explicitly *not* affected: codex adapts sources in place (no mirror dir), claude-code's `emit_skill` is a no-op

### Similar Patterns
- `scripts/little_loops/adapters/qwen.py` `QwenEmitter.emit_skill` — the BUG-3163 wiring, which becomes the body of the shared helper

### Tests
- `scripts/tests/test_adapters.py` — parametrize `TestQwenEmitterSkillCompanions` over `(emitter, mirror_dir)` for all four mirror emitters instead of copying the class three times; the same four cases (copy / drift repair / stale prune / dry-run) then cover kimi, gemini, and omp. This is omp's only coverage, since it has no tracked mirror.
- `scripts/tests/test_wiring_skills_and_commands.py` — parametrize `test_qwen_skill_mirrors_carry_companions` over `.qwen/`, `.kimi-code/`, `.gemini/`; skip mirror dirs with no source `skills/<name>/SKILL.md` (kimi's 28 `ll-*` command bridges) and guard on `mirror_root.exists()`

### Documentation
- `docs/kimi/getting-started.md:68` — skills bullet currently describes the mirror as SKILL.md-only; add the companion-mirroring clause matching `docs/qwen/getting-started.md:68` (updated by BUG-3163)
- No gemini docs dir exists (`docs/qwen/`, `docs/kimi/` only), and `docs/reference/HOST_COMPATIBILITY.md` never mentions companions — no edits needed in either

### Configuration
- N/A

## Implementation Steps

1. Add `_emit_mirrored_skill(skill_meta, host_dir, prepare)` to `core.py`, lifting the body of the current `QwenEmitter.emit_skill` (compute `skill_md_changed`, run `_sync_skill_companions`, fold both into the skip decision) with the host dir and content-prep callable injected.
2. Refactor `QwenEmitter.emit_skill` onto it first and run `TestQwenEmitterSkillCompanions` — a green run proves the helper is behavior-identical before the other three adopt it.
3. Delegate `KimiEmitter`, `GeminiEmitter`, and `OmpEmitter` `emit_skill` to the helper.
4. Regenerate mirrors: `ll-adapt --host kimi-code --apply && ll-adapt --host gemini --apply`; confirm the 23 companions land byte-identical in each mirror and the 28 `ll-*` bridged kimi skills are untouched. Expect ~46 new tracked files in the commit.
5. Parametrize the emitter unit tests over all four emitters and the parity test over the three mirror roots (skipping source-less mirrors, guarding on `mirror_root.exists()`).
6. Run `test_adapters.py`, `test_wiring_skills_and_commands.py`, and the private-refs gate.
7. Update `docs/kimi/getting-started.md:68` to match the qwen companion wording.

## Impact

- **Priority**: P3 - same deterministic breakage as BUG-3163 (P2) but on secondary hosts with no live failure report yet; fix is mechanical now that the helper exists
- **Effort**: Small code change, large generated diff - one shared helper + four one-line delegations + test parametrization, but mirror regeneration adds ~46 newly git-tracked companion files (23 × 2 hosts)
- **Risk**: Low - additive copies into existing mirror dirs; SKILL.md content unchanged; helper already proven on the qwen surface. The one new risk is the qwen refactor onto the shared helper, contained by running the existing qwen companion tests before the other emitters adopt it (step 2)
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| [CONTRIBUTING.md](../../CONTRIBUTING.md) | § Skill File Size: 500-Line Limit & Companion Files — the ENH-494 convention the mirrors break |
| [docs/reference/API.md](../../docs/reference/API.md) | Adapter registry / `ll-adapt --host` surface the emitters belong to |
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | § Host Adapter Capability Map — build-time artifact generation design |

## Status

**Open** | Created: 2026-08-13 | Priority: P3

## Steps to Reproduce

1. In a project where `ll-adapt --host kimi-code --apply` (or `--host gemini --apply`) has run, open the Kimi Code CLI (or Gemini CLI)
2. Invoke any mirrored skill with companions (e.g. `wire-issue`, `audit-issue-conflicts`, `create-loop`)
3. Observe: the skill's relative companion references resolve against `.kimi-code/skills/<name>/` (or `.gemini/skills/<name>/`) and fail — the companions were never mirrored

## Root Cause

- **File**: `scripts/little_loops/adapters/kimi.py`, `scripts/little_loops/adapters/gemini.py`, `scripts/little_loops/adapters/omp.py`
- **Anchor**: `in function KimiEmitter.emit_skill()` (kimi.py:57), `GeminiEmitter.emit_skill()` (gemini.py:80), `OmpEmitter.emit_skill()` (omp.py:52)
- **Cause**: Each `emit_skill` writes only the adapted SKILL.md and never copies sibling files from `skills/<name>/`; the early-return skip check compares SKILL.md content only, so companion drift is invisible to re-runs. Same oversight as FEAT-3159 (BUG-3163) — the ENH-494 companion convention was never considered when these emitters were written.

## Error Messages

Expected at runtime on affected hosts (companion path absent from mirror):

```
File not found: <project-root>/.kimi-code/skills/audit-issue-conflicts/conflict-detection-prompt.md
```

## Environment

Kimi Code CLI and Gemini CLI hosts; little-loops mirrors produced by `ll-adapt --host kimi-code --apply` / `--host gemini --apply` (git-tracked in this repo, SKILL.md-only).

## Frequency

Deterministic — every invocation of an affected mirrored skill that reads a companion file (11 of 18 mirrored skills on each host).

## Location

- **File**: `scripts/little_loops/adapters/kimi.py`, `gemini.py`, `omp.py`
- **Line(s)**: 57-85 / 80-109 / 52-80 respectively (at scan commit: 1223cb7b)
- **Anchor**: `in function <Host>Emitter.emit_skill()`
- **Code**:
```python
if out_path.exists() and out_path.read_text() == new_content:
    if not quiet:
        print(f"  SKIP   {skill_name}: already adapted")
    return "skipped"
```

## Reproduction Steps

Static verification (no host needed): `git ls-files .kimi-code/skills .gemini/skills` shows only SKILL.md entries, while `find skills -mindepth 2 -type f ! -name SKILL.md ! -path '*/agents/*'` lists 23 companions for the same mirrored skill set.

## Proposed Fix

See Proposed Solution. Shared `_emit_mirrored_skill` helper in `core.py` (lifted from the `QwenEmitter` wiring BUG-3163 proved), four emitters delegating to it, mirror regeneration, and parametrized emitter + parity tests.


## Session Log
- `/ll:capture-issue` - 2026-08-13T22:25:31 - `9b452ca8-48d5-4632-a2ce-16c7c6276022.jsonl`
