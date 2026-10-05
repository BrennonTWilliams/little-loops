---
id: ENH-3728
type: ENH
title: Degrade verdicts for history readers under a remote backend
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T01:33:28Z'
parent: EPIC-3693
blocked_by:
- ENH-3677
- ENH-3657
- ENH-3729
relates_to:
- ENH-3729
- ENH-3700
- ENH-3658
---

# ENH-3728: Degrade verdicts for history readers under a remote backend

## Summary

Give the reader sites that have a safe local fallback an explicit **degrade** verdict under `history.backend.provider: libsql` (FEAT-3535): `history summary`, `decisions generate`, `ll-messages` / `extract_conversation_turns` with `reader=auto`, the `improve-claude-md` CT-0 snippet, and the packaged `sft-corpus` `--reader auto` / `enrich` passthrough. Remote SFT passthrough is allowed only with all DB-dependent quality flags disabled; otherwise enrichment refuses through ENH-3729's failure route. These sites do not depend on the central guard or importer audit. ENH-3729 must land first so the intentional quality refusal actually terminates the loop.

## Current Behavior

- `decisions.py:generate_from_completed`, `user_messages.py:extract_conversation_turns` (reader `auto` reaches `resolve_history_db`), and `skills/improve-claude-md` CT-0 (`python3 -c` calling bare `resolve_history_db()`, SKILL.md ~L206-209, ending in `2>/dev/null`) fail or emit empty stdout that reads as "no candidates".
- `scripts/little_loops/loops/sft-corpus.yaml` `stage` (`--reader db`, masked by `2>/dev/null || touch "$OUTPUT"`) and `enrich` (`lookup_session_metadata` is `.exists()`-gated, `history_reader/sessions.py:358`) turn a refusal into an empty corpus routed onward as success.
- `ll-history summary` has a file-scan fallback (`scan_completed_issues`) that it does not reach under remote.

## Expected Behavior

| Site | Under remote | Notes |
|---|---|---|
| `history summary` | **degrade** to the file scan, exit 0 | one `note:` line; `source=files`, date filters retained, loop metrics unavailable (`None`), all DB probes bypassed |
| `decisions.generate_from_completed` | **degrade** to the issues-directory scan | local path stays DB-first; CLI caller owns the note |
| `ll-messages --sft-format` / `extract_conversation_turns` | `reader=auto` -> **degrade** to JSONL | catch `HistoryUnsupported` before the JSONL fallback; explicit `--reader db` refusal is ENH-3657 |
| CT-0 in `skills/improve-claude-md` | **degrade**: explicit skipped verdict with a one-line note | switch to `resolve_history_store`, branch on `RemoteTarget`, remove the snippet's `2>/dev/null`, check the skipped verdict before the empty-feedback branch |
| `sft-corpus.yaml` `stage` | `--reader auto` (degrade to JSONL) | the failure-routing and `|| touch` removal belong to the SFT-routing issue; this issue only changes the reader flag |
| `sft-corpus.yaml` `enrich` | **degrade**: one note and un-enriched passthrough with all DB-quality flags disabled; otherwise **refuse** | classify once before lookup; preserve records/metadata; no invented zero/false quality evidence |

### Notice channel

Degrade notice = one fixed `note:` line on stderr at the human CLI/skill/state boundary, before bypassing the DB, only under a remote target. Libraries (`generate_from_completed`, `extract_conversation_turns`) select their fallback without printing; their CLI callers own the note. Emit it directly on stderr rather than through a verbosity-gated logger. Automatic/library callers keep their existing output contract. CT-0 additionally returns parseable JSON with `verdict: skipped` and a fixed reason, then branches before "no candidates"; remove its `2>/dev/null` so the note survives. Stage delegates its one note to the `ll-messages` CLI and does not add a second one; enrich owns its note or refusal. No endpoint/token/SQL or exception text in either channel.

### Complete summary fallback and selected messages root

After selecting a remote target, do not retain a usable local `db_path`: bypass `issue_events_ever_recorded`, `scan_completed_issues_from_db` and the unconditional `count_loop_runs_in_window` call. Set loop metrics to `(None, None)` (unavailable, never zero), retain the existing file-scan date filtering and `source=files`, and preserve the text/JSON renderer's unavailable representation. A stale local shadow file must not influence any metric. The local branch still queries loop metrics even when issue history itself falls back to files.

Messages auto mode uses the owning `root` parameter (default `None`) introduced by ENH-3657, threaded from `args.cwd or Path.cwd()`. The fallback is only the **existing Claude-shaped JSONL parser**: Codex/Kimi handles do not gain conversation windows in this slice. Document this limitation and exercise a supported JSONL handle with actual windows; do not claim that successful empty output proves multi-host SFT support. Direct library callers that omit `root` retain existing resolution.

