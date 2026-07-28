"""Shell-escaping rule family (MR-7 bash-default, MR-9 shell-pid overescape,
MR-11 unsafe context interpolation): catches interpolation forms the FSM
engine can't parse, or that reach `bash -c` in an unsafe position.
"""

from __future__ import annotations

import re

from little_loops.fsm.schema import FSMLoop

from little_loops.fsm.validation._base import ValidationError, ValidationSeverity


# MR-7: bash-default interpolation detector. Matches ${namespace.path:-default}
# (unescaped bash `:- ` default form) that the FSM interpolator does not support.
# Negative lookbehind exempts the legitimate escaped form $${VAR:-value}.
_BASH_DEFAULT_RE = re.compile(r"(?<!\$)\$\{[^}]*:-[^}]*\}")

# MR-9: over-escaped shell `$$` detector. The FSM interpolator only rewrites the
# brace form `$${...}` → `${...}`; bare `$(...)` and `$VAR` are passed to the shell
# untouched (interpolation.py). Doubling them — `$$(` or `$$VAR` — is NOT an escape:
# the runner's `bash -c` expands the leading `$$` to the PID, so `$$(pwd)/$$DIR`
# becomes `<pid>(pwd)/<pid>DIR`. The lookahead matches `$$(` (command substitution)
# and `$$<identifier-start>` (variable) while exempting the legitimate `$${...}`
# brace escape (next char `{`) and a standalone PID `$$` (followed by `/`, `.`, space,
# or end). See ENH for the interactive-/html-/svg-generator over-escape bug.
_OVERESCAPED_SHELL_RE = re.compile(r"\$\$(?=\(|[A-Za-z_])")

# MR-11: unsafe user-controlled context interpolation detector. Matches
# ${context.<user-controlled>...} placeholders (interpolation.py substitutes these
# with a bare str(value), no shell escaping) so a raw shell-metacharacter value
# (`"`, `$`, backtick, `\`, `!`) breaks bash tokenizing or, from an untrusted
# source, injects commands (BUG-2622).
_UNSAFE_CONTEXT_INTERP_RE = re.compile(
    r"\$\{context\.(?:input|goal|description|task|prompt|query|topic)\b[^}]*\}"
)

# MR-11: quoted heredoc start, e.g. `<<'EOF'` / `<<-"EOF"`. Content between this
# line and a line consisting only of the marker is written to the shell literally
# (no expansion), so a placeholder substituted inside it is safe regardless of
# shell metacharacters.
_QUOTED_HEREDOC_START_RE = re.compile(r"<<-?\s*['\"](\w+)['\"]")

def _find_bash_default_tokens(fsm: FSMLoop) -> list[tuple[str, str]]:
    """Return (state_name, matched_token) for every action with unescaped ${ns.path:-...}.

    Scans ``state.action`` only. The escaped form ``$${VAR:-value}`` is exempted by
    the negative lookbehind in ``_BASH_DEFAULT_RE``; the engine-native ``:default=``
    form does not contain ``:-`` and is therefore never matched.
    """
    findings: list[tuple[str, str]] = []
    for state_name, state in fsm.states.items():
        if not state.action:
            continue
        for match in _BASH_DEFAULT_RE.finditer(state.action):
            findings.append((state_name, match.group(0)))
    return findings

def _validate_bash_default_interpolation(fsm: FSMLoop) -> list[ValidationError]:
    """Validate rule MR-7 (ENH-2348): unescaped bash :-default interpolation.

    The FSM interpolation engine supports ``${namespace.path:default=value}`` for
    author-specified defaults, but does NOT support the bash parameter-expansion form
    ``${namespace.path:-value}``. Any loop action that uses the bash form will crash
    at runtime with ``Path 'ns.path:-value' not found in context``.

    Supported alternatives:
      - ``${context.x:default=queue}``  — engine-native default (always preferred)
      - ``$${VAR:-value}``              — escaped, passed to the shell verbatim

    Suppressed by ``bash_default_ok: true`` at the loop top-level for the rare case
    where an author can justify the unsupported form.
    """
    if fsm.bash_default_ok:
        return []
    errors: list[ValidationError] = []
    for state_name, token in _find_bash_default_tokens(fsm):
        errors.append(
            ValidationError(
                message=(
                    f"[state: {state_name}] {token} uses unsupported bash ':-' default. "
                    "The FSM interpolator will crash at runtime with 'Path not found in context'. "
                    f"Use {token.split(':-')[0]}:default={token.split(':-')[1].rstrip('}')}}}"
                    " (engine default) or $${{VAR:-value}} (shell, escaped). "
                    "Set `bash_default_ok: true` to suppress. (ENH-2348)"
                ),
                path=f"states.{state_name}.action",
                severity=ValidationSeverity.ERROR,
            )
        )
    return errors

