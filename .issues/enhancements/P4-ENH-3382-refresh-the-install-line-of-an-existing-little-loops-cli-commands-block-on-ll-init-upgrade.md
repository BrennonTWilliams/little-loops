---
id: ENH-3382
type: ENH
title: Refresh the Install line of an existing little-loops CLI Commands block on
  ll-init --upgrade
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-03'
captured_at: '2026-09-03T01:47:09Z'
depends_on:
  - BUG-3380
---

# ENH-3382: Refresh the Install line of an existing little-loops CLI Commands block on ll-init --upgrade

## Summary

`write_claude_md()`, `write_agents_md()`, and `write_gemini_md()`
(`scripts/little_loops/init/writers.py`) return `False` without touching the
file whenever the `## little-loops` section marker is already present, and
nothing in `ll-init --upgrade`, `ll-init apply`, or `skills/update/SKILL.md`
refreshes the existing `## little-loops CLI Commands` block. BUG-3380 fixes
the `Install:` line for *newly generated* blocks only; every consumer that
ran `ll-init` before that fix keeps the wrong
`pip install -e "./scripts[dev]"` line, and re-running `ll-init` does not
correct it.

## Current Behavior

Each writer checks `_CLAUDE_MD_SECTION_MARKER in existing` and returns
`False` early. The block (command list + `Install:` line) is never rewritten
once present, so stale command descriptions and a stale `Install:` line
persist indefinitely.

## Expected Behavior

On `ll-init --upgrade` (and the `requested_upgrade` plan flag in `apply`),
an existing `## little-loops CLI Commands` block is replaced in place with the
freshly rendered block for the current `install_source`/`install_path`
(per the BUG-3380 Expected Behavior table). The rewrite is bounded to the
block: from the `## little-loops CLI Commands` heading to the next `## `
heading or EOF. User content outside the block is untouched. Plain
`ll-init` (no `--upgrade`) keeps today's idempotent no-op so it never
surprises a user who hand-edited the block.

## Proposed Solution

Add a `refresh: bool = False` keyword to the three writers; when set and the
marker is present, splice the newly rendered block over the existing one
instead of returning `False`. Pass `refresh=upgrade` from `_run_yes()` and
`refresh=bool(plan.get("requested_upgrade"))` from `_run_apply()`. Mirror
the existing per-writer tests in `scripts/tests/test_init_core.py`
(`TestWriteClaudeMd`, `TestWriteAgentsMd`) with a refresh case that asserts
the old `Install:` line is gone, the new one is present, and surrounding
user content is byte-identical.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- **Splice start must be line-anchored, not the marker hit.** `_CLAUDE_MD_SECTION_MARKER` is `"## little-loops"` (writers.py:156) and the writers test it with bare `in` (:622, :690, :742). The refresh must find the `## little-loops CLI Commands` heading at the start of a line (or at offset 0) to bound the rewrite; the marker's substring position is not a safe start offset. Whatever bound is chosen must still satisfy the issue's stated scope: heading through the next `## ` heading or EOF, user content outside byte-identical.
- **Marker present but canonical heading absent is a real, tested state.** `test_noop_when_section_present_in_root_claude_md` (test_init_core.py:1506) plants `"## little-loops section here."` and expects `False`. With `refresh=True` and no `## little-loops CLI Commands` line to splice over, the writer needs a defined outcome (leave untouched and return `False` is the only choice that keeps every existing noop test green); that outcome should be pinned by a test, since nothing in the issue currently states it.
- **The rendered block carries its own surrounding newlines.** `_render_commands_block()` (writers.py:268-280) returns `"\n## little-loops CLI Commands\n…Install: `…`\n"`. The append path composes `existing.rstrip("\n") + "\n" + block` (:631, :699, :751). A splice that drops in the raw block after removing `[heading_start, next_h2_or_eof)` must strip or account for the block's leading `\n`, or the blank line above the heading doubles on every `--upgrade`; the refresh must be idempotent (a second `--upgrade` is a byte-for-byte no-op).
- **`dry_run` ordering.** Today the marker check precedes the `dry_run` branch, so `--dry-run` on an existing block prints nothing and returns `False` (`test_dry_run_noop_when_section_present`, test_init_core.py:1532). With `refresh=True` and `dry_run=True` the writer must not write; it should report the would-be refresh through `info(...)` the same way the append/create dry-run branches do (`info(f"update {rel} (append ## little-loops CLI Commands)")`) and return `True`. The existing dry-run noop test must stay green for `refresh=False`.
- **No reusable splice primitive; a precedent exists.** `sync_to_local_md()` (`scripts/little_loops/decisions_sync.py:48-57`) does the same heading-bounded replace inline for `## Active Rules`. Searched by name (`_replace_section`, `replace_section`, `_splice_section`, `splice_section`) and by capability across `scripts/little_loops/` — no shared helper. Three near-identical writers each needing the same splice is the consolidation pressure point; a single private helper in `writers.py` avoids three copies, but extracting `decisions_sync`'s version is out of this issue's scope.
- **The TUI caller is covered by the default.** `_apply_config()` (tui.py:900/905/909) calls all three writers without `dry_run` or any upgrade signal; the TUI redirects to `ll-init --upgrade` for refreshes (tui.py:257). No TUI change is required for the stated scope, and none should be made silently.
- **Both CLI callers already have the right install values in hand.** `_run_yes()` resolves `install_source`/`install_path` at cli.py:536 (after any `--upgrade`-driven pip install/upgrade at :539-606, which can flip `install_source` from `None` to `"pypi"` at :546) and `_run_apply()` at cli.py:911, both before their writer calls (:707-728, :942-963). A `refresh` kwarg needs no additional plumbing to render the correct `Install:` line.
- **`apply` may run on a plan without `requested_upgrade`.** `_run_apply()` accepts either a full plan or a bare config dict (`config = plan.get("proposed_config") or plan`, cli.py:900) and `plan.get("requested_upgrade")` (:974) is simply `None` when absent. `refresh=bool(plan.get("requested_upgrade"))` is therefore safe for both shapes.
- **`--upgrade` currently means two things; this adds a third.** In `_run_yes()`, `upgrade` gates package auto-install/auto-upgrade (cli.py:539-606) and `_dispatch_host_upgrade()` (:730-733). `docs/guides/GETTING_STARTED.md:101` enumerates those; the commands-block refresh must be added there and to `docs/reference/CLI.md` (`ll-init` at :35-84) or the flag's documented contract lags the code.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- All anchors below were confirmed against the working tree at refine time (BUG-3380's uncommitted changes to `writers.py`/`cli.py` included); the graph index was stale, so every seed was re-verified by grep.

