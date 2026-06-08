"""Headless init core for little-loops."""

from little_loops.init.core import build_config
from little_loops.init.detect import TemplateMatch, detect_project_type
from little_loops.init.validate import DepWarning, validate_deps
from little_loops.init.writers import (
    deploy_design_tokens,
    deploy_goals,
    install_codex_adapter,
    make_issue_dirs,
    make_learning_tests_dir,
    merge_settings,
    update_gitignore,
    write_config,
)

__all__ = [
    "TemplateMatch",
    "DepWarning",
    "build_config",
    "deploy_design_tokens",
    "deploy_goals",
    "detect_project_type",
    "install_codex_adapter",
    "make_issue_dirs",
    "make_learning_tests_dir",
    "merge_settings",
    "update_gitignore",
    "validate_deps",
    "write_config",
]
