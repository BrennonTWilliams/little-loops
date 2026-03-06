---
url: https://docs.boundaryml.com/guide/development/deploying/aws.mdx
scraped_at: 2026-03-06T01:00:26.657008
filepath: docs-docs-boundaryml-com/guide/development/deploying/awsmdx.md
---


***

## title: AWS

You can use [SST](https://sst.dev/) to define the Lambda configuration and deploy it.

The example below builds the BAML x86\_64 rust binaries into a Lambda layer and uses the layer in the Lambda function.

[Example Node + SST Project](https://github.com/BoundaryML/baml-examples/tree/main/node-aws-lambda-sst)

Let us know if you want to deploy a python BAML project on AWS. Our example project is coming soon.

### Current limitations

The BAML binaries only support the NodeJS 20.x runtime (or a runtime using Amazon Linux 2023). Let us know if you need a different runtime version.
