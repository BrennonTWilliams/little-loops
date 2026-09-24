---
id: ENH-3559
type: ENH
title: Symlink-safe artifact writes and umask-preserving atomic_write
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T18:30:10Z'
parent: EPIC-3556
labels:
- security
- artifacts
blocked_by:
- ENH-3558
confidence_score: 100
outcome_confidence: 64
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 0
---

# ENH-3559: Symlink-safe artifact writes and umask-preserving atomic_write

## Summary

Route the `dashboard`, `render`, `policy-builder`, `design-md`, and `extract`/`refresh` output writes through `file_utils.atomic_write`, which replaces a symlink at the output path instead of following it. Fix `atomic_write` globally so new files get the umask-derived mode instead of `mkstemp`'s `0600`. Pin both with symlink-replacement and mode tests.

Carved out of cancelled ENH-3540 (Scope §4); see that file for the full research trail.

## Current Behavior

- **Artifact writes follow symlinks.** Plain `Path.write_text` at `cli/artifact/dashboard.py:494`, `cli/artifact/render.py:68`, `cli/artifact/policy_builder.py:160`, `cli/artifact/design_md.py:129`, and `cli/artifact/extract.py:238,300`. A symlink planted at the output path redirects the write to its target.
- **Two writes depend on the locale.** `policy_builder.py:160` (`out_path.write_text(html)`) and `design_md.py:129` (`out_path.write_text(document)`) pass no `encoding=`.
- **`atomic_write` makes files owner-only.** `file_utils.atomic_write` (`scripts/little_loops/file_utils.py:16`) creates its temp file with `tempfile.mkstemp` (mode `0600`) and `os.replace`s it into place with no chmod. `write_text` yields `0644` under a typical `022` umask, so routing artifact writes through `atomic_write` unchanged would silently make shared/served HTML owner-only. The `0600` is a `mkstemp` side effect, not a design choice.
- **Templatize `.rejected` writes are already guarded as far as leaf writes can be.** `rejected_dir = out_dir.with_name(out_dir.name + ".rejected")` (`templatize.py:1365`) is `rmtree`d first (`:1366-1367`); `rmtree` raises on a symlink-to-dir, and a dangling symlink fails the later `mkdir(exist_ok=True)`. The remaining window is a race that swaps `rejected_dir` *itself* for a symlink-to-dir between the `rmtree` and the `mkdir`/writes — a parent-directory attack that leaf-level `atomic_write` cannot close. Leaf symlinks inside `rejected_dir` are not reachable: the directory is created by us with a umask-derived mode, so another user cannot plant entries in it. The `tmp_dir` writes (`:1215,1446-1450,1500-1502`) target a fresh private `mkdtemp` and need no change.
- **Already symlink-safe:** `cli/artifact/policy_revision.py:153-158` and `cli/artifact/lockfile.py:108-110` (`mkstemp` + `os.replace`).

## Expected Behavior

- Every predictable-path artifact output write replaces, rather than follows, a symlink at the output path. The symlink's target is untouched and the output path ends up a regular file.
- Files written by `atomic_write` get mode `0o666 & ~umask` (e.g. `0644` under umask `022`).
- All artifact output is written as UTF-8 regardless of locale.

## Motivation

Artifact output directories are predictable (`artifacts.default_output_dir`, `--output`). A symlink planted at `policy-router-builder.html` or `dashboard.html` turns an artifact write into an arbitrary-file overwrite as the user running the command. The fix already exists (`atomic_write`); it just isn't used here, and using it as-is would regress file modes.

Hidden `.{name}.<hex>.tmp` temp names left behind by a crash stay invisible to `.issues/` scanners (no `*.md` glob matches them) and still match the `*.tmp` ignore pattern (`git_operations.py:97`).

## Proposed Solution

1. **Fix `atomic_write`'s file mode globally.** Replace `tempfile.mkstemp` with `os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)` on a random sibling name (e.g. `f".{path.name[:64]}.{secrets.token_hex(8)}.tmp"` in `path.parent`), retrying on `FileExistsError`. The kernel applies the process umask to the `0o666`, so no umask read is needed. This avoids the `os.umask(0); os.umask(old)` idiom, which mutates process-global state, is not thread-safe, and goes stale if cached. `O_EXCL` also refuses to open through a pre-planted symlink at the temp name. Keep the existing cleanup-on-exception and `os.replace`.
   - **Truncate `path.name` in the temp name** (`[:64]`): the prefix/suffix add 22 chars, so an untruncated name over 233 chars would hit `ENAMETOOLONG` where `write_text` succeeds. (Longest issue filename today is 167, so this is a guard, not a live bug.)
   - **Bound the retry loop** (e.g. 100 attempts, then raise `FileExistsError`) so a directory full of collisions cannot spin forever.
   - **Cleanup unlinks only a temp file this call created.** The `os.open` retry loop stays *outside* the cleanup `try`, exactly as `mkstemp` is today: a `FileExistsError` means the name belongs to someone else (another writer's temp file, or a planted symlink), and the cleanup path must never unlink it. Only after `os.open` succeeds does the `try`/`unlink`-on-exception block begin.
   - Decided: global, not an opt-in parameter. The `write_text` calls `atomic_write` replaced produced umask-derived modes.
   - Decided: do not preserve an existing target's mode. Every file `atomic_write` has written so far is `0600` by accident; preserving it would keep the bug forever.
   - Do not add `atomic_write_bytes`: no in-scope write site needs bytes.
2. **Route the artifact write sites** through `atomic_write(path, content, encoding="utf-8")`: `dashboard.py:494`, `render.py:68`, `policy_builder.py:160`, `design_md.py:129`, `extract.py:238,300`. Keep the `data.json` serialization byte-identical (`json.dumps(data, indent=2, ensure_ascii=False)`), so use `atomic_write`, not `atomic_write_json` (which formats differently). Text-mode `os.fdopen` applies the same newline handling as `write_text`, so the bytes do not change.
3. **Consistency only (no security claim):** route the `.rejected` writes in `templatize.py` (`_write_rejected_discovery` and the diff/check writes into `rejected_dir`) through `atomic_write` so every artifact write uses one helper (UTF-8, umask-derived mode, no partial files). This does **not** close the rmtree→mkdir race: that race swaps the `rejected_dir` directory itself, and `atomic_write` only protects the leaf (see Current Behavior). No symlink test for this site.
4. Do **not** implement unlink-then-write: it has a TOCTOU window between unlink and open.

## Integration Map

### Files to Modify
- `scripts/little_loops/file_utils.py` — `atomic_write`: `os.open(..., 0o666)` on a random sibling name instead of `mkstemp`.
- `scripts/little_loops/cli/artifact/dashboard.py` — `cmd_dashboard` output write (`:494`).
- `scripts/little_loops/cli/artifact/render.py` — `render_to_disk` output write (`:68`).
- `scripts/little_loops/cli/artifact/policy_builder.py` — `cmd_policy_builder` output write (`:160`).
- `scripts/little_loops/cli/artifact/design_md.py` — `cmd_design_md_export` output write (`:129`).
- `scripts/little_loops/cli/artifact/extract.py` — `cmd_extract` (`:238`) and `cmd_refresh` (`:300`) `data.json` writes.
- `scripts/little_loops/cli/artifact/templatize.py` — `.rejected` writes (consistency only; see Proposed Solution §3).

### Dependent Files (Callers/Importers)
- ~69 existing `atomic_write` / `atomic_write_json` call sites (52 + 17 by grep, 2026-09-24) across `cli/issues/`, `hooks/`, `init/`, `session_log.py`, and elsewhere inherit the mode change. None write secrets (checked 2026-09-24); the only deliberate `0600` in the package is `transport.py:229`, which calls `chmod` itself and is unaffected.
- Shares `dashboard.py`, `policy_builder.py`, and `extract.py` with ENH-3557 and ENH-3558; blocked on ENH-3558 so the three land sequentially without merge conflicts on the epic branch. ENH-3558 is now `done` (commit `3fffa5be5`); line numbers above were re-verified against post-ENH-3558 `main`.

### Similar Patterns
- `cli/artifact/policy_revision.py:153-158` and `cli/artifact/lockfile.py:108-110` — existing temp-plus-`os.replace` writers (out of scope; they keep `mkstemp`).

### Tests
- `scripts/tests/test_file_utils.py` — `atomic_write` replaces a symlink at the target (target file unchanged, path now a regular file); mode is `0o666 & ~umask` under umasks `022` and `077` (set with `os.umask` in try/finally); temp file cleaned up on write failure (patch `os.replace` to raise; assert no `.{name}.*.tmp` entry remains in the directory); a temp-name collision leaves the pre-existing file untouched (patch `secrets.token_hex` to return a fixed value once, plant a file at that name, assert it survives and the write still succeeds on retry).
- `scripts/tests/test_enh3559_artifact_symlink_safe_writes.py` (new) — parametrized over `dashboard`, `render`, `policy-builder`, `design-md`, `extract`/`refresh` (host stubbed): plant a symlink at the output path pointing outside the output dir; assert the target is untouched, the output path is a regular file, and its mode is `0o666 & ~umask`.
- Existing: `test_enh3268_design_md_export.py`, `test_policy_builder_emit.py`, `test_feat3304_artifact_dashboard.py`, `test_feat3310_artifact_extract.py`, `test_ll_issues_atomic_write.py`.

### Documentation
- `atomic_write` docstring: states symlink replacement and umask-derived mode.
- CHANGELOG (release prep): files written by `atomic_write` change from `0600` to umask-derived modes.

### Configuration
- N/A

## Program Design

### Signatures
- `atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None` — existing, in `file_utils.py`. Same signature; new files get mode `0o666 & ~umask`; a symlink at `path` is replaced, never followed.

### Call Path
`cmd_policy_builder` -> `atomic_write`
`cmd_dashboard` -> `atomic_write`
`cmd_design_md_export` -> `atomic_write`
`cmd_extract` -> `atomic_write` (`data.json`)
`cmd_refresh` -> `atomic_write` (`data.json`)
`cmd_refresh` -> `render_to_disk` -> `atomic_write`

(`render_policy_builder_html`, `build_dashboard_html`, and `extract_data` return content; they do not write.)

### Decision Rules
- Write-mode rule: artifact outputs, and every other `atomic_write` output, end up with mode `0o666 & ~umask`.
- Symlink rule: output writes go through temp-plus-`os.replace`; never unlink-then-write, never `write_text` on a predictable output path.

## Implementation Steps

1. Change `atomic_write` to `os.open(..., O_WRONLY|O_CREAT|O_EXCL, 0o666)` on a random sibling name; add the `test_file_utils.py` symlink and mode tests.
2. Run the full suite (`python -m pytest scripts/tests/`) to confirm the ~80 existing callers tolerate the mode change.
3. Route the six artifact output writes and the `.rejected` writes through `atomic_write`.
4. Add `test_enh3559_artifact_symlink_safe_writes.py`; run it with the existing artifact test files, then `mypy` and `ruff check`.

## Impact

- **Priority**: P2 — needs a local attacker able to plant a symlink in the output directory; lower reach than the XSS children.
- **Effort**: Small — one helper change, seven write sites, two test files.
- **Risk**: Medium — the mode change reaches ~80 callers outside `cli/artifact/`; the full suite is the guard.
- **Breaking Change**: Minor, behavioral: `atomic_write` output files change from `0600` to umask-derived modes.

## Scope Boundaries

- **In scope**: the `atomic_write` mode fix (global); routing the listed artifact output writes and the templatize `.rejected` writes through it; symlink and mode tests.
- **Out of scope**: `policy_revision.py` / `lockfile.py` writes (already symlink-safe); templatize `tmp_dir` writes (fresh private dir); an `atomic_write_bytes` variant; any escaping change (ENH-3557, ENH-3558, ENH-3560).
- **Out of scope, deliberately — symlinked parent directories.** Each site runs `output_dir.mkdir(exist_ok=True)` (or `out_path.parent.mkdir(...)`), which follows a symlinked output directory, then writes a fixed filename into its target. Users legitimately symlink output dirs, and the attacker gains only a fixed-name file (e.g. `dashboard.html`) in a chosen directory, not an arbitrary-path overwrite. The same reasoning covers the templatize `rejected_dir` swap race.

## Acceptance Criteria

- [ ] `atomic_write` creates files with mode `0o666 & ~umask` (`0644` under `022`, `0600` under `077`) and replaces a symlink at the target without touching the symlink's target; `test_file_utils.py` pins both.
- [ ] `atomic_write` does not read or set the process umask.
- [ ] `atomic_write` never unlinks a path it did not create: a temp-name collision leaves the pre-existing entry untouched, the retry loop is bounded, and a failed write leaves no temp file behind; `test_file_utils.py` pins all three.
- [ ] Every artifact output write listed under Files to Modify uses `atomic_write`; a parametrized test plants a symlink at each output path (dashboard, render, policy-builder, design-md, extract/refresh `data.json`) and asserts the target is untouched, the output path is a regular file, and its mode is `0o666 & ~umask`.
- [ ] `policy_builder.py` and `design_md.py` output is written as UTF-8 regardless of locale.
- [ ] `extract`/`refresh` `data.json` bytes are unchanged apart from the write path.
- [ ] The templatize `.rejected` writes (`_write_rejected_discovery` and the `roundtrip.diff` / `lift-reversibility.diff` / `lift-render-check.txt` writes into `rejected_dir`) use `atomic_write` (consistency only; no security claim); `test_artifact_templatize.py` passes unchanged (no symlink test, per Proposed Solution §3).
- [ ] The full `python -m pytest scripts/tests/` passes with the global mode change; `mypy` and `ruff check` pass.

## Related

- EPIC-3556 (parent); ENH-3540 (cancelled, original spec)
- ENH-3558 (sequencing blocker: shared files `dashboard.py`, `extract.py`)

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- Verified against code 2026-09-24: `atomic_write` (`file_utils.py:16`, `mkstemp` + `os.replace`, no chmod), the six `write_text` sites (`dashboard.py:475`, `render.py:68`, `policy_builder.py:143`, `design_md.py:129`, `extract.py:227,289`), locale-dependent writes at `policy_builder.py:143` and `design_md.py:129`, `transport.py:229` `chmod(0o600)` as the only deliberate `0600`, and `mkstemp` + `os.replace` in `policy_revision.py`/`lockfile.py` all match. No test patches `mkstemp`, and no existing test asserts a `0600` mode.
- Corrected: caller count was "~80"; grep finds 52 `atomic_write(` + 17 `atomic_write_json(` call sites (~69).
- Corrected (proposal-vs-integration-map gap, check B6): the Integration Map listed the templatize `.rejected` writes but no Acceptance Criterion covered them; one added.
- Evidence-quote check: clean. Decisions log: no active required rules.

## Status

**Open** | Created: 2026-09-24 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-24_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 64/100 → MODERATE

### Outcome Risk Factors
- Wide blast radius: ~69 existing `atomic_write`/`atomic_write_json` callers inherit the `0600` → umask-derived mode change; the full-suite run (Implementation Step 2) is the only guard, so run it before routing the artifact sites.
- Broad enumeration across 7 modified files plus a local-logic rewrite of `atomic_write` (bounded retry, foreign-temp-safe cleanup, name truncation) — expect some iteration on the collision/cleanup tests.

## Session Log
- `/ll:confidence-check` - 2026-09-24T20:29:53 - `7ccc0a63-5f30-4b64-83f4-7cfd1905bff1.jsonl`
- `/ll:verify-issues` - 2026-09-24T19:13:35 - `27bdfde5-d1ef-4e98-b8ff-2728ac43d651.jsonl`
- `/ll:scope-epic` - 2026-09-24T18:30:39 - `bd7b32d0-d305-4468-99d3-61a8a02d4caa.jsonl`
- Manual review - 2026-09-24 - post-ENH-3558 review: refreshed write-site line numbers; recast templatize `.rejected` routing as consistency-only (leaf `atomic_write` cannot close a dir-swap race); added cleanup-must-not-unlink-foreign-temp, bounded retry, and temp-name truncation to §1 with tests + AC; corrected Program Design call paths; scoped out symlinked parent dirs explicitly
- Manual review - 2026-09-24 - ported ENH-3540 Scope §4 and ACs into this child; replaced the umask-read idiom with `os.open(..., 0o666)`; dropped `atomic_write_bytes` (no caller); added `design_md.py` encoding fix and `blocked_by: ENH-3558` for sequencing
