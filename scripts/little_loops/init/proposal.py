"""Unified detection + proposal model for ll-init.

One function — :func:`build_proposal` — runs the whole "what should this
project's config be?" pipeline (project-type detection, document detection,
manifest introspection, existing-config layering, feature defaults, CLI flag
overrides, ``build_config``, merge, dependency validation) and returns a
:class:`Proposal` that every ll-init surface consumes:

* ``ll-init --yes`` writes ``proposal.config``;
* ``ll-init --plan`` serialises ``proposal.to_plan_dict()``;
* the interactive wizard seeds every prompt from ``proposal.choices`` and
  shows the matching :class:`ProposedField` evidence next to it.

Before this module the headless path and the wizard ran two different
pipelines (the wizard never called ``introspect()``), so the same project got
different defaults depending on whether stdin was a TTY.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from little_loops.init.detect import TemplateMatch
from little_loops.init.introspect import IntrospectResult
from little_loops.init.validate import DepWarning

Provenance = Literal["declared", "inferred", "default", "existing", "flag", "recommended"]

# Flat build_config choice keys for the project.* command fields, in display order.
_PROJECT_FIELDS: tuple[str, ...] = (
    "src_dir",
    "test_dir",
    "test_cmd",
    "lint_cmd",
    "type_cmd",
    "format_cmd",
)
_PROJECT_FIELD_LABELS: dict[str, str] = {
    "src_dir": "Source dir",
    "test_dir": "Test dir",
    "test_cmd": "Test",
    "lint_cmd": "Lint",
    "type_cmd": "Type-check",
    "format_cmd": "Format",
    "build_cmd": "Build",
}


@dataclass(frozen=True)
class ProposedField:
    """A single proposed config value with where it came from."""

    key: str  # dotted config path, e.g. "project.test_cmd"
    value: Any
    provenance: Provenance
    evidence: str = ""

    @property
    def label(self) -> str:
        """Short human label for the wizard/summary (``"declared: [tool.ruff] present"``)."""
        return f"{self.provenance}: {self.evidence}" if self.evidence else self.provenance


@dataclass
class Proposal:
    """Everything ll-init knows about a project before writing anything."""

    project_root: Path
    template: TemplateMatch
    candidates: list[TemplateMatch]
    introspection: IntrospectResult
    documents_categories: dict[str, Any]
    existing_config: dict[str, Any]
    choices: dict[str, Any]
    fields: dict[str, ProposedField]
    config: dict[str, Any]
    warnings: list[DepWarning] = field(default_factory=list)
    is_git_repo: bool = True
    codegraph: Any = None  # CodegraphStatus once the code-graph step lands

    # -- accessors -----------------------------------------------------

    @property
    def runner_up(self) -> TemplateMatch | None:
        return next((c for c in self.candidates[1:] if c.match_count > 0), None)

    def field_for(self, key: str) -> ProposedField | None:
        return self.fields.get(key)

    def provenance_rows(self, include_default: bool = False) -> list[tuple[str, str, str]]:
        """``(label, value, provenance-label)`` rows for the project.* fields.

        Default-provenance rows are omitted unless *include_default* — the
        wizard shows them (so the user sees what will be written), the
        headless summary hides them (they carry no evidence worth reading).
        """
        rows: list[tuple[str, str, str]] = []
        for name in (*_PROJECT_FIELDS, "build_cmd"):
            pf = self.fields.get(f"project.{name}")
            if pf is None or not pf.value:
                continue
            if pf.provenance == "default" and not include_default:
                continue
            rows.append((_PROJECT_FIELD_LABELS[name], str(pf.value), pf.label))
        focus = self.fields.get("scan.focus_dirs")
        if focus is not None and focus.value and (include_default or focus.provenance != "default"):
            rows.append(("Focus dirs", ", ".join(focus.value), focus.label))
        return rows

    def to_plan_dict(
        self,
        *,
        requested_upgrade: bool = False,
        host_options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Serialise for ``ll-init --plan``.

        The seven historical keys (``detected``, ``proposed_config``,
        ``requested_upgrade``, ``host_options``, ``warnings``, ``provenance``,
        ``ambiguities``) keep their shapes — ``skills/init/SKILL.md`` reads
        them — and ``fields`` is additive (full provenance including
        ``existing``/``flag``/``recommended`` sources).
        """
        runner_up = self.runner_up
        plan: dict[str, Any] = {
            "detected": {
                "template_name": self.template.filename,
                "project_type": self.template.name,
                "project_name": self.project_root.name,
                "match_count": self.template.match_count,
                "runner_up": (
                    {"project_type": runner_up.name, "match_count": runner_up.match_count}
                    if runner_up
                    else None
                ),
            },
            "proposed_config": self.config,
            "requested_upgrade": requested_upgrade,
            "host_options": host_options or {},
            "warnings": [
                {"message": w.message, "install_hint": w.install_hint} for w in self.warnings
            ],
            "provenance": [
                {
                    "field": dotted_key,
                    "value": iv.value,
                    "provenance": iv.provenance,
                    "evidence": iv.evidence,
                }
                for dotted_key, iv in self.introspection.values.items()
            ],
            "ambiguities": [
                {"field": a.field, "candidates": a.candidates, "note": a.note}
                for a in self.introspection.ambiguities
            ],
            "fields": [
                {
                    "key": pf.key,
                    "value": pf.value,
                    "provenance": pf.provenance,
                    "evidence": pf.evidence,
                }
                for pf in self.fields.values()
            ],
        }
        if self.codegraph is not None and hasattr(self.codegraph, "to_dict"):
            plan["code_graph"] = self.codegraph.to_dict()
        return plan


