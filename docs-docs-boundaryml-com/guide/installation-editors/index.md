---
url: https://docs.boundaryml.com/guide/installation-editors/
scraped_at: 2026-03-06T01:00:31.197935
filepath: docs-docs-boundaryml-com/guide/installation-editors/index.md
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

Opening BAML PlaygroundSetting Env VariablesRunning TestsReviewing TestsSwitching FunctionsSwitching Test Cases

[Opening BAML Playground](#opening-baml-playground)
[Setting Env Variables](#setting-env-variables)
[Running Tests](#running-tests)
[Reviewing Tests](#reviewing-tests)
[Switching Functions](#switching-functions)
[Switching Test Cases](#switching-test-cases)

We provide a BAML VSCode extension:https://marketplace.visualstudio.com/items?itemName=Boundary.baml-extension

[https://marketplace.visualstudio.com/items?itemName=Boundary.baml-extension](https://marketplace.visualstudio.com/items?itemName=Boundary.baml-extension)
`baml_client`

## Opening BAML Playground


Once you open a.bamlfile, in VSCode, you should see a small button over every BAML function:Open Playground.

`.baml`
`Open Playground`

Or typeBAML Playgroundin the VSCode Command Bar (CMD + Shift + PorCTRL + Shift + P) to open the playground.

`BAML Playground`
`CMD + Shift + P`
`CTRL + Shift + P`

## Setting Env Variables


Click on theSettingsbutton in top right of the playground and set the environment variables.

`Settings`

It should have an indicator if any unset variables are there.


The playground should persist the environment variables between closing and opening VSCode.


You can set environment variables lazily. If anything is unset you’ll get an error when you run the function.


Environment Variables are stored in VSCode’s local storage! We don’t save any additional data to disk, or send them across the network.


## Running Tests


Click onRun tests belowin the right pane of the playground to run all tests.

`Run tests below`

Press the▶️button next to an individual test case to run that just that test case.

`▶️`

## Reviewing Tests


Click the numbers on the left to switch between test results.Press the▶️button next to the drop-down to re-run your tests.


Click the numbers on the left to switch between test results.


Press the▶️button next to the drop-down to re-run your tests.

`▶️`

Toggle the🚀to enable running the tests in parallel.

`🚀`

## Switching Functions


The playground will automatically switch to the function you’re currently editing.


To manually change it, click on the current function name in the playground (next to the dropdown) and search for your desired function.


## Switching Test Cases


You can switch between test cases by selecting it in the results pane or the test selection pane on the right.


You can customize what you see in the Table View, or switch to the Detailed view:
