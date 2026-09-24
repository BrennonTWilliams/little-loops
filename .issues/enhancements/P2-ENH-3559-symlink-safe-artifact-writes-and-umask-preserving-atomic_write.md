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
---

# ENH-3559: Symlink-safe artifact writes and umask-preserving atomic_write

## Summary

Route the `dashboard`, `render`, `policy-builder`, `design-md`, and `extract`/`refresh` output writes through `file_utils.atomic_write`, which replaces a symlink at the output path instead of following it. Fix `atomic_write` globally so new files get the umask-derived mode instead of `mkstemp`'s `0600`. Pin both with symlink-replacement and mode tests.

Carved out of cancelled ENH-3540 (Scope §4); see that file for the full research trail.

## Current Behavior

- **Artifact writes follow symlinks.** Plain `Path.write_text` at `cli/artifact/dashboard.py:475`, `cli/artifact/render.py:68`, `cli/artifact/policy_builder.py:143`, `cli/artifact/design_md.py:129`, and `cli/artifact/extract.py:227,289`. A symlink planted at the output path redirects the write to its target.
- **Two writes depend on the locale.** `policy_builder.py:143` (`out_path.write_text(html)`) and `design_md.py:129` (`out_path.write_text(document)`) pass no `encoding=`.
- **`atomic_write` makes files owner-only.** `file_utils.atomic_write` (`scripts/little_loops/file_utils.py:16`) creates its temp file with `tempfile.mkstemp` (mode `0600`) and `os.replace`s it into place with no chmod. `write_text` yields `0644` under a typical `022` umask, so routing artifact writes through `atomic_write` unchanged would silently make shared/served HTML owner-only. The `0600` is a `mkstemp` side effect, not a design choice.
- **Templatize `.rejected` writes are already largely guarded.** `rejected_dir = out_dir.with_name(out_dir.name + ".rejected")` (`templatize.py:1365`) is `rmtree`d first (`:1366-1367`); `rmtree` raises on a symlink-to-dir, and a dangling symlink fails the later `mkdir(exist_ok=True)`. Only a race between the `rmtree` and the `mkdir`/writes leaves a window. The `tmp_dir` writes (`:1215,1446-1450,1500-1502`) target a fresh private `mkdtemp` and need no change.
- **Already symlink-safe:** `cli/artifact/policy_revision.py:153-158` and `cli/artifact/lockfile.py:108-110` (`mkstemp` + `os.replace`).

## Expected Behavior

- Every predictable-path artifact output write replaces, rather than follows, a symlink at the output path. The symlink's target is untouched and the output path ends up a regular file.
- Files written by `atomic_write` get mode `0o666 & ~umask` (e.g. `0644` under umask `022`).
- All artifact output is written as UTF-8 regardless of locale.

## Motivation

Artifact output directories are predictable (`artifacts.default_output_dir`, `--output`). A symlink planted at `policy-router-builder.html` or `dashboard.html` turns an artifact write into an arbitrary-file overwrite as the user running the command. The fix already exists (`atomic_write`); it just isn't used here, and using it as-is would regress file modes.

## Proposed Solution

1. **Fix `atomic_write`'s file mode globally.** Replace `tempfile.mkstemp` with `os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)` on a random sibling name (e.g. `f".{path.name}.{secrets.token_hex(8)}.tmp"` in `path.parent`), retrying on `FileExistsError`. The kernel applies the process umask to the `0o666`, so no umask read is needed. This avoids the `os.umask(0); os.umask(old)` idiom, which mutates process-global state, is not thread-safe, and goes stale if cached. `O_EXCL` also refuses to open through a pre-planted symlink at the temp name. Keep the existing cleanup-on-exception and `os.replace`.
   - Decided: global, not an opt-in parameter. The `write_text` calls `atomic_write` replaced produced umask-derived modes.
   - Decided: do not preserve an existing target's mode. Every file `atomic_write` has written so far is `0600` by accident; preserving it would keep the bug forever.
   - Do not add `atomic_write_bytes`: no in-scope write site needs bytes.
