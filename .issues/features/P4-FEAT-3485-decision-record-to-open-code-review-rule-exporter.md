---
id: FEAT-3485
type: FEAT
title: Decision-record to open-code-review rule exporter
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-16'
captured_at: '2026-09-16T04:15:42Z'
learning_tests_required:
- open-code-review
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-3485: Decision-record to open-code-review rule exporter

## Summary

Export active required decision rules into open-code-review's (OCR, https://github.com/alibaba/open-code-review) `.opencodereview/rule.json`, so OCR's shipped review plugins enforce little-loops decisions mechanically at review time. Decisions are currently recorded but enforced only through prose (`.claude/CLAUDE.md`, and the `## Active Rules` block that `sync_to_local_md` writes into `.ll/ll.local.md`).

This is piece 1 of a two-piece OCR integration; piece 2 (a delegate-mode review loop that runs `ocr delegate preview` / `ocr delegate rule` as FSM shell states) is planned separately and consumes the same `rule.json`.

**Design stance (revised 2026-09-16):** OCR is not the first rule-export target — `sync_to_local_md()` (`scripts/little_loops/decisions_sync.py:31`) already is one, rendering active required `RuleEntry`s to Claude Code's rule surface. This issue therefore (a) extracts the rule-selection step both exporters share, (b) adds the one genuinely target-agnostic field the rules are missing (a path scope), and (c) adds OCR as a second thin exporter. It does **not** introduce a new intermediate `RuleRecord` type or a lazy-import registry — `RuleEntry` is already the IR, and the `adapters/core.py`-style registry waits for a third target (rule of three).

