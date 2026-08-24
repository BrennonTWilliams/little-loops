---
id: FEAT-3314
title: '`ll-artifact templatize` Phase A: deterministic templating (no LLM)'
type: FEAT
priority: P2
status: done
discovered_by: manual
discovered_date: '2026-08-24'
completed_at: '2026-08-24T20:52:09Z'
parent: FEAT-3308
depends_on: []
relates_to:
- FEAT-3308
- FEAT-3309
- ENH-3035
- FEAT-3036
labels:
- artifact
- ll-artifact
- templates
decision_needed: false
learning_tests_required:
- jinja2-byte-exact-round-trip
confidence_score: 90
outcome_confidence: 85
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-3314: `ll-artifact templatize` Phase A: deterministic templating (no LLM)

## Summary

Decomposed from [FEAT-3308](P2-FEAT-3308-ll-artifact-templatize-save-a-generated-artifact-as-a-reusable-template.md)
(the parent issue's own text: *"Phase A is independently shippable and contains
no LLM call — it is the whole fidelity mechanism, testable end-to-end from a
fixture... If this issue needs splitting for size, split on the A/B boundary."*).

Implements the deterministic half of `ll-artifact templatize`: given an
artifact plus a hand-written region map (`--regions <map.json>`), splice the
regions into Jinja2 expressions/blocks, emit a `manifest.yaml` + `data.json`,
and verify byte-exact round trip via a build-in-temp-then-promote flow. No LLM
call is on this path — Phase B ([FEAT-3315](P2-FEAT-3315-ll-artifact-templatize-phase-b-llm-region-discovery.md))
adds `discover_regions` on top of this.

## Parent Issue

Decomposed from FEAT-3308: `ll-artifact templatize`: save a generated
artifact as a reusable template.

## Current Behavior

No code exists: `grep -rn templatize scripts/` returns nothing. The only way
to obtain a template today is to hand-author one out of a self-contained HTML
file.

## Expected Behavior

```bash
ll-artifact templatize .loops/runs/html-anything/index.html docs/ARCHITECTURE.md \
    -o artifacts/templates/arch-review.llat --regions map.json
```

produces a template directory that (a) validates under `load_manifest()`,
(b) re-renders **byte-identically** against the extracted `data.json`, and
(c) can then be pointed at via `ll-artifact render` **by name** under
`templates_dir`.

**Output naming.** `-o` must resolve to a `<name>.llat` directory, because
`resolve_template()` (`artifact_templates.py:73`) only finds a template by
name at `templates_dir/<name>.llat`; a bare `arch-review` directory is
reachable by path only. If `-o` is given without the suffix, `templatize`
appends `.llat` and logs the resolved path. With no `-o`, the default is
`config.artifacts.templates_dir/<artifact-stem>.llat`. An existing template
at the resolved `-o` is an error unless `--force` is given.

**`<source>` role in Phase A.** The source document is recorded into
`manifest.source` and is otherwise unread — every `data.json` value is
captured from an artifact span. Phase B reads it; Phase A does not.

**Exit codes.** `0` success, `1` malformed input / IO failure, `2`
round-trip rejection (a distinct code so a loop can branch on "extraction
was lossy" without scraping stderr).

## Use Case

A user has generated an artifact (e.g. a `docs/ARCHITECTURE.md` review page)
via an existing HTML loop and wants to re-run the same layout against a
different source document without re-invoking the loop or hand-writing a new
template. They already know which spans of the artifact came from the
source (they can point at the headings/body text) and hand-write a region
map (`map.json`) locating those spans. Running `ll-artifact templatize
<artifact> <source> -o <name>.llat --regions map.json` gives them a
`templates_dir`-resolvable template they can immediately `ll-artifact
render <name>` against new `data.json`, with a hard guarantee (byte-exact
round trip) that the extraction did not silently drop or corrupt anything
from the original.

## Proposed Solution

1. **Region types.** `Region: {start: int, end: int, expr: str, group: str |
   None, anchor_before: str | None, anchor_after: str | None}` — one located
   span; `start`/`end` are the authoritative location, anchors are optional
   diagnostics only.
   `RegionGroup: {id: str, binding: str, array_path: str, start: int, end:
   int, iterations: list[[int, int]]}` — a repeat group: the `for` binding
   name, the path in `data` to the array it iterates, the group's own span,
   and the ordered iteration sub-spans within it (see 2b).
   `DiscoveryResult: {data_schema: dict, data: dict, regions: list[Region],
   groups: list[RegionGroup]}` is the shared contract Phase B will also
   produce.

   **`data` and `data_schema` are outputs, not map inputs.** The `--regions`
   map supplies only `regions` and `groups` — spans and expression paths.
   `load_regions` returns a `DiscoveryResult` with `data={}` and
   `data_schema={}`; `extract_data` then fills `data[expr]` from the artifact
   bytes at each span (`artifact[start:end].decode("utf-8")`) and
   `derive_schema` builds the schema from the expression paths. This is not a
   convenience: it is *why* the round-trip guarantee holds. If the map
   supplied values, an author could hand-write `&` where the artifact has
   `&amp;` and the failure would surface as an opaque render diff. Deriving
   both by construction makes §5's escaped-entity rule automatic rather than
   a discipline the author must remember, and it keeps Phase B's LLM
   responsible only for *locating* spans — never for transcribing their
   contents.

   `anchor_before`/`anchor_after` are **optional** in the on-disk map. They
   are diagnostics only (see §1's own "`start`/`end` are the authoritative
   location"), so requiring them would make every hand-written map carry dead
   weight. When present they are echoed into error messages; when absent,
   errors name byte offsets alone.

   **Duplicate `expr`.** Two regions may bind the same path. If their
   extracted bytes are identical, they collapse to one schema property and
   one `data` value, and both spans render from it. If they differ, that is a
   hard error naming both offsets — silently keeping the last write would
   guarantee a round-trip failure at a span the diff does not point at.

   **Offsets are UTF-8 byte offsets, and the whole pipeline operates on
   `bytes`.** The artifact is read with `Path.read_bytes()`, spliced as
   `bytes`, and compared as `bytes`; it is never round-tripped through
   `read_text`/`write_text`. Two reasons this is not a style choice: (a)
   byte offsets and Python `str` indices diverge on any non-ASCII artifact
   (em dashes, smart quotes, non-ASCII entities are all common), so a `str`
   splice against byte offsets lands silently off-by-N; (b) text-mode reads
   apply universal-newline translation (`\r\n` -> `\n`), so a CRLF artifact
   would "round-trip" successfully while the promoted template renders
   different bytes. Jinja2 renders to `str`; `verify_round_trip` encodes
   that render as UTF-8 once and diffs the bytes. This offset convention is
   part of the shared `DiscoveryResult` contract — Phase B's LLM must be
   told it is counting UTF-8 bytes, not characters.

   Note the fidelity bar stops at `templatize`'s own guarantee: `cmd_render`
   writes its output with `out_path.write_text(rendered, encoding="utf-8")`
   (`render.py:82`), which is not byte-transparent on a platform that
   translates newlines. The round-trip guarantee is "the template plus
   `data.json` *renders* the original bytes", not "every future `render`
   invocation writes them".

   **CRLF artifacts are rejected up front — this is settled, not a choice.**
   `render_template` reads the template body with
   `body_path.read_text(encoding="utf-8")` (`artifact_templates.py:315`),
   which applies universal-newline translation *inside the frozen renderer*.
   Verified: a body written as `b'A\r\n[[= x =]]\r\n'` renders `b'A\nv\n'`.
   No amount of byte-exact splicing on `templatize`'s side can survive that,
   and `render_template` is the shared contract this phase must not fork. So
   `cmd_templatize` scans the artifact for any `\r` byte before doing any
   work and exits **1** with a message saying CRLF/CR artifacts are
   unsupported and why. Leaving this as "round-trips or is rejected" would
   send an implementer to discover the read-mode translation the hard way,
   via a diff that points at the render.

2. **`apply_regions`.** A pure, LLM-free splice over sorted, non-overlapping
   spans: overlapping or out-of-bounds spans are a hard error, not a
   best-effort merge.

   **2a. Block-tag placement is a hard invariant, not a formatting
   preference.** `build_environment()` freezes `trim_blocks=True` and
   `lstrip_blocks=True`. `lstrip_blocks` fires only when the text from the
   line start to the tag is **whitespace-only**; `trim_blocks` fires only
   when the character immediately after the tag is a **newline**. So the two
   strips are independent triggers, and an emitted tag is safe exactly when
   **both fire or neither does**:

   - **Own-line** — whitespace-only prefix **and** immediate newline. Both
     strips fire and exactly cancel the line the splice added. Round-trips
     byte-exactly (indented tags included).
   - **Fully mid-line** — non-whitespace prefix **and** non-newline suffix.
     Neither strip fires, so the tag vanishes leaving its surroundings
     untouched. Also round-trips byte-exactly. Verified:
     `<p>[[% for i in it %]]<span>[[= i =]]</span>[[% endfor %]]</p>\n`
     renders `<p><span>1</span><span>2</span></p>\n`.

   The **mixed** forms are the failure mode, because exactly one strip fires
   and there is nothing to cancel it:

   - whitespace-only prefix, no immediate newline → the leading indent
     *and* the line's trailing newline are both eaten
     (`A\n  [[% for … %]]<li>…[[% endfor %]]\nB\n` →
     `A\n<li>1</li><li>2</li>B\n`).
   - non-whitespace prefix, immediate newline → the newline after the tag is
     eaten (`<p>[[% for … %]]\n<li>…` → `<p><li>1</li>…`).

   Therefore: **every emitted block tag must be either fully own-line or
   fully mid-line; a mixed placement is a hard error naming the offset.** An
   inline group boundary (repeated `<span>`s on one line) is a *supported*
   case, handled by the mid-line form — not an error. Jinja2's `+`
   whitespace-control markers (`[[%+ … +%]]`) inject spurious blank lines and
   fail the round trip in every position — do not reach for them.

   In practice the splicer picks the form from the boundary it is given: if
   the bytes from the preceding newline to `start` are whitespace-only and
   the byte at `end` is a newline, emit own-line (and consume that newline);
   otherwise emit mid-line. Only a boundary that is whitespace-prefixed
   *without* a following newline, or newline-followed *without* a
   whitespace-only prefix, has no safe form and errors.

   **2b. Repeat groups are not a splice.** Turning N cards into one loop
   body requires *deleting* iterations 2..N, not substituting within them, so
   groups need their own step rather than falling out of the span splice:
   - a `RegionGroup` declares its span `[start, end)` and an ordered list of
     iteration sub-spans covering it;
   - iteration 1's span becomes the loop body, with the `Region`s inside it
     rewritten to `[[= <binding>.<field> =]]`; iterations 2..N are dropped;
   - the loop is wrapped in `[[% for <binding> in <array_path> %]]` /
     `[[% endfor %]]` tags placed per 2a — own-line when the group boundary
     sits on its own line, mid-line when the iterations are inlined;
   - **hard check:** the non-region literal text of iterations 2..N must be
     byte-identical to iteration 1's. Mismatch is an error naming the first
     differing byte offset. Without this check a per-card `id="card-2"` or an
     alternating CSS class fails the round trip with a diff that points at
     the render rather than at the real cause.

3. **`escape_literal_delimiters`.** Scan the non-region spans for any
   pre-existing `[[=`, `[[%`, `[[#` (plausible in inlined JS/CSS string
   content) and wrap them in `[[% raw %]]`/`[[% endraw %]]`. Missing this is
   a silent round-trip failure whose diff points nowhere near the real cause.
   The `raw`/`endraw` wrapper is itself two block tags and is subject to 2a —
   but in its **mid-line** form, which is the common case and works.
   Verified: `<script>var a = "[[% raw %]][[= x =]][[% endraw %]]";</script>`
   round-trips byte-exactly. A single-line `<script>` therefore needs no
   line-splitting and no special case; the escaper wraps in place.

   **One literal is genuinely unescapable: `[[% endraw %]]`.** It terminates
   the wrapper from inside, and Jinja2 offers no escape for it — verified:
   `[[% raw %]]lit [[% endraw %]] more[[% endraw %]]` raises
   `TemplateSyntaxError: Encountered unknown tag 'endraw'`. Phase A
   **hard-errors naming the byte offset** rather than emitting a template
   that cannot parse. (The general escape hatch — binding the literal as a
   data value, which renders verbatim per the next sentence — is deliberately
   deferred: it would put splicer-generated keys into `data.json`, a
   `DiscoveryResult` contract change Phase B shares. Revisit only if a real
   artifact hits it.)

   Only literal, non-region text needs escaping: a *value* containing
   `[[= ... =]]` renders verbatim without re-evaluation (verified against the
   frozen environment), so extracted data needs no escaping.

3b. **`--regions` map schema.** The on-disk map is the Phase A/B seam —
   Phase B ([FEAT-3315](P2-FEAT-3315-ll-artifact-templatize-phase-b-llm-region-discovery.md))
   emits the same shape from an LLM — so it gets a documented JSON shape and
   a fail-closed loader, `load_regions(path) -> DiscoveryResult`, that
   rejects unknown keys, missing required fields, and non-integer offsets,
   mirroring `_validate_schema_shape()`'s fail-closed posture
   (`artifact_templates.py:85-140`). Phase B validates its LLM response
   through this same function rather than reimplementing the checks.

   The map's top level carries **only** `regions` and `groups`. `data` and
   `data_schema` are derived (§1), so a map supplying either is rejected as
   an unknown key — that keeps the Phase A/B seam narrow: Phase B's LLM
   returns spans, never transcribed content, which is the one thing an LLM
   cannot be trusted to reproduce byte-exactly.

4. **`build_manifest`.** Emits `{name, version: 1, renderer: "jinja2",
   output, data_schema, source, extraction}`, `theme` omitted. Must validate
   against `_validate_schema_shape()` (`artifact_templates.py:85-140`) before
   writing.

   **Emitted directory layout**, fixed by what `render` already requires:
   - `template.<ext>.j2` — the spliced body. `find_template_body()`
     (`artifact_templates.py:265-275`) requires **exactly one**
     `template.*.j2` at the template root, so the name is derived from the
     artifact's extension (`index.html` -> `template.html.j2`). Because
     `find_template_body` globs `template.*.j2`, the derived suffix must be
     non-empty and dot-free: use **`Path(artifact).suffix` minus its leading
     dot** (`report.min.html` -> `template.html.j2`, not
     `template.min.html.j2`). An **extensionless** artifact would yield
     `template..j2`, which globs but is nonsense — reject it, directing the
     user to rename the artifact or pass `-o` with an explicit extension.
   - `manifest.yaml` with `output` set to the original artifact's basename
     (`index.html`), since `cmd_render` writes `output_dir / manifest["output"]`
     (`render.py:81`).
   - `data.json` at the template root — `cmd_render` defaults `--data` to
     `root / "data.json"` (`render.py:52`), so writing it here makes the
     produced template immediately runnable as a bare `ll-artifact render
     <name>` with no flags.

   **Reserved-key guard.** `load_manifest()` rejects a top-level `ll` in
   `data_schema.properties` (`artifact_templates.py:180-187`), and
   `validate_top_level_data` rejects it in the payload. Since the schema is
   derived from region expression paths, `build_manifest` checks for a
   top-level `ll` binding itself and fails with a message naming the
   offending region — not with a downstream `ManifestError` at load time.

5. **Fidelity constraints.** `autoescape=False` in the frozen environment
   means values are stamped verbatim — extracted values must be captured
   exactly as they appear in the artifact byte stream (e.g. `&amp;` stays
   `&amp;` in `data.json`, not decoded).

6. **Round trip + promote.** `verify_round_trip(template_dir, data,
   original)` renders via `render_template` (`artifact_templates.py:304-328`),
   encodes the result as UTF-8, and diffs the bytes against the original
   bytes. **Any** non-empty diff is a hard failure. Failure is loud and
   non-destructive: `templatize` builds the candidate in a temp directory,
   runs the round trip there, and only then promotes it into the `-o` path.
   On failure it writes the candidate plus `roundtrip.diff` to
   `<out>.rejected/` and exits non-zero, leaving any pre-existing `-o`
   template untouched.

   **The promotion is not a bare `os.replace`.** Two failure modes make the
   naive form wrong, and both sit on paths this issue's own Acceptance
   Criteria exercise:
   - `os.replace(tmp, dst)` onto an **existing non-empty directory** raises
     `OSError: [Errno 66] Directory not empty` (verified). The AC that
     pre-populates `-o` hits this, as does any ordinary re-templatize of an
     existing template.
   - `os.replace` **across filesystems** raises `EXDEV`, so a
     `tempfile.mkdtemp()` build dir under `/tmp` can never be promoted into
     the project tree at all.

   So: build the candidate in a **sibling** temp dir of `-o` (e.g.
   `<out>.tmp-<pid>`), never in the system temp dir, and promote as
   `os.replace(existing, <out>.bak-<pid>)` -> `os.replace(tmp, out)` ->
   `shutil.rmtree(<out>.bak-<pid>)`, restoring the backup if the middle step
   fails. Overwriting a pre-existing `-o` template requires `--force`;
   without it, an existing `-o` is an error before any work is done. A stale
   `<out>.rejected/` from a previous run is removed at the start of a run
   that is about to write one (it is a diagnostic artifact, not user state).
   Both temp and backup dirs are cleaned up on every exit path — **and a run
   also sweeps stale `<out>.tmp-*` / `<out>.bak-*` siblings at start**, since
   a `SIGKILL`ed or crashed previous run leaves them behind and no exit-path
   cleanup can cover that.

7. **CLI wiring.** `templatize` follows the `render` precedent
   (`cli/artifact/__init__.py:111`): `add_templatize_parser(subparsers)` in
   new `cli/artifact/templatize.py`, called after `add_render_parser`, a
   fourth arm in the dispatch if-chain (`:118-124`), plus additions to the
   epilog `Examples:`/`Exit codes:` block (`:49-62`) and `__all__`
   (`:29-35`). Entry point for this phase is `--regions <map.json>` — reading
   a hand-written region map instead of calling an LLM (Phase B replaces
   this with `discover_regions` when `--regions` is absent).

   **`<source>` is recorded, not read.** Nothing on the Phase A code path
   consumes the source document: every value in `data.json` is captured from
   an artifact span, and `<source>` only lands in `manifest.source`. It stays
   a positional (Phase B reads it, and re-recording it on a re-templatize is
   the desired behavior), but its help text and the CLI docs must say so
   explicitly, so an implementer does not go looking for the extraction step
   that reads it.

   **Exit codes.** The shared epilog documents only `0`/`1`
   (`__init__.py:59-62`). A round-trip rejection is a distinct, expected,
   automatable outcome — not an operator error — so `templatize` returns
   **`2`** for it, with `1` reserved for the usual malformed-input/IO
   failures, and the epilog gains the row. This is what lets a loop branch
   on "extraction was lossy" without scraping stderr.

## Program Design

### Types

- `Region: {start: int, end: int, expr: str, group: str | None, anchor_before: str | None, anchor_after: str | None}` — `start`/`end` are UTF-8 **byte** offsets; anchors are optional diagnostics
- `RegionGroup: {id: str, binding: str, array_path: str, start: int, end: int, iterations: list[tuple[int, int]]}` — byte offsets throughout; `iterations` are ordered, contiguous sub-spans covering `[start, end)`
- `DiscoveryResult: {data_schema: dict, data: dict, regions: list[Region], groups: list[RegionGroup]}` — `regions`/`groups` come from the map; `data`/`data_schema` are derived outputs
- `ArtifactTemplate` (`artifact_templates.py:47-64`) — existing; `cmd_templatize` must emit a `manifest` dict that `load_manifest()` accepts

### Signatures

- `cmd_templatize(args: argparse.Namespace, logger: Logger) -> int` — 0 success, 1 error, 2 round-trip rejection
- `load_regions(path: Path) -> DiscoveryResult` — fail-closed parse of the `--regions` map; rejects unknown keys, missing required fields, non-integer offsets. Returns `data={}` / `data_schema={}` (both are derived, not supplied — see Proposed Solution 1); `anchor_before`/`anchor_after` are optional. The Phase A/B seam: Phase B validates its LLM response through this same function.
- `extract_data(artifact: bytes, result: DiscoveryResult) -> dict` — fills `data` from the artifact bytes at each region span (`artifact[start:end].decode("utf-8")`), nesting group regions under their `array_path`. Raises on a duplicate `expr` whose two spans differ, naming both offsets.
- `derive_schema(result: DiscoveryResult) -> dict` — builds `data_schema` from the region expression paths: every leaf `type: string`, every group an `array` of `object`. Must satisfy `_validate_schema_shape()` (`artifact_templates.py:85-140`) by construction.
- `apply_regions(artifact: bytes, result: DiscoveryResult) -> bytes` — bytes in, bytes out (see Proposed Solution 1). Raises on overlap, out-of-bounds, a **mixed** block-tag boundary (per 2a: whitespace-prefixed without a following newline, or newline-followed without a whitespace-only prefix), an unescapable literal `[[% endraw %]]`, or iterations 2..N whose literal text differs from iteration 1's.
- `escape_literal_delimiters(text: bytes) -> bytes`
- `build_manifest(name: str, output: str, schema: dict, source: Path, extraction: dict) -> dict`
- `verify_round_trip(template_dir: Path, data: dict, original: bytes, config: object) -> str | None` — constructs an `ArtifactTemplate(root=template_dir, manifest=load_manifest(template_dir))`, renders via `render_template(template, data, config)`, encodes the result UTF-8, diffs bytes; returns a unified diff or `None`. `config` is required because `render_template`'s third parameter is threaded to `build_ll_namespace` (`artifact_templates.py:292-302`); it is unused while `theme` is omitted, but the parameter is not optional. Runs against the temp build dir, before promotion, **after** `validate_top_level_data(data, manifest["data_schema"])` — a template that round-trips but fails its own `cmd_render` data-validation path (`render.py:61`) is a shippable defect.
- `promote(tmp_dir: Path, out_dir: Path, force: bool) -> None` — sibling-temp-dir promotion with backup/restore (see Proposed Solution 6); not a bare `os.replace`.

### Call Path

`main_artifact` (`cli/artifact/__init__.py:38`) -> `cmd_templatize` (new,
`cli/artifact/templatize.py`) -> *reject any `\r` byte in the artifact* ->
`load_regions` (`--regions <map.json>`) -> `extract_data` -> `derive_schema`
-> `apply_regions` (+ `escape_literal_delimiters`) -> `build_manifest` ->
*write sibling temp dir `<out>.tmp-<pid>`* -> `validate_top_level_data` ->
`verify_round_trip` -> `render_template` (`artifact_templates.py:304-328`)
-> `build_environment` (`:242-262`) -> `promote` (backup existing ->
`os.replace` -> drop backup)

### Codebase Research Findings

- **`cmd_render`'s Jinja2 environment is the frozen contract to reuse, not
  re-derive**: `build_environment()` (`artifact_templates.py:242-262`)
  constructs a `jinja2.sandbox.SandboxedEnvironment` with the frozen
  delimiter set (`[[= =]]`/`[[% %]]`/`[[# #]]`), `trim_blocks=True`,
  `lstrip_blocks=True`, `keep_trailing_newline=True`,
  `undefined=StrictUndefined`, `autoescape=False`. `apply_regions`/
  `verify_round_trip` must import and call `build_environment()` unchanged
  rather than constructing a separate `Environment`.
- **Manifest and template-body constraints**: `load_manifest()`
  (`artifact_templates.py:142-189`) requires exactly
  `_MANIFEST_REQUIRED_KEYS = {"name", "version", "renderer", "output",
  "data_schema"}` with `renderer` literally `"jinja2"`; `data_schema` is
  validated by `_validate_schema_shape()` (`:85-140`); `find_template_body()`
  (`:265-275`) requires exactly one `template.*.j2` file at the template
  root.
- **No round-trip/rollback precedent exists.** `file_utils.py:16-32,35-57`
  provides `atomic_write`/`atomic_write_json` (single-file only); no
  directory-scoped transaction helper exists. The build-in-temp-then-promote
  flow is the directory-level generalization of `atomic_write`'s own
  pattern, and is new code.
- **Error-handling shape to match**: `cmd_policy_builder`
  (`cli/artifact/policy_builder.py:90`) and `cmd_design_md_export`
  (`cli/artifact/design_md.py:57`) share whole-body `try/except Exception as
  exc:  # noqa: BLE001` -> `logger.error(str(exc)); return 1`; success is
  `logger.success(...); return 0`. `cmd_templatize` follows this.
- **Config loading is per-handler.** `cmd_render` resolves `templates_dir =
  config.project_root / config.artifacts.templates_dir` at `render.py:38`.
  `cmd_templatize` does the same — `templates_dir` already exists
  (landed by FEAT-3036), not re-added.
- **`artifact_templates.py` must never import `host_runner` or `anthropic`**
  (module docstring) — irrelevant to this phase since no LLM call is made,
  but constrains where `apply_regions`/`verify_round_trip` may live.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/artifact/templatize.py` (new module) —
  `add_templatize_parser` subparser + `cmd_templatize` handler, registered
  from `cli/artifact/__init__.py:111` immediately after
  `add_render_parser(subparsers)`; also add to `__all__` (`:29-35`) and the
  epilog `Examples:`/`Exit codes:` block (`:49-62`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/__init__.py:52,110` — `main_artifact` re-export; unchanged
- `scripts/tests/test_enh3268_design_md_export.py:354,367,378,394,410` —
  imports `cmd_design_md_export`, `main_artifact` directly; the closest
  existing sibling-subcommand test to model `test_artifact_templatize.py`'s
  dispatch tests after

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/artifact/__init__.py:24` — currently
  `from little_loops.cli.artifact.render import add_render_parser,
  cmd_render`; needs an equivalent
  `from little_loops.cli.artifact.templatize import add_templatize_parser,
  cmd_templatize` import line before either symbol can be registered or
  re-exported [Agent 1 finding]
- `scripts/little_loops/cli/artifact/render.py:13-23` — the import shape to
  mirror: `from little_loops.artifact_templates import (... load_manifest,
  render_template, resolve_template ...)`. `templatize.py`'s
  `apply_regions`/`verify_round_trip` must import `build_environment`,
  `render_template`, `load_manifest` from this same module rather than
  constructing a separate environment [Agent 1 finding]
- `scripts/tests/test_feat3036_artifact_templates.py` — existing coverage
  for the `artifact_templates.py` primitives (`TestBuildEnvironment`,
  `TestLoadManifest`, `TestRenderTemplate`, `TestCmdRender`) that
  `apply_regions`/`verify_round_trip` build on; also contains
  `TestArtifactCLIDispatchRender.test_render_dispatches_to_handler`
  (lines 458-468), the render-specific variant of the dispatch-test pattern
  to model `test_artifact_templatize.py`'s dispatch test after [Agent 1 +
  Agent 3 finding]

### Similar Patterns
- `cmd_policy_builder` (`cli/artifact/policy_builder.py:90`) — the existing
  stamp-and-write shape

### Tests
- New test module `scripts/tests/test_artifact_templatize.py` — round-trip
  fidelity against a checked-in fixture artifact + source pair. The fixture
  must deliberately contain: a repeated region (N=2 and N=5 variants), a
  literal `[[=`/`[[%` inside a single-line inlined `<script>` or CSS block,
  HTML entities (`&amp;`, `&#39;`) inside a templatized region, non-ASCII
  text (em dash / smart quotes) both inside and outside a region, a
  **mid-line repeat group** (a supported case — inline `<span>`s on one
  line), one fixture per **mixed** block-tag boundary (both hard errors), and
  a literal `[[% endraw %]]` (a hard error) — the silent-failure classes this
  phase's ACs gate on. Driven via `--regions <map.json>` with **no LLM in the
  test path**. Fixture artifacts are read and asserted as `bytes`; a CRLF
  variant asserts up-front *rejection*, not a round trip.
- Model dispatch tests on `TestArtifactCLIDispatch`
  (`test_policy_builder_emit.py:204-230`) — mock-handler dispatch (patch
  `sys.argv` + target `cmd_*`, assert `main_artifact()` routes correctly)
  and the missing-subcommand `SystemExit` test.
- No fixture pairing an emitted HTML artifact with its generating source
  document exists yet in `scripts/tests/fixtures/`; nearest transferable
  pattern is `_write_synthetic_profile`/`_reimport` in
  `test_enh3268_design_md_export.py:288-332,42-46`.

_Wiring pass added by `/ll:wire-issue`:_
- New fixture directory `scripts/tests/fixtures/artifact_templatize/` must
  be created — distinct from the existing `scripts/tests/fixtures/
  artifact_templates/` (which holds pre-built `.llat` template dirs for
  `render` tests, via the `_copy_fixture` helper). This new dir holds the
  round-trip artifact+source+region-map fixture set (N=2/N=5 repeated
  region, literal `[[=`/`[[%` in JS/CSS, HTML entities) [Agent 3 finding]
- `scripts/tests/test_policy_builder_emit.py:222-230` —
  `test_missing_subcommand_errors` already exercises the shared
  `subparsers.add_subparsers(dest="command", required=True)` `SystemExit`
  behavior generically; no `templatize`-specific duplicate of this test is
  needed [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md` § `ll-artifact` (line ~4455) — new subcommand
  section (Phase A surface: `--regions`, `--force`), including the
  `--regions` map's documented JSON shape (the Phase A/B seam), the
  UTF-8-byte-offset convention, the exit-code table (`0`/`1`/`2`), the CRLF
  rejection rule, and the note that `<source>` is recorded into
  `manifest.source` but not read in Phase A. Must also call out that `-o`
  means a **template directory** here while `render`'s `-o` means an
  **output directory** — the two subcommands sit adjacent in the same
  epilog, so the overload needs to read as deliberate

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md:918` — `templates_dir` is currently
  documented only as the read-side lookup dir for `ll-artifact render
  <name>`; `templatize`'s default `-o` (per this issue's own "Output
  naming" section) writes into this same `config.artifacts.templates_dir`
  path and should be mentioned as a write site too [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- **`templates_dir` config field location**: `ArtifactsConfig` dataclass in `scripts/little_loops/config/features.py` (default `"artifacts/templates"` at lines 212, 248, 378, 385); JSON Schema entry at `scripts/little_loops/config-schema.json:127,1883`.
- **Two coexisting subcommand-registration shapes exist in `cli/artifact/__init__.py`** — not one uniform pattern: `render`'s parser is built by an exported `add_render_parser(subparsers)` helper defined in `render.py:91-114` and called once from `__init__.py:111`; `policy-builder`/`design-md`'s parser args are instead built inline inside `main_artifact()` itself (`__init__.py:66-109`). The issue's cited precedent (`render`, `:111`) is the exported-helper shape — `templatize` following it means a real `add_templatize_parser` export, not inline argparse calls.
- **No directory-scoped temp-build-then-promote helper exists anywhere in the codebase** (confirms the issue's own claim). The nearest adjacent pattern is `git_operations.py:~726`, which uses `tempfile.TemporaryDirectory()` to stage an isolated `GIT_INDEX_FILE` for a scoped `git add -A` — a temp-dir-scoped git-index trick, not a build-then-`os.replace`-a-directory helper. `verify_round_trip`'s promote step is genuinely new code with no reusable helper to call.
- **`cmd_render`'s own output write is NOT atomic**: `render.py:81-82` does a plain `out_path.write_text(rendered, encoding="utf-8")` with no temp-file/replace step. `templatize`'s build-in-temp-then-promote requirement is a strictly higher fidelity bar than its own sibling command already meets — do not look to `cmd_render`'s write step as a promotion-flow precedent.
- **Existing learning-test evidence already proves the frozen-environment primitives round-trip byte-identically**: `.ll/learning-tests/jinja2-byte-exact-round-trip.md` (raw log at `.ll/learning-tests/raw/jinja2-byte-exact-round-trip.txt`) records passing assertions for `build_environment()`'s delimiter/trim/autoescape settings on literal-only templates — directly relevant proof `apply_regions`/`verify_round_trip` can build on rather than re-deriving from scratch. **Extended 2026-08-24 during issue review** (claims 8-15) with the cases this phase's invariants rest on, each probed against the real environment: fully mid-line block tags round-trip byte-exactly; both *mixed* placements silently corrupt; a mid-line `raw` wrapper escapes a literal delimiter on a single-line `<script>`; a literal `[[% endraw %]]` is unescapable (`TemplateSyntaxError`); a value containing delimiters renders verbatim; `render_template`'s `read_text` destroys CRLF; `[[%+ ... +%]]` injects blank lines. **Implement against these claims, not against intuition about `trim_blocks`/`lstrip_blocks`** — two of them contradict the reading this issue originally shipped with.
- **Closest checked-in-pair fixture convention in the test suite**: `scripts/tests/fixtures/streaming_parity/trace_*/` (`recorded.jsonl` + `expected.jsonl` per case, documented by a `README.md` with a `rebuild.sh` regeneration script) — but that suite asserts a relative-diff *tolerance*, not byte-exactness. The new `test_artifact_templatize.py` round-trip fixture needs a stricter byte-exact assertion; the directory-pair *layout* convention transfers, the diff-tolerance assertion does not.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `from little_loops.cli.artifact.templatize import add_templatize_parser, cmd_templatize` to `scripts/little_loops/cli/artifact/__init__.py`, mirroring the existing `render.py` import line, before wiring the subparser/dispatch/`__all__`/epilog additions already listed under Files to Modify.
- Import `build_environment`, `render_template`, `load_manifest` from `little_loops.artifact_templates` in `templatize.py` — do not construct a separate Jinja2 environment.
- Create fixture directory `scripts/tests/fixtures/artifact_templatize/` (new, distinct from `fixtures/artifact_templates/`) holding the round-trip artifact + source + region-map fixture set.
- Update `docs/reference/CONFIGURATION.md:918` to note `templates_dir` is also a write target for `templatize`'s default `-o` resolution, not read-only.

## Acceptance Criteria

- [ ] `ll-artifact templatize <artifact> <source> -o <name>.llat --regions <map.json>` produces a directory that `load_manifest()` accepts and that `ll-artifact render <name>` resolves **by name** under `templates_dir` (not by path only).
- [ ] Round-trip: rendering the produced template with the produced `data.json` reproduces the original artifact byte-identically, compared as `bytes` (never via `read_text`). Any non-empty diff exits **2**, writes `<out>.rejected/` + `roundtrip.diff`, and leaves a pre-existing `-o` template untouched — asserted by a test that pre-populates `-o` and forces a failure.
- [ ] Promotion over an existing `-o` template works: re-running `templatize --force` against a populated `-o` succeeds (guarding against the `os.replace`-onto-a-non-empty-directory `ENOTEMPTY` failure), and without `--force` an existing `-o` is an error raised before any build work. A test asserts no `<out>.tmp-*` or `<out>.bak-*` directory survives either path.
- [ ] A repeated region in the source (N sections → N cards) is templatized as a Jinja2 loop over an array, not unrolled — asserted by a test with N=2 and N=5 data.
- [ ] A repeat group whose iterations 2..N differ from iteration 1 in non-region literal text (e.g. `id="card-2"`, an alternating CSS class) fails loudly, naming the first differing byte offset, rather than producing a template that fails the round trip with a diff pointing at the render.
- [ ] An artifact containing a literal `[[=` / `[[%` / `[[#` in inlined JS or CSS still round-trips byte-exactly — asserted by a fixture that includes one **on a single-line `<script>`**, wrapped by a mid-line `[[% raw %]]`/`[[% endraw %]]` pair.
- [ ] An artifact containing a literal `[[% endraw %]]` in non-region text is a hard error naming the byte offset — never an emitted template that raises `TemplateSyntaxError` at render time.
- [ ] Block-tag placement: every emitted `[[% ... %]]` tag is **either** fully own-line (whitespace-only prefix **and** immediate newline) **or** fully mid-line (non-whitespace prefix **and** non-newline suffix); both round-trip byte-exactly. Asserted by two fixtures — block-level repeated elements (own-line form) and inline repeated `<span>`s on one line (mid-line form), which is a **supported** case, not an error.
- [ ] A **mixed** block-tag boundary — whitespace-only prefix without a following newline, or newline-followed without a whitespace-only prefix — is a hard error naming the offset, not a best-effort splice. Asserted by a fixture for each of the two mixed forms.
- [ ] An artifact containing HTML entities (`&amp;`, `&#39;`) in a templatized region round-trips byte-exactly; the test asserts `data.json` stores the escaped form.
- [ ] A non-ASCII artifact (em dash / smart quotes outside and inside a region) round-trips byte-exactly — the regression test for byte-offset vs. `str`-index divergence.
- [ ] A CRLF (or lone-`CR`) artifact is **rejected before any build work**, exit **1**, with a message naming the unsupported line ending — because `render_template` reads its body via `read_text` (`artifact_templates.py:315`), no such artifact can round-trip through the frozen renderer. A test asserts the rejection and that no `<out>`, `<out>.tmp-*`, or `<out>.rejected/` directory is created.
- [ ] The produced `data.json` passes `validate_top_level_data(data, manifest["data_schema"])` — the same check `cmd_render` runs at `render.py:61` — asserted inside the temp-dir gate, before promotion, so a template cannot ship that round-trips but fails its own render path.
- [ ] `data.json` values are extracted from the artifact byte stream by `extract_data`, never supplied by the `--regions` map; a map that carries a `data` or `data_schema` key is rejected by `load_regions` as an unknown key.
- [ ] Two regions binding the same `expr` collapse to one value when their spans' bytes are identical, and are a hard error naming both offsets when they differ.
- [ ] `anchor_before`/`anchor_after` are optional in the `--regions` map: a map omitting them loads and templatizes successfully.
- [ ] An extensionless artifact is rejected (it would derive a `template..j2` body name); a multi-dot artifact (`report.min.html`) derives `template.html.j2` from `Path.suffix`, and `find_template_body()` resolves it.
- [ ] A stale `<out>.tmp-*` / `<out>.bak-*` left by a crashed run is swept at the start of the next run — asserted by a test that pre-creates both and confirms a successful `templatize` removes them.
- [ ] `apply_regions` raises on overlapping or out-of-bounds spans rather than merging best-effort.
- [ ] `load_regions` fails closed on a malformed `--regions` map (unknown key, missing required field, non-integer offset) with a message naming the offending field — the Phase A/B seam contract FEAT-3315 validates its LLM response through.
- [ ] A region expression binding a top-level `ll` name fails in `build_manifest` with a message naming the offending region, not as a downstream `ManifestError` at `load_manifest` time.

## Impact

- **Priority**: P2 — blocks Phase B and Phase C; the fidelity mechanism is
  the epic's core deliverable.
- **Effort**: Medium — deterministic code with no LLM in the loop, but the
  temp-build/promote transaction and region-splicing algorithm are novel to
  this codebase.
- **Risk**: Medium — round-trip fidelity is a hard, automatable gate, which
  bounds the risk of a lossy result shipping silently.
- **Breaking Change**: No — new subcommand.

## Related Key Documentation

- `.issues/features/P2-FEAT-3308-ll-artifact-templatize-save-a-generated-artifact-as-a-reusable-template.md` — parent issue
- `.issues/features/P3-FEAT-3036-artifact-templates-design.md` — design hub; read first
- `docs/reference/CLI.md` — `ll-artifact`

## Status

**Open** | Created: 2026-08-24 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-24T20:51:51 - `13014800-8d7a-4804-8830-d1dc2a2e7e78.jsonl`
- `/ll:confidence-check` - 2026-08-24T20:24:40 - `a9467d85-d4e4-4bc1-b81d-d6c20bcd2599.jsonl`
- `/ll:confidence-check` - 2026-08-24T20:01:06 - `490de121-72ec-4c05-9269-025f0ef9af50.jsonl`
- `/ll:confidence-check` - 2026-08-24T19:19:47 - `848282c0-0b6c-443d-872b-4aeef5e9eeab.jsonl`
- `/ll:wire-issue` - 2026-08-24T19:04:46 - `d2894239-e4a9-46b6-b02b-e19d64169f3a.jsonl`
- `/ll:refine-issue` - 2026-08-24T18:58:02 - `ffa41e96-ab11-4f72-8513-f6153385423a.jsonl`
- `/ll:format-issue` - 2026-08-24T18:48:18 - `837a85ca-8f14-41e3-a67f-9059d7bcff74.jsonl`
- `/ll:issue-size-review` - 2026-08-24T18:42:58 - `837a85ca-8f14-41e3-a67f-9059d7bcff74.jsonl`
