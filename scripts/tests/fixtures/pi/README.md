# Pi usage survey (ENH-3648)

Pi CLI **0.84.2** is installed, but the probe could not make a model request
because no API key was configured. There is no real usage-bearing live or
on-disk fixture. All metric/channel availability, field names, cache
inclusivity and write reporting, omission semantics, request grain and resume
behavior, native source-event identity, and reasoning-in-output are
**unknown**. Authentication failure is not evidence of unsupported telemetry.

**Recommendation:** Defer measured ingestion. ENH-3661 owns a versioned
credentialed live/session capture with a tool call and resume; ENH-3534 can
then decide whether Pi needs a normalizer or a separate implementation issue.
