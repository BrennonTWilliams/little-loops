---
target: opentelemetry
date: '2026-07-08'
status: proven
assertions:
- claim: 'Resource.create({"service.name": X}).attributes["service.name"] == X'
  result: pass
- claim: 'tracer.start_span("foo") returns a Span with .name == "foo" and .kind
    == SpanKind.INTERNAL'
  result: pass
- claim: 'set_span_in_context(parent) + tracer.start_span("child", context=ctx)
    produces a child Span whose .parent.span_id equals the parent''s span_id
    (manual parent context without `with` block works for the nested FSM loop /
    state / action span hierarchy in OTelTransport)'
  result: pass
- claim: 'span.set_status(StatusCode.ERROR, "boom") sets span.status.status_code
    == StatusCode.ERROR and preserves the description "boom"'
  result: pass
- claim: 'span.add_event("evaluate", attributes={"k": "v"}) appends an event whose
    .name == "evaluate" and whose attributes include "k" mapped to "v" (string
    attributes round-trip without coercion)'
  result: pass
- claim: 'SimpleSpanProcessor + InMemorySpanExporter captures ended spans; after
    provider.force_flush(), get_finished_spans() contains a span by the recorded
    name (round-trip for scripts/tests/test_transport.py::TestOTelTransport style
    assertions)'
  result: pass
- claim: 'OTLPSpanExporter(endpoint="http://localhost:1", insecure=True) constructs
    without raising (no network IO until .export(); invalid endpoint does not
    break __init__ — important because OTelTransport passes user-configured endpoint
    directly without a pre-flight ping)'
  result: pass
raw_output_path: .ll/learning-tests/raw/opentelemetry.txt
---
