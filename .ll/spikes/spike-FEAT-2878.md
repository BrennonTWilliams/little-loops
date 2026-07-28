# Spike Plan: FEAT-2878 — Trace-level assertions in the eval harness

## Context

From `### Outcome Risk Factors` (Confidence Check Notes, 2026-07-28):

> Deep per-site complexity: the core mechanism — surfacing live `tool_use`
> events out of `subprocess_utils.run_claude_command()` and adding filesystem
> sandboxing to `host_runner.build_streaming()` — is an unproven, novel
> mechanism in this codebase; neither capability exists today and both
> require architectural, not mechanical, changes.
>
> No existing fixture jails filesystem access to a scoped temp workspace; the
> closest scaffolding (`test_subprocess_utils.py::temp_repo`,
> `test_cross_host_baseline.py::_make_loop_project`) is not a ready template,
> so the new sandboxing-assertion fixture needs to be built from scratch.

Both drivers apply: **(a)** zero precedent — no code path anywhere in this
codebase parses `tool_use` content blocks out of the `stream-json` event
format live during a run (only post-hoc, from on-disk JSONL, in
`cli/logs.py`); **(b)** no existing test exercises building an *ordered*
tool-call trace from a live event stream via callback.

This spike proves the riskier and more central of the two named mechanisms —
live tool-call trace capture — since filesystem sandboxing (Decision 3,
`HostCapabilities` flag) is a comparatively mechanical per-host flag addition
once the trace-capture data shape exists, and the issue's own Decision 1
already resolved *where* the trace lives (`RunnerResult.tool_trace`). The
concrete failure this spike must rule out: that parsing `assistant` events'
`content` blocks for `type == "tool_use"` mid-stream, in the same
selector-loop/JSON-per-line shape `run_claude_command()` already uses,
produces a correctly ordered, complete trace — including multi-tool-call
messages and interleaved text/tool_use blocks in one event.

## Approach

Build a standalone event-stream parser library that takes the exact
`stream-json` line shapes `subprocess_utils.run_claude_command()` already
consumes (`type: "assistant"` events with a `message.content` block list) and
extracts an ordered `list[ToolCall]` (name, input, sequence index) via a
callback, mirroring the existing text-extraction branch
(`subprocess_utils.py:475-489`) but for `block.get("type") == "tool_use"`
instead of `"text"`. The parser is fed **synthetic JSONL fixture lines** (no
real host CLI subprocess) — this is a pure data-transformation mechanism, so
a real subprocess is not required to prove it; only the JSON event shape
matters, and that shape is fixed protocol (already relied on elsewhere in
`cli/logs.py`'s post-hoc extraction, `block.get("type") == "tool_use"`,
`block.get("name")`). What's faked: the subprocess/selector loop itself
(real in production, irrelevant to the parsing risk). What's proven: correct,
ordered extraction across message boundaries and multi-block messages.

## Critical files

Read-only references informing the spike:
- `scripts/little_loops/subprocess_utils.py:463-534` — the exact event-loop
  shape and JSON keys (`event.get("type")`, `msg.get("content", [])`,
  `block.get("type")`) the spike's parser must accept as input, and the
  `else: continue` line (522, 524) the spike proves what to do instead of.
- `scripts/little_loops/cli/logs.py` (`_extract_ll_event_streams`,
  `InvocationEvent` dataclass) — the existing post-hoc `tool_use` block
  detection pattern (`block.get("type") == "tool_use"`, `block.get("name")`)
  the live parser's block-matching logic must stay consistent with.
- `scripts/little_loops/runner_spec.py:56-64` — `RunnerResult` shape the
  issue's Decision 1 selected `tool_trace` field to extend; the spike's
  `ToolCall` shape should be JSON-serializable so it drops into that field
  without translation.

New spike paths: `scripts/tests/spike/eval_trace_capture/`.

## Implementation

```
scripts/tests/spike/eval_trace_capture/
├── __init__.py
├── trace_capture.py         # the isolated library proving the core
└── test_trace_capture.py    # the AC test class
```

API sketch (`trace_capture.py`):

```python
@dataclass(frozen=True)
class ToolCall:
    index: int          # position in the overall ordered trace
    name: str
    input: dict[str, Any]

def extract_tool_calls(
    stream_lines: Iterable[str],
    on_tool_call: Callable[[ToolCall], None] | None = None,
) -> list[ToolCall]:
    """Parse stream-json lines (the run_claude_command() event shape) and
    return an ordered ToolCall trace, invoking on_tool_call live per call."""
```

`extract_tool_calls` iterates lines, `json.loads` each, and for
`event.get("type") == "assistant"` walks `message.content` blocks in order,
emitting a `ToolCall` (with a monotonically increasing `index`) for each
`block.get("type") == "tool_use"`, calling `on_tool_call` synchronously
(proving the "live callback during a run" property, not just post-hoc
collection) before appending to the returned list. Malformed/non-JSON lines
are skipped, mirroring `subprocess_utils.py`'s `except (json.JSONDecodeError,
KeyError, TypeError): pass`.

## Acceptance Criteria → Test Table

| Test | Retires (AC / risk) | Kind |
|------|---------------------|------|
| `test_ordered_trace_across_multiple_assistant_events` | Risk (a): zero-precedent live tool_use extraction — proves correct ordering across separate stream events | behavior |
| `test_multiple_tool_calls_in_one_message_preserve_order` | Risk (a): a single `assistant` event with several `tool_use` blocks (parallel tool calls) must not collapse or reorder | behavior |
| `test_interleaved_text_and_tool_use_blocks_only_captures_tool_use` | Risk (a): mirrors the existing text-only extraction branch's block-type filter, proving both can coexist without cross-contamination | behavior |
| `test_callback_invoked_live_per_tool_call` | Risk (b): untested live-callback property (not just post-hoc list building) — this is the "abort mid-run" precondition AC depends on | behavior |
| `test_malformed_json_line_skipped_not_raised` | robustness parity with `subprocess_utils.py`'s existing `except (...): pass` behavior | behavior |
| `test_spike_does_not_import_production_subprocess_utils` | isolation guard — AST sniff that the spike module has no `import little_loops` reference | regression |

## Verification

```bash
python -m pytest scripts/tests/spike/eval_trace_capture/ -v
python -m pytest scripts/tests/test_subprocess_utils.py -v
```

## Out of Scope

- Wiring the parser into `subprocess_utils.run_claude_command()` itself (the
  real `else: continue` branch replacement) — that is the implementation
  task, not the spike.
- Filesystem sandboxing (`host_runner.build_streaming()` workspace jail,
  Decision 3) — a separate, more mechanical mechanism; not spiked here.
- `RunnerResult.tool_trace` wiring, `HostCapabilities` flag, multi-host
  divergence — all downstream integration, out of scope per the issue's own
  Decision 1–3 write-ups.

## Promotion

On acceptance, promote `trace_capture.py`'s parsing logic (adapted into
`subprocess_utils.run_claude_command()`'s existing event loop, replacing the
`else: continue` discard at line 522/524 with a call to an
`on_tool_call` callback) to `scripts/little_loops/spike/eval_trace_capture/`
in a separate PR, then integrate directly into `subprocess_utils.py` per
Implementation Step 1.
