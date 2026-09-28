---
id: ENH-3641
type: ENH
title: ll-doctor check validates configured model_hints against the host model catalog
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-28'
captured_at: '2026-09-28T20:53:36Z'
parent: EPIC-3563
labels:
- multi-host
---

# ENH-3641: ll-doctor check validates configured model_hints against the host model catalog

## Summary

Add an `ll-doctor` check that validates the user's `orchestration.model_hints` values against the host's own model catalog, and warns when a configured model is hidden, upgraded or retiring. It runs only in `ll-doctor`, never on the loop run path, so hint resolution stays deterministic and offline.

## Current Behavior

`resolve_model_hint` (`little_loops.host_runner`) passes `orchestration.model_hints` values through as literals on every CLI backend. Nothing checks that a configured value is a model the host still accepts. Non-Claude hosts have no built-in hint mapping (EPIC-3563 scope), so every Codex/Gemini/Kimi/Qwen/OMP user who declares hints writes model IDs by hand, and those IDs go stale silently. The first sign is a failed host invocation mid-run.

Codex publishes the data needed to catch this: `codex debug models` (codex-cli 0.152.1) prints a catalog JSON (`{"models": [...]}`) with per-model `slug`, `priority`, `visibility` (`list`/`hide`) and `upgrade {model, migration_markdown, retirement_at}`. Example seen 2026-09-28: `gpt-5.5` carries `upgrade.model = "gpt-5.6-sol"`, `retirement_at = 2026-10-14T19:00:00Z`.

## Expected Behavior

`ll-doctor` shows a "Model hints" section. For each backend/hint pair in `orchestration.model_hints` whose host exposes a catalog (Codex today):

- slug not in the catalog → WARN "not in <host> catalog"
- `visibility: hide` → WARN "hidden in <host> catalog"
- `upgrade` present → WARN naming the replacement and `retirement_at`, plus a copy-pasteable config line (`orchestration.model_hints.codex.coding = "gpt-5.6-sol"`)
- otherwise OK

Hosts without a catalog probe, a missing binary, a non-zero exit, a timeout or an unparseable/changed JSON shape each yield one informational "catalog unavailable" row; the check never fails the doctor run. With no `model_hints` configured, the section prints a single "none configured" row.

## Motivation

EPIC-3563 decided against runtime catalog probes and heuristics (second-opinion consult, 2026-09-28): a run-time heuristic is a silent fallback by another name and breaks run reproducibility. That leaves user config as the only path on non-Claude hosts. This check gives config a staleness detector, which also removes the reason seeded/suggested config values were rejected earlier (no update path once copied).

## Proposed Solution

Follow the advisor section pattern in `little_loops.cli.doctor` (`_advisor_data` → `_print_advisor_section` → `@register_check _advisor_check`):

- `_model_hints_data() -> list[dict]` — no-arg, sources `BRConfig(Path.cwd()).orchestration.model_hints`; per catalog-capable backend, calls a probe; emits rows with `name`, `status`, `severity`, `note`.
- `_probe_codex_catalog() -> dict[str, dict] | None` — runs the Codex binary via `resolve_host_named("codex")` (never a `"codex"` literal; see Host CLI Abstraction) with args `debug models`, short timeout, returns `{slug: entry}` or `None` on any failure. Memoize like `_probe_advisor_version`.
- Keep the probe table keyed by backend so a second host can register a catalog probe later without touching the row logic.
- Severity: WARN rows are `warning`; unavailable rows are `informational`.

`codex debug` is a debug subcommand with no stability promise. The probe must treat any schema surprise as "catalog unavailable", and tests must pin the parsed fields (`slug`, `visibility`, `upgrade.model`, `upgrade.retirement_at`) with a fixture, not the live binary.

## Impact

- **Priority**: P3 — no shipped loop declares `model_hint` today; this is the safety net for users who configure non-Claude hints.
- **Effort**: Small — one doctor section on an existing pattern plus fixtures.
- **Risk**: Low — read-only diagnostic; the unstable `codex debug` surface is contained to "catalog unavailable".
- **Breaking Change**: No.

## Scope Boundaries

- **In**: doctor-only check; Codex catalog probe; row/print/register wiring; docs row in `docs/reference/CLI.md` (`ll-doctor`) and a note in `docs/reference/CONFIGURATION.md` (`orchestration.model_hints`).
- **Out**: any use of the catalog during `ll-loop run` or `ll-loop validate`; auto-writing config; models.dev or other network catalogs; built-in non-Claude mappings (see the Codex host-default issue).

## Acceptance Criteria

- [ ] `ll-doctor` prints a Model hints section; `--json` includes its rows.
- [ ] Fixture-driven tests cover: OK slug, unknown slug, hidden slug, upgraded slug (replacement + date + suggested config line in the note), no `model_hints` configured, binary missing, non-zero exit, timeout, malformed JSON, missing `models` key.
- [ ] No failure path raises out of the check or changes the doctor exit code.
- [ ] Codex binary resolved through `host_runner`, not a string literal.

## Status

**Open** | Created: 2026-09-28 | Priority: P3
