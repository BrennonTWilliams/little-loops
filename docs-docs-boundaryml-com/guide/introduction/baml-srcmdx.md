---
url: https://docs.boundaryml.com/guide/introduction/baml_src.mdx
scraped_at: 2026-03-06T01:00:33.091919
filepath: docs-docs-boundaryml-com/guide/introduction/baml-srcmdx.md
---


***

## title: What is baml\_src?

**baml\_src** is where you keep all your BAML files, and where all the prompt-related code lives. It must be named `baml_src` for our tooling to pick it up, but it can live wherever you want.

It helps keep your project organized, and makes it easy to separate prompt engineering from the rest of your code.Some things to note:

1. All declarations within this directory are accessible across all files contained in the `baml_src` folder.
2. You can have multiple files, and even nest subdirectories.

You don't need to worry about including this directory when deploying your code. See: [Deploying](/guide/development/deploying/aws)