**Interface vs. implementation (revised 2026-09-16, review):** the *implementation* stays OCR-specific (grouping/folding logic is a consequence of OCR's first-match-wins semantics and would not be shared by per-file targets like Cursor `.mdc` or Copilot `applyTo:`), but the *user-facing surfaces* are target-keyed from day one because they are expensive to rename later (CLI subparser, docs table, config schema, `ll-adapt` mirror gates):

- CLI is `ll-issues decisions export --target ocr`, not `export-ocr`. A third target is a new choice value, not a new subcommand.
- Config key is `decisions.export.scope_globs` (target-agnostic; scope is meaningful for every target), with any future OCR-only knobs under `decisions.export.ocr.*`.
- `decisions_export.py` exposes `export_rules(rules, target, output_dir, *, scope_globs)` dispatching over a plain `_EXPORTERS: dict[str, Callable]` with one entry. Five lines, eager imports, no Protocol.

Do **not** fold this into the `ll-adapt` host emitters: OCR is a review tool, not a host, and `sync_to_local_md` has different semantics (patches a section of an existing file, auto-runs on `promote`). Sharing the selector is the right amount of coupling.

## Current Behavior

Decisions are recorded via `ll-issues decisions` (`.ll/decisions.yaml` / `.ll/decisions.d/`). The only programmatic consumer that renders them outward is `sync_to_local_md()`, which inlines the selection logic (list `type="rule"` → keep `enforcement == "required"` → `resolve_active()`) and writes free-text bullets to `.ll/ll.local.md`. Nothing consumes decision records during code review, and `RuleEntry` has no way to say which files a rule applies to.

## Expected Behavior

`ll-issues decisions export --target ocr` writes `.opencodereview/rule.json` covering all active (non-superseded) required rules, correctly shaped for OCR's first-match-wins resolution, so OCR flags violations without an agent recalling the prose. Re-running over an unchanged decision set is a no-op on file content.

## Motivation

- Closes the loop between recording a decision and enforcing it mechanically.
- Removes reliance on agent recall for checkable rules.
- Fixes the pre-existing duplication risk: a second exporter that re-inlines `sync_to_local_md`'s selection logic would drift from it. Sharing one selector makes "what counts as an exportable rule" a single definition.
- Establishes the `rule.json` shape piece 2 consumes.

## Proposed Solution

Three layers, sized to the problem:

1. **Shared selector (target-agnostic, refactor of existing code).** Add `active_required_rules(path: Path | None = None) -> list[RuleEntry]` to `scripts/little_loops/decisions.py`, lifting the three-step filter out of `sync_to_local_md()` (`decisions_sync.py:40-45`) and making `sync_to_local_md` call it. Output order must be deterministic (stable on `timestamp`, then `id`) so every exporter is idempotent for free.

2. **Path scope on the rule itself (target-agnostic, small schema addition).** Add `paths: list[str] = field(default_factory=list)` to `RuleEntry` (`decisions.py:106`), round-tripped in `from_dict`/`to_dict`; empty means repo-wide. Expose it on `ll-issues decisions add --type rule` and `promote` as a repeatable `--path <glob>` flag. This is the only field the current model lacks that *every* plausible rule-engine target needs (OCR `path`, Cursor `.mdc` `globs:`, Copilot `applyTo:`). Do **not** add `severity`: OCR has no severity field, `enforcement` already gates inclusion, and no target consumes a graded value.

3. **Target-keyed exporter seam + OCR exporter.** New module `scripts/little_loops/decisions_export.py` holding:
   - `export_rules(rules: list[RuleEntry], target: str, output_dir: Path, *, scope_globs: list[str] | None = None) -> Path` — public entry point; looks up `target` in `_EXPORTERS: dict[str, Callable[..., Path]]` and raises `ValueError` listing `sorted(_EXPORTERS)` on an unknown target.
   - `_export_ocr(rules, output_dir, *, scope_globs) -> Path` — the only OCR-specific code; written via `atomic_write_json()`.
   - `_EXPORTERS = {"ocr": _export_ocr}` — plain eager dict. A future Cursor/Copilot exporter is one private function plus one dict entry. No `Protocol`, no `importlib`; the `adapters/core.py` lazy-map pattern is reserved for a third target *and* an actual import cycle.

### OCR emission rules (correctness, not cosmetics)

Proven in `.ll/learning-tests/open-code-review.md` (`status: proven`): `rule.json` = `{"exclude"?: string[], "rules": [{"path": <one glob>, "rule": <free text>}, ...]}`; the **first** `rules[]` entry whose glob matches a file wins, by declaration order, not specificity; a matching project entry **replaces** OCR's embedded system rules (e.g. `python.md`) for that file; no severity field exists.

Consequences the adapter must implement:

- **N repo-wide rules cannot be N entries.** Only the first `**/*` entry would ever fire. Group rules by path glob; emit one `rules[]` entry per distinct glob, most specific first (fewest wildcards / longest literal prefix, then lexical for determinism); each scoped entry's `rule` body = that glob's rules **plus all repo-wide rules**, since first-match shadows anything later; the final catch-all entry holds the repo-wide set alone.
- **A catch-all entry disables OCR's built-in language rules.** Default `scope_globs` to the project's `src_dir` from `.ll/ll-config.json` (e.g. `scripts/**/*`) rather than `**/*`, and prepend a fixed line to every emitted body reminding the reviewer that OCR's system rules for the file's language still apply. Piece 2 can override `scope_globs` if it wants true repo-wide coverage.
- **Rule body format** per entry: one bullet per rule, `- <rule text> (decision <id>)`, so review output is traceable back to the record. `rationale` is omitted (keeps bodies short; the id is the pointer).
- **Don't emit `exclude`.** It only gates `ocr review --preview` file selection and is a project-level choice, not a decision.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-16 — based on codebase analysis (retained, condensed):_

- Two canonical-form-plus-adapter precedents exist: `host_runner.py`'s `resolve_host()` (single file, eager `dict[str, type]` registry) and `adapters/core.py`'s `resolve_emitter()` (one file per target, lazy `importlib`, existing **only** to break a real circular import per its docstring at `:47-52`). Neither cycle exists here, so a single eager module is correct; the lazy pattern is the model for a registry *if and when* a third target appears.
- `resolve_active()` (`decisions.py:495-503`) is a pure set-membership filter: it drops any entry whose `id` appears in another entry's `supersedes`. Only `RuleEntry` and `CouplingEntry` carry `supersedes`.
- `CouplingEntry.if_changed` is the only existing glob field, but its semantic ("when X changes, audit Y" via `then_check`) has no `rule.json` equivalent and is out of scope for this exporter.
- `generate_schemas()` (`generate_schemas.py:950-966`) and its `test_idempotent_on_second_run` (`test_generate_schemas.py:179-185`) are the write-then-compare idempotency precedent for Acceptance Criteria #2.

### Decision Rationale

**Selected: single eager module (`decisions_export.py`), `host_runner.py`-style.** Scored 12/12 vs. a two-file lazy-import split's 6/12 on consistency, simplicity, testability, risk. `decisions.py` imports nothing OCR-adjacent and nothing that would import back from the new module, so the only justification for lazy resolution in this codebase (`adapters/core.py`'s confirmed `core.py` ↔ `codex.py` cycle) is absent. Several similarly small modules (`decisions_sync.py`, 57 lines; `fsm/continuity.py`, 65 lines; `pricing.py`, 150 lines) hold multiple functions plus a dataclass in one file with eager imports.