# Feature name -> config section whose ``enabled`` key the feature toggles.
_FEATURE_SECTIONS: dict[str, str] = {
    name: name
    for name in (
        "product",
        "analytics",
        "context_monitor",
        "learning_tests",
        "decisions",
        "scratch_pad",
        "session_capture",
        "prompt_optimization",
        "documents",
        "design_tokens",
        "sync",
    )
}


def _apply_disable_flags(config: dict[str, Any], feature_choices: dict[str, Any]) -> None:
    """Make ``--disable <feature>`` stick on a re-init.

    ``build_config`` expresses "disabled" by *omitting* the section, which the
    merge with an existing config then silently restores. An explicit flag is
    the user's decision, so flip the existing section off (or drop it, for
    ``parallel`` whose presence is the enablement) after the merge.
    """
    for key, value in feature_choices.items():
        if value is not False:
            continue
        name = key.removesuffix("_enabled")
        if name in _FEATURE_SECTIONS:
            section = config.get(_FEATURE_SECTIONS[name])
            if isinstance(section, dict):
                section["enabled"] = False
        elif name == "parallel":
            config.pop("parallel", None)
        elif name == "confidence_gate":
            gate = config.get("commands", {}).get("confidence_gate")
            if isinstance(gate, dict):
                gate["enabled"] = False
        elif name == "tdd":
            if isinstance(config.get("commands"), dict) and "tdd_mode" in config["commands"]:
                config["commands"]["tdd_mode"] = False
        elif name == "session_digest":
            digest = config.get("history", {}).get("session_digest")
            if isinstance(digest, dict):
                digest["enabled"] = False


def _flat_key(dotted_key: str) -> str:
    section, name = dotted_key.split(".", 1)
    return f"scan_{name}" if section == "scan" else name


