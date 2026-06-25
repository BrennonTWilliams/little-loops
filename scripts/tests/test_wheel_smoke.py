"""Wheel smoke test — runtime backstop for non-editable installs.

Builds the package wheel, installs it non-editable into a temporary venv
with CLAUDE_PLUGIN_ROOT unset, then exercises each asset-read surface to
confirm none silently degrade. Covers conditional/host-specific paths that
the static manifest check cannot enumerate.

Gated on PYTEST_INTEGRATION=1 so it is skipped in fast local runs but
fires in CI. Mark is already registered in pyproject.toml.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import venv
from pathlib import Path

import pytest


@pytest.mark.slow
@pytest.mark.integration
class TestWheelSmoke:
    """Non-editable-install smoke tests for all in-package asset-read surfaces."""

    @pytest.fixture(scope="class")
    def installed_venv(self, tmp_path_factory: pytest.TempPathFactory):
        """Build the wheel and install it non-editable in a temporary venv."""
        if not os.environ.get("PYTEST_INTEGRATION"):
            pytest.skip("Set PYTEST_INTEGRATION=1 to run wheel smoke tests")

        scripts_dir = Path(__file__).resolve().parents[1]  # scripts/
        tmp = tmp_path_factory.mktemp("wheel_smoke")
        dist_dir = tmp / "dist"
        venv_dir = tmp / "venv"

        # Build the wheel
        result = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir)],
            capture_output=True,
            text=True,
            cwd=str(scripts_dir),
            timeout=120,
            env={**os.environ, "CLAUDE_PLUGIN_ROOT": ""},
        )
        assert result.returncode == 0, f"build failed:\n{result.stderr}"

        wheels = list(dist_dir.glob("*.whl"))
        assert len(wheels) == 1, f"Expected one wheel, got {wheels}"
        wheel = wheels[0]

        # Create a fresh venv and install the wheel (non-editable, no CLAUDE_PLUGIN_ROOT)
        venv.create(str(venv_dir), with_pip=True, clear=True)
        python = venv_dir / "bin" / "python"

        # Upgrade pip silently
        subprocess.run(
            [str(python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
            capture_output=True,
            timeout=60,
        )

        install = subprocess.run(
            [str(python), "-m", "pip", "install", "--quiet", str(wheel)],
            capture_output=True,
            text=True,
            timeout=120,
            env={k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_ROOT"},
        )
        assert install.returncode == 0, f"install failed:\n{install.stderr}"

        return python

    def _run(self, python: Path, code: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
        """Run a Python snippet in the installed venv without CLAUDE_PLUGIN_ROOT."""
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_ROOT"}
        return subprocess.run(
            [str(python), "-c", textwrap.dedent(code)],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

    def test_get_logo_returns_text(self, installed_venv: Path) -> None:
        """get_logo() must return non-empty string (assets/ll-cli-logo.txt is in wheel)."""
        result = self._run(
            installed_venv,
            """\
            from little_loops.logo import get_logo
            logo = get_logo()
            assert logo is not None, "get_logo() returned None — asset missing from wheel"
            assert len(logo.strip()) > 0, "get_logo() returned empty string"
            print("OK")
            """,
        )
        assert result.returncode == 0, result.stderr

    def test_package_data_manifest_all_accessible(self, installed_venv: Path) -> None:
        """All PACKAGE_DATA_ASSETS are accessible in the installed wheel."""
        result = self._run(
            installed_venv,
            """\
            from little_loops.package_data import list_missing_assets
            missing = list_missing_assets()
            assert not missing, f"Assets missing from wheel: {missing}"
            print("OK")
            """,
        )
        assert result.returncode == 0, result.stderr

    def test_load_issue_sections_works(self, installed_venv: Path) -> None:
        """load_issue_sections() resolves templates via in-package path (not repo root)."""
        result = self._run(
            installed_venv,
            """\
            from little_loops.issue_template import load_issue_sections
            sections = load_issue_sections("bug")
            assert sections, "load_issue_sections('bug') returned empty — template missing"
            print("OK")
            """,
        )
        assert result.returncode == 0, result.stderr

    def test_optimize_prompt_hook_file_accessible(self, installed_venv: Path) -> None:
        """The optimize-prompt-hook.md template is importlib-accessible in the wheel."""
        result = self._run(
            installed_venv,
            """\
            import importlib.resources
            t = importlib.resources.files("little_loops")
            t = t.joinpath("hooks").joinpath("prompts").joinpath("optimize-prompt-hook.md")
            assert t.is_file(), "optimize-prompt-hook.md not accessible via importlib.resources"
            print("OK")
            """,
        )
        assert result.returncode == 0, result.stderr

    def test_codex_adapter_hooks_json_accessible(self, installed_venv: Path) -> None:
        """The Codex adapter hooks.json is importlib-accessible in the wheel."""
        result = self._run(
            installed_venv,
            """\
            import importlib.resources
            t = importlib.resources.files("little_loops")
            t = t.joinpath("hooks").joinpath("adapters").joinpath("codex").joinpath("hooks.json")
            assert t.is_file(), "codex/hooks.json not accessible via importlib.resources"
            print("OK")
            """,
        )
        assert result.returncode == 0, result.stderr

    def test_ll_init_dry_run_succeeds(self, installed_venv: Path, tmp_path: Path) -> None:
        """ll-init --yes --dry-run completes without error in a fresh project dir."""
        result = subprocess.run(
            [str(installed_venv.parent / "ll-init"), "--yes", "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(tmp_path),
            env={k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_ROOT"},
        )
        assert result.returncode == 0, f"ll-init --yes --dry-run failed:\n{result.stderr}"