2. **Route the artifact write sites** through `atomic_write(path, content, encoding="utf-8")`: `dashboard.py:475`, `render.py:68`, `policy_builder.py:143`, `design_md.py:129`, `extract.py:227,289`. Keep the `data.json` serialization byte-identical (`json.dumps(data, indent=2, ensure_ascii=False)`), so use `atomic_write`, not `atomic_write_json` (which formats differently).
3. **Defense in depth:** route the `.rejected` writes in `templatize.py` (`_write_rejected_discovery` and the diff/check writes into `rejected_dir`) through `atomic_write` as well, closing the rmtree→mkdir race window. No symlink test for this site: the pre-`rmtree` already rejects a planted symlink before any write is reached.
4. Do **not** implement unlink-then-write: it has a TOCTOU window between unlink and open.

## Integration Map

### Files to Modify
- `scripts/little_loops/file_utils.py` — `atomic_write`: `os.open(..., 0o666)` on a random sibling name instead of `mkstemp`.
- `scripts/little_loops/cli/artifact/dashboard.py` — `cmd_dashboard` output write (`:475`).
- `scripts/little_loops/cli/artifact/render.py` — `render_to_disk` output write (`:68`).
- `scripts/little_loops/cli/artifact/policy_builder.py` — `cmd_policy_builder` output write (`:143`).
- `scripts/little_loops/cli/artifact/design_md.py` — output write (`:129`).
- `scripts/little_loops/cli/artifact/extract.py` — `cmd_extract` (`:227`) and `cmd_refresh` (`:289`) `data.json` writes.
- `scripts/little_loops/cli/artifact/templatize.py` — `.rejected` writes (defense in depth).

### Dependent Files (Callers/Importers)
- ~80 existing `atomic_write` / `atomic_write_json` call sites across `cli/issues/`, `hooks/`, `init/`, `session_log.py`, and elsewhere inherit the mode change. None write secrets (checked 2026-09-24); the only deliberate `0600` in the package is `transport.py:229`, which calls `chmod` itself and is unaffected.
- Shares `dashboard.py`, `policy_builder.py`, and `extract.py` with ENH-3557 and ENH-3558; blocked on ENH-3558 so the three land sequentially without merge conflicts on the epic branch.

### Similar Patterns
- `cli/artifact/policy_revision.py:153-158` and `cli/artifact/lockfile.py:108-110` — existing temp-plus-`os.replace` writers (out of scope; they keep `mkstemp`).

### Tests
- `scripts/tests/test_file_utils.py` — `atomic_write` replaces a symlink at the target (target file unchanged, path now a regular file); mode is `0o666 & ~umask` under umasks `022` and `077` (set with `os.umask` in try/finally); temp file cleaned up on write failure.
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
`cmd_policy_builder` -> `render_policy_builder_html` -> `atomic_write`
`cmd_dashboard` -> `build_dashboard_html` -> `atomic_write`
`cmd_refresh` -> `extract_data` -> `atomic_write` (`data.json`) -> `render_to_disk` -> `atomic_write`

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

## Acceptance Criteria

- [ ] `atomic_write` creates files with mode `0o666 & ~umask` (`0644` under `022`, `0600` under `077`) and replaces a symlink at the target without touching the symlink's target; `test_file_utils.py` pins both.
- [ ] `atomic_write` does not read or set the process umask.
- [ ] Every artifact output write listed under Files to Modify uses `atomic_write`; a parametrized test plants a symlink at each output path (dashboard, render, policy-builder, design-md, extract/refresh `data.json`) and asserts the target is untouched, the output path is a regular file, and its mode is `0o666 & ~umask`.
- [ ] `policy_builder.py` and `design_md.py` output is written as UTF-8 regardless of locale.
- [ ] `extract`/`refresh` `data.json` bytes are unchanged apart from the write path.
- [ ] The full `python -m pytest scripts/tests/` passes with the global mode change; `mypy` and `ruff check` pass.

## Related

- EPIC-3556 (parent); ENH-3540 (cancelled, original spec)
- ENH-3558 (sequencing blocker: shared files `dashboard.py`, `extract.py`)

## Status

**Open** | Created: 2026-09-24 | Priority: P2


## Session Log
- `/ll:scope-epic` - 2026-09-24T18:30:39 - `bd7b32d0-d305-4468-99d3-61a8a02d4caa.jsonl`
- Manual review - 2026-09-24 - ported ENH-3540 Scope §4 and ACs into this child; replaced the umask-read idiom with `os.open(..., 0o666)`; dropped `atomic_write_bytes` (no caller); added `design_md.py` encoding fix and `blocked_by: ENH-3558` for sequencing
