"""Second divergent fake + composition test suite (ENH-3459).

Drives ``fake`` and ``fake-minimal`` — two ``HostRunner`` implementations
whose action vocabulary and capability profile deliberately disagree — through
the **unpatched production executor** (``run_claude_command``,
``run_blocking_json``) against the same directive script, and asserts the
executor produces the same observation for both. A single fake proves the
code runs; a second, deliberately divergent fake proves the executor is
host-agnostic rather than shaped around one fake's assumptions.

``TestExecutorTouchesOnlyAbstractInterface`` and ``TestRegressionGuard`` pin
that mechanically, via an AST walk over ``host_runner.py`` and
``subprocess_utils.py`` sources: the executor chain reads only the abstract
``HostRunner``/``HostInvocation`` surface, with ``_structured_output_args``'s
pinned ``{"claude", "qwen"}`` binary-literal branches as the one named
exception. Ported from the ENH-3456 spike
(``scripts/tests/spike/host_compose/``, now deleted) against the real
executor rather than an in-process shim — see this issue's Decisions.
"""

from __future__ import annotations

import ast
import shutil
import textwrap
import typing
from pathlib import Path

import pytest

from little_loops import host_runner, subprocess_utils
from little_loops.host_runner import (
    _HOST_RUNNER_REGISTRY,
    TEST_ONLY_HOSTS,
    FakeHostRunner,
    FakeMinimalHostRunner,
    HostCapabilities,
    HostRunner,
    run_blocking_json,
)
from tests.conformance.test_host_conformance import (
    Observed,
    _run_and_capture,
    assert_event_kinds,
)

_FAKES = ("fake", "fake-minimal")

_conformance_fake_binary = pytest.mark.skipif(
    shutil.which("ll-fake-host") is None,
    reason="ll-fake-host not on PATH (non-editable install)",
)


# ── AST checker primitives ─────────────────────────────────────────────────
#
# Shared by TestExecutorTouchesOnlyAbstractInterface (asserting the real
# executor sources are clean) and TestRegressionGuard (asserting the same
# checker functions catch synthetic drift). No runtime proxy exists anywhere
# in this repo for consumer-surface enforcement — the in-tree precedent is
# AST-walk-plus-pinned-allow-list (`_ALLOWED_CALLERS`, test_advisor.py:694-696).

_INVOCATION_BINDING_CALLS: frozenset[str] = frozenset(
    {"build_streaming", "build_blocking_json", "build_version_check", "build_detached"}
)
_RUNNER_BINDING_CALLS: frozenset[str] = frozenset({"resolve_host", "resolve_host_named"})

# HostInvocation's public fields (host_runner.py) — the executor's allowed
# read surface.
_ALLOWED_INVOCATION_ATTRS: frozenset[str] = frozenset(
    {"binary", "args", "env", "capabilities", "cleanup_paths", "env_allow"}
)

# HostRunner Protocol members, derived rather than hand-pinned so the
# allow-list never silently drifts from the Protocol it mirrors.
_ALLOWED_RUNNER_ATTRS: frozenset[str] = frozenset(
    getattr(HostRunner, "__protocol_attrs__", None) or typing._get_protocol_attrs(HostRunner)  # type: ignore[attr-defined]
)

# Concrete runner class names, derived from the registry so a new host port
# is automatically covered without a hand-maintained list.
_CONCRETE_RUNNER_NAMES: frozenset[str] = frozenset(
    cls.__name__ for cls in _HOST_RUNNER_REGISTRY.values()
)

# The one function allowed to compare `.binary`/`.name` to a string literal,
# and the pinned literals it may use (Decision 5).
_ALLOWED_BINARY_LITERAL_SITES: dict[str, frozenset[str]] = {
    "_structured_output_args": frozenset({"claude", "qwen"}),
}

_BINARY_OR_NAME_ATTRS = frozenset({"binary", "name"})


