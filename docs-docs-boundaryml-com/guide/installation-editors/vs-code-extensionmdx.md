---
url: https://docs.boundaryml.com/guide/installation-editors/vs-code-extension.mdx
scraped_at: 2026-03-06T01:00:30.815640
filepath: docs-docs-boundaryml-com/guide/installation-editors/vs-code-extensionmdx.md
---


We provide a BAML VSCode extension:     [https://marketplace.visualstudio.com/items?itemName=Boundary.baml-extension](https://marketplace.visualstudio.com/items?itemName=Boundary.baml-extension)

| Feature                                                   | Supported |
| --------------------------------------------------------- | --------- |
| Syntax highlighting for BAML files                        | ✅         |
| Code snippets for BAML                                    | ✅         |
| LLM playground for testing BAML functions                 | ✅         |
| Jump to definition for BAML files                         | ✅         |
| Jump to definition between Python/TS files and BAML files | ✅         |
| Auto generate `baml_client` on save                       | ✅         |
| BAML formatter                                            | ❌         |

## Opening BAML Playground

Once you open a `.baml` file, in VSCode, you should see a small button over every BAML function: `Open Playground`.Or type `BAML Playground` in the VSCode Command Bar (`CMD + Shift + P` or `CTRL + Shift + P`) to open the playground.## Setting Env Variables

Click on the `Settings` button in top right of the playground and set the environment variables.

It should have an indicator if any unset variables are there.The playground should persist the environment variables between closing and opening VSCode.You can set environment variables lazily. If anything is unset you'll get an error when you run the function.Environment Variables are stored in VSCode's local storage! We don't save any additional data to disk, or send them across the network.## Running Tests

* Click on `Run tests below` in the right pane of the playground to run all tests.* Press the `▶️` button next to an individual test case to run that just that test case.

## Reviewing Tests

* Click the numbers on the left to switch between test results.

* Press the `▶️` button next to the drop-down to re-run your tests.* Toggle the `🚀` to enable running the tests in parallel.## Switching Functions

The playground will automatically switch to the function you're currently editing.

To manually change it, click on the current function name in the playground (next to the dropdown) and search for your desired function.

## Switching Test Cases

You can switch between test cases by selecting it in the results pane or the test selection pane on the right.You can customize what you see in the Table View, or switch to the Detailed view:
