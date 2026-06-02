"""SFT training format converters for ll-messages --sft-format output."""

from __future__ import annotations


def to_chatml(turns: list[tuple[str, str]]) -> dict:
    """Convert conversation turns to ChatML format.

    Args:
        turns: List of (role, content) pairs where role is "user" or "assistant"

    Returns:
        Dict with "messages" list of {"role": ..., "content": ...} objects
    """
    return {"messages": [{"role": role, "content": content} for role, content in turns]}


def to_alpaca(turns: list[tuple[str, str]]) -> dict:
    """Convert conversation turns to Alpaca format.

    Maps the first user turn to "instruction", all subsequent user turns to "input",
    and the last assistant turn to "output".

    Args:
        turns: List of (role, content) pairs where role is "user" or "assistant"

    Returns:
        Dict with "instruction", "input", and "output" keys
    """
    user_turns = [content for role, content in turns if role == "user"]
    assistant_turns = [content for role, content in turns if role == "assistant"]

    instruction = user_turns[0] if user_turns else ""
    input_text = "\n\n".join(user_turns[1:]) if len(user_turns) > 1 else ""
    output = assistant_turns[-1] if assistant_turns else ""

    return {"instruction": instruction, "input": input_text, "output": output}


def to_sharegpt(turns: list[tuple[str, str]]) -> dict:
    """Convert conversation turns to ShareGPT format.

    Maps "user" role to "human" and "assistant" role to "gpt".

    Args:
        turns: List of (role, content) pairs where role is "user" or "assistant"

    Returns:
        Dict with "conversations" list of {"from": ..., "value": ...} objects
    """
    role_map = {"user": "human", "assistant": "gpt"}
    return {
        "conversations": [
            {"from": role_map.get(role, role), "value": content} for role, content in turns
        ]
    }
