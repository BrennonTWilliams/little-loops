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
---

# ENH-3728: Degrade verdicts for history readers under a remote backend

## Summary

Give the reader sites that have a safe local fallback an explicit **degrade** verdict under `history.backend.provider: libsql` (FEAT-3535): `history summary`, `decisions generate`, `ll-messages` / `extract_conversation_turns` with `reader=auto`, the `improve-claude-md` CT-0 snippet, and the packaged `sft-corpus` `--reader auto` / `enrich` passthrough. Split from ENH-3700 on 2026-10-04 (Opus review): these sites only need to catch the `HistoryUnsupported` that the **existing** pre-resolve already raises, so they do not depend on the central guard, the `_connect_readonly` contract, or the importer audit, and should not be held behind that higher-risk seam.

## Current Behavior

- `decisions.py:generate_from_completed`, `user_messages.py:extract_conversation_turns` (reader `auto` reaches `resolve_history_db`), and `skills/improve-claude-md` CT-0 (`python3 -c` calling bare `resolve_history_db()`, SKILL.md ~L206-209, ending in `2>/dev/null`) fail or emit empty stdout that reads as "no candidates".
- `scripts/little_loops/loops/sft-corpus.yaml` `stage` (`--reader db`, masked by `2>/dev/null || touch "$OUTPUT"`) and `enrich` (`lookup_session_metadata` is `.exists()`-gated, `history_reader/sessions.py:358`) turn a refusal into an empty corpus routed onward as success.
- `ll-history summary` has a file-scan fallback (`scan_completed_issues`) that it does not reach under remote.

## Expected Behavior

| Site | Under remote | Notes |
|---|---|---|
| `history summary` | **degrade** to the file scan, exit 0 | one `note:` line on stderr; thread `root=project_root` (ENH-3657 prepared the branch) |
| `decisions.generate_from_completed` | **degrade** to the issues-directory scan | local path stays DB-first; CLI caller owns the note |
| `ll-messages --sft-format` / `extract_conversation_turns` | `reader=auto` -> **degrade** to JSONL | catch `HistoryUnsupported` before the JSONL fallback; explicit `--reader db` refusal is ENH-3657 |
| CT-0 in `skills/improve-claude-md` | **degrade**: explicit skipped verdict with a one-line note | switch to `resolve_history_store`, branch on `RemoteTarget`, remove the snippet's `2>/dev/null`, check the skipped verdict before the empty-feedback branch |
| `sft-corpus.yaml` `stage` | `--reader auto` (degrade to JSONL) | the failure-routing and `|| touch` removal belong to the SFT-routing issue; this issue only changes the reader flag |
| `sft-corpus.yaml` `enrich` | **degrade**: explicit note, pass records through un-enriched | |

### Notice channel

Degrade notice = one fixed `note:` line on stderr at the human CLI/skill/state boundary, before bypassing the DB, only under a remote target. Libraries (`generate_from_completed`, `extract_conversation_turns`) select their fallback without printing; their CLI callers own the note. Automatic/library callers keep their existing output contract. CT-0 additionally returns parseable JSON with `verdict: skipped` and a fixed reason, then branches before "no candidates"; remove its `2>/dev/null` so the note survives. For packaged stage/enrich each state owns its designated note; a library warning must not duplicate a deliberate fallback notice. No endpoint/token/SQL or exception text in either channel.

### Docs wording

