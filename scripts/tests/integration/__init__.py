"""End-to-end integration tests.

These tests exercise real little-loops entry points (``main_init``,
``main_issues``, the FSM executor) against a real temp filesystem with no
mocking of the unit under test. The only mocked boundary is the host-CLI/LLM
(and, for init, the pip/plugin installation probe). They are marked
``@pytest.mark.integration`` so ``pytest -m "not integration"`` can skip them.

See ``thoughts/audits/2026-06-26-test-suite-audit.md`` (finding H2) for the
gap these close.
"""
