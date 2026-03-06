---
url: https://docs.boundaryml.com/guide/
scraped_at: 2026-03-06T01:00:20.148455
filepath: docs-docs-boundaryml-com/guide/index.md
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

Demo videoExamplesHigh-level Developer Flow

[Demo video](#demo-video)
[Examples](#examples)
[High-level Developer Flow](#high-level-developer-flow)

The best way to understand BAML and its developer experience is to see it live in a demo (see below).


### Demo video


Here we write a BAML function definition, and then call it from a Python script.


### Examples


Interactive NextJS app with streamingStarter boilerplates for Python, Typescript, Ruby, etc.

[Interactive NextJS app with streaming](https://baml-examples.vercel.app/examples/stream-object)
[Starter boilerplates for Python, Typescript, Ruby, etc.](https://github.com/boundaryml/baml-examples)

### High-level Developer Flow

[1](/guide/introduction/what-is-baml#write-a-baml-function-definition)

### Write a BAML function definition


```
1class WeatherAPI {2city string @description("the user's city")3timeOfDay string @description("As an ISO8601 timestamp")4}56function UseTool(user_message: string) -> WeatherAPI {7client "openai-responses/gpt-5-mini"8prompt #"9Extract.... {# we will explain the rest in the guides #}10"#11}
```


Here you can run tests in the VSCode Playground.

[2](/guide/introduction/what-is-baml#generate-baml_client-from-those-baml-files)

### Generatebaml_clientfrom those .baml files.

`baml_client`

This is auto-generated code with all boilerplate to call the LLM endpoint, parse the output, fix broken JSON, and handle errors.

[3](/guide/introduction/what-is-baml#call-your-function-in-any-language)

### Call your function in any language


with type-safety, autocomplete, retry-logic, robust JSON parsing, etc..


```
1import asyncio2from baml_client import b3from baml_client.types import WeatherAPI45def main():6weather_info = b.UseTool("What's the weather like in San Francisco?")7print(weather_info)8assert isinstance(weather_info, WeatherAPI)9print(f"City: {weather_info.city}")10print(f"Time of Day: {weather_info.timeOfDay}")1112if __name__ == '__main__':13main()
```


Continue on to theInstallation Guidesfor your language to setup BAML in a few minutes!

[Installation Guides](/guide/installation-language)

You don’t need to migrate 100% of your LLM code to BAML in one go! It works along-side any existing LLM framework.
