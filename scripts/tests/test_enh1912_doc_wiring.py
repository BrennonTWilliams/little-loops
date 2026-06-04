"""
ENH-1912 — Name orchestration patterns in create-loop wizard.

Asserts that:
1. SKILL.md contains "Orch: Router" option in Step 1 and "route", "dispatch", "orchestrate" keywords in Step -1
2. templates.md contains "Route / compose / supervise" option in Step 0.1 and the customization block in Step 0.2
3. loop-types.md contains "## Orchestration Loops" section
4. LOOPS_GUIDE.md contains an orchestration row in the Common Loop Patterns table
5. COMMANDS.md contains "orch-router" in the /ll:create-loop type enumeration
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

SKILL_MD = PROJECT_ROOT / "skills" / "create-loop" / "SKILL.md"
TEMPLATES_MD = PROJECT_ROOT / "skills" / "create-loop" / "templates.md"
LOOP_TYPES_MD = PROJECT_ROOT / "skills" / "create-loop" / "loop-types.md"
LOOPS_GUIDE = PROJECT_ROOT / "docs" / "guides" / "LOOPS_GUIDE.md"
COMMANDS_MD = PROJECT_ROOT / "docs" / "reference" / "COMMANDS.md"


class TestSkillMdOrchEntries:
    """SKILL.md must contain Orch: Router option and keyword entries for Step -1 auto-detection."""

    def test_step1_orch_router_option(self):
        content = SKILL_MD.read_text()
        assert "Orch: Router (dynamic dispatch)" in content, (
            "SKILL.md Step 1 options should include 'Orch: Router (dynamic dispatch)'"
        )

    def test_step_minus1_route_keyword(self):
        content = SKILL_MD.read_text()
        assert '"route"' in content or "route" in content, (
            "SKILL.md Step -1 keyword table should include 'route' → orch-router"
        )

    def test_step_minus1_orch_router_type(self):
        content = SKILL_MD.read_text()
        assert "orch-router" in content, "SKILL.md should reference the 'orch-router' type slug"

    def test_type_mapping_orch_router(self):
        content = SKILL_MD.read_text()
        assert "orch-router" in content, (
            "SKILL.md Type Mapping block should include orch-router entry"
        )


class TestTemplatesMdOrchEntries:
    """templates.md must contain the Route/compose/supervise option in Step 0.1 and customization block in Step 0.2."""

    def test_step01_option_present(self):
        content = TEMPLATES_MD.read_text()
        assert "Route / compose / supervise" in content, (
            "templates.md Step 0.1 should include 'Route / compose / supervise other loops' option"
        )

    def test_step02_customization_block_present(self):
        content = TEMPLATES_MD.read_text()
        assert 'For "Route / compose / supervise other loops"' in content, (
            "templates.md Step 0.2 should include a customization block for the orchestration template"
        )

    def test_loop_router_install_reference(self):
        content = TEMPLATES_MD.read_text()
        assert "loop-router" in content, (
            "templates.md should reference loop-router as the canonical loop to clone"
        )


class TestLoopTypesMdOrchSection:
    """loop-types.md must contain an ## Orchestration Loops section with Router questions and YAML generation."""

    def test_orchestration_loops_section(self):
        content = LOOP_TYPES_MD.read_text()
        assert "## Orchestration Loops" in content, (
            "loop-types.md should have a top-level '## Orchestration Loops' section"
        )

    def test_orch_router_questions(self):
        content = LOOP_TYPES_MD.read_text()
        assert "Orch Router Questions" in content, (
            "loop-types.md should have an 'Orch Router Questions' subsection"
        )

    def test_dispatch_loop_interpolation(self):
        content = LOOP_TYPES_MD.read_text()
        assert "captured.chosen.output" in content, (
            "loop-types.md Orchestration section should show the dispatch loop interpolation pattern"
        )

    def test_composer_forthcoming_gate(self):
        content = LOOP_TYPES_MD.read_text()
        assert "EPIC-1811" in content, (
            "loop-types.md should gate Composer/Supervisor entries on EPIC-1811"
        )


class TestLoopsGuideMdOrchEntry:
    """LOOPS_GUIDE.md must contain an orchestration row in the Common Loop Patterns decision tree and table."""

    def test_decision_tree_orchestration_leaf(self):
        content = LOOPS_GUIDE.read_text()
        assert "Orchestration" in content or "orchestration" in content, (
            "LOOPS_GUIDE.md Common Loop Patterns decision tree should have an orchestration leaf"
        )

    def test_table_orchestration_row(self):
        content = LOOPS_GUIDE.read_text()
        assert "Orchestration" in content, (
            "LOOPS_GUIDE.md Common Loop Patterns table should include an Orchestration row"
        )


class TestCommandsMdOrchRouterType:
    """COMMANDS.md /ll:create-loop section must list orch-router in the wizard type enumeration."""

    def test_orch_router_in_type_list(self):
        content = COMMANDS_MD.read_text()
        assert "orch-router" in content, (
            "COMMANDS.md /ll:create-loop step 1 type enumeration should include 'orch-router'"
        )
