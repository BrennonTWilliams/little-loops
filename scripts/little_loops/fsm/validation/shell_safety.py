"""Shell-escaping rule family (MR-7 bash-default, MR-9 shell-pid overescape,
MR-11 unsafe context interpolation): catches interpolation forms the FSM
engine can't parse, or that reach `bash -c` in an unsafe position.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from little_loops.fsm.interp_sweep import _C_FLAG_RE, classify_site, scan_action
from little_loops.fsm.interpolation import InterpolationError, parse_interpolation_suffixes
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

# MR-11: unsafe user-controlled interpolation detector, namespace-generic
# (ENH-3342 widening). Matches ${context.*} / ${captured.*} / ${prev.*} —
# the three namespaces classify_site() has a bash-token-position trust verdict
# for (see Program Design § Decision Rules "Namespace scope of the
# bash-token-position scan"). Untrusted-ness itself comes from classify_site(),
# not this pattern — the pattern only bounds which namespaces are looked at.
_UNSAFE_CONTEXT_INTERP_RE = re.compile(r"\$\{(context|captured|prev)\.([^}]+)\}")

# MR-11: quoted heredoc start, e.g. `<<'EOF'` / `<<-"EOF"`. Content between this
# line and a line consisting only of the marker is written to the shell literally
# (no expansion), so a placeholder substituted inside it is safe regardless of
# shell metacharacters *from bash's perspective* — this scanner only decides
# whether to skip the interior from its own bash-token-position scan; whether
# that interior is also a Python body (and therefore flagged by the delegated
# `scan_action()` half) is a separate question this regex does not answer.
# Group 1 is the `-` of `<<-` (tab-relaxed terminator indent); group 2 is the marker.
_QUOTED_HEREDOC_START_RE = re.compile(r"<<(-)?\s*['\"](\w+)['\"]")

# The `# ll-lint: mr11-ok(<namespace>.<key>) <reason>` per-site suppression
# marker (ENH-3342). Group 1 is everything after `mr11-ok`, parsed further by
# `_parse_mr11_marker()` — kept loose here so a missing `(...)` still matches
# and can be reported as malformed rather than silently ignored as a plain
# comment.
_MR11_MARKER_PREFIX_RE = re.compile(r"#\s*ll-lint:\s*mr11-ok(.*)$")
_MR11_MARKER_BODY_RE = re.compile(r"^\s*\(([^)]*)\)\s*(.*)$")
_ISSUE_ID_RE = re.compile(r"\b[A-Z]{2,}-\d+\b")


@dataclass(frozen=True)
class MarkerParse:
    """One parsed `# ll-lint: mr11-ok(...)` marker line.

    `var` is the exempted `<namespace>.<key>` for a well-formed marker, or
    `None` for a malformed one (`defect` then names the problem). Never
    constructed for an ordinary comment — `_parse_mr11_marker()` returns
    `None` in that case instead.
    """

    var: str | None
    reason: str
    issue_id: str | None
    malformed: bool
    defect: str


def _parse_mr11_marker(line: str) -> MarkerParse | None:
    """Parse a `# ll-lint: mr11-ok(<namespace>.<key>) <reason>` marker.

    Returns `None` for a line with no `mr11-ok` marker at all (an ordinary
    comment). Returns a `MarkerParse` — well-formed or malformed — otherwise.
    A malformed marker (missing `(...)`, empty/dotless variable, no reason,
    a reason with no issue-ID-shaped token, or `${` anywhere in it) is a
    validator ERROR, not a silently-ignored comment (constraint 2/4).
    """
    prefix_match = _MR11_MARKER_PREFIX_RE.search(line)
    if prefix_match is None:
        return None
    rest = prefix_match.group(1)
    body_match = _MR11_MARKER_BODY_RE.match(rest)
    if body_match is None:
        return MarkerParse(
            var=None,
            reason="",
            issue_id=None,
            malformed=True,
            defect="missing `(<namespace>.<key>)` after `mr11-ok`",
        )
    var_text = body_match.group(1).strip()
    reason = body_match.group(2).strip()
    if "${" in var_text or "${" in reason:
        return MarkerParse(
            var=None,
            reason=reason,
            issue_id=None,
            malformed=True,
            defect="marker must not contain `${` — the FSM interpolates the whole "
            "action string, comments included, so a quoted token becomes its own "
            "live interpolation site",
        )
    if not var_text or "." not in var_text:
        return MarkerParse(
            var=None,
            reason=reason,
            issue_id=None,
            malformed=True,
            defect=f"'{var_text}' is not a valid <namespace>.<key>",
        )
    if not reason:
        return MarkerParse(
            var=None,
            reason="",
            issue_id=None,
            malformed=True,
            defect="missing reason — a marker must cite a tracking issue ID",
        )
    issue_match = _ISSUE_ID_RE.search(reason)
    if issue_match is None:
        return MarkerParse(
            var=None,
            reason=reason,
            issue_id=None,
            malformed=True,
            defect="reason must cite a tracking issue ID (e.g. ENH-1234)",
        )
    return MarkerParse(
        var=var_text,
        reason=reason,
        issue_id=issue_match.group(0),
        malformed=False,
        defect="",
    )


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


@dataclass(frozen=True)
class _Mr11Finding:
    """One MR-11 finding, from either scan half."""

    state: str
    token: str
    var: str
    in_python_body: bool
    misapplied_remedy: bool
    line: int = 0
    host_shape: str = ""


def _find_adjacent_marker(
    lines: list[str], markers_by_line: dict[int, MarkerParse], line_no: int, var: str
) -> MarkerParse | None:
    """Return the marker (if any) adjacent to ``line_no`` naming ``var``.

    "Adjacent" (constraint 3) is: trailing on ``line_no`` itself, or alone on
    one of a contiguous run of standalone comment lines directly above it —
    a line at a time, stopping at the first non-comment line. The contiguous
    run (not just exactly ``line_no - 1``) lets two sibling sites on one
    physical line each get their own stacked preceding marker when there is
    no room for both to trail (see the bulk-marker-insertion tooling for
    ENH-3358, which relies on this).
    """
    trailing = markers_by_line.get(line_no)
    if trailing is not None and trailing.var == var:
        return trailing
    i = line_no - 1
    while i >= 1 and lines[i - 1].strip().startswith("#"):
        candidate = markers_by_line.get(i)
        if candidate is not None and candidate.var == var:
            return candidate
        i -= 1
    return None


def _scan_state_for_mr11(
    state_name: str, action: str, fsm_name: str
) -> tuple[list[_Mr11Finding], list[ValidationError]]:
    """Scan one state's shell action for MR-11 findings and marker diagnostics.

    Two independent scan paths, both classified via ``classify_site()``
    (ENH-3338), per the Program Design two-scan-path decision:

      1. Bash-token-position scan (this function's own line walk, scoped to
         the ``context``/``captured``/``prev`` namespaces): unchanged
         single-quote / ``:shell`` clearing rules, a column-0 heredoc
         terminator, and *no* flagging inside a quoted heredoc or a
         `python3 -c "..."` body — those interiors are the delegated half's
         territory.
      2. Delegated Python-literal-position scan via
         ``interp_sweep.scan_action()`` — covers a quoted heredoc that *is*
         a Python body, and a ``python3 -c "..."`` body.

    Markers are parsed from every line up front (before either scan's own
    comment/heredoc skip logic runs), so a marker inside a heredoc's Python
    body is recognized. A well-formed marker on the bash-token half must sit
    on the finding's own line or alone on the line immediately above it
    (constraint 3); on the delegated half it exempts its named variable for
    the whole action (constraint 6, since ``scan_action()`` merges duplicate
    sites action-wide). A malformed marker is always an ERROR; a well-formed
    marker matching no finding is a stale-marker WARNING (constraint 7).
    """
    lines = action.splitlines()
    marker_errors: list[ValidationError] = []
    markers_by_line: dict[int, MarkerParse] = {}
    for line_no, line in enumerate(lines, start=1):
        parsed = _parse_mr11_marker(line)
        if parsed is None:
            continue
        if parsed.malformed:
            marker_errors.append(
                ValidationError(
                    message=(
                        f"[state: {state_name}] malformed `# ll-lint: mr11-ok(...)` "
                        f"marker at line {line_no}: {parsed.defect}. Grammar: "
                        "`# ll-lint: mr11-ok(<namespace>.<key>) <reason citing an "
                        "issue ID>`. (MR-11)"
                    ),
                    path=f"states.{state_name}.action",
                    severity=ValidationSeverity.ERROR,
                )
            )
            continue
        markers_by_line[line_no] = parsed

    consumed: set[str] = set()

    # -- Half 1: bash-token-position scan --
    bash_findings: list[_Mr11Finding] = []
    heredoc_marker: str | None = None
    heredoc_indented = False
    c_quote: str | None = None
    for line_no, line in enumerate(lines, start=1):
        if heredoc_marker is not None:
            terminator_line = line.lstrip("\t") if heredoc_indented else line
            if terminator_line == heredoc_marker:
                heredoc_marker = None
            continue  # heredoc interior: not this half's territory either way
        if c_quote is not None:
            close = line.find(c_quote)
            if close == -1:
                continue  # still inside the -c body
            c_quote = None
            line = line[close + 1 :]
        stripped = line.strip()
        if stripped.startswith("#"):
            continue  # comment line (markers already collected above)
        scan_upto = len(line)
        heredoc_match = _QUOTED_HEREDOC_START_RE.search(line)
        if heredoc_match:
            heredoc_indented = heredoc_match.group(1) is not None
            heredoc_marker = heredoc_match.group(2)
            scan_upto = min(scan_upto, heredoc_match.start())
        c_match = _C_FLAG_RE.search(line, 0, scan_upto)
        if c_match:
            c_quote = c_match.group(1)
            scan_upto = min(scan_upto, c_match.start())
        for match in _UNSAFE_CONTEXT_INTERP_RE.finditer(line, 0, scan_upto):
            namespace = match.group(1)
            raw = match.group(2)
            full_path = f"{namespace}.{raw}"
            try:
                var_path, _default, _nullable, shell_quote = parse_interpolation_suffixes(full_path)
            except InterpolationError:
                shell_quote = False
                var_path = full_path
            if "." not in var_path:
                continue
            _, key_path = var_path.split(".", 1)
            key = key_path.split(".", 1)[0]
            if classify_site(namespace, key) == "C":
                continue
            if shell_quote:
                continue
            if line[: match.start()].count("'") % 2 == 1:
                continue  # inside a single-quoted string
            var = f"{namespace}.{key_path}"
            marker = _find_adjacent_marker(lines, markers_by_line, line_no, var)
            if marker is not None and marker.var == var:
                consumed.add(var)
                continue
            bash_findings.append(
                _Mr11Finding(
                    state=state_name,
                    token=match.group(0),
                    var=var,
                    in_python_body=False,
                    misapplied_remedy=False,
                    line=line_no,
                )
            )

    # -- Half 2: delegated Python-literal-position scan --
    python_findings: list[_Mr11Finding] = []
    for site in scan_action(action, state=state_name, file=fsm_name):
        if site.cls == "C":
            continue
        matched_marker = next((m for m in markers_by_line.values() if m.var == site.var), None)
        if matched_marker is not None:
            consumed.add(site.var)
            continue
        token = "${" + site.var + (":shell" if site.misapplied_remedy else "") + "}"
        python_findings.append(
            _Mr11Finding(
                state=state_name,
                token=token,
                var=site.var,
                in_python_body=True,
                misapplied_remedy=site.misapplied_remedy,
                line=site.line,
                host_shape=site.host_shape,
            )
        )

    # -- Stale-marker detection (constraint 7) --
    for marker in markers_by_line.values():
        if marker.var not in consumed:
            marker_errors.append(
                ValidationError(
                    message=(
                        f"[state: {state_name}] `# ll-lint: mr11-ok({marker.var})` "
                        "marker matches no MR-11 finding in this action — the site it "
                        "exempted may have been converted or removed. Remove the "
                        "stale marker. (MR-11)"
                    ),
                    path=f"states.{state_name}.action",
                    severity=ValidationSeverity.WARNING,
                )
            )

    return bash_findings + python_findings, marker_errors


def _find_unsafe_context_interpolations(fsm: FSMLoop) -> list[tuple[str, str]]:
    """Return (state_name, matched_token) for untrusted interpolations reaching
    a shell body outside a safe position — bash-token position, or inside a
    Python literal embedded in a quoted heredoc / `python3 -c "..."` body.

    Untrusted-ness comes from ``classify_site()`` (ENH-3338): ``captured.*``
    always, ``prev.output``/``prev.stderr`` always, ``context.*`` minus the
    trusted set (``run_dir``, ``promoted_artifact``, any ``_``-prefixed key).
    Not a fixed key allowlist (ENH-3342 widening).

    Safe positions (not flagged):
      - single-quoted string, at a bash token position
      - a quoted heredoc that is *not* a Python body
      - the ``:shell`` suffix, at a bash token position (inside a Python
        body ``:shell`` is flagged — see § Decision Rules)
      - a site exempted by a well-formed ``# ll-lint: mr11-ok(<var>)`` marker
    """
    findings: list[tuple[str, str]] = []
    for state_name, state in fsm.states.items():
        if not state.action:
            continue
        if state.action_type not in ("shell", None):
            continue
        if state.action.lstrip().startswith("/"):
            continue
        state_findings, _marker_errors = _scan_state_for_mr11(state_name, state.action, fsm.name)
        findings.extend((f.state, f.token) for f in state_findings)
    return findings


def _mr11_message(finding: _Mr11Finding) -> str:
    """Build the MR-11 WARNING message, naming a position-appropriate remedy."""
    base = (
        f"[state: {finding.state}] {finding.token} interpolates user-controlled "
        'context raw into a shell body. A value containing ", $, `, \\, '
        "or ! can break bash tokenizing or inject commands (BUG-2622). "
    )
    if finding.in_python_body and finding.misapplied_remedy:
        remedy = (
            "This is inside an embedded Python body, where :shell's shlex quoting "
            "produces a shell-quoted string that breaks the Python parser instead of "
            "protecting it. Hoist the value out to an LL_ARG_X=... environment binding "
            "on the python3 invocation line (using :shell there, where it belongs) and "
            "read it via os.environ inside the body."
        )
    elif finding.in_python_body:
        remedy = (
            "This is inside an embedded Python body (a quoted heredoc or `python3 -c "
            '"..."`), where bash-safe quoting does not protect a Python string '
            "literal. Hoist the value out to an LL_ARG_X=... environment binding on "
            "the python3 invocation line and read it via os.environ, or write it to a "
            "file outside the body and read the file inside it."
        )
    else:
        remedy = (
            "Wrap it in a single-quoted string, write it through a quoted heredoc "
            "(<<'EOF'), or add the :shell suffix to shlex-quote it "
            "(e.g. ${context.input:shell})."
        )
    return (
        base
        + remedy
        + " Set `unsafe_context_interpolation_ok: true` to suppress the whole rule, or "
        "exempt this one site with `# ll-lint: mr11-ok(<namespace>.<key>) <reason citing "
        "an issue>`. (MR-11)"
    )


def _validate_unsafe_context_interpolation(fsm: FSMLoop) -> list[ValidationError]:
    """Validate rule MR-11 (BUG-2622, widened by ENH-3342): unsafe raw
    interpolation of untrusted context/captured/prev values into a shell body,
    or into a Python literal embedded in that shell body.

    ``interpolate()`` substitutes ``${context.*}``/``${captured.*}``/``${prev.*}``
    with a bare ``str(value)`` and no shell escaping. At a bash token position —
    e.g. ``[ -z "${context.input}" ]`` — a value containing ``"``, ``$``, `` ` ``,
    ``\\``, or ``!`` breaks bash tokenizing or, from an untrusted source, injects
    commands. Inside a Python literal (a quoted heredoc that is a Python body, or
    a ``python3 -c "..."`` body), the same value breaks the Python parser instead
    — a quoted heredoc is bash-safe but not Python-safe, which is the inversion
    this widening exists to catch (see ``interp_sweep.py``, ENH-3338).

    Findings are WARNING (see § Severity: raising to ERROR would hard-fail
    ``ll-loop validate`` on consuming projects' pre-existing loops at upgrade
    time). Suppressed loop-wide by ``unsafe_context_interpolation_ok: true``,
    or per-site by a well-formed ``# ll-lint: mr11-ok(<namespace>.<key>)
    <reason>`` marker — a malformed marker is itself an ERROR, and a
    well-formed marker matching no finding is a stale-marker WARNING.
    """
    if fsm.unsafe_context_interpolation_ok:
        return []
    errors: list[ValidationError] = []
    for state_name, state in fsm.states.items():
        if not state.action:
            continue
        if state.action_type not in ("shell", None):
            continue
        if state.action.lstrip().startswith("/"):
            continue
        state_findings, marker_errors = _scan_state_for_mr11(state_name, state.action, fsm.name)
        for finding in state_findings:
            errors.append(
                ValidationError(
                    message=_mr11_message(finding),
                    path=f"states.{state_name}.action",
                    severity=ValidationSeverity.WARNING,
                )
            )
        errors.extend(marker_errors)
    return errors
