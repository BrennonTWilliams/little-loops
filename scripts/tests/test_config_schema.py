"""Tests for config-schema.json structure."""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_SCHEMA = PROJECT_ROOT / "config-schema.json"


class TestConfigSchema:
    """Regression guards for config-schema.json structure."""

    def test_schema_file_exists(self) -> None:
        """config-schema.json must exist at project root."""
        assert CONFIG_SCHEMA.exists(), f"config-schema.json not found: {CONFIG_SCHEMA}"

    def test_extensions_in_properties(self) -> None:
        """extensions key must be inside the properties block."""
        data = json.loads(CONFIG_SCHEMA.read_text())
        assert "properties" in data, "config-schema.json missing top-level properties block"
        assert "extensions" in data["properties"], (
            "extensions key is outside the properties block — "
            "any config using extensions would trigger additionalProperties violation"
        )
