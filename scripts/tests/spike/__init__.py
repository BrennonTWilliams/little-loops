"""Root package for code spikes produced by the `/ll:spike` skill (FEAT-2567).

Each spike lives in its own subpackage `scripts/tests/spike/<slug>/` and proves a
single unprecedented internal mechanism in isolation before the real integration
point is touched. Spike code is transient by design: on acceptance it is promoted
to `scripts/little_loops/spike/<slug>/` in a separate PR (see each spike plan's
Promotion section).
"""
