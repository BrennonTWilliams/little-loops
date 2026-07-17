"""DES variant registry for little-loops observability events (ENH-2475).

The registry enumerates every event shape currently emitted to ``.ll/history.db`` so that
F5 (``observability/tracing.py``, EPIC-2456 § Tier 1) can land its ``gen_ai.usage.*``
emit path against a static-known surface rather than against a runtime shape-coercion
layer.

Public exports:
    DESVariant: Base frozen dataclass for every registered variant
    DES_VARIANTS: Tuple of every registered variant class
    DES_VARIANT_TYPES: Frozenset of discriminator strings (``type`` field defaults)
    AuditResult: Dataclass returned by ``audit_tree``
    audit_tree: Walk a source tree and classify every emit site against DES_VARIANTS
"""

from little_loops.observability.audit import AuditResult, audit_tree
from little_loops.observability.schema import (
    DES_VARIANT_TYPES,
    DES_VARIANTS,
    DESVariant,
)
from little_loops.observability.tracing import (
    OTelAttributes,
    ParityDiff,
    StampUsageEvent,
    StreamingParityChecker,
    vendor_for_runner,
)

__all__ = [
    "DESVariant",
    "DES_VARIANTS",
    "DES_VARIANT_TYPES",
    "AuditResult",
    "audit_tree",
    # FEAT-2478 — OTel gen_ai.* attribute shaping + streaming parity
    "OTelAttributes",
    "StampUsageEvent",
    "StreamingParityChecker",
    "ParityDiff",
    "vendor_for_runner",
]
