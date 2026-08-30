# Spike Plan: FEAT-2797

## Context

From FEAT-2797's `## Confidence Check Notes` → `### Outcome Risk Factors`
(2026-08-30):

> `unproven_mechanism: true` with no `spike_attempted`/`spike_completed` flag
> hard-caps outcome confidence at `outcome_threshold − 1` (64) ... AC4's
> `output:` passthrough has no schema source anywhere in the repo to test
> against (Implementation Step 5 already scopes this as documentation-only
> rather than fabricating a test schema); this is expected for the
> acknowledged unproven mechanism, not a new gap.

And from the issue's own `### Codebase Research Findings`:

> No existing usage site exercises the combination AC4 depends on — no
> `agents/*.md` file in this repo defines a schema-shaped frontmatter field,
> and no adapter's `emit_agent` (including omp's) has ever populated an
> output-schema frontmatter key from one ... there is no direct precedent
> confirming the combination (a real ll agent schema flowing through
> `emit_agent` into `.omp/agents/<name>.md` frontmatter) works.

Both canonical low-confidence drivers apply: **(a)** the combination has zero
precedent — no fixture anywhere exercises a schema-shaped `output:` key
through `OmpEmitter.emit_agent()`; **(b)** no existing test exercises it —
`test_adapters.py`'s omp coverage never supplies a frontmatter key outside
`name`/`description`.

The issue itself (Implementation Step 5) correctly scopes AC4 as
documentation-only — it explicitly rejects "fabricating a schema to test
against" as the production-code fix. This spike does not contradict that: it
does not add a schema format to ll, and it changes zero production code. It
proves the **narrower, already-real mechanism** the docstring claims today —
that `_select_frontmatter_fields()`'s targeted string manipulation leaves an
*arbitrary, unrecognized, nested* frontmatter key (a stand-in for a future
`output:` schema) byte-for-byte intact when combined with the two edits the
function *does* make (`name:` injection, `metadata.short-description:`
strip). That claim is falsifiable independently of whether ll ever grows a
real schema format, and it is exactly what today's docstring asserts without
evidence.

## Approach

Build a small fixture module producing synthetic agent `.md` files whose
frontmatter includes a nested, schema-shaped `output:` block (JSON-Schema-like:
`type`/`properties`/`required`) standing in for a future ll agent output
schema — nothing like it exists in this repo today, which is exactly the gap
the issue's research identified. Feed these fixtures through the **real,
unmodified** production call path — `_select_frontmatter_fields()`
(`scripts/little_loops/adapters/core.py`) and `OmpEmitter.emit_agent()`
(`scripts/little_loops/adapters/omp.py`) — under the three input shapes that
stress its distinct code branches (name injection, short-description strip,
combination with an adjacent `metadata:` block), and assert the `output:`
block survives unmodified and still parses to the same YAML value.

Nothing is faked or stubbed in the mechanism under test — this spike imports
and calls the real production functions (read-only; not modified by this
skill). What's synthetic is only the *input fixture* (the schema-shaped
`output:` value), because no real one exists yet in this codebase.

## Critical files

Read-only references (production, not modified by this spike):

- `scripts/little_loops/adapters/core.py:119-182` —
  `_select_frontmatter_fields()`, the string-manipulation function whose
  untested claim ("untouched keys pass through unmodified") this spike
  checks under the omp-specific branch combination.
- `scripts/little_loops/adapters/omp.py` — `OmpEmitter.emit_agent()` and
  `_fields_read()`, the real end-to-end call path (`frontmatter_fields_read
  = ("description", "name")` per `capabilities.py:120`, so no
  `metadata.short-description` handling — the strip branch fires whenever a
  fixture happens to already carry one).
- `scripts/little_loops/adapters/capabilities.py:106-121` —
  `HOST_CAPABILITIES["omp"]`, confirms the exact `frontmatter_fields_read`
  tuple exercised.

New spike paths:

- `scripts/tests/spike/omp_agent_output_frontmatter_passthrough/__init__.py`
- `scripts/tests/spike/omp_agent_output_frontmatter_passthrough/fixtures.py`
- `scripts/tests/spike/omp_agent_output_frontmatter_passthrough/test_output_passthrough.py`

## Implementation

```
scripts/tests/spike/omp_agent_output_frontmatter_passthrough/
├── __init__.py
├── fixtures.py                      # synthetic schema-shaped `output:` fixture builders
└── test_output_passthrough.py       # AC test class
```

`fixtures.py` sketch:

```python
SCHEMA_SHAPED_OUTPUT = (
    "output:\n"
    "  type: object\n"
    "  properties:\n"
    "    verdict:\n"
    "      type: string\n"
    "  required: [verdict]\n"
)

def agent_md(*, include_name: bool, include_short_description: bool, include_metadata_block: bool) -> str:
    """Build a synthetic agent .md with SCHEMA_SHAPED_OUTPUT plus the requested
    adjacent fields, to stress a specific `_select_frontmatter_fields` branch."""
```

`test_output_passthrough.py` calls
`little_loops.adapters.core._select_frontmatter_fields` directly for the
branch-level tests, and `little_loops.adapters.omp.OmpEmitter().emit_agent()`
(writing under `tmp_path`) for the end-to-end test, then re-parses the
written file's frontmatter with `yaml.safe_load` and compares the `output`
key's parsed value against the fixture's source value.

## Acceptance Criteria → Test Table

| Test | Retires (AC / risk) | Kind |
|------|---------------------|------|
| `test_output_block_survives_name_injection` | Risk (a)/(b): unrecognized nested key untested when `name:` injection fires | behavior |
| `test_output_block_survives_short_description_strip` | Risk (a)/(b): unrecognized nested key untested when the `metadata.short-description` strip branch fires (omp's `fields_read` excludes it) | behavior |
| `test_output_block_survives_metadata_block_adjacency` | Risk (a)/(b): untested interaction between an existing `metadata:` block and an adjacent `output:` block during strip | behavior |
| `test_emit_agent_round_trip_preserves_schema_value` | AC4: no direct precedent that a schema-shaped `output:` key flows through `OmpEmitter.emit_agent()` into `.omp/agents/<name>.md` unmodified — this proves the real end-to-end call path, re-parsed as YAML | behavior |
| `test_spike_writes_only_under_tmp_path` | isolation guard — spike never writes to a real `.omp/agents/` dir in the repo | regression |

## Verification

```bash
python -m pytest scripts/tests/spike/omp_agent_output_frontmatter_passthrough/ -v
python -m pytest scripts/tests/test_adapters.py -v
```

## Out of Scope

- Designing a real ll agent output-schema format — AC4's own Implementation
  Step 5 already scopes that as future work, not this issue's.
- The RPC/`outputSchema` path (Option A) — rejected by this issue's own
  Decision Rationale; not touched here.
- `HOST_COMPATIBILITY.md` / `omp-headless-flags.md` doc corrections (AC1-3) —
  documentation, not a mechanism to prove.
- Modifying `core.py`/`omp.py`/`capabilities.py` — read-only in this skill;
  this spike proves the *existing* mechanism, it does not change it.

## Promotion

Unlike the ENH-2565 golden example, this spike proves an **existing**
production mechanism rather than prototyping new library code — there is no
new implementation to promote to `scripts/little_loops/spike/`. On
acceptance, the useful artifact is the *test coverage itself*: promote
`test_output_passthrough.py`'s cases into `scripts/tests/test_adapters.py`
as permanent regression tests (using the same synthetic schema-shaped
fixture, since no real one exists yet) in a separate PR, so the now-proven
claim stays test-gated once it lands.
