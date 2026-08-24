---
id: FEAT-3315
title: '`ll-artifact templatize` Phase B: LLM region discovery'
type: FEAT
priority: P2
status: open
discovered_by: manual
discovered_date: '2026-08-24'
parent: FEAT-3308
depends_on:
- FEAT-3314
relates_to:
- FEAT-3308
- FEAT-3309
labels:
- artifact
- ll-artifact
- templates
decision_needed: false
confidence_score: 90
outcome_confidence: 85
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-3315: `ll-artifact templatize` Phase B: LLM region discovery

## Summary

Decomposed from [FEAT-3308](P2-FEAT-3308-ll-artifact-templatize-save-a-generated-artifact-as-a-reusable-template.md).
Adds `discover_regions`, the LLM stage that makes `ll-artifact templatize`
usable without a hand-written `--regions` map: given `artifact.html` and
`source.md`, identify the spans of the artifact derived from the source
versus presentation spans, and produce the same `{regions, groups}` payload a
hand-written `--regions` map carries, which
[FEAT-3314](P2-FEAT-3314-ll-artifact-templatize-phase-a-deterministic-templating.md)'s
`apply_regions` splices in.

**The LLM never emits byte offsets** — it quotes each span's literal text, and
`_resolve_offsets()` locates it with `bytes.index`. The Phase A round-trip
gate is self-consistent by construction and therefore *cannot* detect a
wrong-but-orderly offset map, so offset correctness has to be designed out
rather than verified after the fact. See § Decision Rationale →
*Offset resolution*.

**`data_schema`/`data` are NOT part of the LLM contract** — Phase A derives
both from the region map alone (`derive_schema`, `extract_data`), and
`cmd_templatize` never reads `DiscoveryResult.data_schema`/`.data`. See
§ Decision Rationale → *Discovery output scope*.

## Parent Issue

Decomposed from FEAT-3308: `ll-artifact templatize`: save a generated
artifact as a reusable template.

## Depends On

**Resolved** — FEAT-3314 (Phase A) is **done**; dependency satisfied. This phase calls
`apply_regions`, `build_manifest`, and the temp-build/promote/round-trip
flow Phase A implements.

It also extends the `cmd_templatize` CLI scaffold Phase A wires up: when
`--regions` is absent, `discover_regions` runs instead.

## Current Behavior

`ll-artifact templatize` (Phase A, [FEAT-3314](P2-FEAT-3314-ll-artifact-templatize-phase-a-deterministic-templating.md))
only accepts `--regions <map.json>` — a hand-written region map. There is no
way to templatize an artifact without first manually locating and typing out
every region's byte offsets and Jinja2 expression.

## Expected Behavior

```bash
ll-artifact templatize .loops/runs/html-anything/index.html docs/ARCHITECTURE.md \
    -o artifacts/templates/arch-review.llat
```

(no `--regions` flag) calls `discover_regions` to have the LLM identify the
source-derived spans **by quoting their literal text**, which
`_resolve_offsets()` turns into the same `{regions, groups}` byte-offset
payload Phase A's `load_regions()` accepts. A response missing required keys,
carrying unknown keys, or quoting text that cannot be located unambiguously
fails loud (exit 1) before anything is written to disk; a combined
artifact+source input over the configured size ceiling exits 1 naming the
measured size, with no host call issued; a region map that splices but does
not round-trip exits 2. **Every failure downstream of the host call** — exit 1
or exit 2 — writes `discovery.json` (raw response) and `regions.json`
(resolved map) to `<out>.llat.rejected/`, so no failure requires re-paying for
the call.

## Use Case

The same user from Phase A's use case, but without the time or domain
knowledge to hand-locate every region by byte offset — they just want to run
`templatize` against an artifact and its source and get a working template.
`discover_regions` is what makes `templatize` usable without first learning
the region-map format.

## Proposed Solution

1. **`discover_regions` via schema-forced structured output.** Use
   `build_blocking_json(json_schema=...)` (Option A — see Decision
   Rationale below), fail-closed by replicating `advisor.consult()`'s
   `issubset` key-check (`advisor.py:274-280`), since `json_schema=`
   build-time enforcement is host-dependent (Codex-only —
   `host_runner.py:442-465`; Claude Code drops the kwarg). The prompt must
   state the `RegionGroup` byte-identical-literal-text-across-iterations
   rule and the capture-values-as-they-appear-in-the-byte-stream rule.

2. **The LLM never emits byte offsets — it emits quoted text, and Python
   resolves the offsets.** See § Decision Rationale → *Offset resolution*.
   The LLM response schema is a **quote-based discovery payload**, not
   Phase A's region map:

   ```jsonc
   {
     "regions": [
       {"text": "<exact literal substring>", "expr": "title",
        "group": null,                       // or a group id
        "anchor_before": "…", "anchor_after": "…"}   // optional disambiguators
     ],
     "groups": [
       {"id": "rows", "binding": "row", "array_path": "findings",
        "iterations": [{"text": "<exact literal substring of iteration 1>"}, …]}
     ]
   }
   ```

   `_resolve_offsets(artifact_bytes, raw) -> dict` (new, in `discover.py`)
   converts it to Phase A's `{regions, groups}`:

   - Resolve in document order with a **monotonically advancing cursor**,
     using `artifact_bytes.index(text.encode("utf-8"), cursor)`. The
     forward-only scan is what disambiguates repeated literal text and
     guarantees the sorted, non-overlapping ordering `apply_regions`
     (`templatize.py:458-468`) already requires.
   - `anchor_before`/`anchor_after`, when supplied, are **verified** at the
     resolved position (`artifact[:start].endswith(...)` /
     `artifact[end:].startswith(...)`) and are also used to skip a candidate
     match that fails them. They are additionally written into the emitted
     `Region` (`_parse_region` already accepts both, `templatize.py:81`,
     `:111-112`) so the persisted map is self-describing; Phase A itself
     ignores them.
   - **Group spans are derived, not supplied**: `group.start` = first
     iteration's resolved start, `group.end` = last iteration's resolved
     end. Iteration spans resolve first; each group-field region then
     resolves **within its own iteration's byte range**, which satisfies
     `_region_iteration_index` (`templatize.py:201-208`) by construction.
   - Text not found from the cursor, or found but failing its anchors,
     is a loud `RegionMapError` naming the `expr` and the quoted text —
     never a best-effort nearest match.

   This eliminates the entire byte-offset failure class rather than trying
   to detect it downstream, and it is the codebase's own idiom:
   `test_non_ascii_round_trips` (`test_artifact_templatize.py:582-606`)
   computes its offsets with `bytes.index` for exactly this reason.

