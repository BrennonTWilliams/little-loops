"""ENH-2565 spike: readiness-gated pop + concurrency core for rn-refine synthesis.

Standalone library proving the flock-guarded, readiness-gated concurrent pop
correct in isolation before ``rn-refine.yaml``'s ``synth_pop`` action is edited.
After acceptance this package is promoted to
``scripts/little_loops/spike/rn_refine_synth_pop/`` and imported directly by the
``synth_pop`` PYEOF body.
"""

from .queue import mark_complete, queue_is_empty, try_pop_ready

__all__ = ["mark_complete", "queue_is_empty", "try_pop_ready"]
