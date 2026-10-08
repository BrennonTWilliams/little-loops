"""Typed action specifications, grammar and fingerprints for ``ll-next`` (FEAT-3561).

Pure module: no I/O, no clock, no config. It owns

* the ``action_spec`` **tagged union** (every serialized spec carries a required
  ``variant`` discriminator; ``slash`` and ``loop`` are registered),
* the ``action_key`` projection of a spec (seven slash rows plus ``run-loop``),
* ``action_fingerprint`` (host-neutral, path-free, ``working_directory``-free), and
* render/parse round-trip helpers for slash arguments and shell argv.

Display strings are copyable text, never executed by ``ll-next``.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, ClassVar, NamedTuple

from little_loops.next_arena.registry import ACTION_VARIANTS, RESERVED_VARIANTS

#: Prefix of a rendered slash action (display syntax only; never fingerprint material).
SLASH_PREFIX = "/ll:"

_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_SPEC_KEYS = frozenset({"variant", "command", "args", "working_directory"})

#: Shell prefix of a rendered ``loop`` action (``run`` is always explicit: a leading bare
#: loop name triggers the CLI's subcommand insertion).
LOOP_COMMAND_PREFIX: tuple[str, ...] = ("ll-loop", "run")
#: ``action_key`` of the ``loop`` variant.
LOOP_ACTION_KEY = "run-loop"
#: The only fingerprint scope v1 defines: exact target, top-level source identity and bytes.
FINGERPRINT_SCOPE_V1 = "v1/top-level-bytes"
#: Prefix of a built-in ``definition_source``.
BUILTIN_SOURCE_PREFIX = "builtin:"

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_LOOP_SPEC_KEYS = (
    "variant",
    "target",
    "definition_source",
    "definition_digest",
    "fingerprint_scope",
    "working_directory",
)


class ActionSpecError(ValueError):
    """Base error for malformed or unsupported action specifications."""


class UnrepresentableAction(ActionSpecError):
    """A token cannot be faithfully rendered/parsed in the declared syntax.

    Raised for slash tokens with a leading dash, whitespace, quotes or any
    character outside ``[A-Za-z0-9_.:-]``, and for shell options/prefix tokens
    that would be reinterpreted as flags or operands.
    """


class UnknownVariantError(ActionSpecError):
    """``variant`` is missing, reserved for a follow-on slice, or unregistered."""


def validate_token(token: str, *, what: str = "token") -> str:
    """Return *token* unchanged if it is a representable slash token, else raise."""
    if not isinstance(token, str) or not _TOKEN_RE.match(token):
        raise UnrepresentableAction(f"{what} {token!r} is not representable as a slash token")
    return token


@dataclass(frozen=True)
class SlashActionSpec:
    """The ``slash`` variant: ``/ll:<command> <args...>`` run from ``working_directory``.

    ``command`` is the host-neutral command name (no ``/ll:`` prefix); ``args`` is the
    ordered positional token list. Construction validates every token.
    """

    variant: ClassVar[str] = "slash"

    command: str
    args: tuple[str, ...]
    working_directory: str

    def __post_init__(self) -> None:
        validate_token(self.command, what="command")
        object.__setattr__(self, "args", tuple(self.args))
        for arg in self.args:
            validate_token(arg, what="argument")


def _is_relative_posix(path: str) -> bool:
    """True for a non-empty relative POSIX path without ``..``/empty/``.`` segments."""
    if not path or path.startswith("/") or "\\" in path or "\x00" in path:
        return False
    return all(part not in ("", ".", "..") for part in path.split("/"))


def validate_definition_source(source: str) -> str:
    """Return *source* if it is a project-relative path or ``builtin:<relative path>``.

    Absolute, traversing (``..``), empty-segment and drive-style identities are rejected:
    the identity is fingerprint material and must survive relocating the project root.
    """
    if not isinstance(source, str):
        raise ActionSpecError(f"definition_source must be a string, got {type(source).__name__}")
    body = (
        source[len(BUILTIN_SOURCE_PREFIX) :] if source.startswith(BUILTIN_SOURCE_PREFIX) else source
    )
    if not _is_relative_posix(body) or _DRIVE_RE.match(body):
        raise ActionSpecError(f"definition_source {source!r} is not a project-relative identity")
    return source


@dataclass(frozen=True)
class LoopActionSpec:
    """The ``loop`` variant: ``ll-loop run -- <target>`` run from ``working_directory``.

    ``target`` is the exact zero-argument command operand; ``definition_source`` the
    resolved top-level source (project-relative YAML path or ``builtin:<relative path>``);
    ``definition_digest`` the SHA-256 of the **top-level definition bytes** (not the
    expanded executable definition or effective runtime context); ``fingerprint_scope``
    pins that limited meaning. ``working_directory`` is the printed absolute project root
    (execution provenance, never fingerprint material).
    """

    variant: ClassVar[str] = "loop"

    target: str
    definition_source: str
    definition_digest: str
    fingerprint_scope: str
    working_directory: str

    def __post_init__(self) -> None:
        for name in ("target", "definition_source", "definition_digest", "fingerprint_scope"):
            if not isinstance(getattr(self, name), str):
                raise ActionSpecError(f"loop action_spec {name} must be a string")
        if not isinstance(self.working_directory, str) or not self.working_directory:
            raise ActionSpecError("loop action_spec working_directory must be a nonempty string")
        if not self.target or "\x00" in self.target:
            raise UnrepresentableAction(f"loop target {self.target!r} is not representable")
        validate_definition_source(self.definition_source)
        if not _DIGEST_RE.match(self.definition_digest):
            raise ActionSpecError(
                f"definition_digest {self.definition_digest!r} is not sha256:<64 lowercase hex>"
            )
        if self.fingerprint_scope != FINGERPRINT_SCOPE_V1:
            raise ActionSpecError(f"unsupported fingerprint_scope {self.fingerprint_scope!r}")


#: Union of registered spec classes; follow-ons add their variants here.
ActionSpec = SlashActionSpec | LoopActionSpec


def spec_to_dict(spec: ActionSpec) -> dict[str, Any]:
    """Serialize *spec* to its tagged-union JSON shape (``variant`` first)."""
    if isinstance(spec, LoopActionSpec):
        return {
            "variant": spec.variant,
            "target": spec.target,
            "definition_source": spec.definition_source,
            "definition_digest": spec.definition_digest,
            "fingerprint_scope": spec.fingerprint_scope,
            "working_directory": spec.working_directory,
        }
    return {
        "variant": spec.variant,
        "command": spec.command,
        "args": list(spec.args),
        "working_directory": spec.working_directory,
    }


def spec_from_dict(data: Mapping[str, Any]) -> ActionSpec:
    """Deserialize a tagged-union spec, dispatching on ``variant``.

    Raises:
        UnknownVariantError: ``variant`` is missing, reserved (``sprint``, ``scan``) or
            unregistered.
        ActionSpecError: the payload shape is invalid for the named variant.
    """
    if not isinstance(data, Mapping):
        raise ActionSpecError(f"action_spec must be a mapping, got {type(data).__name__}")
    variant = data.get("variant")
    if not isinstance(variant, str):
        raise UnknownVariantError("action_spec requires a string 'variant' discriminator")
    if variant in RESERVED_VARIANTS:
        raise UnknownVariantError(f"action_spec variant {variant!r} is reserved, not registered")
    if variant not in ACTION_VARIANTS:
        raise UnknownVariantError(f"unregistered action_spec variant {variant!r}")
    if variant == LoopActionSpec.variant:
        return _loop_spec_from_dict(data)
    unknown = sorted(set(data) - _SPEC_KEYS)
    missing = sorted(_SPEC_KEYS - set(data))
    if unknown or missing:
        raise ActionSpecError(
            f"slash action_spec keys invalid (unknown: {unknown}, missing: {missing})"
        )
    command, args, cwd = data["command"], data["args"], data["working_directory"]
    if not isinstance(command, str) or not isinstance(cwd, str):
        raise ActionSpecError("slash action_spec command and working_directory must be strings")
    if isinstance(args, str) or not isinstance(args, Sequence):
        raise ActionSpecError("slash action_spec args must be a list of strings")
    if not all(isinstance(a, str) for a in args):
        raise ActionSpecError("slash action_spec args must be a list of strings")
    return SlashActionSpec(command=command, args=tuple(args), working_directory=cwd)


def _loop_spec_from_dict(data: Mapping[str, Any]) -> LoopActionSpec:
    unknown = sorted(set(data) - set(_LOOP_SPEC_KEYS))
    missing = sorted(set(_LOOP_SPEC_KEYS) - set(data))
    if unknown or missing:
        raise ActionSpecError(
            f"loop action_spec keys invalid (unknown: {unknown}, missing: {missing})"
        )
    for key in _LOOP_SPEC_KEYS[1:]:
        if not isinstance(data[key], str):
            raise ActionSpecError(f"loop action_spec {key} must be a string")
    return LoopActionSpec(
        target=data["target"],
        definition_source=data["definition_source"],
        definition_digest=data["definition_digest"],
        fingerprint_scope=data["fingerprint_scope"],
        working_directory=data["working_directory"],
    )


# --- action_key projection -------------------------------------------------------------

#: ``action_key`` -> (command, leading args); the issue ID is appended as the last arg.
ACTION_KEY_TABLE: Mapping[str, tuple[str, tuple[str, ...]]] = MappingProxyType(
    {
        "format-issue": ("format-issue", ()),
        "verify-issues": ("verify-issues", ()),
        "confidence-check": ("confidence-check", ()),
        "refine-issue": ("refine-issue", ()),
        "manage-issue:fix": ("manage-issue", ("bug", "fix")),
        "manage-issue:implement": ("manage-issue", ("feature", "implement")),
        "manage-issue:improve": ("manage-issue", ("enhancement", "improve")),
    }
)

#: Every ``action_key`` the output admits: the seven slash rows plus the loop variant's key.
#: ``ACTION_KEY_TABLE`` itself stays the unchanged seven slash mappings.
ACTION_KEYS: tuple[str, ...] = (*ACTION_KEY_TABLE, LOOP_ACTION_KEY)

_KEY_BY_SHAPE: Mapping[tuple[str, tuple[str, ...]], str] = MappingProxyType(
    {shape: key for key, shape in ACTION_KEY_TABLE.items()}
)


def slash_spec_for(action_key: str, issue_id: str, working_directory: str) -> SlashActionSpec:
    """Build the spec for one of the seven ``action_key`` rows targeting *issue_id*."""
    try:
        command, prefix = ACTION_KEY_TABLE[action_key]
    except KeyError:
        raise ActionSpecError(f"unknown action_key {action_key!r}") from None
    return SlashActionSpec(command, (*prefix, issue_id), working_directory)


def action_key(spec: ActionSpec) -> str:
    """Project *spec* onto its ``action_key`` (pure; inverse of :func:`slash_spec_for`)."""
    if isinstance(spec, LoopActionSpec):
        return LOOP_ACTION_KEY
    if not spec.args:
        raise ActionSpecError(f"{spec.command!r} spec has no target argument")
    key = _KEY_BY_SHAPE.get((spec.command, spec.args[:-1]))
    if key is None:
        raise ActionSpecError(f"no action_key for {spec.command!r} {list(spec.args)!r}")
    return key


# --- fingerprint -------------------------------------------------------------------------


def fingerprint_material(spec: ActionSpec) -> dict[str, Any]:
    """Return the semantic projection fingerprinted for *spec*.

    Host-neutral (no ``/ll:`` prefix) and path-free: ``working_directory`` and
    display text are excluded. The ``loop`` variant binds the exact target, the resolved
    top-level source identity and its captured-bytes digest under the pinned
    ``fingerprint_scope``; effective context, run IDs, timestamps and absolute provenance
    paths are never material.
    """
    if isinstance(spec, LoopActionSpec):
        return {
            "variant": spec.variant,
            "target": spec.target,
            "definition_source": spec.definition_source,
            "definition_digest": spec.definition_digest,
            "fingerprint_scope": spec.fingerprint_scope,
        }
    return {"variant": spec.variant, "command": spec.command, "args": list(spec.args)}


def action_fingerprint(spec: ActionSpec) -> str:
    """Return ``sha256:<hex>`` of the canonical JSON of :func:`fingerprint_material`."""
    canonical = json.dumps(
        fingerprint_material(spec), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --- slash grammar -----------------------------------------------------------------------


def render_slash(spec: SlashActionSpec) -> str:
    """Render *spec* as ``/ll:<command> <arg> ...`` (single-space separated)."""
    return " ".join([SLASH_PREFIX + spec.command, *spec.args])


def parse_slash(text: str) -> tuple[str, tuple[str, ...]]:
    """Parse rendered slash text into ``(command, args)``; no I/O, never executes.

    Raises:
        UnrepresentableAction: *text* is not exactly the :func:`render_slash` grammar.
    """
    if not text.startswith(SLASH_PREFIX):
        raise UnrepresentableAction(f"slash action must start with {SLASH_PREFIX!r}: {text!r}")
    head, *args = text[len(SLASH_PREFIX) :].split(" ")
    validate_token(head, what="command")
    for arg in args:
        validate_token(arg, what="argument")
    return head, tuple(args)


# --- loop command ------------------------------------------------------------------------


def render_loop(spec: LoopActionSpec) -> str:
    """Render a loop spec as ``ll-loop run -- <target>`` (``shlex.join`` quoting).

    The target is always an operand after ``--``, so a leading-dash name stays literal.
    """
    return render_shell(LOOP_COMMAND_PREFIX, (), (spec.target,))


def render_action(spec: ActionSpec) -> str:
    """Render any registered spec as its copyable display command."""
    if isinstance(spec, LoopActionSpec):
        return render_loop(spec)
    return render_slash(spec)


# --- shell argv --------------------------------------------------------------------------


class ParsedShell(NamedTuple):
    """Recovered pieces of a rendered shell action."""

    prefix: tuple[str, ...]
    options: tuple[str, ...]
    operands: tuple[str, ...]


def render_shell(
    prefix: Sequence[str],
    options: Sequence[str] = (),
    operands: Sequence[str] = (),
) -> str:
    """Render shell argv as copyable text with ``shlex.join``.

    Layout: ``prefix... options... [-- operands...]``. Modeled options come before the
    ``--`` terminator and operands after it, so a leading-dash operand can never be
    parsed as a flag. ``prefix`` (program and subcommands) must not start with ``-``;
    ``options`` must be empty or start with a ``-`` token and never contain ``--``.

    Raises:
        UnrepresentableAction: the pieces cannot round-trip through :func:`parse_shell`.
    """
    if not prefix:
        raise UnrepresentableAction("shell action requires a program in prefix")
    if any(tok.startswith("-") for tok in prefix):
        raise UnrepresentableAction("shell prefix tokens must not start with '-'")
    if options and not options[0].startswith("-"):
        raise UnrepresentableAction("shell options must begin with a flag token")
    if "--" in options:
        raise UnrepresentableAction("'--' is reserved as the options terminator")
    argv = [*prefix, *options]
    if operands:
        argv.extend(["--", *operands])
    return shlex.join(argv)


def parse_shell(text: str) -> ParsedShell:
    """Recover ``(prefix, options, operands)`` from :func:`render_shell` output.

    Pure ``shlex.split``; nothing is executed or expanded.
    """
    tokens = shlex.split(text)
    if "--" in tokens:
        cut = tokens.index("--")
        head, operands = tokens[:cut], tokens[cut + 1 :]
    else:
        head, operands = tokens, []
    first_flag = next((i for i, tok in enumerate(head) if tok.startswith("-")), len(head))
    return ParsedShell(tuple(head[:first_flag]), tuple(head[first_flag:]), tuple(operands))
