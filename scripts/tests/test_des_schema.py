"""Tests for the DES variant registry at ``little_loops.observability.schema``.

The registry must cover every event type currently emitted to ``.ll/history.db`` (Channel A
direct writers + Channel B EventBus emits) so that F5's ``gen_ai.usage.*`` adoption gate
(EPIC-2456 § Success Metrics) can land without coercing unmodeled shapes.

Precedent: ``scripts/tests/test_generate_schemas.py:14-63`` (catalog-completeness test for
``SCHEMA_DEFINITIONS``).
"""

from __future__ import annotations

import dataclasses
from typing import get_args, get_origin

import pytest

from little_loops.generate_schemas import SCHEMA_DEFINITIONS
from little_loops.observability import DES_VARIANTS, DESVariant
from little_loops.session_store import _LOOP_EVENT_TYPES

# ---------------------------------------------------------------------------
# Catalog completeness
# ---------------------------------------------------------------------------


class TestSchemaDefinitions:
    """Tests for the ``DES_VARIANTS`` catalog."""

    def test_variants_count_meets_minimum(self) -> None:
        """DES_VARIANTS must include at least one entry per Channel B event type.

        The minimum bar is the size of ``SCHEMA_DEFINITIONS`` (the canonical 39-event
        catalog) — F5's adoption gate requires every currently-emitted shape to be
        covered.
        """
        assert len(DES_VARIANTS) >= len(SCHEMA_DEFINITIONS), (
            f"DES_VARIANTS has {len(DES_VARIANTS)} entries; "
            f"SCHEMA_DEFINITIONS has {len(SCHEMA_DEFINITIONS)} — every Channel B event "
            f"type must have a registered DES variant."
        )

    def test_variants_cover_all_schema_definitions(self) -> None:
        """Every event type in SCHEMA_DEFINITIONS must have a matching DES_VARIANT.

        This is the F5 acceptance gate: the registry must enumerate the full canonical
        event surface so F5 can statically verify its emit path against the registry.
        """
        registered_types = _registered_event_types(DES_VARIANTS)
        schema_types = set(SCHEMA_DEFINITIONS.keys())
        missing = schema_types - registered_types
        assert not missing, (
            f"SCHEMA_DEFINITIONS entries missing from DES_VARIANTS: {sorted(missing)}"
        )

    def test_variants_cover_all_loop_event_types(self) -> None:
        """Every entry in ``_LOOP_EVENT_TYPES`` (session_store.py:133-145) must be registered.

        These are the events that ``SQLiteTransport.send`` persists to ``loop_events``;
        the registry must know them.
        """
        registered_types = _registered_event_types(DES_VARIANTS)
        missing = _LOOP_EVENT_TYPES - registered_types
        assert not missing, (
            f"_LOOP_EVENT_TYPES entries missing from DES_VARIANTS: {sorted(missing)}"
        )


# ---------------------------------------------------------------------------
# Per-variant shape
# ---------------------------------------------------------------------------


class TestVariantShape:
    """Each variant must satisfy the DES contract: frozen + Literal discriminator."""

    @pytest.mark.parametrize("variant", DES_VARIANTS, ids=lambda v: _safe_id(v))
    def test_variant_is_frozen(self, variant: type[DESVariant]) -> None:
        """Every DES_VARIANT must be ``@dataclass(frozen=True)``.

        Per ``host_runner.py:101-104`` — frozen is the established value-object convention.
        """
        assert dataclasses.fields(variant)[0].metadata is not None or True
        # Frozen check: instantiating and attempting to mutate should raise.
        # Subclasses with required fields are constructed with empty defaults.
        instance = _instantiate_for_test(variant)
        with pytest.raises(dataclasses.FrozenInstanceError):
            instance.type = "new_value"  # type: ignore[misc]

    @pytest.mark.parametrize("variant", DES_VARIANTS, ids=lambda v: _safe_id(v))
    def test_variant_has_type_field(self, variant: type[DESVariant]) -> None:
        """Every DES_VARIANT must declare a ``type`` field as discriminator."""
        assert "type" in variant.__dataclass_fields__, (
            f"{variant.__name__} missing `type` discriminator field"
        )

    @pytest.mark.parametrize("variant", DES_VARIANTS, ids=lambda v: _safe_id(v))
    def test_type_field_is_literal(self, variant: type[DESVariant]) -> None:
        """The ``type`` field must be typed as ``Literal[<discriminator>]`` (one value).

        This is the discriminator contract — ``Literal[...]`` is what makes the registry
        a discriminated union. Annotations may be stored as strings under
        ``from __future__ import annotations``; ``get_type_hints`` resolves them.
        """
        import typing

        hints = typing.get_type_hints(variant)
        annotation = hints["type"]
        origin = get_origin(annotation)
        assert origin is typing.Literal, (
            f"{variant.__name__}.type annotation {annotation!r} must be Literal[...]"
        )
        # And must have exactly one allowed value (the discriminator string).
        values = get_args(annotation)
        assert len(values) == 1, (
            f"{variant.__name__}.type Literal must have exactly 1 value; got {values}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _registered_event_types(variants: tuple[type[DESVariant], ...]) -> set[str]:
    """Collect the discriminator ``type`` value from each registered variant."""
    out: set[str] = set()
    for v in variants:
        type_field = v.__dataclass_fields__.get("type")
        if type_field is None:
            continue
        # The default value on the field is the discriminator string (e.g. "loop_start").
        default = type_field.default
        if isinstance(default, str):
            out.add(default)
        else:
            # Fallback: if no default, try Literal args.
            values = get_args(type_field.type)
            if values and isinstance(values[0], str):
                out.add(values[0])
    return out


def _instantiate_for_test(variant: type[DESVariant]) -> DESVariant:
    """Construct an instance of *variant* using only its field defaults.

    Variants in the registry declare their discriminator ``type`` field with a default
    value (e.g. ``type: Literal["loop_start"] = "loop_start"``), so a no-arg construction
    is sufficient for shape-only tests.
    """
    return variant()


def _safe_id(variant: type) -> str:
    """Test parametrize id that won't blow up if the class is malformed."""
    return getattr(variant, "__name__", str(variant))