**Rejected: a `RuleRecord` intermediate type.** It would duplicate `RuleEntry`'s fields and add two (`severity`, `path filters`) with no source on `RuleEntry` and, for `severity`, no consumer on any target. Adding `paths` directly to `RuleEntry` gives every exporter the field without a translation layer.

## Verify First

- ~~OCR's actual rule/config format.~~ **Resolved** — proven in `.ll/learning-tests/open-code-review.md` (raw output `.ll/learning-tests/raw/open-code-review.txt`); see "OCR emission rules" above.
- Confirm OCR's glob dialect for `path` (does `scripts/**/*.py` match files directly under `scripts/`? brace sets like `**/*.{py,pyi}` are used by system rules, so they are supported). Extend the learning test with one assertion if the dialect matters for the specificity ordering.

## Integration Map

### Files to Modify
- `scripts/little_loops/decisions.py` — add `paths: list[str]` to `RuleEntry` (`:106`, `from_dict` `:125`, `to_dict` `:145`); add `active_required_rules()` next to `resolve_active()` (`:495`)
- `scripts/little_loops/decisions_sync.py` — replace the inline filter at `:40-45` with `active_required_rules(decisions_path)`; behaviour unchanged
- New `scripts/little_loops/decisions_export.py` — `export_rules()`, `_EXPORTERS`, `_export_ocr()` plus private helpers `_group_by_glob()`, `_glob_sort_key()`, `_render_body()`
- `scripts/little_loops/cli/issues/decisions.py` — `--path` (repeatable, `action="append"`) on `add` (`:116` region) and `promote` (`:270` region); new `export` subparser in `add_decisions_parser()` (`:15`) with required `--target` (`choices` sourced from `decisions_export._EXPORTERS` keys, or a matching literal tuple guarded by a test), `--output-dir`, `--scope`; dispatch branch in `cmd_decisions()` (`:280`), `_cmd_export(path, target, output_dir, scope) -> int` following `_cmd_sync` (`:550`): lazy import in body, stderr + non-zero on failure
- `scripts/little_loops/config-schema.json` — optional `decisions.export.scope_globs: string[]` (defaults to `[<project.src_dir>/**/*]` when absent); reserve `decisions.export.ocr` as an object for future OCR-only knobs but do not add any now; soft — CLI `--scope` flag suffices for AC

### Dependent Files (Callers/Importers)
- `sync_to_local_md()` — the only existing consumer of the selection logic; becomes the first caller of `active_required_rules()`
- `_cmd_promote` (`cli/issues/decisions.py:953`) calls `_cmd_sync` after promoting a required rule; consider also calling `_cmd_export(..., target="ocr", ...)` when `.opencodereview/` already exists (soft, keeps the two surfaces in step)
- Repo-wide grep confirms zero references to `export_rules` / `decisions_export` / `active_required_rules` today

### Similar Patterns
- `decisions_sync.py`'s `sync_to_local_md` — the sibling exporter
- `file_utils.py`'s `atomic_write_json()` (tested via `TestAtomicWriteJson`) — write path
- `adapters/core.py`'s `_EMITTER_MAP` / `HostEmitter` — model for a *lazy* registry only if a third target arrives with an import cycle; `_EXPORTERS` is the eager, minimal form of the same idea