3. **`discover_regions` lives in a new module, not `templatize.py`.**
   `templatize.py` is forbidden from importing `host_runner`/`anthropic`
   (module docstring, `:9-10`), so `BlockingJsonError` can never be named
   in `cmd_templatize`'s except clause. Put `discover_regions` in
   `scripts/little_loops/cli/artifact/discover.py` and **translate
   `BlockingJsonError` → `RegionMapError` at that module's boundary**;
   `cmd_templatize`'s existing
   `except (ManifestError, SpliceError, RegionMapError)` (`templatize.py:716-718`)
   then already covers the new failure mode, and `templatize.py` stays
   host-free.

4. **Refactor `load_regions()` so the resolved payload can actually be
   validated through it.** `load_regions(path: Path)` (`templatize.py:148`)
   does its own `read_text`/`json.loads`; there is no dict-level entry point,
   so `discover_regions` cannot call it. Extract
   `_parse_region_map(raw: dict[str, Any], where: str) -> DiscoveryResult`
   holding the whole allow-list/required-field/offset-type check, and make
   `load_regions` the thin file-reading wrapper. `discover_regions` validates
   `_resolve_offsets()`'s output through `_parse_region_map`. This is what
   makes "the `--regions` map and the discovery output are the same
   artifact" literally true, and it needs no change to `_MAP_ALLOWED_KEYS`.

5. **Read and validate `source`.** Phase A records `source` into the
   manifest as a string and never opens it — `cmd_templatize` existence-checks
   only the artifact (`:625-627`). Phase B is the first code that reads the
   source document, so it must add the `source_path.is_file()` check and
   fail (exit 1, no host call) when it is missing or unreadable.

6. **Input size ceiling.** Stage 1 sends the whole artifact plus the source
   document in one `build_blocking_json` call, and the artifacts this
   targets run ~100KB. There is no chunking strategy in v1. The command
   enforces an explicit combined-input ceiling and fails loud with the
   measured size when exceeded, rather than issuing a call that silently
   truncates and returns a plausible-looking partial region map that then
   fails the round trip for an unrelated-looking reason.

   - Config key: **`artifacts.templatize_max_input_bytes`**, default
     **`400000`**.
   - Unit is **bytes** (`len(artifact_bytes) + len(source_bytes)`),
     deliberately not tokens — bytes are measurable before any host call and
     need no tokenizer.
   - **v1 uses the flat default; `context_window_for()` is NOT consulted.**
     It stays the cited precedent for a later model-aware pass, but wiring
     it in now buys nothing over a conservative flat byte ceiling.

7. **Preserve the discovery response on *every* post-call failure, not just
   round-trip rejection.** The LLM call is the expensive, non-deterministic
   step. Today a rejection writes only the spliced candidate +
   `roundtrip.diff` to `<out>.rejected/` (`templatize.py:700-707`). Phase B
   must hold the raw response in memory and write it out on **any** failure
   branch downstream of the call — not only exit 2. The exit-1 paths that
   are equally expensive to re-pay for:

   - `_resolve_offsets` / `_parse_region_map` rejection (`RegionMapError`)
   - `apply_regions` `SpliceError` (overlap, out-of-bounds, group literal
     mismatch, unescapable `[[% endraw %]]`)
   - the `UnicodeDecodeError` from `extract_data` (see item 8)
   - `validate_top_level_data` failure (`templatize.py:694-697`)

   Two files land in `<out>.llat.rejected/`:

   - `discovery.json` — the **raw** quote-based LLM response
   - `regions.json` — `_resolve_offsets()`'s output, i.e. the resolved
     `{regions, groups}` map. This one is directly re-feedable as
     `--regions` for a deterministic retry after hand-editing, which is the
     whole point of preserving it.

   **Write-order constraint**: `shutil.copytree(tmp_dir, rejected_dir)`
   (`templatize.py:702`) requires `rejected_dir` not to exist. Both files
   must be written **after** the copytree, exactly as `roundtrip.diff`
   already is (`:703`). On the exit-1 branches that never reach the temp
   build, create `rejected_dir` directly and write the two files into it.

8. **Translate `extract_data`'s `UnicodeDecodeError`.** `extract_data`
   decodes each span with `artifact[start:end].decode("utf-8")`
   (`templatize.py:224`, `:242`). A span landing mid-multibyte-sequence
   raises `UnicodeDecodeError`, which is **not** covered by
   `cmd_templatize`'s `except (SpliceError, RegionMapError)` arm (`:676`) and
   falls through to the bare `except Exception` (`:719-721`) — surfacing the
   most likely discovery failure as a bare
   `'utf-8' codec can't decode byte 0x9c in position 12` with no region
   context. Wrap the two decode sites in `extract_data` and re-raise as
   `SpliceError` naming the region's `expr` and `[start, end)`.

9. **`extraction` metadata for the discovery branch.** Phase A hardcodes
   `{"method": "regions", "regions_map": str(regions_path)}`
   (`templatize.py:674`). `_MANIFEST_OPTIONAL_KEYS`
   (`artifact_templates.py:26`) accepts `extraction` with **no shape
   validation**, so the value is whatever the implementer writes — it must be
   decided here, not invented. The discovery branch emits:

   ```yaml
   extraction:
     method: llm_discovery
     host: <resolve_host_named(...).name>
     model: <the model actually passed to build_blocking_json>
   ```

   `method` is the discriminator between the two branches and is what a
   later phase would key off; `host`/`model` make a bad template's
   provenance recoverable.

10. **`--regions` takes precedence.** When `--regions` is given, the
    deterministic Phase A path runs and `discover_regions` is never called —
    no host call, no size-ceiling check, no `source` read. Discovery is
    strictly the fallback for its absence.

11. **No retry in v1.** One call, one shot. A failed discovery surfaces as a
    non-zero exit with the response preserved — deliberately not a silent
    retry loop, which would re-hide the fail-loud contract Option A exists
    for.

