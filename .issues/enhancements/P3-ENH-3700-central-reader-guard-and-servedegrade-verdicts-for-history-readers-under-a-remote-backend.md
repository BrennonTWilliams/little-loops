---
id: ENH-3700
type: ENH
title: Central reader guard and serve/degrade verdicts for history readers under a
  remote backend
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T17:56:06Z'
blocked_by:
- ENH-3657
- ENH-3677
blocks:
- ENH-3668
- ENH-3684
- ENH-3685
relates_to:
- ENH-3658
- ENH-3682
- ENH-3668
- BUG-3652
parent: EPIC-3693
epic: EPIC-3693
---

# ENH-3700: Central reader guard and serve/degrade verdicts for history readers under a remote backend

> **Split from ENH-3657 on 2026-10-02** (Opus review of EPIC-3693's children). ENH-3657 (3657a) owns the refuse boundary: one boundary helper plus the refuse sites that fail on the pre-resolve's `HistoryBackendNotLocal`, with no contract change. This issue (3657b) owns the risky seam: the central guard, the `_connect_readonly` re-raise that changes the contract for ~67 callers, the exhaustive caller audit, read-mode remote ensure, `ll-harness` serve, and every degrade site. Isolating it keeps the wide-blast-radius change in one reviewable PR. The design below was moved out of ENH-3657's reconciled body (three prior `/ll:advise` Opus reviews).

## Summary

Under `history.backend.provider: libsql` (FEAT-3535), a reader that builds the default `<root>/.ll/history.db` path can `ensure_schema`-create an empty shadow local database, and `_connect_readonly` maps every `HistoryError` to `None`, so a refusal would read as "no data". This issue adds a central guard at the reader seam, makes the guard's own refusal survive `_connect_readonly`, lets `ll-harness` serve from the remote store, and gives the remaining reader sites a degrade verdict.

## Current Behavior

**Load-bearing fact.** `_resolve_once` returns an absolute path verbatim as a `LocalTarget` (BUG-3181), so dropping a pre-resolve does not make a site read remotely: `open_history_readonly(..., ensure=True)` would run `ensure_schema` on that local path and create an empty shadow `.ll/history.db`. Only `cli/harness.py` (relative `DEFAULT_DB_PATH`) can serve.

**Placement bug.** `history_reader/_base.py:_connect_readonly` catches `HistoryError` (parent of `HistoryUnsupported`) and returns `None`, and its ~67 callers all treat `None` as "no data". A refusal raised inside `open_history_readonly` is swallowed into silent empty output unless `_connect_readonly` re-raises it.

**Read-only token.** `ensure=True` runs `check_access(write=True)` (`remote_schema.check_access`, `libsql.py`), which refuses a behind/ahead store and a read-only token, so every reader returns `None` against such a store.

Sites that currently degrade wrongly or silently:
- `decisions.py:generate_from_completed`, `user_messages.py:extract_conversation_turns` (reader `auto` reaches `resolve_history_db`), and `skills/improve-claude-md` CT-0, whose `python3 -c` calls bare `resolve_history_db()` (SKILL.md ~L206-209) and ends in `2>/dev/null`, so the refusal emits empty stdout that reads as "no candidates".
- `scripts/little_loops/loops/sft-corpus.yaml` `stage` and `enrich`: a refusal becomes an empty corpus routed to `enrich` as success; `lookup_session_metadata` is `.exists()`-gated (`history_reader/sessions.py:358`).
- `ll-harness` (5 sites in `cli/harness.py`) pre-resolves and raises.
- `ll-history summary` has a file-scan fallback (`scan_completed_issues`) it does not reach under remote.

## Expected Behavior

### Verdicts

| Site | Under remote | Notes |
|---|---|---|
| `history summary` | **degrade** to the file scan, exit 0 | one `note:` line on stderr |
| `ll-harness` x5 sites | **serve** | relative `DEFAULT_DB_PATH` reaches `LibsqlBackend`; read-mode ensure; never refuses with exit 1 (indistinguishable from a graded FAIL) |
| `decisions.generate_from_completed` | **degrade** to the issues-directory scan | local path stays DB-first |
| `ll-messages --sft-format` / `extract_conversation_turns` | `reader=auto` -> **degrade** to JSONL | catch `HistoryUnsupported` before the JSONL fallback; explicit `db` refusal is ENH-3657 |
| CT-0 in `skills/improve-claude-md` | **degrade**: skip with a one-line note | empty stdout must no longer read as "no candidates"; switch to `resolve_history_store` and branch on `RemoteTarget` (no bare `resolve_history_db()` call) |
| `scripts/little_loops/loops/sft-corpus.yaml` `stage` | `--reader auto` (degrade to JSONL) | a refusal must not become an empty corpus routed to `enrich` as success |
| `scripts/little_loops/loops/sft-corpus.yaml` `enrich` | **degrade**: explicit note, pass records through un-enriched | |

### Central guard (fix the cause once)

In `session_store.backend.open_history_readonly` (the `ensure=True` reader opener): when the configured provider is remote **and** the resolved target is a *default-shaped* absolute local path (`<root>/.ll/history.db`, `LL_HISTORY_DB` unset, no explicit `--db`), raise `HistoryRemoteRefused` (a subclass of `HistoryUnsupported`) instead of `ensure_schema`-creating a shadow DB. It fires only in that case and must respect the BUG-3181 absolute-path contract, an explicit `--db` (wrap it in `LocalTarget` at the CLI), `LL_HISTORY_DB`, and first-use local creation when the provider is not remote. Classify "remote" from the root derived from the path (`<root>/.ll/...`), not the cwd, so an MCP call with a foreign cwd is not misclassified.

### `_connect_readonly` re-raise (contract change)

`history_reader/_base.py:_connect_readonly` re-raises `HistoryRemoteRefused` **above** its `except HistoryError` handler: only the guard's own subclass, never every `HistoryUnsupported`. Other access-policy refusals (`HistoryUnsupported` for a foreign/unstamped migrated store) keep degrading to `None`. Record the contract change ("`None` on failure, raise on a guard refusal") in the docstring. ENH-3682's regression test (an injected access-policy `HistoryUnsupported` still yields `None`) must pass on either merge order.

**Rejected alternative (2026-09-30 Opus):** a no-re-raise seam (`None` + `warn_once`, refusals only at the CLI boundary) to spare the ~67 callers. Rejected: any CLI the boundary helper misses would print silent-empty output, the failure this work exists to remove. The narrowed subclass confines the blast radius to callers that previously created a shadow DB. The compensating control is the exhaustive non-CLI caller audit below.
*Dissent recorded in the 2026-10-02 review:* with no known remote user, the guard and contract change could be cut in favor of per-site refusals (ENH-3657), ENH-3658's hazard gate and the AST test alone. The guard is kept because a shadow DB is a silent data split that per-site fixes and static tests can miss for future callers. If the audit below proves expensive, cutting the guard is defensible.

### Exhaustive caller audit (required before merge)

**Inventory recorded 2026-10-02.** An AST scan of all Python `Import`/`ImportFrom` nodes (including function-local imports) finds **17 external importer modules**, plus 15 modules inside `history_reader`. A text search finds 41 files because it also matches documentation/comments; `prepatch_check.py`, `token_provenance.py`, `fsm/cost_graph.py`, `session_store/{schema,lifecycle,writers,backend}.py`, and `issue_history/workspace_{activity,quality}.py` have text references but no reader imports. They are not additional importer call sites.

Paths below are relative to `scripts/little_loops/`. These are implementation dispositions, not claims that the planned catches already exist. Re-run the AST inventory at implementation and test every call in each importer, including callers reachable through re-exports.

| Importer | Guard/failure disposition |
|---|---|
| `cli/ctx_stats.py` | ENH-3657 refuses default remote reads; usage selectors receive an existing connection; explicit `--db` stays local. |
| `cli/harness.py` | Serve using relative default; read-mode ensure; quiet open and mid-query fallback (this issue). |
| `cli/history.py` | ENH-3657 refuses reader rows; summary file-scan fallback here. |
| `cli/history_context.py` | Relative default/explicit caller path; guard must leave relative remote reads and explicit local paths intact. |
| `cli/logs.py` | ENH-3657 refuses remote DB-backed paths before absolute-path metadata lookup; preserve local missing-data behavior. |
| `cli/loop/evidence.py` | `find_loop_run(run_id)` uses the relative default; guard unaffected. |
| `cli/session.py` | Parser's relative default or caller `--db`; exercise reached reader helpers without converting the default to an absolute local path. |
| `fsm/executor.py` | Relative `DEFAULT_DB_PATH` advisory prepatch reads; ENH-3682 budgets open/query failure. |
| `hooks/session_start.py` | Absolute digest path is already gated by `not _remote_store`; retain that guard. |
| `issue_history/agent_quality.py` | Called under ENH-3657 refusal; local analysis stays intact; future target propagation is ENH-3684. |
| `issue_history/collisions.py` | Same boundary refusal/local-only analysis; future serving is ENH-3684. |
| `issue_history/evolution.py` | Imports only pure `_stale_cutoff`; local-only opener stays under boundary refusal. |
| `issue_history/rework.py` | Same boundary refusal/local-only analysis; future serving is ENH-3684. |
| `mcp_server/tools.py` | ENH-3657 structured refusal using owning project root before absolute default; future serving is ENH-3685. |
| `session_store/queries.py` | `select_usage_coverage` consumes a caller-owned connection for snapshot export; no reader opener; remote snapshot refusal unchanged. |
| `user_messages.py` | Explicit DB reader refuses via ENH-3657; auto reader catches refusal and falls back to JSONL here. |
| `work_verification.py` | Relative default prepatch readers; ENH-3682 best-effort budget, no absolute coercion. |

Reader-internal inventory: `_base`, `__init__`, `context`, `digest`, `events`, `formatting`, `harness`, `hooks`, `models`, `runs`, `search`, `sessions`, `subagents`, `summary_dag`, `usage`. Audit absolute-path coercions and catches in these reached helpers as well as the external importers. Shell/embedded Python is a separate inventory: CT-0 and packaged SFT states are handled here; `skills/update-docs` and the artifact hazard gate belong to ENH-3658; `context-monitor.sh` is the documented no-op (ENH-3680).

Two different functions are named `_connect_readonly`: `history_reader/_base.py` (the `ensure=True` opener whose `None` mapping this issue changes) and `session_store/queries.py` (a raw `mode=ro` URI opener, unaffected). The audit, the AST gate and every test name the module explicitly so neither is conflated with the other. Add an AST regression gate for default-path absolute construction and unaudited importer additions, with reasoned exceptions for explicit local targets, connection-only/pure helpers and remote-gated paths. Do not equate every `Path(...)` call with a hazard; dynamic tests assert no shadow DB in the default remote cases.

### Read-mode remote ensure

Make the ensure step of `open_history_readonly` for a `RemoteTarget` a read-mode check (`check_access(write=False)`, no ensure/migrate); a missing remote schema reads as empty, and `ll-harness` serve treats it as such. **Stamped-schema rule (decided here, 2026-10-02):** serve a store at the exact schema version, **behind** or **ahead**; this is `check_access(write=False)`'s existing policy ("strict reads proceed either way"), so no new refusal code is added. An ahead-store refusal was rejected (2026-10-02 Opus review): it would be new code and `_connect_readonly` would map it to `None`, producing silent-empty `ll-harness` output that violates the epic closure criterion. If an older client queries a column a newer schema renamed or removed, the query fails as an ordinary `HistoryError` and degrades like any other mid-query failure. Project-id mismatch and missing `project_id` still raise. Extend `HranaStub` with a read-only permission mode that permits SELECT and rejects writes (or a controlled equivalent); a token accepted for every SQL statement cannot prove this behavior. ENH-3668 (deferred) must follow this rule if revived.

Distinguish missing configured project ID, a missing store stamp on a migrated store, and a foreign stamp; all fail the read-mode access check. A version-0 store retains the documented non-strict empty fallback. A project/auth/open failure at `ll-harness` also degrades to its existing empty result, with the existing once-only safe library warning; it must not become a graded failure exit. The stricter user-facing error policy is deferred to ENH-3668.

### Non-strict mid-query failures

`HranaError` is already a `HistoryError`, but is not a `sqlite3.Error`. The harness reader's current `except sqlite3.Error` handlers therefore leak a remote error after a successful open. Widen the reached best-effort handlers to `(sqlite3.Error, HistoryError)` and retain the same empty/zero/None result on open **and** query failure. Use the existing safe `warn_once` channel once per call, without raw host/token/SQL text; injected failure after the first successful request proves this path. When ENH-3668 is revived, these handlers re-raise under strict remote mode; explicit best-effort always wins. Keep local SQL fallbacks unchanged.

### SFT pipeline failure routing (owned here)

In `scripts/little_loops/loops/sft-corpus.yaml`, remove stage's `2>/dev/null || touch "$OUTPUT"` masking and use `--reader auto`. Add `on_error: corpus_failed` to stage and enrich, with `corpus_failed` set to `terminal: true, failure: true`. A non-zero shell state with only `next` currently continues, so a process error alone is insufficient. The intentional remote passthrough succeeds with its explicit note; unexpected staging, parsing or serialization errors fail the run. Publish `enriched.jsonl` by writing a unique temporary sibling and atomically replacing it only after successful completion; clean up a failed temp and leave any previous final file untouched. No failure may reach filter/publish or emit the success sentinel. ENH-3685 reuses this wiring if revived.

### Notice channel

Degrade notice = one `note:` line via `print(..., file=sys.stderr)` from the CLI, emitted before touching the seam, only under a remote target, never on stdout, never echoing an endpoint token. The library `remote_telemetry.warn_once` in `_connect_readonly` must **not** also fire for that call: one channel per site.

### Docs wording

Docs and messages say remote readers are "not supported with a remote backend" where refused; they do not promise a follow-up (remote read serving, ENH-3668/3684/3685, is deferred indefinitely).

## Motivation

A refusal from the boundary helper (ENH-3657) only covers CLIs that pre-resolve. Without the central guard, hand-built absolute paths still create a shadow DB under remote config, and without the re-raise a guard refusal reads as empty data. `ll-harness` can serve remotely at near-zero cost and the degrade sites keep local-only fallbacks working.

## Scope Boundaries

- **In scope**: the central guard and `HistoryRemoteRefused`, the `_connect_readonly` re-raise, the audit and its AST test, read-mode remote ensure and the `HranaStub` read-only mode, `ll-harness` serve, the degrade sites above, the CT-0 skill change and mirrors, `sft-corpus` `stage`/`enrich`, the support-table rows for these sites.
- **Out of scope**: the boundary helper and refuse sites (ENH-3657), hand-built paths (ENH-3658), `context-monitor.sh`, prepatch budget (ENH-3682), remote read serving for `ll-history` subcommands and MCP (ENH-3668/3684/3685, deferred), writers/startup paths (BUG-3652, done).

## Proposed Solution

1. **Seams** (`session_store/backend.py`, `history_reader/_base.py`): guard in `open_history_readonly`, `_connect_readonly` re-raise + docstring, read-mode remote ensure (verify against `HranaStub` first, since `ll-harness` serve depends on it). Audit non-CLI absolute-path callers.
2. **Serve** `cli/harness.py` x5 (`_retry_gate`, `_read_target_history`, `_resolve_baseline_of`, `read_baseline`, `cmd_dsl`): drop the pre-resolve, pass the relative default; confirm rows round-trip through `HranaStub` and no local `.ll/history.db` is created.
3. **Degrade** sites: `history summary`, `decisions generate`, `extract_conversation_turns(reader="auto")`, CT-0, packaged `sft-corpus` stage/enrich. Add failure routing and atomic enrichment publication here; remote passthrough is intentional success, unrelated errors are terminal failures.
4. **Skills, mirrors, docs**: CT-0 only in `skills/improve-claude-md/SKILL.md` (344 lines, cap 500; keep `[ -f .ll/decisions.yaml ]` and `decisions list --type rule 2>/dev/null | grep`, pinned by `test_wiring_skills_and_commands.py`); then `ll-adapt --host <gemini|kimi-code|qwen> --apply` and `test_improve_claude_md_skill.py`. Support-table rows in `docs/reference/CONFIGURATION.md` "Remote history backend" (ENH-3657 creates the table), `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/ARCHITECTURE.md:~758`. Keep `test_wiring_reference_docs.py` and `test_docs_audience_gate.py` green; cite `little_loops.<module>` in prose, no `scripts/tests/` paths.
5. **Hazard gate**: if ENH-3658 lands first, remove its temporary CT-0 allowlist entry here. If this issue lands first, ENH-3658 adds no CT-0 exception. The context-monitor exception remains intentional; neither order adds a functional dependency.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store/backend.py` (`open_history_readonly`), `history_reader/_base.py` (`_connect_readonly`), `history_reader/harness.py` (mid-query best-effort catches), `cli/harness.py` (5 sites), `cli/history.py` (`summary` degrade), `decisions.py`, `user_messages.py`, `skills/improve-claude-md/SKILL.md`, `scripts/little_loops/loops/sft-corpus.yaml`, `scripts/tests/hrana_stub.py` (read-only permission mode).
- Anchors drift: re-grep every `resolve_history_db(` site before editing (`decisions.py:596`, `user_messages.py` ~`:1227`).
- `issue_history/evolution._open_db` (sqlite-only choke point) changes only if made remote-aware.

### Loop / digest invariants
- `.loops/ll-logs-telemetry-digest.yaml` `run_stats` greps `"No history.db found"`; keep verbatim and add remote notices as separate stderr lines.
- `ll-messages` default-`auto` callers need a regression test because `extract_conversation_turns` currently reaches the remote pre-resolve.

### Tests
- Guard fires only for the default-shaped case; typed `LocalTarget` for an explicit absolute `<root>/.ll/history.db`, `--db`, `LL_HISTORY_DB`, and non-remote first-use creation are carve-outs.
- `_connect_readonly` re-raises `HistoryRemoteRefused` and does not also `warn_once`; other `HistoryUnsupported` still maps to `None`.
- `ll-harness` serve returns stub data and creates **no** local `.ll/history.db`; read-only-token serve uses an actual permission-rejecting stub; behind and ahead stamped stores are served.
- Degrade tests keep stdout unchanged with exactly one `note:` line and no token; default-`auto` JSONL fallback; `sft-corpus` `stage` reader flag (`test_loops_sft_corpus.py`); `"No history.db found"` invariant (`test_bug_3216_telemetry_digest_invocations.py`).
- Use the hoisted `remote` fixture (ENH-3677; must `delenv("LL_HISTORY_DB")` to override the autouse `conftest._isolate_history_db`); test `main_harness([...])`, not `cmd_*`.
- Keep green: `test_libsql_backend.py::test_resolve_history_db_raises_for_the_remote_target` (fix stays at call sites and the reader seam, not `resolve_history_db`), `test_history_store_chokepoint_gate.py` (no raw `sqlite3.connect`), `test_cli_decisions.py`/`test_decisions.py` DB-first local branch, `test_cli_messages.py`, `test_evolution_triggers.py`, `test_adapt_skills_for_codex.py`, `test_verify_skill_prose.py`, `test_enh494_skill_companions.py`.

### Documentation
- `docs/reference/CONFIGURATION.md` (support-table rows), `docs/reference/CLI.md`, `docs/reference/API.md` (`extract_conversation_turns` relationship paragraph; "SQLite-only prerequisite" `Backend chokepoint` wording), `docs/ARCHITECTURE.md:~758`, `docs/guides/HISTORY_SESSION_GUIDE.md`. Must not contradict the write-side "telemetry is skipped silently" wording at `CONFIGURATION.md:738`.

## Program Design

### Types

- `HistoryError(Exception)` <- `HistoryUnsupported(HistoryError)` <- `HistoryBackendNotLocal(HistoryUnsupported)`, and new `HistoryRemoteRefused(HistoryUnsupported)`, in `little_loops.session_store.backend`; `HistoryUnsupported.operation: str | None` carries the operation name.
- `HistoryTarget = LocalTarget | RemoteTarget` in `little_loops.session_store.targets`; no reader signature accepts it here.

### Signatures

- `open_history_readonly(target=None, *, ensure: bool = False)` — gains the default-shaped-local-path guard (raises `HistoryRemoteRefused`) and a read-mode ensure for `RemoteTarget`.
- `_connect_readonly(db_path: Path) -> sqlite3.Connection | None` — returns `None` on ordinary failure but re-raises `HistoryRemoteRefused`.
- `generate_from_completed(config: BRConfig) -> int` — degrade site in `little_loops.decisions`; local branch stays DB-first.

### Call Path

- `history_reader._connect_readonly` -> `open_history_readonly` -> default-shaped-path guard -> `HistoryRemoteRefused` re-raised -> CLI boundary helper (ENH-3657) or MCP `is_error`.
- `cmd_decisions` -> `generate_from_completed` -> `scan_completed_issues` (degrade, remote only).
- `main_messages` -> `extract_conversation_turns(reader="auto")` -> JSONL path (degrade).
- `main_harness` -> relative `DEFAULT_DB_PATH` -> `LibsqlBackend` read-mode check -> rows.

### Decision Rules

- Serve at the designated `ll-harness` boundary using the relative default. Refuse a plain absolute default-shaped path under remote config; typed explicit `LocalTarget`, applicable `--db`, and `LL_HISTORY_DB` remain local carve-outs.
- Escape hatch: `LL_HISTORY_DB` set, or an explicit `--db` (only `ll-ctx-stats` and `ll-session refresh` define one), runs locally.
- Catch class for the guard is `HistoryRemoteRefused`; the notice channel is one CLI `note:` line; `"No history.db found"` stays verbatim for local-missing.
- Unreachable endpoint on a serve site reads as "no data" (`_connect_readonly` maps other `HistoryError` to `None`); accepted for `ll-harness` and documented.
- Stamped remote schema: exact, behind and ahead are all served (`check_access(write=False)`).

## Implementation Steps

Prerequisites: ENH-3677 (hoisted `remote` fixture) and ENH-3657 (boundary helper, so a guard refusal is never a traceback) landed.

1. Seams, with the read-mode ensure verified against `HranaStub` first, plus the caller audit and its recorded per-module verdicts.
2. `cli/harness.py` serve.
3. Degrade sites, CT-0 skill change, `sft-corpus.yaml`.
4. Skills mirrors (`ll-adapt`), docs, remove the CT-0 allowlist entry from ENH-3658's hazard gate.
5. Tests per the Integration Map. Run `python -m pytest scripts/tests/`, `ruff check scripts/`, `python -m mypy scripts/little_loops/` (scope `ruff format` to changed files).

## Impact

- **Priority**: P3 - opt-in remote-backend users only; startup breakage was BUG-3652.
- **Effort**: Medium-Large - guard, re-raise, 17-external/15-internal-module audit, serve and degrade sites, a skill mirror pass and a loop fix.
- **Risk**: Medium-High - the reader contract changes from "`None` on any failure" to "raise on a guard refusal" across ~67 callers.
- **Breaking Change**: No (local behavior unchanged).

## Acceptance Criteria

- [ ] `HistoryRemoteRefused` exists; `_connect_readonly` re-raises it (documented contract) while other `HistoryUnsupported` from remote ensure still map to `None`; ENH-3682's regression test passes on either merge order.
- [ ] The central guard fires only for a remote provider + default-shaped absolute local path with no `--db`/`LL_HISTORY_DB`, classifies remote from the path-derived root (not cwd), and under remote no reader creates a local `.ll/history.db` (assert absence). A caller-supplied absolute path wrapped as `LocalTarget` stays local.
- [ ] Re-run and reconcile the recorded 17-external/15-internal importer inventory, covering lazy imports and reached helpers; the AST gate catches new unaudited importers/default-path absolute construction with reasoned exceptions, and dynamic tests assert no shadow DB.
- [ ] `ll-harness` serve sites return stub data, create no local `.ll/history.db`, serve an exact, behind or ahead stamped schema and a read-only token (`check_access(write=False)`, tested with a permission-rejecting stub); no ahead-store refusal is added.
- [ ] Degrade sites (`history summary`, `decisions generate`, `--reader auto`, CT-0, `sft-corpus` `enrich`) keep stdout unchanged, exit 0 (CLI cases), and print exactly one `note:` line on stderr only under a remote target; `warn_once` does not also fire; no endpoint token appears in any notice.
- [ ] CT-0 uses `resolve_history_store` and branches on `RemoteTarget`; no bare `resolve_history_db()` remains in `skills/`; mirrors regenerated.
- [ ] Non-strict `ll-harness` open and mid-query Hrana failures preserve existing empty/zero/None fallbacks without traceback, with safe once-only warnings; local failures are unchanged.
- [ ] Packaged SFT stage uses auto fallback without error masking; stage/enrich unexpected failures route to a terminal failure, reach no filter/publish/success sentinel, and never publish partial enrichment. Remote passthrough succeeds with its note. Test a failure after at least one record is written and retention of any previous final file.
- [ ] `"No history.db found"` is unchanged (invariant test).
- [ ] If ENH-3658's temporary CT-0 allowlist exists, remove it here; if the seam lands first, no CT-0 exception is introduced later. Both orders leave the completed gate without that stale exception.
- [ ] With the default local store `python -m pytest scripts/tests/` passes unchanged.

## Related

- ENH-3657 (3657a, refuse boundary; `blocked_by`, lands first), ENH-3677 (shared `remote` fixture; `blocked_by`), ENH-3658 (hazard gate allowlist entry removed here), ENH-3682 (prepatch budget; independent), ENH-3668 (deferred strict-read infra), BUG-3652 (done), FEAT-3535 (remote libSQL backend).

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Exit-code wording vs ENH-3657: this issue owns `ll-harness` exit-code wording (serve; never refuses with exit 1 under a remote backend). ENH-3657's epilog/CLI.md exit notes cover `ll-ctx-stats` and `ll-history` only.

## Status

**Open** | Created: 2026-10-02 | Priority: P3


## Session Log
- `/ll:audit-issue-conflicts` - 2026-10-02T19:46:05 - `f99945f8-c860-47a6-88f6-46140ee77213.jsonl`