def _scoped_walk(node: ast.AST) -> typing.Iterator[ast.AST]:
    """Yield every descendant of *node*, never crossing into a nested def/class.

    A nested function or class is its own unit of checking — its body must
    not be attributed to the enclosing function.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield child
        yield from _scoped_walk(child)


def _annotation_contains_name(annotation: ast.expr | None, name: str) -> bool:
    if annotation is None:
        return False
    return any(isinstance(n, ast.Name) and n.id == name for n in ast.walk(annotation))


def _bindings(
    tree: ast.AST,
    annotation: str,
    fallback_param: str,
    binding_calls: frozenset[str],
) -> list[tuple[ast.FunctionDef, str]]:
    """(FunctionDef node, bound_name) for every function binding *annotation*.

    A function binds the type via: (a) a parameter whose annotation AST
    contains ``Name(annotation)`` (union/``Optional`` included); (b) an
    un-annotated parameter named *fallback_param*; or (c) a local ``Assign``
    to a single ``Name`` target whose value is a call to a bare name or
    attribute in *binding_calls*. Rule (c) is required: ``run_claude_command``
    takes neither type as a parameter — it binds both as locals.
    """
    results: list[tuple[ast.FunctionDef, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        bound: set[str] = set()
        params = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        for arg in params:
            if _annotation_contains_name(arg.annotation, annotation):
                bound.add(arg.arg)
            elif arg.annotation is None and arg.arg == fallback_param:
                bound.add(arg.arg)
        for child in _scoped_walk(node):
            if not (
                isinstance(child, ast.Assign)
                and len(child.targets) == 1
                and isinstance(child.targets[0], ast.Name)
                and isinstance(child.value, ast.Call)
            ):
                continue
            func = child.value.func
            is_binding_call = (isinstance(func, ast.Name) and func.id in binding_calls) or (
                isinstance(func, ast.Attribute) and func.attr in binding_calls
            )
            if is_binding_call:
                bound.add(child.targets[0].id)
        for name in sorted(bound):
            results.append((node, name))
    return results


def _checked_functions(
    module_src: str,
    annotation: str,
    fallback_param: str,
    binding_calls: frozenset[str],
) -> list[tuple[str, str]]:
    """(function_name, bound_name) for every function in *module_src* binding *annotation*."""
    tree = ast.parse(module_src)
    return [
        (node.name, bound)
        for node, bound in _bindings(tree, annotation, fallback_param, binding_calls)
    ]


def _invocation_attr_reads(fn: ast.FunctionDef, name: str) -> set[str]:
    """Attribute names read on *name*: plain ``Attribute`` access, or ``getattr(name, "attr", ...)``."""
    reads: set[str] = set()
    for node in _scoped_walk(fn):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == name
        ):
            reads.add(node.attr)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == name
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            reads.add(node.args[1].value)
    return reads


def _runner_attr_reads(fn: ast.FunctionDef, name: str) -> set[str]:
    """Same rule as :func:`_invocation_attr_reads`, applied to the runner-bound name."""
    return _invocation_attr_reads(fn, name)


def _is_binary_or_name_ref(node: ast.expr) -> bool:
    if isinstance(node, ast.Attribute):
        return node.attr in _BINARY_OR_NAME_ATTRS
    if isinstance(node, ast.Name):
        return node.id in _BINARY_OR_NAME_ATTRS
    return False


def _host_literal_compares(fn: ast.FunctionDef) -> list[tuple[str, str]]:
    """(enclosing_function, literal) for each binary/name comparison against a string constant."""
    results: list[tuple[str, str]] = []
    for node in _scoped_walk(fn):
        if not isinstance(node, ast.Compare) or not _is_binary_or_name_ref(node.left):
            continue
        for op, comparator in zip(node.ops, node.comparators, strict=True):
            if (
                isinstance(op, (ast.Eq, ast.NotEq))
                and isinstance(comparator, ast.Constant)
                and isinstance(comparator.value, str)
            ):
                results.append((fn.name, comparator.value))
            elif isinstance(op, (ast.In, ast.NotIn)) and isinstance(
                comparator, (ast.Tuple, ast.Set, ast.List)
            ):
                for elt in comparator.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        results.append((fn.name, elt.value))
    return results


def _isinstance_targets(fn: ast.FunctionDef) -> set[str]:
    """Second-arg names of every ``isinstance`` call in *fn*."""
    targets: set[str] = set()
    for node in _scoped_walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "isinstance"
            and len(node.args) >= 2
        ):
            second = node.args[1]
            if isinstance(second, ast.Name):
                targets.add(second.id)
            elif isinstance(second, ast.Attribute):
                targets.add(second.attr)
    return targets


def _find_violations(src: str) -> list[str]:
    """Run every check over *src* and return human-readable violation messages."""
    tree = ast.parse(src)
    violations: list[str] = []

    invocation_bindings = _bindings(tree, "HostInvocation", "invocation", _INVOCATION_BINDING_CALLS)
    for fn, bound in invocation_bindings:
        for attr in sorted(_invocation_attr_reads(fn, bound) - _ALLOWED_INVOCATION_ATTRS):
            violations.append(f"{fn.name}: reads disallowed invocation attribute {attr!r}")

    runner_bindings = _bindings(tree, "HostRunner", "runner", _RUNNER_BINDING_CALLS)
    for fn, bound in runner_bindings:
        for attr in sorted(_runner_attr_reads(fn, bound) - _ALLOWED_RUNNER_ATTRS):
            violations.append(f"{fn.name}: reads disallowed runner attribute {attr!r}")

    checked_fns = {fn for fn, _ in invocation_bindings} | {fn for fn, _ in runner_bindings}
    for fn in checked_fns:
        for target in sorted(_isinstance_targets(fn)):
            if target in _CONCRETE_RUNNER_NAMES:
                violations.append(f"{fn.name}: isinstance() against concrete runner {target!r}")

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for func_name, literal in _host_literal_compares(node):
            allowed = _ALLOWED_BINARY_LITERAL_SITES.get(func_name)
            if allowed is None or literal not in allowed:
                violations.append(f"{func_name}: unpinned binary/name literal {literal!r}")

    return violations


# ── TestFakesAreDivergent ───────────────────────────────────────────────────


class TestFakesAreDivergent:
    """Pins the divergence so a future edit cannot quietly make the fakes agree."""

    def test_argv_diverges(self) -> None:
        fake_args = FakeHostRunner().build_streaming(prompt="hi").args
        minimal_args = FakeMinimalHostRunner().build_streaming(prompt="hi").args
        assert fake_args == ["hi"]
        assert minimal_args == ["run", "hi"]

    def test_env_diverges_under_automation(self) -> None:
        from little_loops.host_runner import AutomationContext

        automation = AutomationContext(profile="ll-auto")
        fake_env = FakeHostRunner().build_streaming(prompt="hi", automation=automation).env
        minimal_env = (
            FakeMinimalHostRunner().build_streaming(prompt="hi", automation=automation).env
        )
        assert fake_env
        assert minimal_env == {}

    def test_default_capabilities_diverge(self) -> None:
        """FakeHostRunner defaults to streaming=True; FakeMinimalHostRunner is all-False."""
        fake_caps = FakeHostRunner().capabilities
        minimal_caps = FakeMinimalHostRunner().capabilities
        assert fake_caps != minimal_caps
        assert fake_caps.streaming is True
        assert minimal_caps.streaming is False

    def test_both_share_binary(self) -> None:
        assert FakeHostRunner().describe_capabilities().binary == "ll-fake-host"
        assert FakeMinimalHostRunner().describe_capabilities().binary == "ll-fake-host"

    def test_both_are_test_only_hosts(self) -> None:
        assert TEST_ONLY_HOSTS >= {"fake", "fake-minimal"}

    def test_both_satisfy_host_runner_protocol(self) -> None:
        assert isinstance(FakeHostRunner(), HostRunner)
        assert isinstance(FakeMinimalHostRunner(), HostRunner)


# ── TestCompositionThroughExecutor ──────────────────────────────────────────


@_conformance_fake_binary
@pytest.mark.conformance
class TestCompositionThroughExecutor:
    """Real ``run_claude_command`` via ``_run_and_capture``: equal ``Observed`` across fakes."""

    @pytest.mark.parametrize(
        "case,script,expected_kinds,expected_returncode",
        [
            (
                "happy_path",
                "@@fake\ninit model=m session=s\ntext a\nresult in=1 out=2\n@@end\n",
                ["init", "text", "usage"],
                0,
            ),
            (
                "result_error",
                "@@fake\ninit model=m session=s\nresult error=boom in=1 out=1\n@@end\n",
                ["init", "usage"],
                0,
            ),
            (
                "exit_before_terminal",
                "@@fake\ninit model=m session=s\ntext a\nexit 2\n@@end\n",
                ["init", "text"],
                2,
            ),
        ],
    )
    def test_equal_observation_across_fakes(
        self,
        case: str,
        script: str,
        expected_kinds: list[str],
        expected_returncode: int,
        tmp_path: Path,
        isolated_env: None,
    ) -> None:
        observations: dict[str, Observed] = {}
        for host in _FAKES:
            obs = _run_and_capture(host, script, timeout=30, tmp_path=tmp_path)
            assert_event_kinds(obs, expected_kinds, host=host, case=case)
            assert obs.completed is not None
            assert obs.completed.returncode == expected_returncode, (
                f"[{host}/{case}] expected returncode {expected_returncode}, "
                f"got {obs.completed.returncode}"
            )
            observations[host] = obs

        fake_obs, minimal_obs = observations["fake"], observations["fake-minimal"]
        assert fake_obs.kinds == minimal_obs.kinds, (
            f"[{case}] kinds diverge across fakes: {fake_obs.kinds!r} vs {minimal_obs.kinds!r}"
        )
        assert fake_obs.result_seen == minimal_obs.result_seen
        assert fake_obs.completed is not None and minimal_obs.completed is not None
        assert fake_obs.completed.returncode == minimal_obs.completed.returncode

    def test_run_blocking_json_returns_same_parsed_dict_across_fakes(self, tmp_path: Path) -> None:
        script = '@@fake\nresult structured={"key": "value"}\n@@end\n'
        schema = {"type": "object"}
        parsed: dict[str, object] = {}
        for host, runner_cls in (("fake", FakeHostRunner), ("fake-minimal", FakeMinimalHostRunner)):
            runner = runner_cls(capabilities=HostCapabilities(structured_output=True))
            invocation = runner.build_blocking_json(prompt=script)
            result = run_blocking_json(invocation, schema=schema, timeout=30)
            assert result is not None
            result.pop("_raw_stdout", None)
            parsed[host] = result

        assert parsed["fake"] == parsed["fake-minimal"] == {"key": "value"}


# ── TestExecutorTouchesOnlyAbstractInterface ────────────────────────────────


class TestExecutorTouchesOnlyAbstractInterface:
    """AST over the module sources: the executor chain reads only the abstract surface."""

    def test_host_runner_module_has_no_violations(self) -> None:
        src = Path(host_runner.__file__).read_text()
        assert _find_violations(src) == []

    def test_subprocess_utils_module_has_no_violations(self) -> None:
        src = Path(subprocess_utils.__file__).read_text()
        assert _find_violations(src) == []

    def test_run_claude_command_is_among_checked_functions(self) -> None:
        src = Path(subprocess_utils.__file__).read_text()
        checked = {
            name
            for name, _ in _checked_functions(
                src, "HostInvocation", "invocation", _INVOCATION_BINDING_CALLS
            )
        } | {
            name
            for name, _ in _checked_functions(src, "HostRunner", "runner", _RUNNER_BINDING_CALLS)
        }
        assert "run_claude_command" in checked

    def test_baseline_invocation_attr_reads(self) -> None:
        """Pins the exact attribute-read sets the Design section's baseline names."""
        host_tree = ast.parse(Path(host_runner.__file__).read_text())
        subprocess_tree = ast.parse(Path(subprocess_utils.__file__).read_text())

        def reads_for(tree: ast.AST, fn_name: str) -> set[str]:
            for fn, bound in _bindings(
                tree, "HostInvocation", "invocation", _INVOCATION_BINDING_CALLS
            ):
                if fn.name == fn_name:
                    return _invocation_attr_reads(fn, bound)
            raise AssertionError(f"{fn_name!r} is not a checked invocation-binding function")

        assert reads_for(host_tree, "project_child_env") == {"env", "env_allow"}
        assert reads_for(host_tree, "_structured_output_args") == {"args", "binary", "capabilities"}
        assert reads_for(host_tree, "run_blocking_json") == {"args", "binary", "cleanup_paths"}
        assert reads_for(subprocess_tree, "run_claude_command") == {"binary", "args", "env"}