### Files to Modify
- `scripts/little_loops/init/writers.py` — the three writers `write_claude_md()` (:585-642), `write_agents_md()` (:651-710), `write_gemini_md()` (:713-761). Each short-circuits on `if _CLAUDE_MD_SECTION_MARKER in existing: return False` (:622, :690, :742) **before** the `dry_run` branch, so today the noop fires identically with or without `--dry-run`. The three differ only in target resolution: `.claude/CLAUDE.md` → `CLAUDE.md` → default `.claude/CLAUDE.md` (:611-616); AGENTS.md under the `.kimi-code` directory → root `AGENTS.md` → default root `AGENTS.md` (:679-684); fixed `GEMINI.md` (:737). `write_claude_md` passes `_CLAUDE_MD_DESC_OVERRIDES` to the renderer (:627-629, :637-639); the other two use default descriptions.
- `scripts/little_loops/init/cli.py` — `_run_yes()` (def :468, `upgrade: bool = False` at :476) calls the writers at :707/:714/:723; `_run_apply()` (def :849, not :837 as cited in Program Design → Call Path) calls them at :942/:949/:958. Both already resolve `install_source, installed_version, install_path = detect_installation(project_root)` before the writer calls (:536 and :911, the latter carrying a BUG-3380 comment), so a refresh renders with post-upgrade install values without extra plumbing.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/init/cli.py` — `main_init()`'s `--upgrade` argparse help string (`"Act on version drift automatically (install or upgrade). Default headless behaviour is warn-only."`) and its "Scope of `--force`" epilog text (`"Does NOT rewrite a ## little-loops section already present in CLAUDE.md/AGENTS.md."`) both describe the pre-refresh contract and go stale once `--upgrade` also splices the commands block. Neither is mentioned in Program Design or Implementation Steps, which cite only `_run_yes()`/`_run_apply()`. [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/tui.py:900,905,909` — `_apply_config()` (def :821) is a **third caller** of all three writers, not mentioned in the issue. Its signature has no `upgrade`/`refresh`/`dry_run` parameter and the TUI never performs an upgrade inline; its only upgrade notion is the Screen-1 hint `console.print("  Refresh: [cyan]ll-init --upgrade[/cyan]")` (tui.py:257) that redirects to the headless CLI. A defaulted `refresh=False` kwarg leaves this caller's behavior unchanged, which is the intent.
- `scripts/little_loops/init/__init__.py:20`, `scripts/little_loops/cli/verify_cli_allowlist.py:23`, `scripts/tests/test_deploy_issue_templates.py:9` — import from `writers`; none call the three writers.
- `_dispatch_host_upgrade()` (cli.py:234-285) is the existing `--upgrade`-only refresh path (runs at cli.py:730-733 and :974-975 when `upgrade and not dry_run` / `plan.get("requested_upgrade") and not dry_run`). It force-regenerates hook adapters and the Claude Code plugin; it does **not** touch CLAUDE.md/AGENTS.md/GEMINI.md and the writers are not in its dispatch table. The two paths stay disjoint.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_init_tui.py` — `TestApplyConfigInstallSource` (:1263-1330) is a **fourth caller site to test** (not a fourth production caller): it calls `_apply_config()` directly and asserts `Install:` line content, but never passes/asserts a `refresh` argument since `_apply_config()` has none. Not previously listed as a test for the `_apply_config()` no-op-stays-`False` guarantee. [Agent 1 / Agent 3 finding]

### Conventions in Force
- The marker constant is `_CLAUDE_MD_SECTION_MARKER = "## little-loops"` (writers.py:156) — the short prefix, not the full `## little-loops CLI Commands` heading — and the presence check is a bare `str in str`, not line-anchored. `TestWriteClaudeMd::test_noop_when_section_present_in_root_claude_md` (test_init_core.py:1506-1510) deliberately plants `"## little-loops section here."` and asserts `False`, so the loose match is a tested contract. A refresh splice therefore cannot reuse the marker's `in` hit as its start offset; it must locate the heading at a line start, and must decide what to do when the marker matches but the canonical `## little-loops CLI Commands` heading line is absent (see Proposed Solution findings).
- `_render_commands_block()` (writers.py:268-280) returns a block that **starts with `\n`** (`lines = ["", "## little-loops CLI Commands", ""]`) and **ends with `\n`**, contains exactly one `##` heading and no nested `###` headings. The append path relies on this: `new_content = existing.rstrip("\n") + "\n" + block` (:631, :699, :751) yields exactly one blank line before the heading. A splice that reuses the rendered block as-is must account for its leading `\n` so it neither doubles nor drops the blank line above the heading.
- Heading-bounded in-place section replacement already exists inline in `sync_to_local_md()` (`scripts/little_loops/decisions_sync.py:31-57`): `idx = content.rfind("## Active Rules\n")`, `end = content.find("\n##", idx + 1)`, `content[:idx] + section + (content[end:] if end != -1 else "")`. It is not extracted as a reusable helper — no `_replace_section`/`splice_section`-shaped function exists anywhere in the repo (searched by name and by capability: text + heading in, text with that section replaced out). Note its `"\n##"` boundary also stops at `###`/`####` lines, which is broader than this issue's stated "next `## ` heading" (H2 with trailing space) bound; the two are only equivalent because the commands block has no sub-headings.
- The hook-adapter writers in the same file version-stamp their output (`_KIMI_GEN_VERSION_PREFIX`, `_QWEN_GEN_MARKER`, `_GEMINI_GEN_MARKER`) and use the stamp to decide replace-vs-current; the commands-block writers carry no stamp and use marker presence as their entire idempotency contract. The issue's flag-gated approach keeps that contract; it does not introduce a stamp.

### Tests
- `scripts/tests/test_init_core.py` — `TestWriteClaudeMd` (:1445), `TestWriteAgentsMd` (:1597), `TestWriteGeminiMd` (:1724). Every "section present" test asserts `result is False` and/or unchanged mtime: `test_noop_when_section_present_in_dot_claude_md` (:1497), `test_noop_when_section_present_in_root_claude_md` (:1506), `test_dry_run_noop_when_section_present` (:1532), `test_noop_when_section_present` (:1639, :1757), `test_idempotent_second_run` (:1647, :1765). None exercise a replace path; all must keep passing with the kwarg defaulted off.
- `_run_yes()`/`_run_apply()` have no direct-call tests; all `--upgrade` coverage drives them through `main_init(argv)`: `test_yes_upgrades_when_pypi_stale_with_upgrade_flag` (test_init_core.py:2651), `test_bare_upgrade_implies_yes_never_launches_wizard` (:2681), `test_plan_upgrade_surfaces_requested_upgrade` (:2178, asserts `plan["requested_upgrade"] is True`), and `test_apply_honors_requested_upgrade` / `test_apply_ignores_requested_upgrade_in_dry_run` (`scripts/tests/test_init_audit_fixes.py:488`, :505 — both patch `little_loops.init.cli._dispatch_host_upgrade`). A caller-level refresh test follows the same `main_init([...])` shape.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_init_tui.py::TestApplyConfigInstallSource` (:1263-1330) — owns the only existing `_apply_config()`-calling fixture/helper (`self._apply(...)`, :1268-1281). The natural place for a regression test seeding a stale `Install:` line and asserting it survives `_apply_config()` unchanged (proving the TUI path never refreshes, per Scope Boundaries). [Agent 3 finding]
- `scripts/tests/test_decisions.py::TestSyncToLocalMd` (:491-631) — direct test precedent for the heading-bounded splice this issue adds: `test_replaces_existing_section` (:519) and `test_replaces_last_active_rules_section_when_multiple_present` (:604) are the closest existing model for "old text gone, new text present, content before the section preserved verbatim." Its `"\n##"` boundary (any `##`/`###`/`####` line) is broader than this issue's "next `## ` heading" (H2 only) bound — already flagged in Conventions in Force — so a mirrored test must assert the narrower boundary, not copy the precedent's boundary claim. [Agent 3 finding]
- No fixture/constant for a "stale pre-BUG-3380 `Install:` line" exists anywhere in `scripts/tests/`; every writer test constructs pre-existing content inline via `dest.write_text(...)`. New refresh tests follow that same inline convention rather than importing a shared builder. [Agent 3 finding]

### Documentation
- `docs/guides/GETTING_STARTED.md:101` — describes what `--upgrade` refreshes today (host adapters, plugin); the commands block is not listed.
- `docs/reference/CLI.md:35-84` — `ll-init` section; `ll-init --yes --upgrade` example at :84.
- `skills/update/SKILL.md` — despite the Summary naming it, this skill only wraps `claude plugin update` / `pip install --upgrade` and never references the writers or the marker; it is not a code path this issue changes.

_Wiring pass added by `/ll:wire-issue`:_
- `skills/init/SKILL.md` § "5. Handle `--upgrade`" (~lines 106-115) — states today's narrower contract in prose: "`ll-init apply` honors `requested_upgrade` in the plan by refreshing host adapters after the writes, but it does not upgrade the package or plugin itself." This sentence goes stale once `requested_upgrade` also drives the commands-block splice via `refresh=`. A separate doc surface from `GETTING_STARTED.md`/`CLI.md`. [Agent 1 / Agent 2 finding]
- `CHANGELOG.md` — no entry is currently planned; per project convention (entries promoted into a concrete `## [X.Y.Z] - DATE` section, never `[Unreleased]`) this needs a `**ENH-3382**: ...` bullet under `### Changed` in the next release section during release prep. [Agent 2 finding]

