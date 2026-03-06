---
url: https://docs.boundaryml.com/examples/prompt-engineering/classification.mdx
scraped_at: 2026-03-06T01:00:19.073225
filepath: docs-docs-boundaryml-com/examples/prompt-engineering/classificationmdx.md
---


***

## title: Classification

# Building a Spam Classifier with BAML

In this tutorial, you'll learn how to create a simple but effective spam classifier using BAML and OpenAI's GPT models. By the end, you'll have a working classifier that can distinguish between spam and legitimate messages.

## Prerequisites

* Basic understanding of BAML syntax
* Access to OpenAI API (you'll need an API key)

## Step 1: Define the Classification Schema

First, let's define what our classification output should look like. Create a new file called `spam_classifier.baml` and add the following schema:

```baml
enum MessageType {
  SPAM
  NOT_SPAM
}
```

This schema defines a simple classification with two possible labels: `SPAM` or `NOT_SPAM`.

## Step 2: Create the Classification Function

Next, we'll create a function that uses GPT-4 to classify text. Add this to your `spam_classifier.baml` file:

```baml
function ClassifyText(input: string) -> MessageType {
  client "openai/gpt-5-mini"
  prompt #"
    Classify the message. 

    {{ ctx.output_format }}

    {{ _.role("user") }} 
    
    {{ input }}
  "#
}
```

Let's break down what this function does:

* Takes an input as a string
* Uses the `gpt-5-mini` model
* Provides clear guidelines for classification in the prompt
* Returns a MessageType

## Step 3: Test the Classifier

To ensure our classifier works correctly, let's add some test cases:

```baml
test BasicSpamTest {
  functions [ClassifyText]
  args {
    input "Buy cheap watches now! Limited time offer!!!"
  }
}

test NonSpamTest {
  functions [ClassifyText]
  args {
    input "Hey Sarah, can we meet at 3 PM tomorrow to discuss the project?"
  }
}
```

This is what it looks like in the BAML Playground:## Try it yourself in the Interactive Playground!

Now that you have your classifier set up, try it with your own examples. Here are some messages you can test:

1. "Meeting at 2 PM in the conference room"
2. "CONGRATULATIONS! You've won \$1,000,000!!!"
3. "Can you review the document I sent yesterday?"
4. "Make money fast! Work from home!!!"
