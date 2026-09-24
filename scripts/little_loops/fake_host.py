"""Fake host executable and directive-script parser (FEAT-3454).

``ll-fake-host`` is a real console-script executable driven by
:mod:`little_loops.host_runner`'s ``FakeHostRunner`` through the same
``subprocess.Popen`` path every real host CLI goes through. A test embeds an
exact sequence of wire events, failures, and timings as a "directives script"
inside the prompt string; this module parses that script and emits the
scripted stream-JSON on stdout/stderr, exiting with the scripted code.

See the FEAT-3454 issue's "Directives Language" table for the full grammar;
the vocabulary here is deliberately limited to the wire events
``run_claude_command`` (``subprocess_utils.py``) actually dispatches on.
"""

from __future__ import annotations

import json
import signal
import sys
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import TextIO

_FENCE_START = "@@fake"
_FENCE_END = "@@end"

_TERMINAL_KINDS = frozenset({"result", "turn_completed"})
_ALLOWED_AFTER_TERMINAL = frozenset({"exit", "hang"})
_KNOWN_KINDS = frozenset(
    {
        "init",
        "text",
        "tool",
        "result",
        "turn_completed",
        "raw",
        "stderr",
        "sleep",
        "exit",
        "hang",
    }
)


@dataclass(frozen=True)
class Directive:
    """One parsed directive line."""

    kind: str
    args: dict[str, Any]
    lineno: int


@dataclass(frozen=True)
class DirectivesScript:
    """A parsed, validated directive script.

    Construction validates terminal discipline: at most one of
    ``result``/``turn_completed``; nothing but ``exit``/``hang`` may follow
    it; ``exit``/``hang`` (if present) must be the last directive.
    """

    directives: list[Directive] = field(default_factory=list)
    terminal_index: int | None = None
    exit_code: int = 0

    def __post_init__(self) -> None:
        terminal_index: int | None = None
        for i, d in enumerate(self.directives):
            if d.kind in _TERMINAL_KINDS:
                if terminal_index is not None:
                    raise ValueError(
                        f"line {d.lineno}: multiple terminal directives "
                        "(only one of result/turn_completed allowed)"
                    )
                terminal_index = i
            elif terminal_index is not None and d.kind not in _ALLOWED_AFTER_TERMINAL:
                raise ValueError(
                    f"line {d.lineno}: only 'exit' or 'hang' may follow a terminal "
                    f"directive, got {d.kind!r}"
                )
        for i, d in enumerate(self.directives):
            if d.kind in ("exit", "hang") and i != len(self.directives) - 1:
                raise ValueError(f"line {d.lineno}: {d.kind!r} must be the last directive")
        object.__setattr__(self, "terminal_index", terminal_index)


DEFAULT_SCRIPT = DirectivesScript(
    directives=[
        Directive("init", {"model": "fake-model", "session": "fake-session"}, 0),
        Directive("text", {"text": "ok"}, 0),
        Directive("result", {"in": "1", "out": "1"}, 0),
    ],
)


def _parse_kv(rest: str, lineno: int, known_keys: frozenset[str]) -> dict[str, str]:
    """Parse ``key=value`` tokens, folding non-``key=`` tokens into the previous value.

    Lets a value contain spaces (``error=connection reset``) without quoting,
    as long as the value itself doesn't look like ``key=...`` for a key in
    *known_keys*.
    """
    result: dict[str, str] = {}
    current_key: str | None = None
    for token in rest.split(" "):
        if not token:
            continue
        key, sep, value = token.partition("=")
        if sep and key in known_keys:
            result[key] = value
            current_key = key
        elif current_key is not None:
            result[current_key] += " " + token
        else:
            raise ValueError(f"line {lineno}: unrecognized token {token!r}")
    return result


