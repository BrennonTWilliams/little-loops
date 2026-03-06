---
url: https://docs.boundaryml.com/guide/boundary-cloud/observability/
scraped_at: 2026-03-06T01:00:24.657794
filepath: docs-docs-boundaryml-com/guide/boundary-cloud/observability/index.md
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

Getting StartedDashboardTracesTracing Custom EventsExampleAdding custom tagsTags on BAML calls and retrieving them with the CollectorTracing with ThreadPoolExecutor (Python)Expected BehaviorWhy This HappensBest Practices

[Getting Started](#getting-started)
[Dashboard](#dashboard)
[Traces](#traces)
[Tracing Custom Events](#tracing-custom-events)
[Example](#example)
[Adding custom tags](#adding-custom-tags)
[Tags on BAML calls and retrieving them with the Collector](#tags-on-baml-calls-and-retrieving-them-with-the-collector)
[Tracing with ThreadPoolExecutor (Python)](#tracing-with-threadpoolexecutor-python)
[Expected Behavior](#expected-behavior)
[Why This Happens](#why-this-happens)
[Best Practices](#best-practices)

Deprecation notice:Boundary Studio v1 atapp.boundaryml.comwill be deprecated byend of March 2026. Please migrate to the newBoundary Studioatstudio.boundaryml.com.

`app.boundaryml.com`
[Boundary Studio](https://studio.boundaryml.com/)
`studio.boundaryml.com`

## Getting Started


To enable observability with BAML, sign up for aBoundary Studioaccount.

[Boundary Studio](https://studio.boundaryml.com/)

Once you’ve signed up, create a new project and get your API key. Then add the following environment variable before running your application:


```
$export BOUNDARY_API_KEY=your_api_key_here
```


That’s it — your BAML function calls will now be traced automatically.


## Dashboard


The dashboard gives you a high-level overview of your LLM usage across all your BAML functions


## Traces


The traces view lets you inspect every LLM call your application makes.
Since Studio has access to the BAML definitions, it can represent your traces as functions, with typed parameters, inputs and outputs. Other observability platforms can only show you raw json blobs, which makes it hard to connect your data to your code.


## Tracing Custom Events


BAML allows you to trace any function with the@tracedecorator.
This will make the function’s input and output show up in the Boundary dashboard. This works for any python or Typescript function you define.


BAML LLM functions (or any other function declared in a .baml file) are already traced by default. Logs are only sent to the Dashboard if you setupBOUNDARY_API_KEYenvironment variable.

`BOUNDARY_API_KEY`

### Example


In the example below, we trace each of the two functionspre_process_textandfull_analysis:

`pre_process_text`
`full_analysis`

```
1from baml_client import baml2from baml_client.types import Book, AuthorInfo3from baml_client.tracing import trace45# You can also add a custom name with trace(name="my_custom_name")6# By default, we use the function's name.7@trace8def pre_process_text(text):9return text.replace("\n", " ")101112@trace13async def full_analysis(book: Book):14sentiment = await baml.ClassifySentiment(15pre_process_text(book.content)16)17book_analysis = await baml.AnalyzeBook(book)18return book_analysis192021@trace22async def test_book1():23content = """Before I could reply that he [Gatsby] was my neighbor...24"""25processed_content = pre_process_text(content)26return await full_analysis(27Book(28title="The Great Gatsby",29author=AuthorInfo(firstName="F. Scott", lastName="Fitzgerald"),30content=processed_content,31),32)
```


### Adding custom tags


The dashboard view allows you to see custom tags for each of the function calls. This is useful for adding metadata to your traces and allow you to query your generated logs more easily.


To add a custom tag, you can importset_tags(..)as below:


```
1from baml_client.tracing import set_tags, trace2import typing34@trace5async def pre_process_text(text):6set_tags(userId="1234")78# You can also create a dictionary and pass it in9tags_dict: typing.Dict[str, str] = {"userId": "1234"}10set_tags(**tags_dict) # "**" unpacks the dictionary11return text.replace("\n", " ")
```


### Tags on BAML calls and retrieving them with the Collector


You can also set tags directly on a BAML function call and then retrieve them from theCollector. Tags from a parent trace are inherited by the BAML function call and merged with any function-specific tags you pass.

`Collector`

```
1from baml_client import b2from baml_client.tracing import trace, set_tags3from baml_py import Collector45@trace6async def parent_fn(msg: str):7# Set tags on the parent trace (these propagate to child BAML calls)8set_tags(parent_id="p123", run="xyz")910collector = Collector(name="tags-collector")1112# You can also set per-call tags via baml_options13await b.TestOpenAIGPT4oMini(14msg,15baml_options={16"collector": collector,17"tags": {"call_id": "first", "version": "v1"},18},19)2021# Retrieve tags from the last function log22log = collector.last23assert log is not None24print(log.tags)  # {"parent_id": "p123", "run": "xyz", "call_id": "first", "version": "v1"}
```


Notes:


Tags fromset_tags/setTagson a parenttraceare merged into the BAML function’s tags.Per-call tags are provided viabaml_optionsin Python and the options object in TypeScript; in Go useb.WithTags(map[string]string).Retrieve tags from aFunctionLogusinglog.tags(Python/TypeScript) orlog.Tags()(Go).

`set_tags`
`setTags`
`trace`
`baml_options`
`b.WithTags(map[string]string)`
`FunctionLog`
`log.tags`
`log.Tags()`

### Tracing with ThreadPoolExecutor (Python)


When using Python’sconcurrent.futures.ThreadPoolExecutor, traced functions submitted to the thread pool will start withfresh, independent tracing contexts. This is by design and differs from async/await execution.

`concurrent.futures.ThreadPoolExecutor`

#### Expected Behavior


```
1from concurrent.futures import ThreadPoolExecutor2from baml_client.tracing import trace34@trace5def parent_function():6with ThreadPoolExecutor() as executor:7# Submit worker to thread pool8future = executor.submit(worker_function, "data")9result = future.result()1011@trace12def worker_function(data):13# This will be an independent root trace14# NOT a child of parent_function15process_data(data)1617@trace18def process_data(data):19# This WILL be a child of worker_function20# (same thread execution)21return data.upper()
```


In the trace hierarchy, you’ll see:


parent_functionas a root trace (depth 1)worker_functionas anindependent roottrace (depth 1) - not a childprocess_dataas a child ofworker_function(depth 2)

`parent_function`
`worker_function`
`process_data`
`worker_function`

#### Why This Happens


Python’scontextvars(used for tracing context) don’t automatically propagate to thread pool threads. Each worker thread starts with a fresh context to:

`contextvars`

Avoid complexity with context sharing across threadsPrevent potential race conditionsMaintain clear thread boundaries


#### Best Practices


Use async/await for related work: If you need to maintain parent-child relationships for parallel execution, useasyncioinstead of thread pools:

`asyncio`

```
1@trace2async def parent_async():3# These will maintain parent-child relationship4results = await asyncio.gather(5async_worker("task1"),6async_worker("task2")7)
```


Understand the trace hierarchy: When debugging, remember that thread pool workers appear as separate root traces in your observability dashboard.Tags don’t propagate: Tags set in the parent function won’t automatically appear in thread pool workers since they have independent contexts.


Understand the trace hierarchy: When debugging, remember that thread pool workers appear as separate root traces in your observability dashboard.


Tags don’t propagate: Tags set in the parent function won’t automatically appear in thread pool workers since they have independent contexts.