## Program Design

### Signatures

- `write_claude_md(project_root: Path, dry_run: bool = False, install_source: str | None = None, install_path: str | None = None, refresh: bool = False) -> bool`
- `write_agents_md(project_root: Path, dry_run: bool = False, install_source: str | None = None, install_path: str | None = None, refresh: bool = False) -> bool`
- `write_gemini_md(project_root: Path, dry_run: bool = False, install_source: str | None = None, install_path: str | None = None, refresh: bool = False) -> bool`

### Call Path

`_run_yes()` (`scripts/little_loops/init/cli.py:468`) -> `write_claude_md(..., refresh=upgrade)` -> `_render_commands_block()` (`scripts/little_loops/init/writers.py:268`)

`_run_apply()` (`scripts/little_loops/init/cli.py:849`) -> `write_claude_md(..., refresh=bool(plan.get("requested_upgrade")))` -> `_render_commands_block()`

### Splice Helper

One private helper in `writers.py` shared by all three writers, so the splice is written once:

- `_splice_commands_block(existing: str, block: str) -> str | None` — returns the new file text, or `None` when no line-anchored `## little-loops CLI Commands` heading is present. Locates the heading by comparing each line's `rstrip()` to the canonical heading (so trailing whitespace and CRLF files still match); region runs from that line through the character before the next line starting with `## ` or EOF; replacement is `block.lstrip("\n")`, plus a single `"\n"` separator when a following heading exists so the blank line above the next section is preserved.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- Call Path line references are stale in this section: `_run_apply()` is defined at `scripts/little_loops/init/cli.py:849` (not :837); the writer call sites are `write_claude_md` at cli.py:707 (`_run_yes`) and :942 (`_run_apply`), `write_agents_md` at :714/:949, `write_gemini_md` at :723/:958. `_run_yes()` is at :468 as cited.
- Third caller omitted from Call Path: `_apply_config()` (`scripts/little_loops/init/tui.py:821`) -> `write_claude_md(project_root, install_source=..., install_path=...)` (tui.py:900) / `write_agents_md` (:905) / `write_gemini_md` (:909) — no `refresh` argument; relies on the default `False`.
- Existing writer signature (all three): `(project_root: Path, dry_run: bool = False, install_source: str | None = None, install_path: str | None = None) -> bool`. Return contract today: `True` = wrote or would-write (dry-run), `False` = marker already present. The `refresh=True` branch extends the `True` meaning to "replaced or would-replace"; the marker-present-but-no-canonical-heading case has no defined return value yet (see Proposed Solution findings).
- Renderer signature the splice consumes: `_render_commands_block(install_source: str | None, install_path: str | None, project_root: Path, desc_overrides: dict[str, str] | None = None) -> str` (writers.py:268). Its output begins with `"\n"` and ends with `"\n"`.
- Splice precedent signature: `sync_to_local_md(path: Path | None = None) -> None` (`scripts/little_loops/decisions_sync.py:31`), with bounding `rfind("## Active Rules\n")` / `find("\n##", idx + 1)` at :48-57. Not reusable as-is (no text-in/text-out shape).
- Types: no new data shapes; one new `bool` keyword on three functions.

