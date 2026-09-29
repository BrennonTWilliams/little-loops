# OMP usage survey (ENH-3648)

The OMP CLI is absent from this machine, so no real versioned live or stored
usage capture was possible. Existing `session.jsonl` and
`legacy_no_title_slot.jsonl` are **synthetic** fixtures made from vendored
session types. Their assistant `message.usage` examples contain
`input`, `output`, `cacheRead`, and `cacheWrite`, but those samples do not prove
what an installed producer emits. There is no supported or unsupported native
metric/channel claim from these fixtures.

Version, live fields, stored fields, cache inclusivity, omission semantics,
grain/resume behavior, native source-event identity, and reasoning-in-output
all remain **unknown**. The current OMP normalizer drops usage from its
Claude-shaped `iter_events()` output. Missing CLI access is not evidence of
native absence.

**Recommendation:** Defer measured ingestion. ENH-3664 owns a real versioned
capture with a tool call and resume. ENH-3534 can then assess the native
fields and normalization path.