def _parse_line(line: str, lineno: int) -> Directive:
    parts = line.split(None, 1)
    kind = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    if kind not in _KNOWN_KINDS:
        raise ValueError(f"line {lineno}: unknown directive {kind!r}")

    if kind == "init":
        return Directive(kind, _parse_kv(rest, lineno, frozenset({"model", "session"})), lineno)

    if kind in ("text", "raw", "stderr"):
        if not rest:
            raise ValueError(f"line {lineno}: {kind!r} requires a value")
        text = rest.replace("\\n", "\n") if kind == "text" else rest
        return Directive(kind, {"text": text}, lineno)

    if kind == "tool":
        if not rest:
            raise ValueError(f"line {lineno}: 'tool' requires a name")
        name, _, json_part = rest.partition(" ")
        args: dict[str, Any] = {"name": name}
        json_part = json_part.strip()
        if json_part:
            try:
                args["input"] = json.loads(json_part)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {lineno}: invalid tool json-input: {exc}") from exc
        return Directive(kind, args, lineno)

    if kind == "result":
        known = frozenset({"error", "in", "out", "cache", "create", "omit", "structured"})
        return Directive(kind, _parse_kv(rest, lineno, known), lineno)

    if kind == "turn_completed":
        return Directive(
            kind,
            _parse_kv(rest, lineno, frozenset({"in", "out", "cached", "cache_write", "omit"})),
            lineno,
        )

    if kind == "sleep":
        value = rest.strip()
        if not value:
            raise ValueError(f"line {lineno}: 'sleep' requires a numeric value")
        try:
            float(value)
        except ValueError as exc:
            raise ValueError(f"line {lineno}: 'sleep' requires a numeric value: {value!r}") from exc
        return Directive(kind, {"seconds": value}, lineno)

    if kind == "exit":
        value = rest.strip()
        if not value:
            raise ValueError(f"line {lineno}: 'exit' requires an integer code")
        try:
            int(value)
        except ValueError as exc:
            raise ValueError(f"line {lineno}: 'exit' requires an integer code: {value!r}") from exc
        return Directive(kind, {"code": value}, lineno)

    # kind == "hang"
    if rest.strip():
        raise ValueError(f"line {lineno}: 'hang' takes no arguments")
    return Directive(kind, {}, lineno)


def parse_directives(prompt: str) -> DirectivesScript:
    """Parse the ``@@fake``/``@@end`` script block out of *prompt*.

    Returns :data:`DEFAULT_SCRIPT` when no fence is present. Raises
    ``ValueError(f"line {n}: ...")`` on any malformed directive or
    terminal-discipline violation (mirrors ``fsm/policy_rules.py``'s
    line-numbered ``ValueError`` convention).
    """
    lines = prompt.splitlines()
    fence_start = next((i for i, line in enumerate(lines) if line.strip() == _FENCE_START), None)
    if fence_start is None:
        return DEFAULT_SCRIPT

    fence_end = next(
        (i for i in range(fence_start + 1, len(lines)) if lines[i].strip() == _FENCE_END), None
    )
    if fence_end is None:
        raise ValueError(
            f"line {fence_start + 1}: '{_FENCE_START}' with no matching '{_FENCE_END}'"
        )

    directives: list[Directive] = []
    exit_code = 0
    for idx in range(fence_start + 1, fence_end):
        lineno = idx + 1
        raw_line = lines[idx].strip()
        if not raw_line or raw_line.startswith("#"):
            continue
        directive = _parse_line(raw_line, lineno)
        directives.append(directive)
        if directive.kind == "exit":
            exit_code = int(directive.args["code"])

    return DirectivesScript(directives=directives, exit_code=exit_code)


def _write_json(stream: TextIO, event: dict[str, Any]) -> None:
    print(json.dumps(event), file=stream, flush=True)


