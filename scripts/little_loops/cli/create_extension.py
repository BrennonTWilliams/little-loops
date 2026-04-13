"""ll-create-extension: Scaffold a new little-loops extension project."""

from __future__ import annotations

import argparse
from pathlib import Path

from little_loops.cli.output import configure_output, use_color_enabled
from little_loops.cli_args import add_dry_run_arg
from little_loops.logger import Logger


def _to_pkg_name(name: str) -> str:
    """Convert kebab-case name to snake_case package name."""
    return name.replace("-", "_")


def _to_class_name(name: str) -> str:
    """Convert kebab-case name to PascalCase class name."""
    return "".join(part.capitalize() for part in name.replace("-", "_").split("_") if part)


def _get_cwd() -> Path:
    """Return current working directory."""
    return Path.cwd()


def _target_exists(target: Path) -> bool:
    """Return True if target directory already exists."""
    return target.exists()


def _write_scaffold(target: Path, files: dict[Path, str]) -> None:
    """Write scaffolded files to disk, creating parent directories as needed."""
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _render_pyproject(name: str, pkg_name: str, class_name: str) -> str:
    """Render pyproject.toml content for the scaffolded extension."""
    parts: list[str] = [
        "[build-system]",
        'requires = ["hatchling"]',
        'build-backend = "hatchling.build"',
        "",
        "[project]",
        f'name = "{name}"',
        'version = "0.1.0"',
        'description = "A little-loops extension"',
        'requires-python = ">=3.11"',
        'dependencies = ["little-loops"]',
        "",
        '[project.entry-points."little_loops.extensions"]',
        f'{name} = "{pkg_name}.extension:{class_name}"',
    ]
    return "\n".join(parts) + "\n"


def _render_init(name: str) -> str:
    """Render __init__.py content for the scaffolded extension package."""
    parts: list[str] = [
        f'"""{name} — a little-loops extension."""',
    ]
    return "\n".join(parts) + "\n"


def _render_extension(name: str, class_name: str) -> str:
    """Render extension.py skeleton for the scaffolded extension."""
    parts: list[str] = [
        f'"""{name} — a little-loops extension."""',
        "",
        "from __future__ import annotations",
        "",
        "from little_loops import LLEvent",
        "",
        "",
        f"class {class_name}:",
        f'    """{class_name} extension.',
        "",
        "    Implement on_event to handle little-loops lifecycle events.",
        "    Optional mixin Protocols (InterceptorExtension, ActionProviderExtension,",
        "    EvaluatorProviderExtension) are opt-in — implement their methods to activate.",
        '    """',
        "",
        "    def on_event(self, event: LLEvent) -> None:",
        '        """Handle an incoming event."""',
        "        # See docs/reference/EVENT-SCHEMA.md for all available event types and payload fields",
        "        pass",
    ]
    return "\n".join(parts) + "\n"


def _render_test(class_name: str, pkg_name: str) -> str:
    """Render test_extension.py content using LLTestBus for the scaffolded extension."""
    parts: list[str] = [
        f'"""Tests for {class_name}."""',
        "",
        "from __future__ import annotations",
        "",
        "from little_loops import LLTestBus",
        "",
        f"from {pkg_name}.extension import {class_name}",
        "",
        "",
        f"class Test{class_name}:",
        "    def test_receives_events(self) -> None:",
        '        """Extension receives events via LLTestBus replay."""',
        "        bus = LLTestBus([])",
        f"        ext = {class_name}()",
        "        bus.register(ext)",
        "        bus.replay()",
        "        assert bus.delivered_events == []",
    ]
    return "\n".join(parts) + "\n"


def main_create_extension() -> int:
    """Entry point for ll-create-extension command.

    Scaffold a new little-loops extension project directory.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    parser = argparse.ArgumentParser(
        prog="ll-create-extension",
        description="Scaffold a new little-loops extension project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s my-dashboard-ext            # Create extension scaffold
  %(prog)s my-dashboard-ext --dry-run  # Preview without writing files
""",
    )

    parser.add_argument(
        "name",
        help="Extension name in kebab-case (e.g. my-dashboard-ext)",
    )
    add_dry_run_arg(parser)

    args = parser.parse_args()
    name: str = args.name
    dry_run: bool = args.dry_run

    configure_output()
    logger = Logger(use_color=use_color_enabled())

    pkg_name = _to_pkg_name(name)
    class_name = _to_class_name(name)
    target = _get_cwd() / name

    if _target_exists(target):
        logger.error(f"directory '{name}' already exists. Remove it or choose a different name.")
        return 1

    files: dict[Path, str] = {
        target / "pyproject.toml": _render_pyproject(name, pkg_name, class_name),
        target / pkg_name / "__init__.py": _render_init(name),
        target / pkg_name / "extension.py": _render_extension(name, class_name),
        target / "tests" / "test_extension.py": _render_test(class_name, pkg_name),
    }

    if dry_run:
        logger.info(f"[DRY RUN] Would create: {name}/")
        for path in files:
            logger.info(f"  {path.relative_to(target)}")
        return 0

    _write_scaffold(target, files)
    logger.success(f"Created: {name}/")
    for path in files:
        logger.info(f"  {path.relative_to(target)}")
    logger.info("\nNext steps:")
    logger.info(f"  cd {name}")
    logger.info("  pip install -e .")
    logger.info("  python -m pytest tests/")

    return 0
