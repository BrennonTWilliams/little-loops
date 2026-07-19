# Spike Plan — FEAT-2672 (F1-prereq (b) — Deferred tool loading)

## Context

From FEAT-2672's `### Outcome Risk Factors` (current pass, `Confidence Check
Notes` 2026-07-18 reconfirmation):

> Novel mechanism: the stub/resolve boundary has no internal precedent to
> model against; recommend proving the resolve-on-demand round trip in
> isolation... before building the surrounding `DeferredToolsConfig` plumbing.

The issue's own later refinement pass ("Refinement pass (2026-07-19, later
pass)") already corrected the *premise* of that risk factor: there is no
client-side stub/resolve boundary to build at all. The installed `anthropic`
SDK (0.104.1) confirms this directly (verified locally against
`anthropic/types/tool_param.py`,
`tool_search_tool_bm25_20251119_param.py`):

- `defer_loading: bool` is a per-tool field on the existing full `ToolParam`
  dict — no separate stub payload shape exists.
- Making `defer_loading` do anything requires exactly one
  `ToolSearchToolBm25_20251119Param` (or regex variant) entry present in the
  same request's `tools` array.
- Resolution happens server-side via a `tool_search_tool_result` →
  `tool_reference` round trip through the model; there is no local
  resolve-a-stub-back-to-its-definition function to write.

So this spike targets both canonical low-confidence drivers, narrowed to
what's actually novel and unprecedented in *this* codebase's request-building
code (`little_loops/tool_catalog.py`, `host_runner.py`):

- **(a) zero precedent**: no code in this codebase has ever set `defer_loading`
  on a `ToolDefinition`/serialized tool dict, or assembled a `tools` array
  containing both flagged tools and a search-tool entry.
- **(b) no existing test exercises the risky core**: `test_tool_catalog.py`
  and `test_cache_control.py` cover `cache_control` attachment but nothing
  about `defer_loading` or search-tool injection.

The spike proves the request-shape mechanism deterministically (no live API
call, no `ANTHROPIC_API_KEY` needed) and, separately, records what a
live-call round trip would require so that gap is explicit rather than
silently assumed.

## Approach

Build a small standalone library that mirrors — without importing —
`tool_catalog.to_anthropic_tools()` and `host_runner.build_anthropic_request()`'s
tool-array assembly, then prove two things against the **real installed
`anthropic` SDK types** (not a project stub):

1. Given a list of tool-like entries and a size threshold, tools above the
   threshold get `defer_loading: True` set, and constructing them as
   `anthropic.types.ToolParam` TypedDicts round-trips through
   `anthropic._models` validation used by request construction (proves the
   flag is a real, SDK-accepted field — not a name that happens to work
   because Python dicts don't validate).
2. When any tool in the array is deferred, exactly one search-tool entry
   (`ToolSearchToolBm25_20251119Param`, chosen over the regex variant because
   it requires no per-tool pattern configuration — matching the catalog's
   plain name+description shape) is present in the assembled `tools` array;
   when none are deferred, no search-tool entry is added and the array is
   byte-identical to the undeferred baseline (the "default-off, no behavior
   change" AC, proven at the request-shape level).

What's faked: the live model round trip (tool_search_tool_result →
tool_reference → tool invocation) is **not** exercised — that requires a
network call and is out of scope per the plan-template's "Out of Scope"
section below. What's real: the actual `anthropic` SDK type definitions and
their structural shape, so a shape mismatch here would also break the real
integration.

## Critical files

Read-only references (production contracts the spike must honor):

- `scripts/little_loops/tool_catalog.py` — `ToolDefinition` dataclass (no
  `defer_loading` field yet), `to_anthropic_tools()` (the "omit falsy key
  entirely" serialization pattern this spike's stand-in mirrors).
- `scripts/little_loops/host_runner.py:build_anthropic_request()`
  (lines 1263-1328) — the `tools` array assembly this spike's search-tool
  injection point models.
- `anthropic/types/tool_param.py`, `tool_search_tool_bm25_20251119_param.py`
  (installed package, not vendored) — the vendor contract being proven
  against.

New spike paths:

```
scripts/tests/spike/tool_defer_loading/
├── __init__.py
├── defer_assembly.py
└── test_defer_assembly.py
```

## Implementation

```
scripts/tests/spike/tool_defer_loading/
├── __init__.py
├── defer_assembly.py       # isolated library proving the core
└── test_defer_assembly.py  # AC test class
```

`defer_assembly.py` API sketch:

```python
from dataclasses import dataclass
from typing import Any

