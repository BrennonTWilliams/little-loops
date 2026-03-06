---
url: https://docs.boundaryml.com/guide/installation-language/
scraped_at: 2026-03-06T01:00:31.763363
filepath: docs-docs-boundaryml-com/guide/installation-language/index.md
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

BAML with Jupyter Notebooks

[BAML with Jupyter Notebooks](#baml-with-jupyter-notebooks)
[https://github.com/BoundaryML/baml-examples/tree/main/python-fastapi-starter](https://github.com/BoundaryML/baml-examples/tree/main/python-fastapi-starter)

To set up BAML with Python do the following:

[1](/guide/installation-language/python#install-baml-vscodecursor-extension)

### Install BAML VSCode/Cursor Extension


https://marketplace.visualstudio.com/items?itemName=boundary.baml-extension

[https://marketplace.visualstudio.com/items?itemName=boundary.baml-extension](https://marketplace.visualstudio.com/items?itemName=boundary.baml-extension)

syntax highlightingtesting playgroundprompt previews


In your VSCode User Settings, highly recommend adding this to get better autocomplete for python in general, not just BAML.


```
1{2"python.analysis.typeCheckingMode": "basic"3}
```

[2](/guide/installation-language/python#install-baml)

### Install BAML


```
$pip install baml-py
```

[3](/guide/installation-language/python#add-baml-to-your-existing-project)

### Add BAML to your existing project


This will give you some starter BAML code in abaml_srcdirectory.

`baml_src`

```
$baml-cli init
```

[4](/guide/installation-language/python#generate-the-baml_client-python-module-from-baml-files)

### Generate thebaml_clientpython module from.bamlfiles

`baml_client`
`.baml`

One of the files in yourbaml_srcdirectory will have agenerator block. The next commmand will auto-generate thebaml_clientdirectory, which will have auto-generated python code to call your BAML functions.

`baml_src`
[generator block](/ref/baml/generator)
`baml_client`

Any types defined in .baml files will be converted into Pydantic models in thebaml_clientdirectory.

`baml_client`

```
$baml-cli generate
```


SeeWhat is baml_clientto learn more about how this works.

[What is baml_client](/guide/introduction/baml_client)

If you set up theVSCode extension, it will automatically runbaml-cli generateon saving a BAML file.

[VSCode extension](https://marketplace.visualstudio.com/items?itemName=Boundary.baml-extension)
`baml-cli generate`
[5](/guide/installation-language/python#use-a-baml-function-in-python)

### Use a BAML function in Python!

`baml_client`

```
1from baml_client.sync_client import b2from baml_client.types import Resume34def example(raw_resume: str) -> Resume:5# BAML's internal parser guarantees ExtractResume6# to be always return a Resume type7response = b.ExtractResume(raw_resume)8return response910def example_stream(raw_resume: str) -> Resume:11stream = b.stream.ExtractResume(raw_resume)12for msg in stream:13print(msg) # This will be a PartialResume type1415# This will be a Resume type16final = stream.get_final_response()1718return final
```


## BAML with Jupyter Notebooks


You can use the baml_client in a Jupyter notebook.


One of the common problems is making sure your code changes are picked up by the notebook without having to restart the whole kernel (and re-run all the cells)


To make sure your changes in .baml files are reflected in your notebook you must do these steps:

[1](/guide/installation-language/python#setup-the-autoreload-extension)

### Setup the autoreload extension


```
1%load_ext autoreload2%autoreload 2
```


This will make sure to reload imports, such as baml_client’s “b” object before every cell runs.

[2](/guide/installation-language/python#import-baml_client-module-in-your-notebook)

### Import baml_client module in your notebook


Note it’s different from how we import in python.


```
1# Assuming your baml_client is inside a dir called app/2import app.baml_client as client # you can name this "llm" or "baml" or whatever you want
```


Usually we import things asfrom baml_client import b, and we can call our functions usingb, but the%autoreloadnotebook extension does not work well withfrom...importstatements.

`from baml_client import b`
`b`
`%autoreload`
`from...import`
[3](/guide/installation-language/python#call-baml-functions-using-the-module-name-as-a-prefix)

### Call BAML functions using the module name as a prefix


```
1raw_resume = "Here's some resume text"2client.b.ExtractResume(raw_resume)
```


Now your changes in .baml files are reflected in your notebook automatically, without needing to restart the Jupyter kernel.


If you want to keep using thefrom baml_client import bstyle, you’ll just need to re-import it everytime you regenerate the baml_client.

`from baml_client import b`

Pylance will complain about any schema changes you make in .baml files. You can ignore these errors. If you want it to pick up your new types, you’ll need to restart the kernel.
This auto-reload approach works best if you’re only making changes to the prompts.


You’re all set! Continue on to theDeployment Guidesfor your language to learn how to deploy your BAML code or check out theInteractive Examplesto see more examples.

[Deployment Guides](/guide/development/deploying/docker)
[Interactive Examples](https://baml-examples.vercel.app/)