### Decision Rules
- New gate: refresh fires only when `refresh is True` **and** the canonical `## little-loops CLI Commands` heading is found at a line start in `existing`. Inputs: `refresh: bool`, `existing: str`. Bound: from that heading line through the character before the next line starting with `## ` (H2, trailing space) or EOF. Escape hatch: `refresh=False` (the default, and what plain `ll-init` and the TUI pass) preserves the current marker-present noop exactly.
- **Blank-line separator is preserved.** The region above swallows any blank lines between the old block and the next `## ` heading, and the rendered block ends with exactly one `\n` after the `Install:` line. The splice therefore re-emits one `"\n"` after the block whenever a following heading exists; otherwise the result reads `Install: \`…\`\n## Next Section` with no blank line. The idempotency fixture must place a user section *after* the block so this is exercised.
- **No-op refresh returns `False` and does not write.** When the spliced text equals `existing` byte-for-byte (block already current), the writer returns `False` without calling `atomic_write` and without emitting `info(...)`, mirroring the existing "unchanged mtime" contract. Otherwise every `--upgrade` prints three spurious `update …` lines and bumps three mtimes. Pinned by a test asserting mtime unchanged and `False` on the second refresh.
- **Heading match tolerates trailing whitespace and CRLF.** The heading is located by `line.rstrip() == "## little-loops CLI Commands"`, not by searching for `"## little-loops CLI Commands\n"`. Otherwise a CRLF file silently falls into the marker-present-no-heading branch and is never refreshed. The rest of the file's line endings are not normalized.
- **Hand edits inside the block are discarded.** `--upgrade` replaces the block wholesale; customized descriptions or notes placed under the `Install:` line are lost. This is deliberate (the block is generated content, and refresh is opt-in via `--upgrade`), and must be stated in the `--upgrade` help text and the GETTING_STARTED row rather than left implicit.

## Scope Boundaries

- **In scope**: `write_claude_md()`, `write_agents_md()`, `write_gemini_md()` gaining a `refresh` kwarg; `_run_yes()` and `_run_apply()` passing `refresh` from `upgrade`/`plan["requested_upgrade"]`; splicing the block bounded from the `## little-loops CLI Commands` heading to the next `## ` heading or EOF.
- **Out of scope**: changes to `_render_commands_block()` itself (BUG-3380 already owns the per-`install_source` `Install:` line); refreshing any other CLAUDE.md/AGENTS.md/GEMINI.md content outside the marked block; behavior of plain `ll-init` without `--upgrade` (stays a no-op); preserving hand edits made inside the block (the block is generated content and is replaced wholesale on `--upgrade`); normalizing line endings of the surrounding file; extracting `decisions_sync.sync_to_local_md()`'s inline splice into a shared helper.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-03 — based on codebase analysis:_

- Each of `write_claude_md()`, `write_agents_md()`, `write_gemini_md()` (`scripts/little_loops/init/writers.py:585-761`) accepts `refresh: bool = False`; with it off, every existing `TestWriteClaudeMd`/`TestWriteAgentsMd`/`TestWriteGeminiMd` case in `scripts/tests/test_init_core.py:1445-1821` passes unchanged.
- A single private `_splice_commands_block(existing, block) -> str | None` helper in `writers.py` (see Program Design → Splice Helper) implements the heading-bounded replace once; the three writers call it rather than each carrying its own copy.
- With `refresh=True` and the canonical heading present, the region from `## little-loops CLI Commands` (line-anchored, matched via `rstrip()` so trailing whitespace/CRLF still hit) to the next `## ` heading or EOF is replaced by the output of `_render_commands_block()` for the supplied `install_source`/`install_path`, with its leading `\n` stripped and one `\n` separator re-emitted before a following heading; content before and after the region is byte-identical; a second refresh with the same inputs returns `False`, does not write, and leaves mtime unchanged. Verified by a per-writer test placed alongside the existing noop tests whose fixture has a user `## ` section *after* the block and asserts the old `Install:` line is gone, the new one is present, surrounding content (including the blank line before the following section) is unchanged, and the second refresh is a `False`/unchanged-mtime no-op.
- A CRLF-file case (`"## little-loops CLI Commands\r\n"`) is refreshed rather than silently skipped; pinned by one test per writer or a parametrized case on the helper.
- With `refresh=True` and the marker present but no canonical heading line (the `"## little-loops section here."` fixture at test_init_core.py:1506), the writer's outcome is defined and tested; the only outcome that keeps that fixture's existing assertion green is unchanged-file, `False`.
- With `refresh=True, dry_run=True` the file is not written and the would-be refresh is reported via `info(...)`; `test_dry_run_noop_when_section_present` (test_init_core.py:1532) keeps passing for the default.
- `_run_yes()` passes `refresh=upgrade` at its three writer calls (`scripts/little_loops/init/cli.py:707-728`) and `_run_apply()` passes `refresh=bool(plan.get("requested_upgrade"))` at :942-963; `_apply_config()` (tui.py:900-909) is left untouched. Covered by a `main_init(["--yes", "--upgrade", ...])`-driven test next to `test_yes_upgrades_when_pypi_stale_with_upgrade_flag` (test_init_core.py:2651) and an apply-side test next to `test_apply_honors_requested_upgrade` (`scripts/tests/test_init_audit_fixes.py:488`), each seeding a stale `Install:` line and asserting the refreshed one; a no-`--upgrade` counterpart asserts the stale line survives.
- `docs/guides/GETTING_STARTED.md:101` and `docs/reference/CLI.md` (`ll-init`, :35-84) state that `--upgrade` also refreshes the commands block in CLAUDE.md/AGENTS.md/GEMINI.md, and say explicitly that the block is replaced wholesale (hand edits inside it are not preserved).
- Dry-run message for the refresh path: `info(f"update {rel} (refresh ## little-loops CLI Commands)")`, distinct from the append path's `(append …)` wording so `--dry-run` output distinguishes the two.
- `python -m pytest scripts/tests/test_init_core.py scripts/tests/test_init_audit_fixes.py` exits 0.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `skills/init/SKILL.md` § "5. Handle `--upgrade`" — reflect that `requested_upgrade` now also drives the commands-block refresh, not just host adapters
- Update `scripts/little_loops/init/cli.py::main_init()` — the `--upgrade` argparse help string (:1105-1110) and the "Scope of `--force`" epilog text (:1019, `"Does NOT rewrite a ## little-loops section already present…"`), both of which currently state the pre-refresh contract; the `--upgrade` help must mention that the commands block is replaced wholesale
- Add `scripts/tests/test_init_tui.py::TestApplyConfigInstallSource` — a regression test seeding a stale `Install:` line and asserting it survives `_apply_config()` unchanged (TUI path stays `refresh=False`)
- Add `**ENH-3382**: ...` under `### Changed` in `CHANGELOG.md` during release prep

