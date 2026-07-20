"""Headless init core for little-loops."""

from little_loops.init.core import build_config
from little_loops.init.detect import TemplateMatch, detect_project_type
from little_loops.init.install_check import (
    InstallStatus,
    check_version,
    detect_installation,
    fetch_latest_plugin,
    fetch_latest_pypi,
    installed_package_version,
)
from little_loops.init.introspect import (
    Ambiguity,
    IntrospectedValue,
    IntrospectResult,
    introspect,
)
from little_loops.init.validate import DepWarning, validate_deps
from little_loops.init.writers import (
    deploy_design_tokens,
    deploy_goals,
    deploy_issue_templates,
    install_codex_adapter,
    make_issue_dirs,
    make_learning_tests_dir,
    merge_settings,
    read_adapter_gen_version,
    update_gitignore,
    write_config,
)

__all__ = [
    "InstallStatus",
    "TemplateMatch",
    "DepWarning",
    "Ambiguity",
    "IntrospectedValue",
    "IntrospectResult",
    "build_config",
    "check_version",
    "deploy_design_tokens",
    "deploy_goals",
    "deploy_issue_templates",
    "detect_installation",
    "detect_project_type",
    "fetch_latest_plugin",
    "fetch_latest_pypi",
    "install_codex_adapter",
    "installed_package_version",
    "introspect",
    "make_issue_dirs",
    "make_learning_tests_dir",
    "merge_settings",
    "read_adapter_gen_version",
    "update_gitignore",
    "validate_deps",
    "write_config",
]
