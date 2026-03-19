# ENH-815: FSM Diagram Edge Label Colors Configurable in ll-config

**Date**: 2026-03-19  
**Issue**: ENH-815  
**Action**: improve  

## Solution Design

Add `CliColorsEdgeLabelsConfig` dataclass to the config layer, wire it through the rendering chain so `_colorize_diagram_labels` respects user config instead of hardcoded `_EDGE_LABEL_COLORS`.

## Implementation Phases

### Phase 0: Write Tests (Red)

**test_config.py** — `CliColorsEdgeLabelsConfig` tests:
- `test_edge_labels_defaults` — `CliColorsEdgeLabelsConfig()` has correct defaults
- `test_edge_labels_from_dict_default` — `from_dict({})` returns defaults
- `test_edge_labels_from_dict_override` — `from_dict({"yes": "36"})` overrides
- `test_cli_colors_has_fsm_edge_labels` — `CliColorsConfig().fsm_edge_labels` is populated
- `test_cli_colors_from_dict_fsm_edge_labels` — nested override flows through

**test_ll_loop_display.py** — rendering tests:
- `test_edge_label_custom_color_applied` — `_render_fsm_diagram(..., edge_label_colors={"yes": "99"})` produces `\033[99m` 
- `test_edge_label_custom_color_no_default` — default color not present when overridden

### Phase 1: Config Layer

**`config/cli.py`**: Add `CliColorsEdgeLabelsConfig` before `CliColorsConfig`:
```python
@dataclass
class CliColorsEdgeLabelsConfig:
    yes: str = "32"
    no: str = "38;5;208"
    error: str = "31"
    partial: str = "33"
    next: str = "2"
    default: str = "2"
    blocked: str = "31"
    retry_exhausted: str = "38;5;208"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CliColorsEdgeLabelsConfig:
        return cls(
            yes=data.get("yes", "32"),
            no=data.get("no", "38;5;208"),
            error=data.get("error", "31"),
            partial=data.get("partial", "33"),
            next=data.get("next", "2"),
            default=data.get("default", "2"),
            blocked=data.get("blocked", "31"),
            retry_exhausted=data.get("retry_exhausted", "38;5;208"),
        )

    def to_dict(self) -> dict[str, str]:
        """Convert to dict suitable for _colorize_diagram_labels (maps 'default' -> '_')."""
        return {
            "yes": self.yes, "no": self.no, "error": self.error,
            "partial": self.partial, "next": self.next, "_": self.default,
            "blocked": self.blocked, "retry_exhausted": self.retry_exhausted,
        }
```

Add `fsm_edge_labels` to `CliColorsConfig`.

### Phase 2: Schema

**`config-schema.json`**: Add `fsm_edge_labels` object after `fsm_active_state` under `cli.colors.properties`.

### Phase 3: Layout Layer

**`layout.py`**:
1. `_colorize_diagram_labels(diagram, colors=None)` — use `colors or _EDGE_LABEL_COLORS`
2. `_render_layered_diagram(...)` — add `edge_label_colors: dict[str, str] | None = None`, pass to `_colorize_diagram_labels` at line 1414
3. `_render_horizontal_simple(...)` — add `edge_label_colors: dict[str, str] | None = None`, pass to `_colorize_diagram_labels` at line 1606
4. `_render_fsm_diagram(...)` — add `edge_label_colors: dict[str, str] | None = None`, thread to both renderers

### Phase 4: Wiring

**`_helpers.py`**: `run_foreground(...)` — add `edge_label_colors: dict[str, str] | None = None`, pass to `_render_fsm_diagram`

**`run.py`**: `cmd_run(...)` — read `BRConfig(...).cli.colors.fsm_edge_labels.to_dict()`, pass to `run_foreground`

## Success Criteria

- [ ] `CliColorsEdgeLabelsConfig` dataclass with correct defaults
- [ ] `CliColorsConfig.fsm_edge_labels` field plumbed through config layer
- [ ] `config-schema.json` has `fsm_edge_labels` object with per-label properties
- [ ] `_colorize_diagram_labels` accepts optional colors dict
- [ ] `_render_fsm_diagram` accepts and threads `edge_label_colors`
- [ ] `run_foreground` accepts and threads `edge_label_colors`
- [ ] `cmd_run` reads config and passes colors to `run_foreground`
- [ ] All tests pass (pytest)
- [ ] Lint and type checks pass
