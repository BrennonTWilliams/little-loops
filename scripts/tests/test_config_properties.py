"""Property-based tests for BRConfig using Hypothesis.

Verifies that BRConfig.to_dict() is idempotent: reloading a serialized
config and serializing again produces the same output.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from little_loops.config import BRConfig


@st.composite
def minimal_config_dict(draw: st.DrawFn) -> dict[str, Any]:
    """Generate a minimal config dict accepted by BRConfig."""
    cfg: dict[str, Any] = {}
    if draw(st.booleans()):
        cfg["project"] = {
            "name": draw(st.text(min_size=1, max_size=40).filter(lambda s: "\x00" not in s)),
        }
    if draw(st.booleans()):
        cfg["automation"] = {
            "timeout_seconds": draw(st.integers(min_value=1, max_value=7200)),
        }
    if draw(st.booleans()):
        cfg["parallel"] = {
            "max_workers": draw(st.integers(min_value=1, max_value=8)),
        }
    if draw(st.booleans()):
        cfg["commands"] = {
            "tdd_mode": draw(st.booleans()),
        }
    if draw(st.booleans()):
        cfg["loops"] = {
            "queue_wait_timeout_seconds": draw(st.integers(min_value=1, max_value=600)),
        }
    return cfg


class TestBRConfigProperties:
    """Property tests for BRConfig serialization."""

    @pytest.mark.slow
    @given(cfg=minimal_config_dict())
    @settings(
        max_examples=50,
        deadline=None,
        suppress_health_check=list(HealthCheck),
    )
    def test_to_dict_idempotent(self, cfg: dict[str, Any]) -> None:
        """BRConfig.to_dict() is idempotent: load→serialize→load→serialize yields the same dict.

        The sound invariant for BRConfig is dump∘load idempotency, not round-trip equality,
        because _parse_config() fills defaults for missing keys — so
        to_dict(load(arbitrary_dict)) != arbitrary_dict in general.
        The stable property is: to_dict(load(to_dict(load(d)))) == to_dict(load(d)).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".ll").mkdir()
            config_path = root / ".ll" / "ll-config.json"

            # First load: apply defaults to arbitrary input
            config_path.write_text(json.dumps(cfg))
            d1 = BRConfig(root).to_dict()

            # Second load: defaults are already applied; output must be stable
            config_path.write_text(json.dumps(d1))
            d2 = BRConfig(root).to_dict()

            assert d1 == d2, (
                f"to_dict is not idempotent.\n"
                f"First pass keys not in second: {set(d1) - set(d2)}\n"
                f"Second pass keys not in first: {set(d2) - set(d1)}"
            )