12. **No `--prompt` flag; drop the `prompt` parameter.** The wiring pass
    flagged `discover_regions(prompt: str | None)` as unreachable from the
    CLI. Resolve it by **dropping the parameter**, not by adding a flag: a
    prompt override has no caller, and it sits badly with the no-retry rule
    (item 11) — there is no iterate-and-re-ask loop for it to serve.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- **Resolved** (Proposed Solution 4): the `load_regions()` contract conflict
  is dissolved by narrowing the region map to `{regions, groups}` and
  extracting `_parse_region_map()`. `_MAP_ALLOWED_KEYS` is left untouched and
  `test_rejects_data_key`/`test_rejects_data_schema_key`
  (`test_artifact_templatize.py:56-65`) keep passing unmodified.
- Update `scripts/little_loops/cli/artifact/templatize.py` — the three
  "required for Phase A" strings that become wrong once `--regions` is
  optional: the `if not args.regions` hard error (`:628-630`), the
  subcommand `help=` (`:733-734`), and the `--regions` flag `help=`
  (`:755-759`)
- **Resolved** (Proposed Solution 12): drop `discover_regions`'s unreachable
  `prompt: str | None` parameter rather than adding a `--prompt` flag
- Wrap `extract_data`'s two `.decode("utf-8")` sites (`:224`, `:242`) so a
  mid-multibyte span raises a region-naming `SpliceError` instead of a bare
  `UnicodeDecodeError` (Proposed Solution 8)
- Update `scripts/little_loops/config/core.py` — thread
  `artifacts.templatize_max_input_bytes` through `BRConfig.to_dict()`'s
  hand-enumeration (`:917-920`)
- Update `scripts/little_loops/config/features.py` — add the field to the
  `ArtifactsConfig` dataclass (`:368-387`) and its `from_dict()`
- Update `scripts/little_loops/config-schema.json` — add the key under
  `"artifacts"` (`:1875-1890`), which is `"additionalProperties": false`
- Update `scripts/little_loops/cli/artifact/__init__.py` — update
  `main_artifact()`'s `epilog=` example invocation and exit-codes block for
  the optional (no-`--regions`) branch
- Update `docs/reference/CONFIGURATION.md` — document the new `artifacts`
  ceiling key
- Add/extend `scripts/tests/test_config_schema.py` — `test_artifacts_in_schema`
  and `TestSchemaValueParity.test_to_dict_values_match_schema_defaults`
  (Guard 1) for the new ceiling key
- Add `discover_regions` unit tests mocking `build_blocking_json`/
  `run_blocking_json`, following `test_advisor.py`'s `TestConsult` pattern
- Add a CLI-level default-branch (no `--regions`) **happy-path** test in
  `test_artifact_templatize.py`, monkeypatching `discover_regions` the way
  `verify_round_trip` is monkeypatched at `:467-471`
- Add the input-size-ceiling test asserting no host call issued, following
  `test_render_makes_no_llm_call` (`test_feat3036_artifact_templates.py:345-353`)
- Add the missing-source-file test (exit 1, no host call issued)
- Add the non-ASCII `_resolve_offsets` test: a quoted region whose text sits
  after multibyte content resolves to the correct **byte** offsets (see Tests
  subsection — no existing adversarial coverage)
- Add the `<out>.llat.rejected/{discovery.json,regions.json}`-preserved tests,
  covering **both** an exit-1 branch and the exit-2 round-trip branch
- Add the manifest `source`/`extraction`-present, `theme`-omitted test,
  asserting `extraction.method == "llm_discovery"` and the `host`/`model` keys

### Codebase Research Findings

This codebase holds two disagreeing conventions for an LLM-driven
discovery/extraction stage like `discover_regions`:

**Option A**: Schema-forced structured output via
`build_blocking_json(json_schema=...)`, as `advisor.consult()` does
(`advisor.py:149-160`, `_VERDICT_SCHEMA`; call+check at `:269-280`). The schema is materialized into
the host-CLI call at build time; the caller checks
`_VERDICT_KEYS.issubset(result.keys())` and raises `BlockingJsonError` on any
mismatch — every failure is loud.

> **Selected:** Option A — schema-forced structured output, matching
> `advisor.consult()`'s raise-on-mismatch contract; see Decision Rationale
> below.

**Option B**: Prompt-embedded schema with a regex-scraped envelope, as
`learning_tests/extractor.py` does (`_default_llm_call:116`,
`extract_learning_targets:195`). `build_blocking_json` is called with no
`json_schema=` argument; the contract is a `TARGETS_JSON:{...}` marker the
prompt asks the model to emit, scraped by regex. Every failure mode
(timeout, missing binary, non-zero exit, bad JSON, no regex match) degrades
to an empty result rather than raising — documented as "a best-effort safety
net" (`extractor.py:126-128`).

### Decision Rationale

**Selected**: Option A — schema-forced structured output via
`build_blocking_json(json_schema=...)`, matching `advisor.consult()`'s
raise-on-mismatch contract (`advisor.py:149-160`, `:269-280`).

**Reasoning**: Option B's fail-soft-to-empty-result contract
(`extractor.py:126-128`) directly contradicts this phase's explicit
"fail-closed against the emitted schema" requirement — a silently-empty
`data_schema` would look identical to "the LLM found nothing" rather than
"the call failed," corrupting the round-trip verify stage's diagnosis.
Option A's `BlockingJsonError` raise-on-mismatch (`advisor.py:272-278`) is
the codebase's only precedent that actually fails loud.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 2 | 0 |
| Simplicity | 2 | 2 |
| Testability | 3 | 1 |
| Risk | 2 | 0 |
| **Total** | **9/12** | **3/12** |

#### Discovery output scope: `{regions, groups}` only

**Selected**: `discover_regions` returns **only** `regions` and `groups`. The
LLM is never asked for `data` or `data_schema`.

**Reasoning**: Phase A derives both itself and never reads the
`DiscoveryResult` fields.

- `derive_schema()` (`templatize.py:250-290`) builds `data_schema` purely from
  region `expr` paths; every leaf is `{"type": "string"}`.
- `extract_data()` pulls every value from an artifact byte span.
- `cmd_templatize` (`:667-676`) calls both and passes the *derived* schema to
  `build_manifest` — nothing on the path reads
  `DiscoveryResult.data_schema`/`.data` (verified).

