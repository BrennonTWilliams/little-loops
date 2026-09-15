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

`_incumbent_content_hash()` (`scripts/little_loops/cli/harness.py:1707`) hashes the **stripped** stdout of `git show HEAD:<path>` (it goes through `_git_output()`, `:67`, which returns `proc.stdout.strip()`), while every baseline row written by `--measure-baseline` records `target_content_hash` from `_hash_file()` (`:129`), which hashes the file's raw bytes. Every skill file ends in a newline, so on a real checkout the two hashes never agree for the same content.

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

- `_incumbent_content_hash()` hashes the exact blob bytes (`git cat-file blob HEAD:<path>` captured with `text=False` and no strip), so it equals `_hash_file()` of an unmodified working-tree file — including an empty tracked file, which today resolves to "cannot resolve incumbent" because `_git_output` returns `None` for empty output.
- Skill `--compare-baseline` finds rows written by `--measure-baseline` on the unmutated subject, and the unmutated-subject refusal fires when the file matches HEAD.
- One test builds a real temporary git repo (commit a file ending in `\n`), and asserts `_incumbent_content_hash(path) == _hash_file(path)` without patching `_git_output`.

## Impact

- **Priority**: P2 — the HEAD-resolution half of ENH-3435 is silently non-functional in every real project; the `--baseline-of` path still works, which is why it went unnoticed.
- Blocks ENH-3465: its pin stores `_incumbent_content_hash()` (AC1) and looks the frozen arm up by it (AC5); with the mismatch the frozen arm fails closed forever.

## Program Design

### Types

- No new types. `_hash_bytes(data: bytes) -> str` (`scripts/little_loops/cli/harness.py:124`) stays the single hash function for both sides.

### Signatures

- New `_git_blob(rel: str, *, ref: str = "HEAD") -> bytes | None` (`cli/harness.py`, next to `_git_output`) — runs `git cat-file blob <ref>:<rel>` with `capture_output=True`, `text=False`, timeout 5, and returns `proc.stdout` unmodified on exit 0, else `None`. Same bare-`except Exception` best-effort contract as `_git_output()` (`:67-90`).
  - **Plumbing, not porcelain**: `git show <ref>:<path>` honors `.gitattributes` textconv filters on blobs and prints a tree listing for a directory path; `cat-file blob` emits raw bytes or exits non-zero, nothing else.
  - **Empty blob is a valid result**: return `b""` on exit 0 (verified: `git cat-file blob HEAD:<empty-file>` emits `b''`, rc 0). Do **not** copy `_git_output`'s `proc.stdout.strip() or None` idiom — `b"" or None` would collapse an empty tracked file back into the "untracked" refusal.
  - The `ref` parameter is a cheap generalization for ENH-3465 (D8 pins `pinned_head_sha` and the `--measure-pin` follow-up needs `git cat-file blob <pinned_head_sha>:<path>`); this issue only ever passes the default.
- `_incumbent_content_hash(target_path: Path | None) -> str | None` (`:1707`) — unchanged signature; body calls `_git_blob(rel)` instead of `_git_output("show", f"HEAD:{rel}")` and returns `_hash_bytes(blob)` — for `blob == b""` that is `_hash_bytes(b"")`, equal to `_hash_file()` of an empty file.

### Call Path

`cmd_skill` compare branch (`:2272`) -> `_incumbent_content_hash(skill_path)` -> `_git_output("rev-parse", "--show-toplevel")` (unchanged, stripped SHA/path is correct there) -> `_git_blob(rel)` -> `_hash_bytes(raw)`; the resulting hash now equals what `_record()` stored via `_hash_file(skill_path)` (`:2205`) for the same content, so `_compare_baseline_refusal()` (`:1837`) and the unmutated check (`:2281`) behave as ENH-3435 specified.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- Confirmed via code graph + repo-wide search: `_incumbent_content_hash` has exactly one caller in the whole codebase, `cmd_skill` (`harness.py:2298`) — no other file calls it, no dynamic/reflective dispatch references it.
- `_git_output`'s other two callers that read git state near this code, `_record_harness_event::_write` (`harness.py:287`) and `pytest_history_plugin.py::LLHistoryPlugin._record` (`:141-142`), both use `rev-parse` verbs only — confirmed unaffected by rerouting the `show HEAD:` blob read to `_git_blob`.
- `BlobReader` (`scripts/little_loops/cli/verify_evidence.py`) and `read_blob_at_ref` (`scripts/tests/spike/git_show_blob_at_ref/blob_reader.py`, FEAT-2652 spike) are same-named-in-concept raw-git-blob readers but structurally disconnected — neither imports from nor is imported by `harness.py`; no coupling.

### Tests