**Preserve local selection through direct schema callers (review #4).** Root-aware resolution alone does not protect local summary/decisions reads: `issue_history.parsing.issue_events_ever_recorded`, `scan_completed_issues_from_db` and `count_loop_runs_in_window` all call `schema.connect(db_path)`, which re-resolves a plain default-shaped Path against ambient cwd. A local owning DB from a foreign remote cwd was observed to contact the remote endpoint and raise `HistoryDbUnavailable`. ENH-3657's typed-local reader setup fix cannot cover these direct schema callers.

Add optional keyword-only `db_target: LocalTarget | None = None` to those three parsing helpers, retaining their Path argument for filesystem checks; when supplied, call `schema.connect(db_target)`. In this slice's local summary and `generate_from_completed` branches, carry the already-selected local target through those helpers. Existing callers that omit the argument keep the existing resolver behavior; do not turn every unclassified Path into an explicit override inside the helpers. Remote branches still bypass all three helpers. This issue owns the direct-schema propagation; it does not wait for ENH-3700 or broaden the writer/hook resolution rules.

### Remote SFT enrichment and quality contract

In the packaged enrich action, resolve the target once before any filesystem probe or `lookup_session_metadata` call. Under remote, with `require_issue_outcome=false`, `exclude_user_corrections=false`, `min_tool_invocations=0` and `require_file_modifications=false`, copy parsed records through without adding/replacing metadata, preserving any existing metadata, emit one fixed stderr note, and publish through ENH-3729's atomic path. Local/environ-override enrichment keeps its current metadata shape.

If **any** of those four flags is enabled, remote enrichment exits non-zero with a fixed reason that quality metadata is unavailable and suggests `LL_HISTORY_DB` for a local override. Detect this before opening the output/temp or looking up a record, even for an empty corpus. Existing input metadata does not waive this backend refusal: per-record provenance/filter redesign is outside scope. In particular, absent `has_corrections` must not masquerade as verified `False` and admit unchecked examples with `exclude_user_corrections=true`. ENH-3729 supplies the terminal failure route and atomic publication; no filter/publish/success sentinel is reached. Do not change the existing first-record-only filter implementation here.

Pass the four context flags into the Python action through the existing quoted `:shell` environment pattern and parse booleans/numeric thresholds explicitly, matching the filter states. A string `false` must not become truthy through `bool(string)`. Preserve existing FSM interpolation/escaping conventions.

### Docs wording

Degrade rows are added to the single support table in `docs/reference/CONFIGURATION.md` (ENH-3657 creates it; merge rows, do not replace siblings'). Refused rows elsewhere say "not supported with a remote backend" and promise no follow-up.

## Motivation

Local-only fallbacks already exist for these sites; routing remote users to them is low-risk and keeps `ll-messages`, `decisions` and the SFT pipeline usable instead of silently empty or tracebacking.

## Proposed Solution

1. Catch `HistoryUnsupported` (never bare `HistoryError`) in the library fallback paths and CLI callers; emit the single `note:` at the CLI/skill/state boundary under a remote target only. In `extract_conversation_turns`, only `reader=auto` catches and falls through with empty DB windows; explicit `reader=db` still propagates to ENH-3657's refusal boundary.
2. CT-0: `skills/improve-claude-md/SKILL.md` (344 lines, cap 500; keep `[ -f .ll/decisions.yaml ]` and `decisions list --type rule 2>/dev/null | grep`, pinned by `test_wiring_skills_and_commands.py`), then `ll-adapt --host <gemini|kimi-code|qwen> --apply` and `test_improve_claude_md_skill.py`.
3. `sft-corpus.yaml`: `--reader auto` on `stage`, one-time remote classification and the exact passthrough/quality-refusal contract on `enrich`, preserving ENH-3729's failure routes and atomic output path.
4. Docs, support-table rows, `docs/reference/CLI.md`, `docs/reference/API.md` (`extract_conversation_turns` relationship paragraph), `docs/guides/HISTORY_SESSION_GUIDE.md`; keep `test_wiring_reference_docs.py` and `test_docs_audience_gate.py` green; cite `little_loops.<module>` in prose, no `scripts/tests/` paths.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/history.py` (`summary`), `scripts/little_loops/decisions.py` / `scripts/little_loops/cli/issues/decisions.py`, `user_messages.py` / `cli/messages.py`, `skills/improve-claude-md/SKILL.md` (+ mirrors), `scripts/little_loops/loops/sft-corpus.yaml`.
- `scripts/little_loops/issue_history/parsing.py` — selected-local target parameter (default `None`) on the three summary/decisions DB helpers; preserve existing filesystem Paths and legacy caller behavior. ENH-3657 owns the reader-side setup/conversation prerequisite; no ENH-3700 edge is added.
- Anchors drift: re-grep every `resolve_history_db(` site (`scripts/little_loops/decisions.py:596`, `user_messages.py` ~`:1227`).

### Tests
- Degrade tests keep stdout unchanged with exactly one `note:` line and no token; default-`auto` JSONL fallback; `ll-messages` default-`auto` regression (`extract_conversation_turns` currently reaches the remote pre-resolve); `"No history.db found"` invariant (`test_bug_3216_telemetry_digest_invocations.py`); `sft-corpus` `stage` reader flag (`test_loops_sft_corpus.py`).
- Use the hoisted `remote` fixture (ENH-3677; `delenv("LL_HISTORY_DB")` to override the autouse `conftest._isolate_history_db`).
- Summary tests execute `main_history` with text/JSON, date filters, a populated stale shadow DB and a foreign cwd; all three DB helpers are asserted uncalled, loop metrics are unavailable, and only file issues contribute. Preserve local DB-first, legitimate empty-window and file-fallback loop metrics.
- Local summary/decisions tests select a local owning root from a remote foreign cwd and observe seeded issue/loop data through all reached helpers, with zero remote reader requests and no fallback masking. Include `LL_HISTORY_DB` pointing to a default-shaped local file; match the existing explicit/env resolution precedence and keep legacy parsing callers unchanged.
- Execute the packaged stage/enrich actions through the real FSM after ENH-3729: remote/no-quality-flags preserves records and pre-existing metadata with one note and zero metadata lookups; each of the four enabled flags fails before output publication (also with empty input), retaining the previous good output and never reaching filters/sentinel. A local `LL_HISTORY_DB` override enriches actual session data. No copied enrich script alone is sufficient evidence.
- Exercise public messages `--cwd` in both foreign-cwd directions and direct auto-library fallback without a notice; supported Claude-shaped JSONL produces actual windows and Codex/Kimi remain at their documented limitation.
- Keep green: `test_cli_decisions.py`/`test_decisions.py` DB-first local branch, `test_cli_messages.py`, `test_adapt_skills_for_codex.py`, `test_verify_skill_prose.py`, `test_enh494_skill_companions.py`.

## Program Design

### Types
- `HistoryError(Exception)` <- `HistoryUnsupported(HistoryError)` <- `HistoryBackendNotLocal(HistoryUnsupported)` in `little_loops.session_store.backend`.

### Signatures
- `generate_from_completed(config: BRConfig) -> int` — degrade site in `little_loops.decisions`; local branch stays DB-first.
- `extract_conversation_turns(..., reader="auto")` — catches `HistoryUnsupported` before the JSONL fallback.
- `issue_events_ever_recorded(db_path: Path, *, db_target: LocalTarget | None = None) -> bool`, `scan_completed_issues_from_db(db_path: Path, since=None, until=None, *, db_target: LocalTarget | None = None) -> list[CompletedIssue]`, `count_loop_runs_in_window(db_path: Path, since, until, *, db_target: LocalTarget | None = None) -> tuple[int | None, int | None]` — optional local provenance for these callers; filesystem checks keep the Path, SQL receives the supplied target.

### Call Path
- `cmd_decisions` -> `generate_from_completed` -> `scan_completed_issues` (degrade, remote only).
- `main_messages` -> `extract_conversation_turns(reader="auto")` -> JSONL path (degrade).
- `main_history summary` -> `scan_completed_issues` (degrade, remote only).

### Decision Rules
- Catch class is `HistoryUnsupported`; one CLI `note:` line; `"No history.db found"` stays verbatim for local-missing; local behavior unchanged.

## Implementation Steps

Prerequisites: ENH-3677 (hoisted `remote` fixture), ENH-3657 (boundary helper and selected-root threading) and ENH-3729 (SFT failure routes and atomic publish) landed. The ENH-3729 edge is functional: this issue introduces an intentional remote quality refusal that must terminate rather than continue through `next`.

1. Library fallbacks + CLI notes for `history summary`, `decisions generate`, `reader=auto`; preserve the already-selected local target through the direct-schema parsing helpers and consume ENH-3657's conversation/setup fix.
2. CT-0 skill change, mirrors.
3. `sft-corpus.yaml` reader flag and enrich passthrough.
4. Docs/support-table rows; remove the CT-0 allowlist entry from ENH-3658's hazard gate if it exists.
5. Tests per the Integration Map; run `python -m pytest scripts/tests/`, `ruff check scripts/`, `python -m mypy scripts/little_loops/` (scope `ruff format` to changed files).

## Impact

- **Priority**: P3 - opt-in remote-backend users only.
- **Effort**: Medium - four library/CLI sites, one skill + mirrors, one loop YAML, docs.
- **Risk**: Medium - selected-local provenance crosses direct schema helpers, summary metrics must remain unavailable under remote, and SFT quality refusal must preserve the predecessor's failure route/atomic publication. These require actual data and packaged-state tests beyond catching `HistoryUnsupported`.
- **Breaking Change**: No.

## Scope Boundaries

- **In scope**: the six sites above, the CLI-boundary notes, CT-0 skill change + `ll-adapt` mirrors, support-table rows, removing the CT-0 entry from ENH-3658's hazard-gate allowlist if present.
- **Out of scope**: the boundary helper and refuse sites (ENH-3657); the central guard, catch widening and `ll-harness` serve (ENH-3700); SFT failure routing / atomic enrichment publish (ENH-3729); SFT filter redesign or new host transcript parsers; hand-built paths (ENH-3658); `context-monitor.sh` (ENH-3680, cancelled); remote read serving (ENH-3668/3684/3685, deferred).

## Acceptance Criteria

- [ ] `history summary`, `decisions generate`, `--reader auto` and permitted `sft-corpus` enrich passthrough preserve data stdout, exit 0 for intentional fallbacks and emit their single safe stderr note only under remote config; direct/automatic library fallbacks add no notice.
- [ ] Remote summary bypasses every DB probe/count helper even with a stale shadow DB, preserves date filtering and `source=files`, and exposes unavailable loop metrics in text/JSON. Local summary's DB-first/empty-window/loop-count behavior is retained.
- [ ] Local summary/decisions from a foreign remote cwd read seeded issue/loop data via their selected local target with zero remote reader requests, including default-shaped env redirection. Direct-schema parsing helpers preserve optional provenance through `schema.connect`, and existing callers without provenance retain their resolution behavior; no ENH-3700 dependency is needed.
- [ ] CT-0 emits parseable `verdict: skipped` plus its note and never reports "no candidates" for a remote skip; it uses `resolve_history_store` and branches on `RemoteTarget`; no bare `resolve_history_db()` remains in `skills/`; mirrors regenerated.
- [ ] Packaged stage uses `--reader auto` and preserves the CLI's single note. Remote enrich with all DB-quality flags disabled preserves input records/metadata, makes no metadata lookup and adds no fabricated zero/false fields; its output is published atomically.
- [ ] Each enabled DB-quality flag makes remote enrich fail through `corpus_failed` before output publication, including empty input and pre-existing metadata; previous output survives and filter/publish/sentinel do not run. The actual packaged YAML/FSM tests also prove a local env override still enriches.
- [ ] Messages auto fallback honors selected `--cwd` through the owning root, produces actual supported JSONL windows, and documentation states the existing Claude-shaped-only fallback limitation.
- [ ] No endpoint/token/SQL/exception text in any note; no duplicate library warning; the catch class is `HistoryUnsupported`, never bare `HistoryError`.
- [ ] `"No history.db found"` is unchanged (invariant test); if ENH-3658's temporary CT-0 allowlist entry exists, it is removed here.
- [ ] With the default local store `python -m pytest scripts/tests/` passes unchanged.

## Related

- ENH-3700 (central guard + harness serve; split sibling), ENH-3657 (refuse boundary; `blocked_by`), ENH-3677 (shared fixture; `blocked_by`), ENH-3729 (SFT failure route/atomic publish; `blocked_by`), ENH-3658 (hazard-gate allowlist), FEAT-3535.

## Related Key Documentation

- `docs/reference/CONFIGURATION.md` (reader support and remote SFT quality refusal), `docs/reference/CLI.md` (messages fallback), `docs/reference/API.md` (library fallback contract), `docs/guides/HISTORY_SESSION_GUIDE.md`.

## Status

**Open** | Created: 2026-10-05 | Priority: P3

## Confidence Check Notes

Scope amended 2026-10-05; no readiness or passing-test claim is made. Re-run `/ll:confidence-check` after ENH-3677, ENH-3657 and ENH-3729 land. The summary's secondary query and remote SFT quality refusal need executable entry-point/FSM evidence.

## Session Log

- EPIC-3693 review #4 - 2026-10-05 - direct-schema summary/decisions helpers now preserve selected local provenance so foreign remote cwd cannot re-resolve them or hide failure behind file fallback; ENH-3657 owns the earlier reader setup fix. Fresh Opus consult skipped: existing per-chat budget exhausted; implementation not performed.
- EPIC-3693 review #3 + `/ll:advise` (claude-opus-5-5, user_requested, confidence 0.80) - 2026-10-05 - complete summary fallback, selected messages root, exact SFT passthrough/quality-refusal semantics and ENH-3729 dependency added; implementation not performed