Two consequences that were driving the earlier design and no longer apply:

1. **An LLM-emitted `data_schema` could never reach the manifest**, so
   policing its key set (`additionalProperties`, `minItems`, …) with
   `_validate_schema_shape()` guards a field with no consumer. A derived
   schema is structurally incapable of carrying a forbidden key.
2. **Keeping the LLM schema is not salvageable as a typing upgrade** either:
   every extracted value is a string sliced from a byte span, so a schema
   asserting numbers/enums would fail `validate_top_level_data`
   (`templatize.py:695`) on its own extracted data.

Narrowing the contract also removes the `load_regions()` `data`/`data_schema`
rejection conflict entirely rather than working around it.

#### Offset resolution: quoted text, resolved in Python

**Selected**: the LLM emits the **exact literal text** of each span; Python
resolves byte offsets via a forward-only `bytes.index` scan
(§ Proposed Solution 2). The LLM is never asked for a numeric offset.

**Reasoning**: an earlier revision asked the model for UTF-8 byte offsets
directly and leaned on the Phase A round-trip gate to catch bad ones. **That
gate structurally cannot catch them.** `extract_data` slices
`artifact[start:end]` (`templatize.py:224`, `:242`), `apply_regions` replaces
*that same span* with `[[= expr =]]` (`:471`), and `render_template`
substitutes the extracted bytes back. Any in-bounds, non-overlapping,
UTF-8-decodable span set therefore round-trips **byte-exactly by
construction** — including one that is uniformly off by N. A
character-index map over non-ASCII content yields **exit 0 and a
semantically garbage template**, not a rejection.

The only wrong-offset maps that fail at all today do so incidentally:

| Failure | Where | Exit |
|---|---|---|
| Span lands mid-multibyte sequence | `extract_data` decode (`:224`, `:242`) | 1 |
| Group iteration literals stop matching | `_splice_group` (`:395-406`) | 1 |
| Spans overlap or run out of bounds | `apply_regions` (`:465-468`) | 1 |
| Consistently off-by-N but decodable and ordered | **nothing** | **0** |

Resolving offsets in Python removes the whole class instead of trying to
detect it: the model's job becomes "quote a substring," which it can
actually do over a 400KB document, whereas counting UTF-8 bytes across one
it cannot. This is also the dominant outcome risk the flat
`templatize_max_input_bytes: 400000` ceiling would otherwise carry
(§ Impact → Risk).

Secondary benefit: it puts `Region.anchor_before`/`anchor_after` to work.
Both are parsed by `_parse_region` (`templatize.py:81`, `:111-112`) and used
**nowhere** in Phase A — dead fields that exist for exactly this
disambiguation job.

**Key evidence**:
- `advisor.py:274-280` — Option A's raise-on-mismatch shape, directly copyable
- `extractor.py:116-227` — Option B's fail-soft design, explicitly documented as a "best-effort safety net," incompatible with this phase's fail-closed requirement
- `host_runner.py:442-465,736-770` — `json_schema=` is Codex-only at the builder level; Claude Code (default host) silently drops it, so caller-side key-checking is required regardless of option chosen

## Program Design

### Signatures

