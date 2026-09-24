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

Route the `dashboard`, `render`, `policy-builder`, `design-md`, and `extract`/`refresh` output writes (and the templatize `.rejected` writes) through `file_utils.atomic_write`, which replaces a symlink at the output path instead of following it. Add an opt-in `shared_mode=True` keyword to `atomic_write` so artifact writes get a umask-derived mode (or keep an existing target's mode) instead of `mkstemp`'s `0600`; every other caller keeps its current `0600`. Pin both with symlink-replacement and mode tests.

Carved out of cancelled ENH-3540 (Scope §4); see that file for the full research trail.

## Current Behavior

- **Artifact writes follow symlinks.** Plain `Path.write_text` at `cli/artifact/dashboard.py:494`, `cli/artifact/render.py:68`, `cli/artifact/policy_builder.py:160`, `cli/artifact/design_md.py:129`, and `cli/artifact/extract.py:238,300`. A symlink planted at the output path redirects the write to its target.
- **Two writes depend on the locale.** `policy_builder.py:160` (`out_path.write_text(html)`) and `design_md.py:129` (`out_path.write_text(document)`) pass no `encoding=`.
- **`atomic_write` makes files owner-only.** `file_utils.atomic_write` (`scripts/little_loops/file_utils.py:16`) creates its temp file with `tempfile.mkstemp` (mode `0600`) and `os.replace`s it into place with no chmod. `write_text` yields `0644` under a typical `022` umask, so routing artifact writes through `atomic_write` unchanged would silently make shared/served HTML owner-only.
- **Some existing `atomic_write` callers rely on the `0600`.** It is a `mkstemp` side effect, but callers that rewrite user config preserve content that may be secret: `adapters/claude_code.py:68` (`emit_mcp_config`) rewrites `.mcp.json` keeping other servers' entries, including their `env` values; `init/writers.py:1236` and `:1382` rewrite `.qwen/settings.json` / `.gemini/settings.json` preserving every non-managed key. Changing the default mode globally would turn a `0600` `.mcp.json` into `0644`. So the mode change must be opt-in.
- **Templatize `.rejected` writes follow leaf symlinks.** `rejected_dir = out_dir.with_name(out_dir.name + ".rejected")` (`templatize.py:1365`) is `rmtree`d first (`:1366-1367`); the writes into it (`roundtrip.diff` `:1463`, `lift-reversibility.diff` `:1487`, `lift-render-check.txt` `:1513`, and `discovery.json` / `regions.json` in `_write_rejected_discovery` `:1572,1576`) are plain `write_text`. Whether another user can plant a leaf symlink depends on how the directory was created:
  - Round-trip / lift paths (`:1462,1486,1512`) create it with `shutil.copytree(tmp_dir, rejected_dir)`, which copies the `mkdtemp` directory's `0700` mode — private.
  - Discovery-only failure paths (`:1411,1440,1456`) create it with `rejected_dir.mkdir(parents=True, exist_ok=True)` in `_write_rejected_discovery` (`:1571`), which is umask-derived — group-writable under umask `002`, so a group member can plant `discovery.json` / `regions.json` symlinks.

  Separately, a race that swaps `rejected_dir` *itself* for a symlink-to-dir between the `rmtree` and the `mkdir`/`copytree` is a parent-directory attack that leaf-level `atomic_write` cannot close (out of scope; see Scope Boundaries). The `tmp_dir` writes (`:1446-1450` etc.) target a fresh private `mkdtemp` and need no change.
- **Already symlink-safe:** `cli/artifact/policy_revision.py:153-158` and `cli/artifact/lockfile.py:108-110` (`mkstemp` + `os.replace`).

## Expected Behavior

- Every predictable-path artifact output write replaces, rather than follows, a symlink at the output path. The symlink's target is untouched and the output path ends up a regular file.
- Artifact files written via `atomic_write(..., shared_mode=True)` get mode `0o666 & ~umask` (e.g. `0644` under umask `022`) when newly created, and keep the existing file's mode when replacing a regular file (so a deliberately restricted artifact stays restricted).
- Every other `atomic_write` caller keeps its current `0600` mode; no existing config/secret-bearing file loosens.
- All artifact output is written as UTF-8 regardless of locale.

## Motivation

Artifact output directories are predictable (`artifacts.default_output_dir`, `--output`). A symlink planted at `policy-router-builder.html` or `dashboard.html` turns an artifact write into an arbitrary-file overwrite as the user running the command. The fix already exists (`atomic_write`); it just isn't used here, and using it as-is would regress artifact file modes to `0600`.

Hidden `.ll-<hex>.tmp` temp names left behind by a crash stay invisible to `.issues/` scanners (no `*.md` glob matches them) and still match the `*.tmp` ignore pattern (`git_operations.py:97`).

## Proposed Solution

1. **Rework `atomic_write`'s temp-file creation, with an opt-in shared mode.** New signature: `atomic_write(path, content, encoding="utf-8", *, shared_mode: bool = False)`.
   - Replace `tempfile.mkstemp` with `os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, create_mode)` on a short fixed-shape ASCII sibling name, `path.parent / f".ll-{secrets.token_hex(8)}.tmp"` (25 bytes regardless of `path.name`, so no `ENAMETOOLONG` for any name `write_text` accepts, including multibyte names). `O_EXCL` also refuses to open through a pre-planted (including dangling) symlink at the temp name.
   - `create_mode` is `0o600` by default (unchanged behavior for all existing callers) and `0o666` when `shared_mode=True`; the kernel applies the process umask, so no umask read is needed. This avoids the `os.umask(0); os.umask(old)` idiom, which mutates process-global state and is not thread-safe.
   - **Existing-target mode (shared_mode only):** before writing, `os.lstat(path)`; if it is a regular file (`stat.S_ISREG`), `os.fchmod` the temp fd to `S_IMODE(st.st_mode)`, so a file someone deliberately restricted keeps its mode. A symlink, a missing path, or any other type falls through to `0o666 & ~umask`. Artifacts were previously written by `write_text`, so no artifact is stuck at an accidental `0600`.
   - **Bound the retry loop** (e.g. 100 attempts, then raise `FileExistsError`) so a directory full of collisions cannot spin forever.
   - **Cleanup unlinks only a temp file this call created.** The `os.open` retry loop stays *outside* the cleanup `try`, exactly as `mkstemp` is today: a `FileExistsError` means the name belongs to someone else (another writer's temp file, or a planted symlink), and the cleanup path must never unlink it. Only after `os.open` succeeds does the `try`/`unlink`-on-exception block begin (covering `fchmod`, encoding/write failures, and `os.replace`).
   - Decided: opt-in, not global. Existing callers (`.mcp.json`, `.qwen`/`.gemini` `settings.json`) can carry secrets; the default stays `0600`.
   - Do not add `atomic_write_bytes`: no in-scope write site needs bytes. `atomic_write_json` is unchanged (keeps default mode).
2. **Route the artifact write sites** through `atomic_write(path, content, encoding="utf-8", shared_mode=True)`: `dashboard.py:494`, `render.py:68`, `policy_builder.py:160`, `design_md.py:129`, `extract.py:238,300`. Keep the `data.json` serialization byte-identical (`json.dumps(data, indent=2, ensure_ascii=False)`), so use `atomic_write`, not `atomic_write_json` (which formats differently). Text-mode `os.fdopen` applies the same newline handling as `write_text`, so the bytes do not change.
3. **Route the templatize `.rejected` writes** (`_write_rejected_discovery`'s `discovery.json` / `regions.json`, and `roundtrip.diff` / `lift-reversibility.diff` / `lift-render-check.txt`) through `atomic_write(..., shared_mode=True)`. This closes leaf-symlink redirection inside `rejected_dir` (reachable when it was created by `mkdir` under a group-writable umask). It does **not** close the rmtree→mkdir directory-swap race (out of scope).
4. Do **not** implement unlink-then-write: it has a TOCTOU window between unlink and open.

## Integration Map

### Files to Modify
- `scripts/little_loops/file_utils.py` — `atomic_write`: `os.open(..., O_EXCL, mode)` on a `.ll-<hex>.tmp` sibling instead of `mkstemp`; new keyword-only `shared_mode`.
- `scripts/little_loops/cli/artifact/dashboard.py` — `cmd_dashboard` output write (`:494`).
- `scripts/little_loops/cli/artifact/render.py` — `render_to_disk` output write (`:68`).
- `scripts/little_loops/cli/artifact/policy_builder.py` — `cmd_policy_builder` output write (`:160`).
- `scripts/little_loops/cli/artifact/design_md.py` — `cmd_design_md_export` output write (`:129`).
- `scripts/little_loops/cli/artifact/extract.py` — `cmd_extract` (`:238`) and `cmd_refresh` (`:300`) `data.json` writes.
- `scripts/little_loops/cli/artifact/templatize.py` — `.rejected` writes (`:1463,1487,1513` and `_write_rejected_discovery` `:1572,1576`).

### Dependent Files (Callers/Importers)
- 69 existing `atomic_write` / `atomic_write_json` call sites (52 + 17 by grep, 2026-09-24) keep the default `shared_mode=False` and therefore their current `0600` mode; the only behavioral change for them is the temp-file name (`tmpXXXX.tmp` → `.ll-<hex>.tmp`). Secret-bearing examples that must stay `0600`: `adapters/claude_code.py:68` (`.mcp.json`), `init/writers.py:1236,1382` (`.qwen`/`.gemini` `settings.json`). `transport.py:229` calls `chmod(0o600)` itself and is unaffected.
- Shares `dashboard.py`, `policy_builder.py`, and `extract.py` with ENH-3557 and ENH-3558; blocked on ENH-3558 so the three land sequentially without merge conflicts on the epic branch. ENH-3558 is now `done` (commit `3fffa5be5`); line numbers above were re-verified against post-ENH-3558 `main`.

### Similar Patterns
- `cli/artifact/policy_revision.py:153-158` and `cli/artifact/lockfile.py:108-110` — existing temp-plus-`os.replace` writers (out of scope; they keep `mkstemp`).

### Tests
- `scripts/tests/test_file_utils.py`:
  - Symlink at the target is replaced (target file unchanged, path now a regular file), with and without `shared_mode`.
  - Mode: default call → `0600` under umasks `022` and `077`; `shared_mode=True` new file → `0o666 & ~umask` under `022` and `077` (set with `os.umask` in try/finally); `shared_mode=True` over an existing `0600` regular file → stays `0600`; `shared_mode=True` over a symlink → `0o666 & ~umask` (symlink target's mode ignored).
  - Temp-name collision: patch `secrets.token_hex` to return a fixed value once, plant a file at that name, assert it survives and the write succeeds on retry.
  - Dangling-symlink collision: plant a dangling symlink at the first temp name; assert `O_EXCL` refuses it, the symlink survives (and its target is not created), and the write succeeds on retry.
  - Retry exhaustion: `token_hex` always returns the planted name; assert `FileExistsError` after the bound and the planted entry is untouched.
  - Cleanup on replace failure: patch `os.replace` to raise; assert no `.ll-*.tmp` entry remains.
  - Cleanup on a real write failure: content with a lone surrogate (`"\ud800"`) raises `UnicodeEncodeError`; assert it propagates, the target is unchanged, and no `.ll-*.tmp` remains.
  - Multibyte filename: a target whose name is ≥ 250 bytes of multibyte UTF-8 (valid on the filesystem) writes successfully.
- `scripts/tests/test_enh3559_artifact_symlink_safe_writes.py` (new):
  - Parametrized over `dashboard`, `render`, `policy-builder`, `design-md`, `extract`/`refresh` (host stubbed): plant a symlink at the output path pointing outside the output dir; assert the target is untouched, the output path is a regular file, and its mode is `0o666 & ~umask`.
  - `extract`/`refresh` `data.json` with non-ASCII content: bytes equal `json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")` exactly.
  - Templatize discovery-failure path: pre-create `rejected_dir` and plant `discovery.json` as a symlink to an outside file; assert the outside file is untouched and `discovery.json` is a regular file.
- `scripts/tests/test_adapters.py` — regression test: an existing `.mcp.json` chmod'd `0600` stays `0600` after `emit_mcp_config(apply=True)`.
- Existing: `test_enh3268_design_md_export.py`, `test_policy_builder_emit.py`, `test_feat3304_artifact_dashboard.py`, `test_feat3310_artifact_extract.py`, `test_ll_issues_atomic_write.py`, `test_artifact_templatize.py`.

### Documentation
- `atomic_write` docstring: states symlink replacement, the default `0600` mode, and `shared_mode` semantics (umask-derived for new files, existing regular-file mode preserved).
- CHANGELOG (release prep): artifact outputs are now written atomically and replace symlinks at the output path; `atomic_write` gains `shared_mode`.

### Configuration
- N/A

## Program Design

### Signatures
- `atomic_write(path: Path, content: str, encoding: str = "utf-8", *, shared_mode: bool = False) -> None` — existing, in `file_utils.py`. A symlink at `path` is replaced, never followed. Default: new file mode `0600` (unchanged). `shared_mode=True`: mode of an existing regular file at `path`, else `0o666 & ~umask`.

### Call Path
`cmd_policy_builder` -> `atomic_write`
`cmd_dashboard` -> `atomic_write`
`cmd_design_md_export` -> `atomic_write`
`cmd_extract` -> `atomic_write` (`data.json`)
`cmd_refresh` -> `atomic_write` (`data.json`)
`cmd_refresh` -> `render_to_disk` -> `atomic_write`
`cmd_templatize` -> `_write_rejected_discovery` -> `atomic_write`

(`render_policy_builder_html`, `build_dashboard_html`, and `extract_data` return content; they do not write.)

### Decision Rules
- Write-mode rule: artifact outputs pass `shared_mode=True` and end up with the existing regular file's mode, else `0o666 & ~umask`; all other `atomic_write` outputs keep `0600`.
- Symlink rule: output writes go through temp-plus-`os.replace`; never unlink-then-write, never `write_text` on a predictable output path.

## Implementation Steps

1. Change `atomic_write` to `os.open(..., O_WRONLY|O_CREAT|O_EXCL, mode)` on a `.ll-<hex>.tmp` sibling with bounded retry and the `shared_mode` keyword; add the `test_file_utils.py` tests and the `.mcp.json` mode regression test.
2. Route the six artifact output writes and the five `.rejected` writes through `atomic_write(..., shared_mode=True)`.
3. Add `test_enh3559_artifact_symlink_safe_writes.py`; run it with the existing artifact test files, then the full `python -m pytest scripts/tests/`, `mypy`, and `ruff check`.

## Impact

- **Priority**: P2 — needs a local attacker able to plant a symlink in the output directory; lower reach than the XSS children.
- **Effort**: Small — one helper change, six artifact writes plus five `.rejected` writes, two new test files plus additions to `test_file_utils.py`.
- **Risk**: Low — the mode change is opt-in and limited to artifact sites; existing callers change only their temp-file name.
- **Breaking Change**: None for existing callers. Artifact outputs keep their `write_text`-era umask-derived modes.

## Scope Boundaries

- **In scope**: the `atomic_write` temp-file rework and `shared_mode` keyword; routing the listed artifact output writes and the templatize `.rejected` writes through it; symlink, mode, collision, and cleanup tests.
- **Out of scope**: changing the default mode for existing `atomic_write` callers; `policy_revision.py` / `lockfile.py` writes (already symlink-safe); templatize `tmp_dir` writes (fresh private dir); an `atomic_write_bytes` variant; any escaping change (ENH-3557, ENH-3558, ENH-3560).
- **Out of scope, deliberately — symlinked parent directories.** Each site runs `output_dir.mkdir(exist_ok=True)` (or `out_path.parent.mkdir(...)`), which follows a symlinked output directory, then writes a fixed filename into its target. Users legitimately symlink output dirs, and the attacker gains only a fixed-name file (e.g. `dashboard.html`) in a chosen directory, not an arbitrary-path overwrite. The same reasoning covers the templatize `rejected_dir` rmtree→mkdir swap race.

## Acceptance Criteria

- [ ] `atomic_write` default mode is unchanged (`0600`); `shared_mode=True` creates new files with `0o666 & ~umask` (`0644` under `022`, `0600` under `077`) and preserves an existing regular file's mode; both modes replace a symlink at the target without touching its target; `test_file_utils.py` pins all of these.
- [ ] `atomic_write` does not read or set the process umask.
- [ ] Temp names are `.ll-<16 hex>.tmp` (fixed length, ASCII); a ≥ 250-byte multibyte target filename writes successfully.
- [ ] `atomic_write` never unlinks a path it did not create: a temp-name collision (regular file or dangling symlink) leaves the pre-existing entry untouched; retry exhaustion raises `FileExistsError`; a failed `os.replace` and a real encoding failure both leave no temp file behind; `test_file_utils.py` pins all of these.
- [ ] An existing `0600` `.mcp.json` stays `0600` after `emit_mcp_config(apply=True)`.
- [ ] Every artifact output write listed under Files to Modify uses `atomic_write(..., shared_mode=True)`; a parametrized test plants a symlink at each output path (dashboard, render, policy-builder, design-md, extract/refresh `data.json`) and asserts the target is untouched, the output path is a regular file, and its mode is `0o666 & ~umask`.
- [ ] `policy_builder.py` and `design_md.py` output is written as UTF-8 regardless of locale.
- [ ] `extract`/`refresh` `data.json` bytes (including non-ASCII content) equal `json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")`.
- [ ] The templatize `.rejected` writes use `atomic_write(..., shared_mode=True)`; a planted `discovery.json` symlink in a pre-existing `rejected_dir` is replaced, not followed; `test_artifact_templatize.py` passes.
- [ ] The full `python -m pytest scripts/tests/` passes; `mypy` and `ruff check` pass.

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

_Added by `/ll:confidence-check` on 2026-09-24_ (re-run after the opt-in `shared_mode` revision; write-site line numbers re-verified against `main`)

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 64/100 → MODERATE

### Outcome Risk Factors
- Wide blast radius: `atomic_write` has ~69 callers (`atomic_write`/`atomic_write_json`); the mode default is unchanged, but every one inherits the temp-file rework (`mkstemp` → `os.open(O_EXCL)`, `.ll-<hex>.tmp` name, bounded retry). Run the full suite right after step 1, before routing artifact sites.
- Broad enumeration across 7 modified files plus a local-logic rewrite of `atomic_write` (foreign-temp-safe cleanup, retry bound) — expect some iteration on the collision/cleanup tests.

## Session Log
- `/ll:confidence-check` - 2026-09-24T21:02:35 - `f7a68862-e3ea-425a-b71a-21cc3db44d65.jsonl`
- Manual review - 2026-09-24 - external review (Astra): global mode change reverted to opt-in `atomic_write(..., shared_mode=True)` because `.mcp.json` / `.qwen` / `.gemini` `settings.json` rewrites carry secrets (existing `0600` would become `0644`); shared mode preserves an existing regular file's mode; temp name changed from `.{name[:64]}.<hex>.tmp` (could exceed 255 bytes for multibyte names) to fixed `.ll-<hex>.tmp`; `.rejected` leaf-symlink exemption removed (`_write_rejected_discovery` mkdir is umask-derived, group-writable under `002`) and a symlink test added; tests added for retry exhaustion, dangling-symlink collision, real encoding failure, multibyte filename, non-ASCII `data.json` bytes, and `.mcp.json` mode regression; caller count unified at 69; write-site count corrected to six artifact + five `.rejected`
- `/ll:confidence-check` - 2026-09-24T20:29:53 - `7ccc0a63-5f30-4b64-83f4-7cfd1905bff1.jsonl`
- `/ll:verify-issues` - 2026-09-24T19:13:35 - `27bdfde5-d1ef-4e98-b8ff-2728ac43d651.jsonl`
- `/ll:scope-epic` - 2026-09-24T18:30:39 - `bd7b32d0-d305-4468-99d3-61a8a02d4caa.jsonl`
- Manual review - 2026-09-24 - post-ENH-3558 review: refreshed write-site line numbers; recast templatize `.rejected` routing as consistency-only (leaf `atomic_write` cannot close a dir-swap race); added cleanup-must-not-unlink-foreign-temp, bounded retry, and temp-name truncation to §1 with tests + AC; corrected Program Design call paths; scoped out symlinked parent dirs explicitly
- Manual review - 2026-09-24 - ported ENH-3540 Scope §4 and ACs into this child; replaced the umask-read idiom with `os.open(..., 0o666)`; dropped `atomic_write_bytes` (no caller); added `design_md.py` encoding fix and `blocked_by: ENH-3558` for sequencing