- New `TestIncumbentContentHashRealGit` in `scripts/tests/test_cli_harness.py`: `git init` a tmp repo, commit a file whose content ends in `\n`, one with trailing whitespace on the last line, **and one that is empty**, `chdir` into it, assert `_incumbent_content_hash(path) == _hash_file(path)` for all three with **no** `_git_output`/`_git_blob` patch; assert `None` for an untracked file and for a committed directory path (`cat-file blob` on a tree exits non-zero).
- Existing `TestBaselineCompare` tests keep their `_git_output` side-effect helpers (`:2759`, `:3091`); the helper that answers `show` must be updated to patch `_git_blob` (returning bytes) instead, or the compare branch would no longer see the mocked incumbent.

_Wiring pass added by `/ll:wire-issue`:_
- `_make_git_stub()` (`scripts/tests/test_cli_harness.py:2755-2773`) is a single closure answering all four `_git_output` verbs; it must be split — `_git_output`'s stub keeps only the three `rev-parse` branches, and a new bytes-returning stub (e.g. `head_content.encode("utf-8")`) is patched onto `_git_blob` for the `show HEAD:` branch.
- Correction to the six-class claim in the Codebase Research Findings below: only `TestBaselineCompare` (all 7 methods, `:3082-3238`) and `TestBaselineStoreBidirectional` (`test_measure_after_commit_reuses_candidate_rows_across_head`, `:3374`) are fully affected by rerouting `show HEAD:` to `_git_blob`; `TestBaselineIncumbentResolution` is affected in only 1 of 3 methods (`test_dirty_tree_compare_reads_only_head_incumbent`, `:3244`); `TestBaselineDegrade`, `TestBaselineMeasure`, and `TestBaselineFlaglessUnchanged` call `_git_output` with a bare `return_value="sha0"` or exercise only `measure_baseline` (never `compare_baseline`), so none call `_incumbent_content_hash` and none are affected.
- New test gap (zero existing coverage): a `cmd_skill`-level test asserting the "cannot resolve incumbent content ... untracked file or no git repo" refusal (`harness.py:2301-2303`) actually fires — no test in the suite currently asserts on this message.
- Optional new test: a tracked file with non-UTF-8 content now hashes successfully post-fix (per the Non-UTF-8 blob edge case note below) where it silently refused before — currently uncovered either way.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-15 — based on codebase analysis:_

- Call-graph confirmation (codebase-analyzer, code-graph query): the other 6 `_git_output()` call sites — `cmd_cmd` (`harness.py:2354`), `cmd_mcp` (`harness.py:2482`), `cmd_prompt` (`harness.py:2617`), `cmd_dsl` (`harness.py:2776`, `:2805`), and `_incumbent_content_hash`'s own `rev-parse --show-toplevel` (`harness.py:1719`) — are all single-line rev-parse/branch reads that depend on the strip; none reads `git show` blob content. This confirms the design choice above (add a separate `_git_blob`, leave `_git_output` untouched) is consistent with every other consumer's contract — none would tolerate an unstripped/bytes change.
- Full list of test classes/fixtures in `scripts/tests/test_cli_harness.py` that patch `little_loops.cli.harness._git_output` via the module-level `_make_git_stub()` helper (`:2755-2773`, whose closure answers a `show HEAD:...` call with `head_content`): `TestBaselineCompare` (`_stub_git` autouse fixture, `:3092`), `TestBaselineIncumbentResolution` (`:3285`, `:3331`, `:3362`), `TestBaselineStoreBidirectional` (`:3408`, `:3432`), `TestBaselineDegrade` (`_stub_git`, `:3485`), `TestBaselineMeasure` (`_stub_git`, `:2929`), `TestBaselineFlaglessUnchanged` (`_stub_git`, `:3611`) — six classes route through the show-branch of `_make_git_stub`, versus the three (`TestBaselineCompare`/`TestBaselineStoreBidirectional`/`TestBaselineDegrade`) named in the Tests note above. `TestSampleLoopIntegration` (`:1031`) and `TestRetryOfGate` (`:2001`, `:2120`, `:2169`) also patch `_git_output` directly but only for `rev-parse`-style calls, not `show HEAD:` — unaffected by rerouting the blob read to `_git_blob`.
- Existing precedent for a real-temp-git-repo test (supports the `TestIncumbentContentHashRealGit` plan above): `_init_git_repo()` already exists in this same file (`test_cli_harness.py:3655-3661`), used by `TestExpectNoGitChanges`; an independent equivalent exists in `scripts/tests/test_git_operations.py:242-249,332-341`. Neither is a shared `conftest.py` fixture (none exists in `scripts/tests/conftest.py`) — each is file-local, so the new test's local repo setup follows established per-file convention rather than introducing a new one.
- Capability search for an existing raw-bytes git-blob reader to reuse instead of adding `_git_blob` (codebase-pattern-finder): `BlobReader` (`scripts/little_loops/cli/verify_evidence.py:799-876`) already returns raw `bytes | None` from git, but via a long-lived `git cat-file --batch` process addressed by blob OID (built for high-volume evidence-quote scanning, ~0.048ms/blob), and it catches the narrower `(OSError, subprocess.SubprocessError)`/`(OSError, ValueError)` rather than this file's bare `except Exception` — not a drop-in fit for a single per-invocation `git show HEAD:<path>` read. A second precedent, `read_blob_at_ref()` (`scripts/tests/spike/git_show_blob_at_ref/blob_reader.py`, FEAT-2652), matches the one-shot `git show <ref>:<path>` shape but returns `str` (not `bytes`) and was never promoted out of `scripts/tests/spike/`.
- Non-UTF-8 blob edge case (codebase-analyzer): today, `_git_output`'s `text=True` decode of a non-UTF-8 blob raises `UnicodeDecodeError` inside its own `try`, caught by the bare `except Exception`, so `_incumbent_content_hash` returns `None` and `cmd_skill` shows the same "cannot resolve incumbent content ... untracked file or no git repo" refusal as a genuinely untracked file (`harness.py:2299-2306`) — the real cause (non-UTF-8 content) is indistinguishable from "untracked" in that message today. The proposed `_git_blob(text=False)` reads raw bytes with no decode step, so it would no longer hit this failure mode — a non-UTF-8 tracked file would hash successfully post-fix where it silently refuses today. Worth a one-line note if this behavior change is user-visible; not a blocker for the fix itself.