- `discover_regions(artifact_bytes: bytes, source_text: str, config: BRConfig) -> DiscoveryResponse` — new, in `cli/artifact/discover.py`; the LLM stage, and the only function on this call path that touches `host_runner`. Takes **bytes**, not `str` — `_resolve_offsets` needs the byte stream `extract_data`/`apply_regions` will slice, and re-encoding a decoded `str` is a needless round trip. Raises `RegionMapError` on any host or response failure; `BlockingJsonError` is translated at this module's boundary and never escapes. No `prompt` parameter (§ Proposed Solution 12).
- `DiscoveryResponse` — small dataclass returned by `discover_regions`, carrying `result: DiscoveryResult` (validated, offsets resolved), `raw: dict[str, Any]` (the LLM's quote-based response, for `discovery.json`), `resolved: dict[str, Any]` (the `{regions, groups}` map, for `regions.json`), and `host: str` / `model: str` (for `extraction`). `cmd_templatize` needs all five on the failure paths, so returning a bare `DiscoveryResult` would strand them.
- `_resolve_offsets(artifact: bytes, raw: dict[str, Any]) -> dict[str, Any]` — new, in `discover.py`; the quote-to-byte-offset resolver (§ Proposed Solution 2). Raises `RegionMapError` naming the `expr` and quoted text on a not-found, ambiguous, or anchor-failing match.
- `_parse_region_map(raw: dict[str, Any], where: str) -> DiscoveryResult` — **refactor** of the existing `load_regions()` body in `templatize.py`, extracted so the same fail-closed checks run against an in-memory resolved map
- `load_regions(path: Path) -> DiscoveryResult` — **unchanged signature**, becomes the thin file-reading wrapper over `_parse_region_map`

**The region-map shape is defined by FEAT-3314, not here.** Phase A owns the
contract and its fail-closed checks; `discover_regions` must validate
`_resolve_offsets()`'s output through `_parse_region_map` rather than
reimplementing them — that is what makes the `--regions` map and the discovery
output the same artifact.

Because offsets are resolved in Python, the byte-offset rule **drops out of
the prompt entirely**. What must still be stated in the prompt is the
`RegionGroup` constraint: the non-region literal text between fields must be
byte-identical across every iteration (enforced by `_splice_group`,
`templatize.py:395-406`), so the model must quote iterations that genuinely
share a template rather than merely look similar.

### Call Path

`cmd_templatize` (from FEAT-3314, `cli/artifact/templatize.py`) -> [no
`--regions` given] -> `discover_regions` (`cli/artifact/discover.py`) ->
`build_blocking_json` (`host_runner.py:442`, `json_schema=` path) ->
`run_blocking_json` -> `_resolve_offsets` -> `_parse_region_map` -> [same
downstream flow as Phase A: `extract_data` -> `derive_schema` ->
`apply_regions` -> `build_manifest` -> temp build -> `verify_round_trip` ->
promote]

`discover_regions` must not live in `artifact_templates.py` or in
`templatize.py` — neither module may import `host_runner` or `anthropic`
(`artifact_templates.py` module docstring, design principle 2;
`templatize.py:9-10`). It lives in its own `discover.py` and converts
`BlockingJsonError` to `RegionMapError` so `cmd_templatize`'s existing
`except (ManifestError, SpliceError, RegionMapError)` arm (`:716-718`) needs
no host-aware change.

### Exit Codes

| Condition | Exit |
|---|---|
| Success | 0 |
| Combined input over `templatize_max_input_bytes` (no host call issued) | 1 |
| Source file missing/unreadable (no host call issued) | 1 |
| Host failure or malformed/missing-key discovery response | 1 |
| Quoted text not found / ambiguous / anchor mismatch (`_resolve_offsets`) | 1 |
| Resolved map fails `_parse_region_map`, `apply_regions`, `extract_data` decode, or `validate_top_level_data` | 1 |
| Discovered map splices but fails round-trip verification | 2 |

Matches Phase A's published 0/1/2 semantics; no new codes. Every row below
the two no-host-call rows writes `discovery.json` + `regions.json` to
`<out>.llat.rejected/` (§ Proposed Solution 7).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- **`load_regions()`'s actual current contract is narrower than "validate a populated `DiscoveryResult`"** (`scripts/little_loops/cli/artifact/templatize.py:148-185`): it takes a file `Path`, `json.loads()`s it, and its top-level key check (`_MAP_ALLOWED_KEYS = {"regions", "groups"}`, line 86) hard-rejects any input carrying `data`/`data_schema` — `RegionMapError: "unknown top-level key(s) ... 'data'/'data_schema' are derived outputs, not inputs"`, asserted by `TestLoadRegions.test_rejects_data_schema_key` (`scripts/tests/test_artifact_templatize.py:61-65`). Every successful `load_regions()` call returns `DiscoveryResult(data_schema={}, data={}, regions=..., groups=...)` — `data`/`data_schema` are always zeroed, never populated from the input.
- **Consequence — RESOLVED** (§ Decision Rationale → *Discovery output scope*, § Proposed Solution 3): the LLM contract is narrowed to `{regions, groups}`, so nothing needs stripping and `_MAP_ALLOWED_KEYS` is left untouched. The remaining obstacle is mechanical, not contractual: **`load_regions()` takes a `Path` and does its own `read_text`/`json.loads` (`:155-158`), so there is no dict-level entry point for `discover_regions` to call at all** — hence the `_parse_region_map(raw, where)` extraction.
- **`_validate_schema_shape()` is not on this issue's critical path.** It lives in `scripts/little_loops/artifact_templates.py:85-140`, and today only runs inside `load_manifest()` (`:178`), reached via `verify_round_trip()` in `cmd_templatize`'s temp-build phase (`templatize.py:699`). Because the manifest's `data_schema` is always the output of `derive_schema()` (all-string leaves, `{type, properties, items}` only), an LLM response can never introduce a forbidden key into it. The check stays as Phase A's backstop; Phase B adds no call to it.
- **`cmd_templatize`'s exception surface has no `host_runner` awareness today**: the outer `except (ManifestError, SpliceError, RegionMapError)` (`templatize.py:716-718`) does not include `BlockingJsonError` (`host_runner.py:2019-2031`), and `templatize.py` has a module-level constraint (docstring, line 9-10) against importing `host_runner`/`anthropic` directly. **This constraint forces the resolution**: `cmd_templatize` *cannot* name `BlockingJsonError` in an except arm without violating it, so `discover_regions` must live in a separate module (`cli/artifact/discover.py`) and translate at its boundary (§ Proposed Solution 2).
- **Phase A never reads or validates `source`**: `cmd_templatize` existence-checks only the artifact (`:625-627`); `source_path` is stringified into the manifest (`:673`) and never opened — the `source` argument's own help text says so (`:737-744`). Phase B is the first code on this path that reads the source document, so the `is_file()` check and read-failure handling are new work here, not inherited.

## Integration Map

### Files to Create
- `scripts/little_loops/cli/artifact/discover.py` — `discover_regions`,
  `DiscoveryResponse`, `_resolve_offsets`; the only module on this path that
  imports `host_runner`, and the boundary where `BlockingJsonError` becomes
  `RegionMapError`

### Files to Modify
- `scripts/little_loops/cli/artifact/templatize.py` —
  (a) extract `_parse_region_map(raw, where)` from `load_regions()`'s body and
  make `load_regions` its file-reading wrapper;
  (b) wire `discover_regions` as the default (no `--regions`) branch of
  `cmd_templatize`, replacing the `if not args.regions` hard error (`:628-630`);
  (c) add the `source_path.is_file()` check and the input-size-ceiling check,
  both before any host call;
  (d) write `discovery.json` + `regions.json` into `<out>.llat.rejected/` on
  **every** post-call failure branch — after the `shutil.copytree` (`:702`) on
  the round-trip path, and via a direct `mkdir` on the exit-1 paths that never
  reach the temp build;
  (e) update the subcommand `help=` (`:733-734`) and `--regions` flag `help=`
  (`:755-759`), which both say "required for Phase A";
  (f) re-raise `extract_data`'s `.decode("utf-8")` failures (`:224`, `:242`)
  as a region-naming `SpliceError`;
  (g) branch `build_manifest`'s `extraction=` between the `regions` and
  `llm_discovery` shapes (`:674`)
- `scripts/little_loops/config/features.py` — add
  `templatize_max_input_bytes: int = 400000` to `ArtifactsConfig`
  (`:368-387`) and to its `from_dict()`. The dataclass docstring currently
  documents only `default_output_dir`; extend it to state the new key's
  **unit (bytes, not tokens)** and that it is measured as
  `len(artifact_bytes) + len(source_bytes)` before any host call
- `scripts/little_loops/config-schema.json` — add the key under `"artifacts"`
  (`:1875-1890`; `"additionalProperties": false`, so omission = hard reject)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/artifact/__init__.py` — `main_artifact()`'s
  `epilog=` string hardcodes an example invocation showing `--regions` as
  required-looking and an `Exit codes:` block scoped only to round-trip
  rejection (`0`/`1`/`2`); both need the optional (no-`--regions`) variant
  documented [Agent 2 finding]

### Tests
- Extend `scripts/tests/test_artifact_templatize.py` — default-branch
  happy-path test (mocked discovery response over a small fixture, exit 0,
  `.llat/` promoted, round trip clean), malformed-response failure tests
  (missing required key / unknown key, and a resolved map with a non-integer
  offset routed through `_parse_region_map`), `_resolve_offsets` failure tests
  (quoted text absent, ambiguous without anchors, anchor mismatch),
  input-size-ceiling test and missing-source test (both asserting no host call
  issued), and the `discovery.json` + `regions.json`-preserved tests on both
  an exit-1 and the exit-2 branch.
- New `_resolve_offsets` unit tests, independent of the CLI: correct byte
  offsets after multibyte content; forward-only cursor disambiguating repeated
  literal text; group span derived as first-iteration-start to
  last-iteration-end; group-field regions confined to their own iteration
  range.
- New test: `extract_data` raises a `SpliceError` naming the region (not a
  bare `UnicodeDecodeError`) for a span landing mid-multibyte sequence.
- `_parse_region_map` refactor must leave every existing `TestLoadRegions`
  case passing unmodified — including `test_rejects_data_key` /
  `test_rejects_data_schema_key` (`:56-65`).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_advisor.py` — reuse `TestConsult`'s
  `resolve_host_named`/`run_blocking_json` patch-pair pattern (`:101-119`,
  `:210-250`, `pytest.raises(BlockingJsonError)`) for mocking
  `discover_regions`'s host call in the schema-validation and
  missing-required-keys tests, rather than hand-rolling a new `FakeRunner`
  [Agent 3 finding]
- `scripts/tests/test_feat3036_artifact_templates.py` — reuse
  `test_render_makes_no_llm_call` (`:345-353`,
  `resolve_host.assert_not_called()`) as the pattern for asserting the
  input-size-ceiling test issues no host call [Agent 3 finding]
- New test: non-ASCII offset resolution — no existing coverage found anywhere
  in the suite; `test_non_ascii_round_trips` (`test_artifact_templatize.py:582-606`)
  computes correct offsets via `bytes.index` and round-trips, but nothing
  exercises resolution itself. **Note the revised design makes the original
  "character-index adversarial" test impossible to write meaningfully** — the
  LLM no longer supplies offsets, and the round-trip gate cannot detect a
  consistently-wrong one anyway (§ Decision Rationale → *Offset resolution*).
  The replacement asserts `_resolve_offsets` produces byte offsets, not
  character indices, for a region following multibyte content [Agent 3
  finding — gap, redirected]
- New test: manifest carries `source`/`extraction` and omits `theme`, with
  `extraction == {"method": "llm_discovery", "host": ..., "model": ...}` —
  model after `TestBuildManifest.test_builds_expected_shape`
  (`test_artifact_templatize.py:333-347`, which already asserts
  `"theme" not in manifest`) [Agent 3 finding]
- `scripts/tests/test_config_schema.py` — extend `test_artifacts_in_schema`
  (`:473-493`) and `TestSchemaValueParity.test_to_dict_values_match_schema_defaults`
  (`:1268-1290`, "BUG-3192 Guard 1") for `templatize_max_input_bytes`;
  Guard 1 walks every `BRConfig().to_dict()` leaf against
  `config_mod.schema_default(path)` and raises if a new `artifacts.<key>`
  leaf has no matching schema default [Agent 2 finding]

### Documentation
- `docs/reference/CLI.md` § `ll-artifact` — extend the `templatize` section
  for the default (LLM-driven) invocation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CONFIGURATION.md` — `### \`artifacts\`` section (table +
  JSON example) needs a row for `templatize_max_input_bytes` (default
  `400000`, unit **bytes**) [Agent 2 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/core.py` — `BRConfig.to_dict()` (`:917-920`)
  hand-enumerates the `artifacts` keys (`default_output_dir`,
  `templates_dir`); `templatize_max_input_bytes` must be added there
  explicitly or it silently never appears in `to_dict()` output, and
  `test_config_schema.py`'s Guard 1 (above) will fail on the resulting
  schema/dataclass mismatch [Agent 2 finding]
- Verification command is **`ll-config get artifacts.templatize_max_input_bytes`**
  — `get` is the only `ll-config` subcommand (`scripts/little_loops/cli/config.py:43`).
  An earlier revision of this issue cited a nonexistent `ll-config show`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- **Per-host `json_schema=` behavior in `host_runner.py`, confirmed at the implementation level**: `ClaudeCodeRunner.build_blocking_json` (`:442-471`) discards the kwarg entirely (`_ = json_schema` at `:465`) — the claude CLI's inline `--json-schema` flag exists but is only reachable through the separate `run_blocking_json(schema=...)` path (`:2034-2052`, `:2139-2140`), never through `build_blocking_json`'s own parameter. `CodexRunner.build_blocking_json` (`:736-770`) is the *only* implementation that materializes `json_schema` — it writes it to a `tempfile.NamedTemporaryFile` and passes `--output-schema <path>`, returning the temp path in `HostInvocation.cleanup_paths` for later cleanup. `GeminiRunner`/`OmpRunner` also silently drop it; `OpenCodeRunner`/`PiRunner` raise `HostNotConfigured` (stubs). This is strictly more detailed than the issue's existing citation and confirms caller-side key-checking is required on every host except Codex, not just Claude Code.
- **`context_window.py`'s `context_window_for()` (`:39-77`) is the existing "size a limit off the model/host" precedent** for the new input-size-ceiling config this issue proposes — five-tier precedence (explicit override → `LL_CONTEXT_LIMIT` env → `[1m]` model-id suffix → exact `MODEL_CONTEXT_WINDOW` lookup → 200k default floor). No existing `config-schema.json` key covers a raw combined-input-size ceiling (verified by grep — only an unrelated `hard_ceiling_pct` under compaction config exists); this ceiling is new schema, but `context_window_for()` is the pattern to model its model-awareness after.
- **Reusable `build_blocking_json` test fakes already exist**: `scripts/tests/test_action.py:40`, `scripts/tests/test_cli_harness.py:37`, and `scripts/tests/test_runner_spec.py:37,160` each define a fake `build_blocking_json` stub — usable scaffolding for mocking `discover_regions`'s host call in the schema-validation-failure and missing-required-keys tests this issue's Acceptance Criteria require.

_Added by `/ll:refine-issue` — 2026-08-24 — based on codebase analysis:_

- `scripts/little_loops/host_runner.py` — `resolve_host()`/`resolve_host_named()` is the required entry point per CLAUDE.md's Host CLI Abstraction; `ClaudeCodeRunner.build_blocking_json` (`:442-471`, discards `json_schema` at `:465`) and `CodexRunner.build_blocking_json` (`:736-770`, materializes it via `--output-schema <tempfile>`) are the two implementations `discover_regions` will actually run against in practice.
- `scripts/little_loops/advisor.py` — `consult()` (`:192-290`) is the concrete Option A precedent to model `discover_regions`'s call and raise-on-mismatch shape after: `_VERDICT_SCHEMA`/`_VERDICT_KEYS` module-level (`:149-160`), `build_blocking_json(..., json_schema=_VERDICT_SCHEMA)` call (`:269-271`), `_VERDICT_KEYS.issubset(result.keys())` check (`:274-280`, a subset check — extra keys tolerated, only missing required keys raise `BlockingJsonError`).
- `scripts/little_loops/config-schema.json` — the `"artifacts"` object schema (`:1875-1890`) has exactly two properties today (`default_output_dir`, `templates_dir`) and `"additionalProperties": false` (`:1889`) — the new input-size-ceiling config key must be added here or it will be schema-rejected. Python-side counterpart: `ArtifactsConfig` dataclass (`scripts/little_loops/config/features.py:368-387`).
- `scripts/little_loops/context_window.py` — `context_window_for(model, override)` (`:39-77`, five-tier precedence: explicit override → `LL_CONTEXT_LIMIT` env → `[1m]` model-id suffix → exact `MODEL_CONTEXT_WINDOW` lookup → 200k default floor) is the existing model-aware sizing precedent for the new combined-input ceiling.
- `docs/reference/CLI.md` — the `#### ll-artifact templatize` section (`:4532-4559`, re-verified current as of this pass since it changed after the prior refine) already has a Phase B forward-reference at line 4534 naming `discover_regions`/FEAT-3315, but its flags table (`:4544-4548`) still lists `--regions <path>` as unconditionally "required for Phase A," and its exit-code note (`:4557`) documents only Phase A's 0/1/2 semantics — both need the optional/no-`--regions` variant added.
- Existing `build_blocking_json`-backed test suites usable as a testing-pattern reference (not to modify): `scripts/tests/test_advisor.py`, `scripts/tests/test_host_runner.py`, `scripts/tests/test_learning_tests_extractor.py`, `scripts/tests/test_cli_advise.py`.

## Acceptance Criteria

- [ ] **Happy path**: with no `--regions`, a mocked discovery response over a small non-trivial fixture (at least one `RegionGroup`) exits 0, promotes a `.llat/` directory, and passes round-trip verification.
- [ ] A `discover_regions` response that is malformed — missing a required key or carrying an unknown key — raises rather than degrading to an empty result (Option A contract), asserted with a mocked host call. A resolved map carrying a non-integer offset is rejected by FEAT-3314's `_parse_region_map` rather than a Phase-B-local validator.
- [ ] `_resolve_offsets` produces **byte** offsets, not character indices: a region quoted from a position following multibyte content resolves to offsets that satisfy `artifact_bytes[start:end].decode("utf-8") == text`, and the run round-trips clean.
- [ ] `_resolve_offsets` fails loud (exit 1, naming the `expr` and quoted text) when a quoted span is absent from the artifact, is ambiguous with no anchors to disambiguate it, or resolves to a position whose `anchor_before`/`anchor_after` do not match — never a best-effort nearest match.
- [ ] A span landing mid-multibyte-sequence surfaces as a `SpliceError` naming the region and its `[start, end)`, not a bare `UnicodeDecodeError` through `cmd_templatize`'s catch-all.
- [ ] A combined artifact+source input over `artifacts.templatize_max_input_bytes` exits 1 naming the measured size, with no host call issued.
- [ ] A missing or unreadable `source` file exits 1 with no host call issued.
- [ ] `--regions`, when given, runs the deterministic Phase A path with no host call, no size-ceiling check, and no `source` read.
- [ ] **Every** failure downstream of the host call writes `discovery.json` (raw response) and `regions.json` (resolved map) into `<out>.llat.rejected/` — asserted on both an exit-1 branch (e.g. `apply_regions` `SpliceError`) and the exit-2 round-trip branch, where they sit alongside the candidate and `roundtrip.diff`.
- [ ] The emitted manifest carries `source` and `extraction`, omits `theme`, and its `extraction` is `{"method": "llm_discovery", "host": ..., "model": ...}` on the discovery branch and unchanged (`{"method": "regions", "regions_map": ...}`) on the `--regions` branch.
- [ ] `templatize.py` still imports neither `host_runner` nor `anthropic` after the change (assertable by module inspection), and the existing `TestLoadRegions` suite passes unmodified through the `_parse_region_map` refactor.

## Impact

- **Priority**: P2 — makes `templatize` usable without a hand-written region
  map; the epic's stated fan-out value depends on this, not just Phase A.
- **Effort**: Large — region discovery over an opaque self-contained file is
  the hard problem in the epic.
- **Risk**: Medium. **The round-trip gate is not an offset-correctness gate** —
  it is self-consistent by construction and passes a uniformly-off-by-N map
  (§ Decision Rationale → *Offset resolution*). Quote-based resolution moves
  that risk out of the LLM and into `bytes.index`, which is why it is the
  selected design rather than an optimization. Residual risk after that is
  *semantic* region-map quality — the model quoting the wrong spans, or
  grouping iterations that do not share byte-identical literal text — which
  `_splice_group` and the round trip **do** catch, at exit 1 / exit 2.
- **Breaking Change**: No.

## Related Key Documentation

- `.issues/features/P2-FEAT-3308-ll-artifact-templatize-save-a-generated-artifact-as-a-reusable-template.md` — parent issue
- `.issues/features/P2-FEAT-3314-ll-artifact-templatize-phase-a-deterministic-templating.md` — dependency (Phase A)
- `.issues/features/P3-FEAT-3036-artifact-templates-design.md` — design hub

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-08-24_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 70/100 → MODERATE

### Concerns

_Both concerns below were resolved in the 2026-08-24 review pass; retained for
provenance._

- ~~AC #2 marked `⚠ Superseded` — `load_regions()` rejects `data`/`data_schema`.~~
  **Resolved**: the LLM contract is narrowed to `{regions, groups}`
  (§ Decision Rationale → *Discovery output scope*), so `_MAP_ALLOWED_KEYS`
  needs no change. The real obstacle turned out to be that `load_regions()`
  takes a `Path` and has no dict-level entry point at all — addressed by the
  `_parse_region_map` extraction (§ Proposed Solution 4).
- ~~`stale_cli_flag` flagged `ll-config show (no such subcommand)`.~~
  **Confirmed stale and corrected**: `get` is the only `ll-config`
  subcommand (`cli/config.py:43`).

### Findings added by the 2026-08-24 review pass

- The LLM's `data_schema`/`data` were dead outputs — Phase A derives both and
  reads neither `DiscoveryResult` field. Removing them from the contract cut
  Proposed Solution 1's schema-key prose, the whole in-process
  `_validate_schema_shape()` step, and the original AC #1.
- `BlockingJsonError` handling is forced, not optional: `templatize.py`'s
  no-`host_runner` constraint means the translation must happen in a separate
  module (`cli/artifact/discover.py`).
- Phase A never opens the `source` file; reading and validating it is new
  work in this phase.
- The size ceiling now has a concrete key, unit, and default
  (`artifacts.templatize_max_input_bytes`, bytes, `400000`), and v1
  explicitly does not consult `context_window_for()`.
- Added: a happy-path AC (all prior ACs were failure modes), preservation of
  the raw discovery response on rejection, an explicit no-retry rule, and a
  concrete exit-code table.

### Findings added by the pre-implementation review pass (2026-08-24, later)

All verified against Phase A's merged code, not inferred from the issue text.

1. **The original AC #3 was unachievable, and it exposed a design flaw**
   (blocking). It asserted a character-index region map would be caught by
   round-trip rejection at exit 2. Round-trip verification is **self-consistent
   by construction** — `extract_data` slices `artifact[start:end]`
   (`templatize.py:224`, `:242`), `apply_regions` replaces that same span
   (`:471`), render substitutes it back — so a uniformly-off-by-N map
   round-trips byte-exactly and exits **0** with a garbage template. Resolved
   by removing byte offsets from the LLM contract entirely: the model quotes
   literal text, `_resolve_offsets` locates it with `bytes.index`
   (§ Proposed Solution 2, § Decision Rationale → *Offset resolution*). This
   also retires two dead Phase A fields, `Region.anchor_before`/`anchor_after`
   (`templatize.py:81`, `:111-112`), which are parsed but used nowhere.
2. **Discovery response preservation was scoped only to exit 2.** Four
   post-call exit-1 branches discarded an equally expensive response.
   Broadened to every post-call failure, and a **write-order constraint** was
   documented: `shutil.copytree` (`:702`) requires `rejected_dir` not to
   exist, so both files must be written after it (§ Proposed Solution 7).
   `regions.json` (the resolved map) was added alongside `discovery.json`
   because it is directly re-feedable as `--regions`.
3. **`extract_data`'s `UnicodeDecodeError` escapes the typed handler.** Not
   covered by `except (SpliceError, RegionMapError)` (`:676`), it falls to the
   bare `except Exception` (`:719-721`) and surfaces the most likely discovery
   failure as a contextless codec message (§ Proposed Solution 8).
4. **The discovery branch's `extraction` value was unspecified.**
   `_MANIFEST_OPTIONAL_KEYS` (`artifact_templates.py:26`) accepts `extraction`
   with **no shape validation**, so it would have been invented at
   implementation time. Pinned to
   `{"method": "llm_discovery", "host": ..., "model": ...}`
   (§ Proposed Solution 9).
5. **`--regions` precedence was implied but never stated** (§ Proposed
   Solution 10).
6. **The `prompt` parameter is dropped**, not backed by a new `--prompt` flag
   — it has no caller and no iterate-and-re-ask loop to serve
   (§ Proposed Solution 12).
7. **Citation drift corrected** against merged Phase A: subcommand `help=` is
   `:733-734` (was `:737`), `--regions` `help=` is `:755-759` (was `:746`),
   the `if not args.regions` error is `:628-630`, the rejection block is
   `:700-707`, `load_regions`'s read is `:155-158`, `ArtifactsConfig` is
   `features.py:368-387`, and `advisor.consult`'s key-check is
   `advisor.py:274-280`. `except (ManifestError, SpliceError, RegionMapError)`
   at `:716-718` and the schema's `artifacts` block at `:1875-1890` were
   confirmed accurate.

**Outcome confidence revised 86 → 80.** The offset-counting risk that the
flat 400KB ceiling silently carried is now designed out rather than merely
gated, but the change enlarges the surface (`_resolve_offsets`, its own test
class, the two-file rejection artifact) relative to the version scored at 86.

## Status

**Open** | Created: 2026-08-24 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-08-24T21:59:38 - `e9d964d9-67ff-4d09-b50d-9eccaed8ef33.jsonl`
- `/ll:confidence-check` - 2026-08-24T21:24:57 - `4c963e2d-de26-4bbd-81d9-9a468cb16596.jsonl`
- `/ll:confidence-check` - 2026-08-24T21:15:01 - `f6542b25-721a-49ab-ba69-b9d4746b6ed4.jsonl`
- `/ll:wire-issue` - 2026-08-24T21:10:03 - `bf6a3113-6115-4098-8fb1-1cdb2c5eeb4c.jsonl`
- `/ll:refine-issue` - 2026-08-24T20:56:38 - `de9e1af4-5c22-4ebf-87ee-74fb60da3cea.jsonl`
- `/ll:refine-issue` - 2026-08-24T18:58:03 - `ffa41e96-ab11-4f72-8513-f6153385423a.jsonl`
- `/ll:format-issue` - 2026-08-24T18:48:18 - `837a85ca-8f14-41e3-a67f-9059d7bcff74.jsonl`
- `/ll:issue-size-review` - 2026-08-24T18:42:58 - `837a85ca-8f14-41e3-a67f-9059d7bcff74.jsonl`
