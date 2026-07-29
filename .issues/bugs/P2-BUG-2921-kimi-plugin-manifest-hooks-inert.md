---
id: BUG-2921
title: kimi plugin-manifest hooks — cwd locality fix + print-mode/doc caveats (0.30.0)
type: BUG
status: open
priority: P2
captured_at: "2026-07-29T19:25:44Z"
discovered_date: 2026-07-29
discovered_by: capture-issue
parent: EPIC-2910
labels:
- kimi
- host-compat
---

# BUG-2921: kimi plugin-manifest hooks — cwd locality fix + print-mode/doc caveats (0.30.0)

## Summary

Initial report (same-day): "plugin-manifest hooks inert on kimi 0.30.0."
That premise was **wrong** — plugin-sourced hooks DO fire on 0.30.0 in TUI
sessions, proven by live telemetry. The investigation surfaced three real
defects instead: one in our shims (fixed below) and two kimi-side behaviors
to document and route around. The initial misdiagnosis came from querying
the project's `.ll/history.db` while plugin-route telemetry was landing in
the *managed plugin copy's* database.

## Motivation

The plugin route (`/plugins install`, FEAT-2917) is the kimi-native
packaging path and must be trustworthy end-to-end: hooks firing, config and
telemetry resolving against the **project**, and documented behavior for
headless automation.

## Confirmed findings (2026-07-29, kimi 0.30.0)

1. **Plugin hooks fire in TUI sessions** — `hook_events` rows for
   `session_39f08962` (PreToolUse/PostToolUse/SessionStart, 19:21Z) and
   `session_a8fddc3b` (SessionStart, 19:50Z) exist in the managed copy's
   `.ll/history.db`. The `/plugins info` panel simply does not render a
   Hooks section — a **display gap**, not a load failure.
2. **Plugin commands work** — `/ll:commit` confirmed by user test.
3. **FIXED (ours): shims ran with cwd = managed plugin root.** Kimi spawns
   plugin hooks with `cwd = record.root` (`enabledHooks()`), so
   `resolve_config_path` read the frozen copy's `.ll/ll-config.json` and
   telemetry went to the copy's `.ll/history.db` — config drift + history
   split from the project. Fix: all 8 shims now `cd` into the payload's
   `cwd` before dispatching (`scripts/little_loops/hooks/adapters/kimi/*.sh`,
   whitespace-tolerant extraction). Verified live: SessionStart telemetry
   now lands in the project's `.ll/history.db` (rows 65227-65228), nothing
   in the managed copy. Regression test `test_shim_cd_into_payload_cwd`
   added; managed copy re-synced (reinstall picks it up permanently).
4. **Hardened (ours, defensive): bare `python`.** Shims invoked bare
   `python`, which fails silently (fail-open) under a minimal hook-process
   PATH (proven: exit 127). Not the cause here (the TUI hook process
   inherits the full user PATH), but a real portability fix: shims now
   resolve `LL_PYTHON` → `python3` → `python`. The codex and claude-code
   adapters share the old pattern — separate hardening candidate.
5. **Kimi behavior: `kimi -p` (print mode) does not fire plugin hooks.**
   A print-mode run post-install produced no shim execution, while
   config.toml `[[hooks]]` fire fine in print mode (FEAT-2911 spike).
   Consequence: **headless automation (`ll-auto` via `kimi -p`) gets
   little-loops hooks only via the config.toml managed block**
   (`ll-init --hosts kimi-code`), not via the plugin. The plugin route is
   sufficient for interactive TUI use.

## Remaining work

- [x] Shim cd fix + interpreter hardening + tests (11/11 pass)
- [x] Live verification (TUI session telemetry in project DB)
- [x] Docs: `docs/kimi/hook-events.md` (print-mode + cwd + display-gap
      notes), `HOST_COMPATIBILITY.md` `[^kimiplugin]` + Installation row
- [ ] Optional: report upstream — (a) `/plugins info` does not render a
      Hooks section; (b) print mode does not load plugin hooks (or document
      it). Watch the kimi changelog and re-test on releases.
- [ ] Close after user confirms a TUI session shows expected hook effects
      (e.g. session-start context) with the synced shims.

## Integration Map

### Files Modified (fix)
- `scripts/little_loops/hooks/adapters/kimi/*.sh` (all 8) — cd-to-payload-cwd + LL_PYTHON hardening
- `scripts/tests/test_kimi_adapter.py` — cd regression test + assertion updates
- `~/.kimi-code/plugins/managed/ll/...` — managed copy synced (diagnostic only; permanent fix lands via plugin reinstall)

### Files Modified (docs)
- `docs/kimi/hook-events.md`, `docs/reference/HOST_COMPATIBILITY.md`, this issue

## Impact

- **Priority**: P2 — shipped-feature correctness; fix landed same-day, residual is documentation + upstream watch
- **Effort**: Small — shim patch + tests + docs
- **Risk**: Low — shims remain thin transports; cd is payload-driven and guarded
- **Breaking Change**: No

## Session Log
- `/ll:audit-issue-conflicts` - 2026-07-29T20:39:42 - `7dce485a-c75c-400c-ac56-53fcf2521623.jsonl`
- `/ll:capture-issue` - 2026-07-29T19:25:44Z - kimi-code host adapter session (plugin hook diagnosis)
- diagnosis + fix - 2026-07-29T20:05:00Z - live TUI verification, shim cd fix, docs

---

**Open** | Created: 2026-07-29 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's shim fixes (cd-to-payload-`cwd`, `LL_PYTHON` → `python3` → `python`) patch the adapter originally scoped in FEAT-2915. FEAT-2915's Implementation Step 1 describes the pre-fix 4-line shim shape; treat this issue's shipped shims as canonical there.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's print-mode finding (plugin hooks do not fire under `kimi -p`) bounds FEAT-2917's claim that the plugin install path provides hooks "without running `ll-init`" — FEAT-2917's README section must caveat TUI-only hook coverage and point headless users at `ll-init --hosts kimi-code`.
