---
url: https://docs.boundaryml.com/guide/baml-advanced/
scraped_at: 2026-03-06T01:00:20.684898
filepath: docs-docs-boundaryml-com/guide/baml-advanced/index.md
---

[Home](/home)
[Guide](/guide/introduction/what-is-baml)
[Examples](/examples/interactive-examples)
[BAML Reference](/ref/overview)
[Playground](https://promptfiddle.com/)
[Agents.md](/agents-md/claude-code)
[Changelog](/changelog/changelog)

IntroductionWhat is BAML?Why BAML?What's the baml_src folderWhat's baml_clientInstallation: EditorsVSCode ExtensionCursor ExtensionJetBrains IDEsZedClaude CodeOthersInstallation: LanguagePythonTypescriptGoRubyRustREST API (other languages)ElixirFramework IntegrationReact/Next.jsDevelopmentEnvironment VariablesTerminal LogsUpgrade BAML versionsDeployingBAML BasicsPrompting with BAMLSwitching LLMsTesting functionsStreamingMulti-Modal (Images / Audio)Error HandlingConfiguring TimeoutsConcurrent CallsAbortSignal / CancellationBAML AdvancedCollector (track tokens)LLM Client RegistryDynamic TypesReusing Prompt SnippetsPrompt Caching / Message Role MetadataChecks and AssertsModular APIPrompt OptimizationBoundary CloudObservabilityComparisonsBAML vs LangchainBAML vs MarvinBAML vs Ai-SDKBAML vs OpenAI SDKBAML vs PydanticContact


What is BAML?Why BAML?What's the baml_src folderWhat's baml_client

[What is BAML?](/guide/introduction/what-is-baml)
[Why BAML?](/guide/introduction/why-baml)
[What's the baml_src folder](/guide/introduction/baml_src)
[What's baml_client](/guide/introduction/baml_client)

VSCode ExtensionCursor ExtensionJetBrains IDEsZedClaude CodeOthers

[VSCode Extension](/guide/installation-editors/vs-code-extension)
[Cursor Extension](/guide/installation-editors/cursor-extension)
[JetBrains IDEs](/guide/installation-editors/jetbrains)
[Zed](/guide/installation-editors/zed)
[Claude Code](/guide/installation-editors/claude-code)
[Others](/guide/installation-editors/others)

PythonTypescriptGoRubyRustREST API (other languages)Elixir

[Python](/guide/installation-language/python)
[Typescript](/guide/installation-language/typescript)
[Go](/guide/installation-language/go)
[Ruby](/guide/installation-language/ruby)
[Rust](/guide/installation-language/rust)
[REST API (other languages)](/guide/installation-language/rest-api-other-languages)
[Elixir](/guide/installation-language/elixir)

React/Next.js


Environment VariablesTerminal LogsUpgrade BAML versionsDeploying

[Environment Variables](/guide/development/environment-variables)
[Terminal Logs](/guide/development/terminal-logs)
[Upgrade BAML versions](/guide/development/upgrade-baml-versions)

Prompting with BAMLSwitching LLMsTesting functionsStreamingMulti-Modal (Images / Audio)Error HandlingConfiguring TimeoutsConcurrent CallsAbortSignal / Cancellation

[Prompting with BAML](/guide/baml-basics/prompting-with-baml)
[Switching LLMs](/guide/baml-basics/switching-llms)
[Testing functions](/guide/baml-basics/testing-functions)
[Streaming](/guide/baml-basics/streaming)
[Multi-Modal (Images / Audio)](/guide/baml-basics/multi-modal)
[Error Handling](/guide/baml-basics/error-handling)
[Configuring Timeouts](/guide/baml-basics/timeouts)
[Concurrent Calls](/guide/baml-basics/concurrent-calls)
[AbortSignal / Cancellation](/guide/baml-basics/abort-signal)

Collector (track tokens)LLM Client RegistryDynamic TypesReusing Prompt SnippetsPrompt Caching / Message Role MetadataChecks and AssertsModular APIPrompt Optimization

[Collector (track tokens)](/guide/baml-advanced/collector-track-tokens)
[LLM Client Registry](/guide/baml-advanced/llm-client-registry)
[Dynamic Types](/guide/baml-advanced/dynamic-types)
[Reusing Prompt Snippets](/guide/baml-advanced/reusing-prompt-snippets)
[Prompt Caching / Message Role Metadata](/guide/baml-advanced/prompt-caching-message-role-metadata)
[Checks and Asserts](/guide/baml-advanced/checks-and-asserts)
[Modular API](/guide/baml-advanced/modular-api)
[Prompt Optimization](/guide/baml-advanced/prompt-optimization)

Observability


BAML vs LangchainBAML vs MarvinBAML vs Ai-SDKBAML vs OpenAI SDKBAML vs Pydantic

[BAML vs Langchain](/guide/comparisons/baml-vs-langchain)
[BAML vs Marvin](/guide/comparisons/baml-vs-marvin)
[BAML vs Ai-SDK](/guide/comparisons/baml-vs-ai-sdk)
[BAML vs OpenAI SDK](/guide/comparisons/baml-vs-open-ai-sdk)
[BAML vs Pydantic](/guide/comparisons/baml-vs-pydantic)

Contact

[Contact](/guide/contact)
[Help on Discord](https://discord.gg/BTNBeXGuaS)

Quick StartCommon Use CasesBasic LoggingManaging Collector StateUsing Multiple CollectorsUsage TrackingCached Token TrackingAPI ReferenceCollector ClassFunctionLog ClassTiming ClassStreamTiming Class (extends Timing)Usage ClassLLMCall ClassLLMStreamCall Class (extends LLMCall)HttpRequest ClassHttpResponse ClassHTTPBody ClassRelated TopicsBest Practices

[Quick Start](#quick-start)
[Common Use Cases](#common-use-cases)
[Basic Logging](#basic-logging)
[Managing Collector State](#managing-collector-state)
[Using Multiple Collectors](#using-multiple-collectors)
[Usage Tracking](#usage-tracking)
[Cached Token Tracking](#cached-token-tracking)
[API Reference](#api-reference)
[Collector Class](#collector-class)
[FunctionLog Class](#functionlog-class)
[Timing Class](#timing-class)
[StreamTiming Class (extends Timing)](#streamtiming-class-extends-timing)
[Usage Class](#usage-class)
[LLMCall Class](#llmcall-class)
[LLMStreamCall Class (extends LLMCall)](#llmstreamcall-class-extends-llmcall)
[HttpRequest Class](#httprequest-class)
[HttpResponse Class](#httpresponse-class)
[HTTPBody Class](#httpbody-class)
[Related Topics](#related-topics)
[Best Practices](#best-practices)

This feature was added in 0.79.0


TheCollectorallows you to inspect the internal state of BAML function calls, including raw HTTP requests, responses, usage metrics, and timing information, so you can always see the raw data, without any abstraction layers.

`Collector`

## Quick Start


```
1from baml_client import b2from baml_py import Collector34# Create a collector with optional name5collector = Collector(name="my-collector")67# Use it with a function call8result = b.ExtractResume("...", baml_options={"collector": collector})910# Access logging information11print(collector.last.usage)  # Print usage metrics12print(collector.last.raw_llm_response)  # Print final response as string13# since there may be retries, print the last http response received14print(collector.last.calls[-1].http_response)
```


## Common Use Cases


### Basic Logging


```
1from baml_client import b2from baml_py import Collector  # Import the Collector class34def run():5# Create a collector instance with an optional name6collector = Collector(name="my-collector")7# collector will be modified by the function to include all internal state8res = b.ExtractResume("...", baml_options={"collector": collector})9# This will print the return type of the function10print(res)1112# This is guaranteed to be set by the function13assert collector.last is not None1415# This will print the id of the last request16print(collector.last.id)1718# This will print the usage of the last request19# (This aggregates usage from all retries if there was usage emitted)20print(collector.last.usage)2122# This will print the raw response of the last request23print(collector.last.calls[-1].http_response)2425# This will print the raw text we used to run the parser.26print(collector.last.raw_llm_response)
```


### Managing Collector State


```
1from baml_client import b2from baml_py import Collector34def run():5collector = Collector(name="reusable-collector")6res = b.ExtractResume("...", baml_options={"collector": collector})78# Reuse the same collector9res = b.TestOpenAIGPT4oMini("Second call", baml_options={"collector": collector})
```


### Using Multiple Collectors


You can use multiple collectors to track different aspects of your application:


```
1from baml_client import b2from baml_py import Collector34def run():5# Create separate collectors for different parts of your application6collector_a = Collector(name="collector-a")7collector_b = Collector(name="collector-b")89# Use both collectors for the same function call10res = b.ExtractResume("...", baml_options={"collector": [collector_a, collector_b]})1112# Both collectors will have the same logs13assert collector_a.last.usage.input_tokens == collector_b.last.usage.input_tokens1415# Use only collector_a for another call16res2 = b.TestOpenAIGPT4oMini("another call", baml_options={"collector": collector_a})1718# collector_a will have 2 logs, collector_b will still have 119assert len(collector_a.logs) == 220assert len(collector_b.logs) == 1
```


### Usage Tracking


```
1from baml_client import b2from baml_py import Collector34def run():5collector_a = Collector(name="collector-a")6res = b.ExtractResume("...", baml_options={"collector": collector_a})78collector_b = Collector(name="collector-b")9res = b.ExtractResume("...", baml_options={"collector": collector_b})1011# The total usage of both logs is now available12print(collector_a.usage)13print(collector_b.usage)
```


### Cached Token Tracking


When using providers that support prompt caching (like Anthropic, OpenAI, Google, or Vertex), you can track cached input tokens via thecached_input_tokensfield:

`cached_input_tokens`

```
1from baml_client import b2from baml_py import Collector34async def run():5collector = Collector(name="cache-tracker")67# First call - content will be cached by the provider8res = await b.TestCaching(large_content, "Question 1", baml_options={"collector": collector})910# Second call with same content - should use cached tokens11res2 = await b.TestCaching(large_content, "Question 2", baml_options={"collector": collector})1213# Access cached token counts14first_log = collector.logs[0]15second_log = collector.logs[1]1617print(f"First call cached tokens: {first_log.usage.cached_input_tokens}")18print(f"Second call cached tokens: {second_log.usage.cached_input_tokens}")1920# Collector aggregates cached tokens across all calls21print(f"Total cached tokens: {collector.usage.cached_input_tokens}")2223# You can also access cached tokens per LLM call (including retries)24print(f"Per-call cached tokens: {first_log.calls[0].usage.cached_input_tokens}")
```


Cached token tracking is supported for Anthropic, OpenAI, Google AI, and Vertex AI providers. AWS Bedrock does not currently support cached token reporting and will returnnullfor this field.

`null`

## API Reference


### Collector Class


The Collector class provides properties to introspect the internal state of BAML function calls.

`logs`
`List[FunctionLog]`
`last`
`FunctionLog | null`
`usage`
`Usage`

The Collector class provides the following methods:

`id(id: string)`
`FunctionLog | null`
`clear()`
`void`

### FunctionLog Class


TheFunctionLogclass has the following properties:

`FunctionLog`
`id`
`string`
`function_name`
`string`
`log_type`
`"call" | "stream"`
`timing`
`Timing`
`usage`
`Usage`
`calls`
`(LLMCall | LLMStreamCall)[]`
`raw_llm_response`
`string | null`
`tags`
`Map[str, any]`

### Timing Class


TheTimingclass has the following properties:

`Timing`
`start_time_utc_ms`
`int`
`duration_ms`
`int | null`

#### StreamTiming Class (extends Timing)

`time_to_first_token_ms`
`int | null`

### Usage Class


TheUsageclass has the following properties:

`Usage`
`input_tokens`
`int | null`
`output_tokens`
`int | null`
`cached_input_tokens`
`int | null`
`cache_read_input_tokens`

Note: Usage may not include all provider-specific token types like “thinking_tokens” or “cache_creation_input_tokens”. For those, you may need to look at the raw HTTP response and build your own adapters.


### LLMCall Class


TheLLMCallclass has the following properties:

`LLMCall`
`client_name`
`str`
`provider`
`str`
`timing`
`Timing`
`http_request`
`HttpRequest`
`http_response`
`HttpResponse | null`
`usage`
`Usage | null`
`selected`
`bool`

### LLMStreamCall Class (extends LLMCall)


TheLLMStreamCallincludes the same properties asLLMCallplus the following:

`LLMStreamCall`
`LLMCall`
`timing`
`StreamTiming`
`chunks`
`string[]`

### HttpRequest Class


TheHttpRequestclass has the following properties:

`HttpRequest`
`url`
`str`
`method`
`str`
`headers`
`object`
`body`
`HTTPBody`

### HttpResponse Class


TheHttpResponseclass has the following properties:

`HttpResponse`
`status`
`int`
`headers`
`object`
`body`
`HTTPBody`

### HTTPBody Class


TheHTTPBodyclass has the following properties:

`HTTPBody`
`text()`
`string`
`json()`
`object`

## Related Topics


Using with_options- Learn how to configure logging globallyTypeBuilder- Build custom types for your BAML functionsClient Registry- Manage LLM clients and their configurations

[Using with_options](/ref/baml_client/with-options)
[TypeBuilder](/ref/baml_client/type-builder)
[Client Registry](/ref/baml_client/client-registry)

## Best Practices


Use a single collector instance when tracking related function calls in a chain.Consider using multiple collectors to track different parts of your application.Use function IDs when tracking specific calls in parallel operations.For streaming calls, be aware thathttp_responsewill be null, but you can still access usage information.

`http_response`