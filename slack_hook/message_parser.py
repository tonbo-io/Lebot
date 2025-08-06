"""Shared message parsing utilities for Slack assistant messages."""

from typing import Any, List, Dict, Union, Optional


def parse_assistant_message(
    text: str, attachments: Optional[List[Dict[str, Any]]] = None
) -> Union[List[Dict[str, Union[str, Dict[str, str]]]], tuple]:
    """Parse assistant message to recover thinking blocks and tool use blocks.

    Args:
        text: The message text content
        attachments: Optional Slack attachments containing metadata

    Returns either:
    - A list of content blocks for regular assistant messages
    - A tuple of (content_blocks, tool_results) where tool_results is a list of
      {"tool_use_id": "...", "result": "..."} dicts that should be added as a
      separate user message with tool_result blocks
    """
    # Ignore system warning messages
    if text.startswith(":warning:"):
        return []

    content_blocks = []
    tool_results = []  # Separate list for tool results

    # Extract metadata from attachments
    thinking_signatures = []
    tool_infos = []

    if attachments:
        for attachment in attachments:
            footer = attachment.get("footer", "")
            # Parse thinking metadata from footer: thinking:signature
            if footer.startswith("thinking:"):
                signature = footer[9:]  # Skip "thinking:"
                thinking_signatures.append(signature)
            # Parse tool metadata from footer: Tool ID: id
            elif footer.startswith("Tool ID: "):
                tool_id = footer[9:]  # Skip "Tool ID: "
                # Get tool name from title
                title = attachment.get("title", "")
                if title.startswith("Tool: "):
                    tool_name = title[6:]  # Skip "Tool: "
                    tool_infos.append({"name": tool_name, "id": tool_id, "text": attachment.get("text", "")})

    # Process text content
    lines = text.split("\n")
    current_block = []
    in_thinking = False
    thinking_index = 0
    tool_index = 0

    for line in lines:
        # Check if this is quoted thinking content
        if line.startswith(">"):
            if not in_thinking:
                # Start of thinking block - save any accumulated text first
                if current_block:
                    text_content = "\n".join(current_block).strip()
                    if text_content:
                        content_blocks.append({"type": "text", "text": text_content})
                    current_block = []
                in_thinking = True
            # Remove the '> ' prefix
            current_block.append(line[2:] if len(line) > 2 else "")
        elif line.startswith("*Tool:") and "*" in line[6:]:
            # Tool output line format: *Tool: tool_name*
            if current_block:
                # Save any accumulated content
                if in_thinking:
                    # Get signature from ordered list
                    thinking_content = {
                        "type": "thinking",
                        "thinking": "\n".join(current_block),
                    }
                    if thinking_index < len(thinking_signatures):
                        thinking_content["signature"] = thinking_signatures[thinking_index]
                    content_blocks.append(thinking_content)
                    thinking_index += 1
                else:
                    text_content = "\n".join(current_block).strip()
                    if text_content:
                        content_blocks.append({"type": "text", "text": text_content})
                current_block = []
                in_thinking = False

            # Get tool info from ordered list
            if tool_index < len(tool_infos):
                tool_info = tool_infos[tool_index]
                tool_index += 1
                # Add tool use block
                content_blocks.append(
                    {
                        "type": "tool_use",
                        "id": tool_info["id"],
                        "name": tool_info["name"],
                        "input": {},  # We don't store the original input
                    }
                )
                # Store tool result separately - it needs to be in a user message
                if tool_info.get("text"):
                    tool_results.append({"tool_use_id": tool_info["id"], "result": tool_info["text"]})
        else:
            # Regular text line
            if in_thinking:
                # End of thinking block
                thinking_content = {
                    "type": "thinking",
                    "thinking": "\n".join(current_block),
                }
                if thinking_index < len(thinking_signatures):
                    thinking_content["signature"] = thinking_signatures[thinking_index]
                content_blocks.append(thinking_content)
                thinking_index += 1
                current_block = []
                in_thinking = False
            current_block.append(line)

    # Save any remaining content
    if current_block:
        if in_thinking:
            thinking_content = {
                "type": "thinking",
                "thinking": "\n".join(current_block),
            }
            if thinking_index < len(thinking_signatures):
                thinking_content["signature"] = thinking_signatures[thinking_index]
            content_blocks.append(thinking_content)
        else:
            text_content = "\n".join(current_block).strip()
            if text_content:
                content_blocks.append({"type": "text", "text": text_content})

    # Reorganize content blocks to ensure thinking blocks come first
    # This is required when thinking mode is enabled
    thinking_blocks = [block for block in content_blocks if block["type"] == "thinking"]
    text_blocks = [block for block in content_blocks if block["type"] == "text"]
    tool_use_blocks = [block for block in content_blocks if block["type"] == "tool_use"]

    # Reconstruct with thinking blocks first, then text, then tool uses
    ordered_blocks = thinking_blocks + text_blocks + tool_use_blocks

    # Return tuple if we have tool results, otherwise just the content blocks
    if tool_results:
        return ordered_blocks, tool_results
    return ordered_blocks