### Tests
- `scripts/tests/test_decisions.py` — `TestRuleEntry` round-trip for `paths` (present, absent, legacy dict without the key); `TestActiveRequiredRules` (advisory excluded, superseded excluded, deterministic order); `TestSyncToLocalMd` (`:491`) unchanged and still green
- New `scripts/tests/test_decisions_export.py` — fixture set with: two repo-wide rules, one `scripts/**/*.py` rule, one superseded rule, one advisory rule. Assert: superseded/advisory absent; exactly one entry per distinct glob; scoped entry listed before catch-all; scoped body contains both its own and the repo-wide rule texts; catch-all body contains only repo-wide; each bullet carries its decision id; second run yields byte-identical file (AC #2); `scope_globs=None` resolves to `src_dir`; `export_rules(..., target="nope", ...)` raises `ValueError` naming `ocr`
- `scripts/tests/test_cli_decisions.py` — `TestDecisionsCLIExport` (`--target ocr` writes file, exit 0; bad output path → exit 1; unknown `--target` → argparse exit 2; missing `--target` → exit 2); `TestDecisionsCLIAdd` gains a `--path` case; `TestDecisionsCLINoSubcommand.test_no_subcommand` unaffected

### Documentation
- `docs/reference/CLI.md` — `ll-issues decisions` table row for `export`, `**export flags:**` subsection (`--target {ocr}`, `--output-dir`, `--scope`), `--path` under add/promote flags, bash example line
- `docs/reference/API.md` — `### active_required_rules`, `### export_rules` (document `_EXPORTERS` as the extension point); note `paths` under `### RuleEntry`
- `docs/guides/DECISIONS_LOG_GUIDE.md` — "Exporting to OCR" section (including the first-match/system-rule-replacement caveats) + ToC entry; mention `--path`
- `docs/ARCHITECTURE.md` — add exporter to "Key consumers" in the Decisions Log section

### Configuration
- `decisions.export.scope_globs` (optional, target-agnostic, see above); `decisions.export.ocr` reserved, empty

### Behavior Parity

The only existing behaviour touched is `sync_to_local_md()` (`scripts/little_loops/decisions_sync.py:31`). After the refactor it must:

- Select exactly the same entries: `type="rule"`, `enforcement == "required"`, not superseded via `resolve_active()`. `active_required_rules()` adds a stable sort; the current implementation preserves `list_entries` order, which is already timestamp order, so rendered bullet order is unchanged for existing logs.
- Render bullets as `- {r.rule}` only — no decision id, no `paths`, no rationale. OCR-style traceability suffixes are OCR-adapter concerns and must not leak into `ll.local.md`.
- Keep the `## Active Rules` replace-or-append logic and `atomic_write` call untouched.
- Guard: `TestSyncToLocalMd` (`scripts/tests/test_decisions.py:491`) passes without modification.

`.ll/learning-tests/open-code-review.md` is read-only input; nothing in it is replaced.

## Program Design

### Types

- `RuleEntry` (existing, `decisions.py:106`) gains `paths: list[str] = field(default_factory=list)`. Empty = repo-wide. This is the exporter IR; no new type.

### Signatures

- `active_required_rules(path: Path | None = None) -> list[RuleEntry]` — `list_entries(path, type="rule")` → keep `enforcement == "required"` → `resolve_active()` → stable sort `(timestamp, id)`. Target-agnostic; shared by `sync_to_local_md` and `export_rules`.
- `export_rules(rules: list[RuleEntry], target: str, output_dir: Path, *, scope_globs: list[str] | None = None) -> Path` — public entry point; `_EXPORTERS[target](rules, output_dir, scope_globs=scope_globs)`, `ValueError` on unknown target.
- `_export_ocr(rules: list[RuleEntry], output_dir: Path, *, scope_globs: list[str] | None = None) -> Path` — groups by glob, orders specific-first, folds repo-wide rules into every scoped body, writes `output_dir / ".opencodereview" / "rule.json"` via `atomic_write_json`, returns the path. `scope_globs` replaces the catch-all `**/*` for repo-wide rules; `None` → `[f"{src_dir}/**/*"]` from config, falling back to `["**/*"]` when no config resolves.

### Call Path

`active_required_rules()` → `export_rules(target="ocr")` → `_export_ocr()` → `.opencodereview/rule.json`
`active_required_rules()` → `sync_to_local_md()` → `.ll/ll.local.md` (existing, now shared)

## Implementation Steps

1. Add `paths` to `RuleEntry` with round-trip tests; add `--path` to `add`/`promote`.
2. Add `active_required_rules()`; refactor `sync_to_local_md()` onto it; confirm `TestSyncToLocalMd` stays green.
3. Implement `decisions_export.py`: `_export_ocr()` with the grouping/ordering/folding logic and `src_dir` default scope, `_EXPORTERS = {"ocr": _export_ocr}`, and `export_rules()` dispatch.
4. Wire `export --target ocr` into `ll-issues decisions` (`choices` from `_EXPORTERS`); optionally call it from `_cmd_promote` when `.opencodereview/` exists.
5. Tests per Integration Map; idempotency check by double-run comparison.
6. Docs per Integration Map; run `ll-adapt --host <gemini|kimi-code|qwen> --apply` if any mirrored surface changed.

## Acceptance Criteria

1. `ll-issues decisions export --target ocr` writes `.opencodereview/rule.json` containing every active required rule and no superseded or advisory rule; an unknown `--target` is rejected by argparse with the valid choices listed, and `export_rules()` raises `ValueError` for the same.
2. Idempotent: re-running over an unchanged decision set produces a byte-identical file.
3. Exactly one `rules[]` entry per distinct path glob; more-specific globs precede the catch-all; every scoped entry's body also contains all repo-wide rules; each bullet carries its decision id.
4. Repo-wide rules are scoped to `src_dir` by default, not `**/*`, and the scope is overridable.
5. `RuleEntry.paths` round-trips through YAML/JSON and legacy entries without the key still load.
6. `sync_to_local_md()` output is unchanged after the refactor onto `active_required_rules()`.

## Priority Rationale

P4 — small, unblocked, first of the two OCR pieces. Slightly larger than the original "few dozen lines" estimate because of the `paths` field and the grouping logic, but still a single-session change.

## Impact

- **Priority**: P4
- **Effort**: Small–medium — ~150 lines plus tests; one schema field addition
- **Risk**: Low — additive; the only touch to existing behaviour is the `sync_to_local_md` refactor, covered by existing tests
- **Breaking Change**: No — `paths` defaults to empty; existing decision files load unchanged

## Related Key Documentation

- `docs/guides/DECISIONS_LOG_GUIDE.md`
- `.ll/learning-tests/open-code-review.md`

## Status

**Open** | Created: 2026-09-16 | Priority: P4

## Use Case

**Who**: A little-loops maintainer running OCR-based code review on this repo.

**Context**: A required rule has been recorded via `ll-issues decisions` but is enforced only through prose.

**Goal**: Run `ll-issues decisions export --target ocr` so OCR checks the rule automatically, scoped to the files it applies to.

**Outcome**: Code review flags violations of active decisions, each traceable to its decision id, without disabling OCR's built-in language rules.

## API/Interface

```python
# decisions.py
@dataclass
class RuleEntry:
    ...
    paths: list[str] = field(default_factory=list)  # empty = repo-wide

def active_required_rules(path: Path | None = None) -> list[RuleEntry]:
    """Active (non-superseded) required rules in deterministic order. Shared by all exporters."""

# decisions_export.py
def _export_ocr(
    rules: list[RuleEntry],
    output_dir: Path,
    *,
    scope_globs: list[str] | None = None,
) -> Path:
    """Write .opencodereview/rule.json. The only OCR-specific function."""

_EXPORTERS: dict[str, Callable[..., Path]] = {"ocr": _export_ocr}

def export_rules(
    rules: list[RuleEntry],
    target: str,
    output_dir: Path,
    *,
    scope_globs: list[str] | None = None,
) -> Path:
    """Dispatch to the exporter registered for `target`; ValueError if unknown."""
```

```bash
ll-issues decisions add --type rule --enforcement required --path 'scripts/little_loops/fsm/**/*.py' ...
ll-issues decisions export --target ocr [--output-dir .] [--scope 'scripts/**/*']
```

## Edge Cases

- No active required rules → write `{"rules": []}` (valid, idempotent) rather than deleting the file.
- Same glob on several rules → one entry, bullets in selector order.
- A rule with multiple `paths` → its text appears in each glob's entry.
- `src_dir` missing from config and no `--scope` → fall back to `**/*` with a stderr warning about system-rule replacement.

## UI/UX Details

`export --target ocr` prints the written path and the count of entries/rules on success, matching `sync`'s one-line output style.

## Session Log
- `/ll:confidence-check` - 2026-09-16T16:19:48 - `0451feb3-8293-4e5a-aa46-79c33e20da03.jsonl`
- `/ll:wire-issue` - 2026-09-16T04:59:13 - `1e024021-4acc-4b11-a8a1-c8c2d8acfc34.jsonl`
- `/ll:decide-issue` - 2026-09-16T04:49:13 - `03cedaa9-993e-49e8-a8ba-5c2ffbf2b4a2.jsonl`
- `/ll:refine-issue` - 2026-09-16T04:42:32 - `03cedaa9-993e-49e8-a8ba-5c2ffbf2b4a2.jsonl`
- `/ll:refine-issue` - 2026-09-16T04:29:14 - `3cab3e66-607f-42d5-a4a3-fd8f1228edab.jsonl`
- `/ll:format-issue` - 2026-09-16T04:19:47 - `6c5fb4c3-b655-4820-8bf8-9f99b327e9fc.jsonl`
- `/ll:capture-issue` - 2026-09-16T04:15:49 - `b650788f-edb5-4a45-abe3-046c38ae23e3.jsonl`
