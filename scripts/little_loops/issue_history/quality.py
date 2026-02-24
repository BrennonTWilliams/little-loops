"""Issue history quality analysis: test gaps, rejections, manual patterns, config gaps."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from little_loops.issue_history.models import (
    CompletedIssue,
    ConfigGap,
    ConfigGapsAnalysis,
    HotspotAnalysis,
    ManualPattern,
    ManualPatternAnalysis,
    RejectionAnalysis,
    RejectionMetrics,
    TestGap,
    TestGapAnalysis,
)
from little_loops.issue_history.parsing import _find_test_file, _parse_resolution_action


def analyze_test_gaps(
    issues: list[CompletedIssue],
    hotspots: HotspotAnalysis,
) -> TestGapAnalysis:
    """Correlate bug occurrences with test coverage gaps.

    Args:
        issues: List of completed issues (unused, for API consistency)
        hotspots: Pre-computed hotspot analysis

    Returns:
        TestGapAnalysis with test coverage gap information
    """
    # Build map of source files to bug info from hotspots
    bug_files: dict[str, dict[str, Any]] = {}

    for hotspot in hotspots.file_hotspots:
        bug_count = hotspot.issue_types.get("BUG", 0)
        if bug_count > 0:
            # Filter to only BUG issue IDs
            bug_ids = [iid for iid in hotspot.issue_ids if iid.startswith("BUG-")]
            bug_files[hotspot.path] = {
                "bug_count": bug_count,
                "bug_ids": bug_ids,
            }

    if not bug_files:
        return TestGapAnalysis()

    # Analyze test coverage for each file with bugs
    gaps: list[TestGap] = []
    files_with_tests: list[int] = []  # bug counts
    files_without_tests: list[int] = []  # bug counts

    for source_file, data in bug_files.items():
        bug_count = data["bug_count"]
        bug_ids = data["bug_ids"]

        test_file = _find_test_file(source_file)
        has_test = test_file is not None

        # Calculate gap score: higher = more urgent to add tests
        # Files without tests get amplified scores
        if has_test:
            gap_score = bug_count * 1.0
            files_with_tests.append(bug_count)
        else:
            gap_score = bug_count * 10.0  # Amplify untested files
            files_without_tests.append(bug_count)

        # Determine priority based on bug count and test presence
        if not has_test and bug_count >= 5:
            priority = "critical"
        elif not has_test and bug_count >= 3:
            priority = "high"
        elif not has_test or bug_count >= 4:
            priority = "medium"
        else:
            priority = "low"

        gaps.append(
            TestGap(
                source_file=source_file,
                bug_count=bug_count,
                bug_ids=bug_ids,
                has_test_file=has_test,
                test_file_path=test_file,
                gap_score=gap_score,
                priority=priority,
            )
        )

    # Sort by gap score descending (highest priority first)
    gaps.sort(key=lambda g: (-g.gap_score, -g.bug_count))

    # Calculate averages for correlation
    avg_with_tests = sum(files_with_tests) / len(files_with_tests) if files_with_tests else 0.0
    avg_without_tests = (
        sum(files_without_tests) / len(files_without_tests) if files_without_tests else 0.0
    )

    # Identify untested bug magnets (from hotspot analysis)
    untested_magnets = [h.path for h in hotspots.bug_magnets if _find_test_file(h.path) is None]

    # Priority test targets: untested files sorted by bug count
    priority_targets = [g.source_file for g in gaps if not g.has_test_file]

    return TestGapAnalysis(
        gaps=gaps[:15],  # Top 15
        untested_bug_magnets=untested_magnets,
        files_with_tests_avg_bugs=avg_with_tests,
        files_without_tests_avg_bugs=avg_without_tests,
        priority_test_targets=priority_targets[:10],
    )


def analyze_rejection_rates(
    issues: list[CompletedIssue],
    contents: dict[Path, str] | None = None,
) -> RejectionAnalysis:
    """Analyze rejection and invalid closure patterns.

    Args:
        issues: List of completed issues
        contents: Pre-loaded issue file contents (path -> content)

    Returns:
        RejectionAnalysis with overall and grouped metrics
    """
    if not issues:
        return RejectionAnalysis()

    # Count by category
    overall = RejectionMetrics()
    by_type: dict[str, RejectionMetrics] = {}
    by_month: dict[str, RejectionMetrics] = {}
    reason_counts: dict[str, int] = {}

    for issue in issues:
        if contents is not None and issue.path in contents:
            content = contents[issue.path]
        else:
            try:
                content = issue.path.read_text(encoding="utf-8")
            except Exception:
                continue

        category = _parse_resolution_action(content)
        overall.total_closed += 1

        # Update overall counts
        if category == "completed":
            overall.completed_count += 1
        elif category == "rejected":
            overall.rejected_count += 1
        elif category == "invalid":
            overall.invalid_count += 1
        elif category == "duplicate":
            overall.duplicate_count += 1
        elif category == "deferred":
            overall.deferred_count += 1

        # By type
        if issue.issue_type not in by_type:
            by_type[issue.issue_type] = RejectionMetrics()
        type_metrics = by_type[issue.issue_type]
        type_metrics.total_closed += 1
        if category == "rejected":
            type_metrics.rejected_count += 1
        elif category == "invalid":
            type_metrics.invalid_count += 1
        elif category == "duplicate":
            type_metrics.duplicate_count += 1
        elif category == "deferred":
            type_metrics.deferred_count += 1
        elif category == "completed":
            type_metrics.completed_count += 1

        # By month
        if issue.completed_date:
            month_key = issue.completed_date.strftime("%Y-%m")
            if month_key not in by_month:
                by_month[month_key] = RejectionMetrics()
            month_metrics = by_month[month_key]
            month_metrics.total_closed += 1
            if category == "rejected":
                month_metrics.rejected_count += 1
            elif category == "invalid":
                month_metrics.invalid_count += 1
            elif category == "duplicate":
                month_metrics.duplicate_count += 1
            elif category == "deferred":
                month_metrics.deferred_count += 1
            elif category == "completed":
                month_metrics.completed_count += 1

        # Extract reason for rejection/invalid
        if category in ("rejected", "invalid", "duplicate", "deferred"):
            reason_match = re.search(r"\*\*Reason\*\*:\s*(.+?)(?:\n|$)", content)
            if reason_match:
                reason = reason_match.group(1).strip()
                reason_counts[reason] = reason_counts.get(reason, 0) + 1

    # Calculate trend from monthly data
    sorted_months = sorted(by_month.keys())
    if len(sorted_months) >= 3:
        recent = sorted_months[-3:]
        rates = [by_month[m].rejection_rate + by_month[m].invalid_rate for m in recent]
        if rates[-1] < rates[0] * 0.8:
            trend = "improving"
        elif rates[-1] > rates[0] * 1.2:
            trend = "degrading"
        else:
            trend = "stable"
    else:
        trend = "stable"

    # Sort reasons by count
    common_reasons = sorted(reason_counts.items(), key=lambda x: -x[1])[:10]

    return RejectionAnalysis(
        overall=overall,
        by_type=by_type,
        by_month=by_month,
        common_reasons=common_reasons,
        trend=trend,
    )


# Pattern definitions for manual activity detection
_MANUAL_PATTERNS: dict[str, dict[str, Any]] = {
    "test": {
        "patterns": [
            r"(?:pytest|python -m pytest|npm test|yarn test|jest|cargo test|go test)",
            r"(?:python -m unittest|nosetests|tox)",
        ],
        "description": "Test execution after code changes",
        "suggestion": "Add post-edit hook for automatic test runs",
        "complexity": "trivial",
    },
    "lint": {
        "patterns": [
            r"(?:ruff check|ruff format|black|isort|flake8|pylint)",
            r"(?:eslint|prettier|tslint)",
        ],
        "description": "Lint/format fixes after implementation",
        "suggestion": "Add pre-commit hook for auto-formatting",
        "complexity": "simple",
    },
    "type_check": {
        "patterns": [
            r"(?:mypy|pyright|python -m mypy)",
            r"(?:tsc|npx tsc)",
        ],
        "description": "Type checking during development",
        "suggestion": "Add mypy to pre-commit or post-edit hook",
        "complexity": "simple",
    },
    "build": {
        "patterns": [
            r"(?:npm run build|yarn build|make|cargo build|go build)",
            r"(?:python -m build|pip install -e)",
        ],
        "description": "Build steps during implementation",
        "suggestion": "Add build verification to test suite or CI",
        "complexity": "moderate",
    },
    "git": {
        "patterns": [
            r"git (?:add|commit|push|pull|checkout|branch)",
        ],
        "description": "Git operations during issue resolution",
        "suggestion": "Use /ll:commit skill for standardized commits",
        "complexity": "trivial",
    },
}


def detect_manual_patterns(
    issues: list[CompletedIssue],
    contents: dict[Path, str] | None = None,
) -> ManualPatternAnalysis:
    """Detect recurring manual activities that could be automated.

    Args:
        issues: List of completed issues
        contents: Pre-loaded issue file contents (path -> content)

    Returns:
        ManualPatternAnalysis with detected patterns
    """
    if not issues:
        return ManualPatternAnalysis()

    # Track pattern occurrences
    pattern_data: dict[str, dict[str, Any]] = {}

    for pattern_type, config in _MANUAL_PATTERNS.items():
        pattern_data[pattern_type] = {
            "count": 0,
            "issues": [],
            "commands": [],
            "config": config,
        }

    # Scan issue content for patterns
    for issue in issues:
        if contents is not None and issue.path in contents:
            content = contents[issue.path]
        else:
            try:
                content = issue.path.read_text(encoding="utf-8")
            except Exception:
                continue

        for pattern_type, config in _MANUAL_PATTERNS.items():
            for pattern in config["patterns"]:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    data = pattern_data[pattern_type]
                    data["count"] += len(matches)
                    if issue.issue_id not in data["issues"]:
                        data["issues"].append(issue.issue_id)
                    # Store unique command examples
                    for match in matches:
                        if match not in data["commands"]:
                            data["commands"].append(match)

    # Build ManualPattern objects
    patterns: list[ManualPattern] = []
    total_interventions = 0
    automatable = 0

    for pattern_type, data in pattern_data.items():
        if data["count"] > 0:
            config = data["config"]
            pattern = ManualPattern(
                pattern_type=pattern_type,
                pattern_description=config["description"],
                occurrence_count=data["count"],
                affected_issues=data["issues"],
                example_commands=data["commands"][:5],
                suggested_automation=config["suggestion"],
                automation_complexity=config["complexity"],
            )
            patterns.append(pattern)
            total_interventions += data["count"]
            automatable += data["count"]

    # Sort by occurrence count descending
    patterns.sort(key=lambda p: -p.occurrence_count)

    # Build automation suggestions
    suggestions = [p.suggested_automation for p in patterns if p.occurrence_count >= 2]

    return ManualPatternAnalysis(
        patterns=patterns,
        total_manual_interventions=total_interventions,
        automatable_count=automatable,
        automation_suggestions=suggestions[:10],
    )


# Mapping from manual pattern types to configuration solutions
_PATTERN_TO_CONFIG: dict[str, dict[str, Any]] = {
    "test": {
        "hook_event": "PostToolUse",
        "description": "Automatic test execution after code changes",
        "suggested_config": """hooks/hooks.json:
  "PostToolUse": [{
    "matcher": "Edit|Write",
    "hooks": [{
      "type": "command",
      "command": "pytest tests/ -x -q",
      "timeout": 30000
    }]
  }]""",
    },
    "lint": {
        "hook_event": "PreToolUse",
        "description": "Automatic formatting before file writes",
        "suggested_config": """hooks/hooks.json:
  "PreToolUse": [{
    "matcher": "Write|Edit",
    "hooks": [{
      "type": "command",
      "command": "ruff format --check .",
      "timeout": 10000
    }]
  }]""",
    },
    "type_check": {
        "hook_event": "PostToolUse",
        "description": "Type checking after code modifications",
        "suggested_config": """hooks/hooks.json:
  "PostToolUse": [{
    "matcher": "Edit|Write",
    "hooks": [{
      "type": "command",
      "command": "mypy --fast .",
      "timeout": 30000
    }]
  }]""",
    },
    "build": {
        "hook_event": "PostToolUse",
        "description": "Build verification after changes",
        "suggested_config": """hooks/hooks.json:
  "PostToolUse": [{
    "matcher": "Edit|Write",
    "hooks": [{
      "type": "command",
      "command": "npm run build",
      "timeout": 60000
    }]
  }]""",
    },
}


def detect_config_gaps(
    manual_pattern_analysis: ManualPatternAnalysis,
    project_root: Path | None = None,
) -> ConfigGapsAnalysis:
    """Detect configuration gaps based on manual pattern analysis.

    Args:
        manual_pattern_analysis: Results from detect_manual_patterns()
        project_root: Project root directory (defaults to cwd)

    Returns:
        ConfigGapsAnalysis with identified gaps and coverage metrics
    """
    if project_root is None:
        project_root = Path.cwd()

    # Discover current configuration
    current_hooks: list[str] = []
    current_skills: list[str] = []
    current_agents: list[str] = []

    # Load hooks configuration
    hooks_file = project_root / "hooks" / "hooks.json"
    if hooks_file.exists():
        try:
            with open(hooks_file, encoding="utf-8") as f:
                hooks_data = json.load(f)
            current_hooks = list(hooks_data.get("hooks", {}).keys())
        except Exception:
            pass

    # Scan for agents
    agents_dir = project_root / "agents"
    if agents_dir.is_dir():
        for agent_file in agents_dir.glob("*.md"):
            current_agents.append(agent_file.stem)

    # Scan for skills
    skills_dir = project_root / "skills"
    if skills_dir.is_dir():
        for skill_dir in skills_dir.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                current_skills.append(skill_dir.name)

    # Identify gaps from manual patterns
    gaps: list[ConfigGap] = []
    covered_patterns = 0
    recognized_patterns = 0

    for pattern in manual_pattern_analysis.patterns:
        config_mapping = _PATTERN_TO_CONFIG.get(pattern.pattern_type)
        if not config_mapping:
            continue

        recognized_patterns += 1
        hook_event = config_mapping["hook_event"]

        # Check if hook event is already configured
        if hook_event in current_hooks:
            covered_patterns += 1
            continue

        # Determine priority based on occurrence count
        if pattern.occurrence_count >= 10:
            priority = "high"
        elif pattern.occurrence_count >= 5:
            priority = "medium"
        else:
            priority = "low"

        gap = ConfigGap(
            gap_type="hook",
            description=config_mapping["description"],
            evidence=pattern.affected_issues,
            suggested_config=config_mapping["suggested_config"],
            priority=priority,
            pattern_type=pattern.pattern_type,
        )
        gaps.append(gap)

    # Calculate coverage score based on recognized patterns only
    coverage_score = covered_patterns / recognized_patterns if recognized_patterns > 0 else 1.0

    # Sort gaps by priority (high first)
    priority_order = {"high": 0, "medium": 1, "low": 2}
    gaps.sort(key=lambda g: priority_order.get(g.priority, 3))

    return ConfigGapsAnalysis(
        gaps=gaps,
        current_hooks=current_hooks,
        current_skills=current_skills,
        current_agents=current_agents,
        coverage_score=coverage_score,
    )