## Impact

- **Priority**: P4 - Cosmetic drift (stale `Install:` line) with a manual `--upgrade` workaround already available; not blocking.
- **Effort**: Small - One new kwarg threaded through three near-identical writer functions plus two call sites; mirrors the existing `_render_commands_block()` call already in each writer.
- **Risk**: Low - Rewrite is bounded to the marked block via existing heading-detection logic; gated behind explicit `--upgrade`/`requested_upgrade` so default `ll-init` behavior is unchanged.
- **Breaking Change**: No - Default `refresh=False` preserves current idempotent behavior; only `--upgrade` callers see the new rewrite.

## Related

- Follow-up to BUG-3380 (per-`install_source` `Install:` line for newly
  generated blocks). Depends on it: the refreshed block must render through
  the same `install_source`/`install_path`-aware `_render_commands_block()`.

## Status

**Open** | Created: 2026-09-03 | Priority: P4


## Review Notes

_Pre-implementation review — 2026-09-02:_

- BUG-3380 is `done` (commit `28a49a9de`), so the `depends_on` edge resolves; the issue is unblocked.
- Four spec gaps were folded into Decision Rules / Implementation Steps: the splice boundary swallowed the blank line before the next `## ` heading; the no-op refresh return value was undefined (now `False`, no write); a CRLF/trailing-whitespace heading would silently miss the line-anchored match; and wholesale replacement of hand-edited blocks was implicit rather than stated in docs/help text.
- Program Design → Call Path `_run_apply()` line ref corrected from :837 to :849; a named `_splice_commands_block()` helper was added so the three writers share one splice.

## Session Log
- `/ll:wire-issue` - 2026-09-03T02:24:32 - `0ede70ea-abc7-4e95-bfe6-24a012dc95a9.jsonl`
- `/ll:refine-issue` - 2026-09-03T02:12:23 - `530a68c3-069b-4c6c-b3fd-b695a90a9e2c.jsonl`
- `/ll:format-issue` - 2026-09-03T02:02:58 - `1a5710fd-de34-4cc6-b93d-c2bb79974725.jsonl`
