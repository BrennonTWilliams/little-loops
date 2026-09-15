---
id: BUG-3479
type: BUG
title: _incumbent_content_hash strips the HEAD blob so it never matches _hash_file
  rows; skill --compare-baseline HEAD resolution is dead
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-15'
captured_at: '2026-09-15T14:19:48Z'
labels:
- harness
- baseline
- evaluation
---

# BUG-3479: _incumbent_content_hash strips the HEAD blob so it never matches _hash_file rows; skill --compare-baseline HEAD resolution is dead

## Summary

`_incumbent_content_hash()` (`scripts/little_loops/cli/harness.py:1682`) hashes the **stripped** stdout of `git show HEAD:<path>` (it goes through `_git_output()`, `:67`, which returns `proc.stdout.strip()`), while every baseline row written by `--measure-baseline` records `target_content_hash` from `_hash_file()` (`:129`), which hashes the file's raw bytes. Every skill file ends in a newline, so on a real checkout the two hashes never agree for the same content.

Verified on a clean, unmodified `commands/check-code.md` at HEAD:

```
git show raw bytes / file bytes : 0fb68dcd8ce256ae
_incumbent_content_hash (strip) : d4cbd633dd215092
```

## Current Behavior

- `ll-harness skill <target> --compare-baseline` (no `--baseline-of`) resolves the incumbent via `_incumbent_content_hash()` and looks rows up by that hash (`cmd_skill`, `:2272-2287`); the rows `--measure-baseline` wrote carry the `_hash_file()` hash, so `_compare_baseline_refusal()` (`:1837`) always reports "no measured baseline" on a real repo. The ENH-3435 bidirectional store is unreachable on the HEAD-resolution path.
- The "subject is unmutated; nothing to compare" refusal (`:2281`) compares the stripped-HEAD hash to the working-tree `_hash_file()` hash, so it never fires for an unmodified file.
- Every test in `TestBaselineCompare` / `TestBaselineStoreBidirectional` / `TestBaselineDegrade` patches `little_loops.cli.harness._git_output` with a fixed return value, so the suite never exercises the strip against real blob bytes.

## Steps to Reproduce

1. In a clean checkout of this repo (`git status --short commands/check-code.md` prints nothing), run:
   ```bash
   python - <<'EOF'
   from little_loops.cli.harness import _incumbent_content_hash, _hash_file, _resolve_skill_target_path
   p = _resolve_skill_target_path("check-code")
   print(_incumbent_content_hash(p), _hash_file(p))
   EOF
   ```
2. Observe two different 16-char hashes (`d4cbd633dd215092` vs `0fb68dcd8ce256ae` at the HEAD this was filed against). Hashing `git show HEAD:commands/check-code.md` as raw bytes reproduces the second value; stripping it first reproduces the first.
3. Run `ll-harness skill check-code --samples 2 --measure-baseline` (records rows under the `_hash_file()` hash), then mutate the file and run `ll-harness skill check-code --samples 2 --compare-baseline`: it refuses with "no measured baseline … incumbent content d4cbd633dd215092" even though the baseline rows exist.

## Expected Behavior

- `_incumbent_content_hash()` hashes the exact blob bytes (`git show HEAD:<path>` captured with `text=False` and no strip, or `git cat-file blob HEAD:<path>`), so it equals `_hash_file()` of an unmodified working-tree file.
- Skill `--compare-baseline` finds rows written by `--measure-baseline` on the unmutated subject, and the unmutated-subject refusal fires when the file matches HEAD.
- One test builds a real temporary git repo (commit a file ending in `\n`), and asserts `_incumbent_content_hash(path) == _hash_file(path)` without patching `_git_output`.

## Impact

- **Priority**: P2 — the HEAD-resolution half of ENH-3435 is silently non-functional in every real project; the `--baseline-of` path still works, which is why it went unnoticed.
- Blocks ENH-3465: its pin stores `_incumbent_content_hash()` (AC1) and looks the frozen arm up by it (AC5); with the mismatch the frozen arm fails closed forever.

## Program Design

### Types

- No new types. `_hash_bytes(data: bytes) -> str` (`scripts/little_loops/cli/harness.py:124`) stays the single hash function for both sides.

### Signatures

- New `_git_blob(rel: str) -> bytes | None` (`cli/harness.py`, next to `_git_output`) — runs `git show HEAD:<rel>` with `capture_output=True`, `text=False`, timeout 5, and returns `proc.stdout` unmodified on exit 0, else `None`. Same bare-`except Exception` best-effort contract as `_git_output()` (`:67-90`).
- `_incumbent_content_hash(target_path: Path | None) -> str | None` (`:1682`) — unchanged signature; body calls `_git_blob(rel)` instead of `_git_output("show", f"HEAD:{rel}")` and returns `_hash_bytes(blob)`.

### Call Path

`cmd_skill` compare branch (`:2272`) -> `_incumbent_content_hash(skill_path)` -> `_git_output("rev-parse", "--show-toplevel")` (unchanged, stripped SHA/path is correct there) -> `_git_blob(rel)` -> `_hash_bytes(raw)`; the resulting hash now equals what `_record()` stored via `_hash_file(skill_path)` (`:2205`) for the same content, so `_compare_baseline_refusal()` (`:1837`) and the unmutated check (`:2281`) behave as ENH-3435 specified.

### Tests

- New `TestIncumbentContentHashRealGit` in `scripts/tests/test_cli_harness.py`: `git init` a tmp repo, commit a file whose content ends in `\n` (and one with trailing whitespace on the last line), `chdir` into it, assert `_incumbent_content_hash(path) == _hash_file(path)` with **no** `_git_output` patch; assert `None` for an untracked file.
- Existing `TestBaselineCompare` tests keep their `_git_output` side-effect helpers (`:2759`, `:3091`); the helper that answers `show` must be updated to patch `_git_blob` (returning bytes) instead, or the compare branch would no longer see the mocked incumbent.

## Implementation Notes

- Keep `_git_output()` as-is (its `.strip()` is relied on for `rev-parse` SHAs); add the bytes-returning `_git_blob()` for the blob read.
- No change to the store or to `baseline_for()`.
- Update `docs/reference/CLI.md` `--compare-baseline` row only if the wording about HEAD resolution changes; add a `CHANGELOG.md` line in the current release section.

## Status

**Open** | Created: 2026-09-15 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-09-15T14:38:24 - `6634e3cc-f741-4813-a1cf-617029cd83fa.jsonl`