def build_proposal(
    project_root: Path,
    templates_dir: Path | None,
    *,
    feature_choices: dict[str, Any] | None = None,
    force: bool = False,
    plugin_version: str | None = None,
    existing_config: dict[str, Any] | None = None,
) -> Proposal:
    """Run the full detection pipeline and return the proposed config.

    Precedence (lowest to highest): template default < manifest introspection
    < existing ``.ll/ll-config.json`` < recommended/existing feature set <
    ``--enable``/``--disable`` flags. ``--force`` bypasses the final merge
    with the existing config (reset-to-template semantics) but still uses the
    existing values to pre-populate, matching the historical ``--yes`` path.

    Args:
        project_root: Project root directory.
        templates_dir: Bundled templates dir (``None`` → auto-discovery).
        feature_choices: ``{feature}_enabled`` overrides from the CLI flags.
        force: ``--force`` — skip the merge with the existing config.
        plugin_version: When given, run :func:`validate_deps` and attach the
            warnings. ``None`` skips validation (the wizard validates after
            the user has confirmed).
        existing_config: Pre-loaded existing config; loaded from disk when
            omitted.
    """
    from little_loops.init.core import (
        RECOMMENDED_FEATURES,
        build_config,
        recommended_feature_choices,
        reinit_feature_choices,
    )
    from little_loops.init.detect import detect_documents, detect_project_type_all
    from little_loops.init.introspect import introspect
    from little_loops.init.validate import validate_deps
    from little_loops.init.writers import load_existing_config, merge_with_existing

    candidates = detect_project_type_all(project_root, templates_dir)
    template = candidates[0]
    documents_categories = detect_documents(project_root)
    introspection = introspect(project_root, template)
    if existing_config is None:
        existing_config = load_existing_config(project_root)

    choices: dict[str, Any] = {"project_name": project_root.name}
    fields: dict[str, ProposedField] = {
        "project.name": ProposedField(
            "project.name", project_root.name, "default", "directory name"
        )
    }

    # 1. manifest introspection (declared / inferred / default)
    for dotted_key, iv in introspection.values.items():
        choices[_flat_key(dotted_key)] = iv.value
        fields[dotted_key] = ProposedField(dotted_key, iv.value, iv.provenance, iv.evidence)

    # 2. existing config wins over introspection
    if existing_config:
        evidence = "ll-config.json"
        ex_proj = existing_config.get("project", {})
        if ex_proj.get("name"):
            choices["project_name"] = ex_proj["name"]
            fields["project.name"] = ProposedField(
                "project.name", ex_proj["name"], "existing", evidence
            )
        for name in (
            "src_dir",
            "test_dir",
            "test_cmd",
            "lint_cmd",
            "format_cmd",
            "type_cmd",
            "build_cmd",
        ):
            if ex_proj.get(name):
                choices[name] = ex_proj[name]
                fields[f"project.{name}"] = ProposedField(
                    f"project.{name}", ex_proj[name], "existing", evidence
                )
        if existing_config.get("scan", {}).get("focus_dirs"):
            choices["scan_focus_dirs"] = existing_config["scan"]["focus_dirs"]
            fields["scan.focus_dirs"] = ProposedField(
                "scan.focus_dirs", choices["scan_focus_dirs"], "existing", evidence
            )
        for key, value in reinit_feature_choices(existing_config).items():
            choices[key] = value
            fields[f"feature.{key.removesuffix('_enabled')}"] = ProposedField(
                f"feature.{key.removesuffix('_enabled')}", value, "existing", evidence
            )
    else:
        for key, value in recommended_feature_choices().items():
            choices[key] = value
            name = key.removesuffix("_enabled")
            fields[f"feature.{name}"] = ProposedField(
                f"feature.{name}",
                value,
                "recommended" if name in RECOMMENDED_FEATURES else "default",
                "recommended for new projects"
                if name in RECOMMENDED_FEATURES
                else "schema default",
            )

    # 3. explicit CLI flags win over everything
    for key, value in (feature_choices or {}).items():
        choices[key] = value
        name = key.removesuffix("_enabled")
        fields[f"feature.{name}"] = ProposedField(
            f"feature.{name}", value, "flag", "--enable/--disable"
        )

    # 4. documents: detected categories, unless the existing config already has a section
    if documents_categories and not existing_config.get("documents"):
        choices["documents_categories"] = documents_categories
        fields["documents.categories"] = ProposedField(
            "documents.categories",
            sorted(documents_categories),
            "inferred",
            f"{sum(len(c.get('files', [])) for c in documents_categories.values())} docs detected",
        )

    # 5. code graph: an existing index turns the code_query block on
    from little_loops.init.codegraph import detect_codegraph

    codegraph = detect_codegraph(project_root)
    if codegraph.index_present:
        choices["code_query_enabled"] = True
        fields["code_query.provider"] = ProposedField(
            "code_query.provider", "auto", "inferred", f"{codegraph.db_path.name} index present"
        )

    config = build_config(template, choices)
    config = merge_with_existing(config, existing_config, force)
    _apply_disable_flags(config, feature_choices or {})

    warnings: list[DepWarning] = []
    if plugin_version is not None:
        warnings = validate_deps(config, plugin_version, project_root)

    from little_loops.init.cli import _is_git_repo

    return Proposal(
        project_root=project_root,
        template=template,
        candidates=candidates,
        introspection=introspection,
        documents_categories=documents_categories,
        existing_config=existing_config,
        choices=choices,
        fields=fields,
        config=config,
        warnings=warnings,
        is_git_repo=_is_git_repo(project_root),
        codegraph=codegraph,
    )