Degrade rows are added to the single support table in `docs/reference/CONFIGURATION.md` (ENH-3657 creates it; merge rows, do not replace siblings'). Refused rows elsewhere say "not supported with a remote backend" and promise no follow-up.

## Motivation

Local-only fallbacks already exist for these sites; routing remote users to them is low-risk and keeps `ll-messages`, `decisions` and the SFT pipeline usable instead of silently empty or tracebacking.

## Proposed Solution

1. Catch `HistoryUnsupported` (never bare `HistoryError`) in the library fallback paths and CLI callers; emit the single `note:` at the CLI/skill/state boundary under a remote target only.
2. CT-0: `skills/improve-claude-md/SKILL.md` (344 lines, cap 500; keep `[ -f .ll/decisions.yaml ]` and `decisions list --type rule 2>/dev/null | grep`, pinned by `test_wiring_skills_and_commands.py`), then `ll-adapt --host <gemini|kimi-code|qwen> --apply` and `test_improve_claude_md_skill.py`.
3. `sft-corpus.yaml`: `--reader auto` on `stage`, passthrough note on `enrich` (coordinate with the SFT-routing issue, which edits the same states).
4. Docs, support-table rows, `docs/reference/CLI.md`, `docs/reference/API.md` (`extract_conversation_turns` relationship paragraph), `docs/guides/HISTORY_SESSION_GUIDE.md`; keep `test_wiring_reference_docs.py` and `test_docs_audience_gate.py` green; cite `little_loops.<module>` in prose, no `scripts/tests/` paths.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/history.py` (`summary`), `decisions.py` / `cli/decisions.py`, `user_messages.py` / `cli/messages.py`, `skills/improve-claude-md/SKILL.md` (+ mirrors), `scripts/little_loops/loops/sft-corpus.yaml`.
- Anchors drift: re-grep every `resolve_history_db(` site (`decisions.py:596`, `user_messages.py` ~`:1227`).

### Tests
- Degrade tests keep stdout unchanged with exactly one `note:` line and no token; default-`auto` JSONL fallback; `ll-messages` default-`auto` regression (`extract_conversation_turns` currently reaches the remote pre-resolve); `"No history.db found"` invariant (`test_bug_3216_telemetry_digest_invocations.py`); `sft-corpus` `stage` reader flag (`test_loops_sft_corpus.py`).
- Use the hoisted `remote` fixture (ENH-3677; `delenv("LL_HISTORY_DB")` to override the autouse `conftest._isolate_history_db`).
- Keep green: `test_cli_decisions.py`/`test_decisions.py` DB-first local branch, `test_cli_messages.py`, `test_adapt_skills_for_codex.py`, `test_verify_skill_prose.py`, `test_enh494_skill_companions.py`.

## Program Design

### Types
- `HistoryError(Exception)` <- `HistoryUnsupported(HistoryError)` <- `HistoryBackendNotLocal(HistoryUnsupported)` in `little_loops.session_store.backend`.

### Signatures
- `generate_from_completed(config: BRConfig) -> int` — degrade site in `little_loops.decisions`; local branch stays DB-first.
- `extract_conversation_turns(..., reader="auto")` — catches `HistoryUnsupported` before the JSONL fallback.

### Call Path
- `cmd_decisions` -> `generate_from_completed` -> `scan_completed_issues` (degrade, remote only).
- `main_messages` -> `extract_conversation_turns(reader="auto")` -> JSONL path (degrade).
- `main_history summary` -> `scan_completed_issues` (degrade, remote only).

### Decision Rules
- Catch class is `HistoryUnsupported`; one CLI `note:` line; `"No history.db found"` stays verbatim for local-missing; local behavior unchanged.

## Implementation Steps

Prerequisites: ENH-3677 (hoisted `remote` fixture) and ENH-3657 (boundary helper and summary root threading) landed.

1. Library fallbacks + CLI notes for `history summary`, `decisions generate`, `reader=auto`.
2. CT-0 skill change, mirrors.
3. `sft-corpus.yaml` reader flag and enrich passthrough.
4. Docs/support-table rows; remove the CT-0 allowlist entry from ENH-3658's hazard gate if it exists.
5. Tests per the Integration Map; run `python -m pytest scripts/tests/`, `ruff check scripts/`, `python -m mypy scripts/little_loops/` (scope `ruff format` to changed files).

## Impact

- **Priority**: P3 - opt-in remote-backend users only.
- **Effort**: Medium - four library/CLI sites, one skill + mirrors, one loop YAML, docs.
- **Risk**: Low - catches only the already-raised `HistoryUnsupported`; local behavior unchanged.
- **Breaking Change**: No.

## Scope Boundaries

- **In scope**: the six sites above, the CLI-boundary notes, CT-0 skill change + `ll-adapt` mirrors, support-table rows, removing the CT-0 entry from ENH-3658's hazard-gate allowlist if present.
- **Out of scope**: the boundary helper and refuse sites (ENH-3657); the central guard, catch widening and `ll-harness` serve (ENH-3700); SFT failure routing / atomic enrichment publish (SFT-routing issue); hand-built paths (ENH-3658); `context-monitor.sh` (ENH-3680, cancelled); remote read serving (ENH-3668/3684/3685, deferred).

## Acceptance Criteria

- [ ] `history summary`, `decisions generate`, `--reader auto` and `sft-corpus` `enrich` preserve data stdout, exit 0 for intentional fallbacks and emit their single safe stderr note only under remote config; direct/automatic library fallbacks add no notice.
- [ ] CT-0 emits parseable `verdict: skipped` plus its note and never reports "no candidates" for a remote skip; it uses `resolve_history_store` and branches on `RemoteTarget`; no bare `resolve_history_db()` remains in `skills/`; mirrors regenerated.
- [ ] `sft-corpus` `stage` uses `--reader auto`; remote JSONL fallback succeeds with its note; `enrich` passes records through un-enriched under remote with a note.
- [ ] No endpoint/token/SQL/exception text in any note; no duplicate library warning; the catch class is `HistoryUnsupported`, never bare `HistoryError`.
- [ ] `"No history.db found"` is unchanged (invariant test); if ENH-3658's temporary CT-0 allowlist entry exists, it is removed here.
- [ ] With the default local store `python -m pytest scripts/tests/` passes unchanged.

## Related

- ENH-3700 (central guard + harness serve; split sibling), ENH-3657 (refuse boundary; `blocked_by`), ENH-3677 (shared fixture; `blocked_by`), the SFT-routing issue (edits the same `sft-corpus.yaml` states), ENH-3658 (hazard-gate allowlist), FEAT-3535.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-10-05 | Priority: P3