# ── TestRegressionGuard ──────────────────────────────────────────────────────


class TestRegressionGuard:
    """The same checker functions run over synthetic snippets and must report each drift."""

    def test_session_id_attribute_read_flagged(self) -> None:
        src = textwrap.dedent(
            """
            def consumer(invocation: HostInvocation) -> str:
                return invocation.session_id
            """
        )
        violations = _find_violations(src)
        assert any("consumer" in v and "session_id" in v for v in violations), violations

    def test_session_id_getattr_read_flagged(self) -> None:
        src = textwrap.dedent(
            """
            def consumer(invocation: HostInvocation) -> str | None:
                return getattr(invocation, "session_id", None)
            """
        )
        violations = _find_violations(src)
        assert any("consumer" in v and "session_id" in v for v in violations), violations

    def test_isinstance_concrete_runner_flagged(self) -> None:
        src = textwrap.dedent(
            """
            def consumer(runner: HostRunner) -> bool:
                return isinstance(runner, FakeHostRunner)
            """
        )
        violations = _find_violations(src)
        assert any("consumer" in v and "FakeHostRunner" in v for v in violations), violations

    def test_binary_equality_outside_allowlist_flagged(self) -> None:
        src = textwrap.dedent(
            """
            def consumer(invocation: HostInvocation) -> bool:
                if invocation.binary == "ll-fake-host":
                    return True
                return False
            """
        )
        violations = _find_violations(src)
        assert any("consumer" in v and "ll-fake-host" in v for v in violations), violations

    def test_name_in_collection_outside_allowlist_flagged(self) -> None:
        src = textwrap.dedent(
            """
            def consumer(runner: HostRunner) -> bool:
                return runner.name in ("claude-code", "qwen")
            """
        )
        violations = _find_violations(src)
        assert any("consumer" in v and "claude-code" in v for v in violations), violations
        assert any("consumer" in v and "qwen" in v for v in violations), violations

    def test_pinned_function_unpinned_literal_flagged(self) -> None:
        src = textwrap.dedent(
            """
            def _structured_output_args(invocation, schema):
                if invocation.binary == "gemini":
                    return []
                return []
            """
        )
        violations = _find_violations(src)
        assert any("_structured_output_args" in v and "gemini" in v for v in violations), violations

    def test_local_binding_via_build_streaming_is_checked(self) -> None:
        """A local ``invocation = runner.build_streaming(...)`` binding is checked too (rule c)."""
        src = textwrap.dedent(
            """
            def consumer(runner):
                invocation = runner.build_streaming(prompt="x")
                return invocation.session_id
            """
        )
        violations = _find_violations(src)
        assert any("consumer" in v and "session_id" in v for v in violations), violations