from anthropic.types import ToolParam
from anthropic.types.tool_search_tool_bm25_20251119_param import (
    ToolSearchToolBm25_20251119Param,
)

@dataclass(frozen=True)
class SpikeToolEntry:
    name: str
    description: str
    input_schema: dict[str, Any]

def assemble_deferred_tools(
    entries: list[SpikeToolEntry],
    *,
    defer_threshold: int,
) -> list[dict[str, Any]]:
    """Mirrors to_anthropic_tools() + defer_loading + search-tool injection.

    Entries at index >= defer_threshold get defer_loading=True. If any entry
    is deferred, prepends one ToolSearchToolBm25_20251119Param entry. Returns
    plain dicts shaped as ToolParam / ToolSearchToolBm25_20251119Param.
    """

def validates_as_tool_param(tool_dict: dict[str, Any]) -> bool:
    """True if tool_dict round-trips through anthropic's ToolParam TypedDict
    shape (checked via anthropic._models model_construct/validation, not just
    isinstance(dict))."""
```

## Acceptance Criteria → Test Table

| Test | Retires (AC / risk) | Kind |
|------|---------------------|------|
| `test_defer_loading_flag_set_above_threshold` | Risk (a): unprecedented `defer_loading` field usage | behavior |
| `test_tool_param_with_defer_loading_validates_against_sdk` | Risk (a): flag is a real, SDK-validated field, not a coincidental dict key | behavior |
| `test_search_tool_injected_when_any_tool_deferred` | Risk (b): untested search-tool-array assembly | behavior |
| `test_no_search_tool_and_no_defer_when_below_threshold` | AC bullet 3: default-off, no behavior change | behavior |
| `test_search_tool_param_validates_against_sdk` | Risk (a): search-tool entry is a real, SDK-validated shape | behavior |
| `test_spike_does_not_import_tool_catalog_or_host_runner` | isolation guard | regression |

## Verification

```bash
python -m pytest scripts/tests/spike/tool_defer_loading/ -v
python -m pytest scripts/tests/test_tool_catalog.py -v
python -m pytest scripts/tests/test_cache_control.py -v
```

## Out of Scope

- The real integration wiring (`ToolDefinition.defer_loading` field,
  `build_anthropic_request()`'s search-tool injection, `DeferredToolsConfig`,
  the six downstream call-site reviews) — that is FEAT-2672's actual
  implementation, not this spike.
- A live network round trip proving the model actually resolves a
  `tool_reference` back to a deferred tool's full definition. This spike
  proves the *request* is well-formed per the installed SDK types; it does
  not and cannot (no `ANTHROPIC_API_KEY`/OAuth profile in this environment)
  prove the *server-side* search-and-resolve behavior. This residual gap
  should be noted, not silently assumed proven, when confidence-check
  re-scores this issue.
- Choosing between `tool_search_tool_bm25_20251119` and
  `tool_search_tool_regex_20251119` as a final production decision — this
  spike picks bm25 for its own test only; FEAT-2672's Concerns section lists
  this as a still-undecided design parameter for implementation.
- The catalog-size threshold's real value — the spike takes it as a test
  parameter, not a recommendation.

## Promotion

Not promoted directly: this spike's `defer_assembly.py` logic (defer-flag
threshold + search-tool injection) informs the real
`tool_catalog.py`/`host_runner.py` changes but is re-implemented there against
the actual `ToolDefinition` dataclass rather than moved verbatim, since the
production code must integrate with `cache_control` marking and the F1 oracle
that this isolated spike deliberately excludes. Document in FEAT-2672's
implementation which spike test cases the production `test_tool_catalog.py` /
`test_cache_control.py` additions (Wiring Phase — Round 3, items 17-18) should
mirror.