def emit(script: DirectivesScript, *, stdout: TextIO, stderr: TextIO) -> int:
    """Write *script*'s scripted stream-JSON to *stdout*/*stderr*.

    Every line is flushed immediately: with a pipe on stdout, Python
    block-buffers by default, and an unflushed line before a ``sleep`` or
    ``hang`` would never reach a real consumer.
    """
    exit_code = script.exit_code
    for d in script.directives:
        if d.kind == "init":
            event: dict[str, Any] = {"type": "system", "subtype": "init"}
            if "model" in d.args:
                event["model"] = d.args["model"]
            if "session" in d.args:
                event["session_id"] = d.args["session"]
            _write_json(stdout, event)
        elif d.kind == "text":
            _write_json(
                stdout,
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": d.args["text"]}]},
                },
            )
        elif d.kind == "tool":
            block = {"type": "tool_use", "name": d.args["name"], "input": d.args.get("input", {})}
            _write_json(stdout, {"type": "assistant", "message": {"content": [block]}})
        elif d.kind == "result":
            is_error = "error" in d.args
            # ENH-3538: emit all four keys by default (real Claude ``result``
            # events do) so complete-data tests stay complete.
            usage = _usage_block(
                d.args,
                {
                    "input_tokens": ("in", 0),
                    "output_tokens": ("out", 0),
                    "cache_read_input_tokens": ("cache", 0),
                    "cache_creation_input_tokens": ("create", 0),
                },
            )
            event = {
                "type": "result",
                "subtype": "success",
                "is_error": is_error,
                "result": d.args.get("error", "ok"),
                "usage": usage,
            }
            if is_error:
                event["error"] = d.args["error"]
            if "structured" in d.args:
                event["structured_output"] = json.loads(d.args["structured"])
            _write_json(stdout, event)
        elif d.kind == "turn_completed":
            # codex-cli 0.152.1 always emits cache_write_input_tokens (BUG-3531);
            # ``omit=cache_write`` reproduces the older-CLI shape.
            usage = _usage_block(
                d.args,
                {
                    "input_tokens": ("in", 0),
                    "output_tokens": ("out", 0),
                    "cached_input_tokens": ("cached", 0),
                    "cache_write_input_tokens": ("cache_write", 0),
                },
            )
            _write_json(stdout, {"type": "turn.completed", "usage": usage})
        elif d.kind == "raw":
            print(d.args["text"], file=stdout, flush=True)
        elif d.kind == "stderr":
            print(d.args["text"], file=stderr, flush=True)
        elif d.kind == "sleep":
            time.sleep(float(d.args["seconds"]))
        elif d.kind == "exit":
            exit_code = int(d.args["code"])
        elif d.kind == "hang":
            while True:
                signal.pause()
    return exit_code


def _usage_block(
    args: dict[str, Any], keys: dict[str, tuple[str, int | None]]
) -> dict[str, int | None]:
    """Build a usage dict from directive args (ENH-3538).

    *keys* maps each emitted usage key to ``(arg_name, default)``; a ``None``
    default means "omit unless the arg is given". Per-key options: ``omit=k1,k2``
    drops those arg names, and ``<arg>=null`` emits an explicit JSON ``null``.
    """
    omitted = {name for name in str(args.get("omit", "")).split(",") if name}
    usage: dict[str, int | None] = {}
    for usage_key, (arg_name, default) in keys.items():
        if arg_name in omitted:
            continue
        if arg_name in args:
            raw = args[arg_name]
            usage[usage_key] = None if raw == "null" else int(raw)
        elif default is not None:
            usage[usage_key] = default
    return usage


def main(argv: Sequence[str] | None = None) -> int:
    """Console-script entry point for ``ll-fake-host``.

    The prompt is the argv element containing the ``@@fake`` fence, falling
    back to ``argv[-1]`` only when no element does — ``_structured_output_args``
    appends ``--json-schema <json>`` *after* the runner's args, so bare
    ``argv[-1]`` is not always the prompt.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    prompt = next((a for a in args if _FENCE_START in a), args[-1] if args else "")
    script = parse_directives(prompt)
    return emit(script, stdout=sys.stdout, stderr=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