## Implementation Notes

- Keep `_git_output()` as-is (its `.strip()` is relied on for `rev-parse` SHAs); add the bytes-returning `_git_blob()` for the blob read.
- No change to the store or to `baseline_for()`.
- Known limitation, out of scope: if a consuming project sets `core.autocrlf` or clean/smudge filters on the target path, the HEAD blob and the working-tree `_hash_file()` still differ for unmodified content. Neither is configured in this repo (no `.gitattributes`, `core.autocrlf` unset); note it in the `_git_blob` docstring, do not try to compensate.
- Update `docs/reference/CLI.md` `--compare-baseline` row only if the wording about HEAD resolution changes; add a `CHANGELOG.md` line in the current release section.

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `CHANGELOG.md` — append a `- **BUG-3479**: ...` bullet to the existing `### Fixed` subsection under the current `## [1.164.0] - 2026-09-13` section (matches the format of the existing `- **BUG-3452**: ...` bullet); no new version section is needed.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- Confirmed no wording change is required anywhere: `docs/reference/CLI.md:238` and the `--compare-baseline` help text (`harness.py:629-637`) both already say "resolves the incumbent from the HEAD blob," not "stripped stdout" — accurate before and after the fix. `docs/reference/EVENT-SCHEMA.md:1795`, `docs/ARCHITECTURE.md:683`, `docs/guides/HISTORY_SESSION_GUIDE.md:110`, and `docs/guides/EVALUATION_GUIDE.md:371-433` describe the match key abstractly with no strip-vs-raw-bytes mechanics. This resolves the Implementation Notes conditional above ("update ... only if the wording ... changes" — it doesn't).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Split `_make_git_stub()` (`scripts/tests/test_cli_harness.py:2755-2773`) into a rev-parse-only stub for `_git_output` and a new bytes-returning stub for `_git_blob`; repoint the patches in `TestBaselineCompare` (`:3086-3095`), `TestBaselineIncumbentResolution::test_dirty_tree_compare_reads_only_head_incumbent` (`:3285`), and `TestBaselineStoreBidirectional` (`:3383-3413`) at the new target.
- Add a `cmd_skill`-level test asserting the "cannot resolve incumbent content ... untracked file or no git repo" refusal fires (no existing coverage).
- Append a `- **BUG-3479**: ...` bullet to `CHANGELOG.md`'s existing `### Fixed` subsection under `## [1.164.0] - 2026-09-13`.

## Status

**Open** | Created: 2026-09-15 | Priority: P2


## Session Log
- `/ll:wire-issue` - 2026-09-15T15:08:04 - `eb318cee-ddb1-40b6-a7a9-f7f1b403ae44.jsonl`
- `/ll:refine-issue` - 2026-09-15T14:58:55 - `a770d268-1a31-4c89-8452-2802b7501458.jsonl`
- `/ll:format-issue` - 2026-09-15T14:38:24 - `6634e3cc-f741-4813-a1cf-617029cd83fa.jsonl`
