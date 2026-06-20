"""Shared rule grammar for policy-based decision-table routing.

This module implements parse / serialize / evaluate for the policy-router
fragment library (lib/policy-router.yaml). The grammar is intentionally
minimal and conjunctive-only in v1: rows of AND-joined predicates, first
match wins, optional catch-all wildcard.

This module is the single source of truth for the grammar so that
lib/policy-router.yaml's ``policy_table_dispatch`` fragment and
ENH-2233's ``edit-routes`` lens both import the same parse / serialize logic.

Public API:
    parse_rules(text)              -> list[Rule]
    serialize_rules(rules)         -> str
    evaluate_rules(rules, scores)  -> str | None
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ORDERED_OPS: frozenset[str] = frozenset({">=", "<=", "<", ">"})
_ALL_OPS: frozenset[str] = frozenset({">=", "<=", "==", "!=", "<", ">"})

# Predicate format: <dim>:<op><value>  (e.g. "confidence:>=85", "flag:==true")
# The dim may contain word chars, spaces, and hyphens.
_PRED_PATTERN = re.compile(
    r"^(?P<dim>[\w][\w\s\-]*?)\s*:\s*(?P<op>>=|<=|==|!=|<|>)\s*(?P<value>\S.*?)$"
)

# Valid state-name characters for the -> target
_TARGET_PATTERN = re.compile(r"^[\w][\w\-]*$")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Predicate:
    """Single comparison in a rule LHS."""

    dim: str
    op: str  # one of: >=, <=, ==, !=, <, >
    value: str  # raw string from rule text; numeric for ordered ops


@dataclass
class Rule:
    """One row of the decision table.

    A catch-all rule (``is_catchall=True``) has an empty ``predicates`` list
    and matches unconditionally when reached.
    """

    predicates: list[Predicate] = field(default_factory=list)
    target: str = ""
    is_catchall: bool = False


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_predicate(text: str) -> Predicate:
    """Parse ``<dim>:<op><value>`` into a :class:`Predicate`.

    Raises :class:`ValueError` if the text does not match the expected format
    or if an ordered operator is given a non-numeric value.
    """
    m = _PRED_PATTERN.match(text.strip())
    if not m:
        raise ValueError(
            f"Invalid predicate {text!r} — expected '<dim>:<op><value>' "
            f"where op is one of {sorted(_ALL_OPS)}"
        )
    dim = m.group("dim").strip()
    op = m.group("op")
    value = m.group("value").strip()
    if op in _ORDERED_OPS:
        try:
            float(value)
        except ValueError as err:
            raise ValueError(
                f"Ordered operator {op!r} requires a numeric value; "
                f"got {value!r} in predicate {text!r}"
            ) from err
    return Predicate(dim=dim, op=op, value=value)


def parse_rules(text: str) -> list[Rule]:
    """Parse a newline-separated policy rule table into a list of :class:`Rule`.

    Syntax::

        # comment lines (skipped)
        <blank lines>              (skipped)
        <dim>:<op><value> -> <state>
        <dim>:<op><value> & <dim2>:<op2><value2> -> <state>
        * -> <state>

    Operators: ``>=``, ``<=``, ``==``, ``!=``, ``<``, ``>``

    Ordered operators (``>=``, ``<=``, ``<``, ``>``) require numeric values;
    a non-numeric value for an ordered operator raises :class:`ValueError` at
    parse time.  The ``==`` and ``!=`` operators accept any string value.

    The wildcard catch-all ``* -> <state>`` matches unconditionally and should
    appear as the last rule.

    Args:
        text: Raw rule table text.

    Returns:
        Ordered list of :class:`Rule` objects (source order preserved).

    Raises:
        ValueError: On malformed rules (missing ``->``, empty target, invalid
            predicate syntax, or non-numeric value with an ordered operator).
    """
    rules: list[Rule] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "->" not in line:
            raise ValueError(f"Line {lineno}: rule is missing '->': {line!r}")
        lhs, _, rhs = line.partition("->")
        lhs = lhs.strip()
        target = rhs.strip()
        if not target:
            raise ValueError(f"Line {lineno}: empty target state in: {line!r}")
        if not _TARGET_PATTERN.match(target):
            raise ValueError(
                f"Line {lineno}: invalid target state name {target!r} "
                "(only word chars and hyphens allowed)"
            )
        if lhs == "*":
            rules.append(Rule(predicates=[], target=target, is_catchall=True))
        else:
            parts = [p.strip() for p in lhs.split("&") if p.strip()]
            if not parts:
                raise ValueError(f"Line {lineno}: empty LHS in: {line!r}")
            preds = [_parse_predicate(p) for p in parts]
            rules.append(Rule(predicates=preds, target=target, is_catchall=False))
    return rules


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def serialize_rules(rules: list[Rule]) -> str:
    """Serialize a rule list back to text (lossless inverse of :func:`parse_rules`).

    The round-trip ``parse_rules(serialize_rules(rules))`` produces a :class:`Rule`
    list equal in structure to the original (stable).

    Args:
        rules: List of :class:`Rule` objects.

    Returns:
        Newline-separated rule table text.
    """
    lines: list[str] = []
    for rule in rules:
        if rule.is_catchall:
            lines.append(f"* -> {rule.target}")
        else:
            pred_strs = [f"{p.dim}:{p.op}{p.value}" for p in rule.predicates]
            lines.append(f"{' & '.join(pred_strs)} -> {rule.target}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def _eval_predicate(pred: Predicate, scores: dict[str, object]) -> bool:
    """Evaluate a single predicate against the scores dict."""
    raw = scores.get(pred.dim)

    if raw is None:
        # Missing dimension: treat != as matching (absent != any value),
        # all other ops as non-matching.
        return pred.op == "!="

    op = pred.op

    if op in _ORDERED_OPS:
        # Both sides coerced to float (guaranteed numeric by parse_rules).
        try:
            lhs = float(str(raw))
            rhs = float(pred.value)
        except ValueError:
            return False
        if op == ">":
            return lhs > rhs
        if op == "<":
            return lhs < rhs
        if op == ">=":
            return lhs >= rhs
        # op == "<="
        return lhs <= rhs

    # == or != : try numeric coercion first, fall back to string comparison.
    try:
        lhs_f = float(str(raw))
        rhs_f = float(pred.value)
        if op == "==":
            return lhs_f == rhs_f
        # op == "!="
        return lhs_f != rhs_f
    except ValueError:
        lhs_s = str(raw)
        rhs_s = pred.value
        if op == "==":
            return lhs_s == rhs_s
        # op == "!="
        return lhs_s != rhs_s


def evaluate_rules(rules: list[Rule], scores: dict[str, object]) -> str | None:
    """Return the target state of the first matching rule, or ``None`` if none match.

    Evaluation order follows the list order (priority: first match wins).
    A catch-all rule always matches and should be the last rule in the list.

    Numeric coercion: ordered operators (``>=``, ``<=``, ``<``, ``>``) compare
    both sides as ``float``.  For example, ``"9" < "10"`` evaluates to ``True``
    (numeric), not ``False`` (lexical).

    Args:
        rules: Ordered list of :class:`Rule` objects from :func:`parse_rules`.
        scores: Dict mapping dimension names to score values (numeric or string).

    Returns:
        The target state name of the first matching rule, or ``None``.
    """
    for rule in rules:
        if rule.is_catchall:
            return rule.target
        if all(_eval_predicate(p, scores) for p in rule.predicates):
            return rule.target
    return None