def _validate_overescaped_shell(fsm: FSMLoop) -> list[ValidationError]:
    """Validate rule MR-9: over-escaped shell ``$$`` that expands to the PID.

    The FSM interpolation engine only rewrites the brace form ``$${...}`` → ``${...}``;
    bare ``$(...)`` command substitution and ``$VAR`` references are passed through to
    ``bash -c`` untouched. Doubling them is therefore NOT an escape — ``$$(`` and
    ``$$VAR`` reach the shell literally, where the leading ``$$`` expands to the process
    ID. An ``init`` state that does ``echo "$$(pwd)/$$DIR"`` captures ``<pid>(pwd)/<pid>DIR``
    instead of an absolute path, silently corrupting every downstream ``${captured…}``
    reference (observed in interactive-/html-/svg-generator).

    Correct forms:
      - ``$(pwd)`` / ``$DIR``   — command substitution / variable (shell handles them)
      - ``$${VAR}`` / ``$${VAR:-x}`` — ONLY brace vars collide with ``${ns.path}`` and
        need the ``$$`` escape; the interpolator converts ``$${`` → ``${``.

    Scans shell actions only (``action_type`` shell/untyped, excluding slash commands);
    ``$$VAR`` in a prompt is inert text. Suppressed by ``shell_pid_ok: true`` at the
    loop top-level for the rare case where a literal PID is intended.
    """
    if fsm.shell_pid_ok:
        return []
    errors: list[ValidationError] = []
    for state_name, state in fsm.states.items():
        if not state.action:
            continue
        # Shell-only: prompt/slash-command actions never reach `bash -c`, so a `$$`
        # there is harmless text. Mirror the shell gate used by other shell rules.
        if state.action_type not in ("shell", None):
            continue
        if state.action.lstrip().startswith("/"):
            continue
        for match in _OVERESCAPED_SHELL_RE.finditer(state.action):
            # Show the offending token plus the next char for context (e.g. `$$(` / `$$D`).
            start = match.start()
            token = state.action[start : start + 3]
            errors.append(
                ValidationError(
                    message=(
                        f"[state: {state_name}] '{token}' over-escapes shell `$$`. "
                        "The interpolator only converts the brace form $${{...}}; bare "
                        "$(...) and $VAR pass through untouched, so $$ here expands to the "
                        "PID at `bash -c` time (e.g. $$(pwd)/$$DIR -> <pid>(pwd)/<pid>DIR). "
                        "Use single $ ($(pwd), $DIR); reserve $$ for the $${{VAR}} brace "
                        "escape. Set `shell_pid_ok: true` to suppress. (MR-9)"
                    ),
                    path=f"states.{state_name}.action",
                    severity=ValidationSeverity.ERROR,
                )
            )
    return errors

def _find_unsafe_context_interpolations(fsm: FSMLoop) -> list[tuple[str, str]]:
    """Return (state_name, matched_token) for user-controlled ${context.*} vars
    interpolated into a shell body outside a safe position.

    Safe positions (not flagged):
      - single-quoted string (``'...'``) — bash performs no expansion inside it
      - quoted heredoc (``<<'EOF'`` / ``<<-"EOF"``) — content is written literally
      - the ``:shell`` suffix — interpolation.py shlex-quotes it at substitution time

    Everything else (double-quoted, or a bare unquoted token position) is
    flagged: a value containing ``"``, ``$``, `` ` ``, ``\\``, or ``!`` breaks
    bash tokenizing there, or injects commands from an untrusted source.
    """
    findings: list[tuple[str, str]] = []
    for state_name, state in fsm.states.items():
        if not state.action:
            continue
        if state.action_type not in ("shell", None):
            continue
        if state.action.lstrip().startswith("/"):
            continue
        heredoc_marker: str | None = None
        for line in state.action.splitlines():
            stripped = line.strip()
            if heredoc_marker is not None:
                if stripped == heredoc_marker:
                    heredoc_marker = None
                continue
            if stripped.startswith("#"):
                continue  # comment line, not evaluated by bash
            heredoc_match = _QUOTED_HEREDOC_START_RE.search(line)
            if heredoc_match:
                heredoc_marker = heredoc_match.group(1)
            for match in _UNSAFE_CONTEXT_INTERP_RE.finditer(line):
                token = match.group(0)
                if token.endswith(":shell}"):
                    continue
                if line[: match.start()].count("'") % 2 == 1:
                    continue  # inside a single-quoted string
                findings.append((state_name, token))
    return findings

def _validate_unsafe_context_interpolation(fsm: FSMLoop) -> list[ValidationError]:
    """Validate rule MR-11 (BUG-2622): unsafe raw shell interpolation of user context.

    ``interpolate()`` substitutes ``${context.*}`` with a bare ``str(value)`` and no
    shell escaping (interpolation.py). When a `shell` action pastes a user-controlled
    value (``input``/``goal``/``description``/``task``/``prompt``/``query``/``topic``)
    into a bash token position — e.g. ``[ -z "${context.input}" ]`` — a value
    containing ``"``, ``$``, `` ` ``, ``\\``, or ``!`` breaks bash tokenizing (the
    action misroutes to `on_error`/`on_no`) or, from an untrusted source, injects
    commands.

    Fix: wrap the placeholder in a single-quoted string, write it through a quoted
    heredoc (``<<'EOF'``), or add the ``:shell`` suffix (``${context.input:shell}``)
    to shlex-quote it at interpolation time.

    Suppressed by ``unsafe_context_interpolation_ok: true`` at the loop top-level.
    """
    if fsm.unsafe_context_interpolation_ok:
        return []
    errors: list[ValidationError] = []
    for state_name, token in _find_unsafe_context_interpolations(fsm):
        errors.append(
            ValidationError(
                message=(
                    f"[state: {state_name}] {token} interpolates user-controlled "
                    'context raw into a shell body. A value containing ", $, `, \\, '
                    "or ! can break bash tokenizing or inject commands (BUG-2622). "
                    "Wrap it in a single-quoted string, write it through a quoted "
                    "heredoc (<<'EOF'), or add the :shell suffix to shlex-quote it "
                    "(e.g. ${context.input:shell}). Set "
                    "`unsafe_context_interpolation_ok: true` to suppress. (MR-11)"
                ),
                path=f"states.{state_name}.action",
                severity=ValidationSeverity.WARNING,
            )
        )
    return errors