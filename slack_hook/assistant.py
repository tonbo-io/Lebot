import logging
from typing import Any, List, Dict, Union, Optional
from slack_bolt import Assistant, BoltContext, Say, SetStatus, Ack
from slack_sdk import WebClient

from .claude import Claude
from tools import ToolRegistry

# Initialize LLM lazily to avoid import-time errors
llm = Claude()

# Thread model preferences - stores model choice per thread
# Format: {channel_id: {thread_ts: "model_name"}}
thread_models: Dict[str, Dict[str, str]] = {}


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
                    if thinking_index < len(thinking_signatures):
                        content_blocks.append(
                            {
                                "type": "thinking",
                                "thinking": "\n".join(current_block),
                                "signature": thinking_signatures[thinking_index],
                            }
                        )
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
                if thinking_index < len(thinking_signatures):
                    content_blocks.append(
                        {
                            "type": "thinking",
                            "thinking": "\n".join(current_block),
                            "signature": thinking_signatures[thinking_index],
                        }
                    )
                thinking_index += 1
                current_block = []
                in_thinking = False
            current_block.append(line)

    # Save any remaining content
    if current_block:
        if in_thinking:
            if thinking_index < len(thinking_signatures):
                content_blocks.append(
                    {
                        "type": "thinking",
                        "thinking": "\n".join(current_block),
                        "signature": thinking_signatures[thinking_index],
                    }
                )
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


def create_assistant(tool_registry: ToolRegistry) -> Assistant:
    """Factory function to create an Assistant with the given tool registry.

    Args:
        tool_registry: The ToolRegistry instance to use for tool execution

    Returns:
        A configured Assistant instance
    """
    # Refer to https://tools.slack.dev/bolt-python/concepts/assistant/ for more details
    assistant = Assistant()

    # This listener is invoked when a human user opened an assistant thread
    @assistant.thread_started
    def start_assistant_thread(
        say: Say,
        logger: logging.Logger,
        context: BoltContext,
        client: WebClient,
    ):

        try:
            # Send greeting with model selection buttons
            say(
                blocks=[
                    {"type": "section", "text": {"type": "mrkdwn", "text": "How can I help you?"}},
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": ":zap: Beast Mode (Opus 4)", "emoji": True},
                                "value": "beast_mode",
                                "action_id": "enable_beast_mode",
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": ":white_check_mark: Normal Mode (Sonnet 4)",
                                    "emoji": True,
                                },
                                "value": "normal_mode",
                                "action_id": "enable_normal_mode",
                                "style": "primary",  # Highlight normal mode as active
                            },
                        ],
                    },
                    {
                        "type": "context",
                        "elements": [{"type": "mrkdwn", "text": "Currently using: *Normal Mode* (Claude Sonnet 4)"}],
                    },
                ],
                text="How can I help you?",
            )
        except Exception as e:
            logger.exception(f"Failed to handle an assistant_thread_started event: {e}", e)
            say(f":warning: Something went wrong! ({e})")

    # This listener is invoked when the human user sends a reply in the assistant thread
    @assistant.user_message
    def respond_in_assistant_thread(
        logger: logging.Logger,
        context: BoltContext,
        set_status: SetStatus,
        client: WebClient,
        say: Say,
    ):
        if context.channel_id is None:
            logger.error("Channel ID is None. Cannot fetch thread replies.")
            say(":warning: Something went wrong! (Channel ID is missing)")
            return

        if context.thread_ts is None:
            logger.error("Thread timestamp (thread_ts) is None. Cannot fetch thread replies.")
            say(":warning: Something went wrong! (Thread timestamp is missing)")
            return

        # Fetch all messages with pagination support
        messages_in_thread: List[Dict[str, Any]] = []
        all_messages: List[Dict[str, Any]] = []
        cursor = None

        # Keep fetching until we have all messages
        while True:
            params = {
                "channel": context.channel_id,
                "ts": context.thread_ts,
                "limit": 10,  # Max allowed per request
            }

            # Add cursor for pagination if we have one
            if cursor:
                params["cursor"] = cursor

            replies = client.conversations_replies(**params)
            messages = replies.get("messages", [])

            if messages:
                all_messages.extend(messages)

            # Check if there are more messages to fetch
            response_metadata = replies.get("response_metadata", {})
            cursor = response_metadata.get("next_cursor")

            # Break if no more messages
            if not cursor:
                break

        # Sort messages by timestamp to ensure chronological order
        # Slack's pagination may return pages in different order
        all_messages.sort(key=lambda m: float(m.get("ts", 0)))
        messages = all_messages

        if not messages:
            logger.error("No messages found in thread")
            say(":warning: No messages found in this thread")
            return

        for message in messages:
            if message.get("bot_id") is None:
                # User message - keep as is
                messages_in_thread.append({"role": "user", "content": message["text"]})
            else:
                # Assistant message - parse to recover thinking blocks
                # Get attachments if available
                attachments = message.get("attachments", [])
                parse_result = parse_assistant_message(message["text"], attachments)

                # Handle the two possible return types
                if isinstance(parse_result, tuple):
                    # We have tool uses and results
                    content_blocks, tool_results = parse_result
                    # Only add assistant message if it has content
                    if content_blocks:
                        messages_in_thread.append({"role": "assistant", "content": content_blocks})

                    # Add tool results as a user message if we have them
                    if tool_results:
                        tool_result_content = []
                        for tool_result in tool_results:
                            tool_result_content.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": tool_result["tool_use_id"],
                                    "content": tool_result["result"],
                                }
                            )
                        messages_in_thread.append({"role": "user", "content": tool_result_content})
                elif parse_result:  # Only add if not empty
                    # Regular assistant message without tool uses
                    messages_in_thread.append({"role": "assistant", "content": parse_result})

        try:
            # Check if beast mode is enabled for this thread
            if context.channel_id in thread_models and context.thread_ts in thread_models[context.channel_id]:
                model_name = thread_models[context.channel_id][context.thread_ts]
                llm.message(
                    set_status=set_status,
                    messages_in_thread=messages_in_thread,
                    say=say,
                    tool_registry=tool_registry,
                    model=model_name,
                )
            else:
                # Use default model
                llm.message(
                    set_status=set_status,
                    messages_in_thread=messages_in_thread,
                    say=say,
                    tool_registry=tool_registry,
                )
        except Exception as e:
            logger.exception(f"Failed to handle a user message event: {e}")
            say(f":warning: Something went wrong! ({e})")

    return assistant


# Button action handler for beast mode
def handle_beast_mode_button(ack: Ack, body: Dict[str, Any], client: WebClient, logger: logging.Logger):
    """Handle the beast mode button click to enable Claude Opus 4 for a thread."""
    ack()  # Acknowledge the action immediately

    # Extract necessary information from the body
    channel_id = body.get("channel", {}).get("id")
    thread_ts = body.get("message", {}).get("thread_ts") or body.get("message", {}).get("ts")
    user_id = body.get("user", {}).get("id")
    message_ts = body.get("message", {}).get("ts")

    # Validate required fields
    if not channel_id or not user_id or not thread_ts:
        logger.error(f"Missing required fields: channel_id={channel_id}, user_id={user_id}, thread_ts={thread_ts}")
        return

    # Store the model preference for this thread
    if channel_id not in thread_models:
        thread_models[channel_id] = {}

    thread_models[channel_id][thread_ts] = "claude-opus-4-20250514"

    # Update the original message with new status
    try:
        client.chat_update(
            channel=channel_id,
            ts=message_ts,
            blocks=[
                {"type": "section", "text": {"type": "mrkdwn", "text": "How can I help you?"}},
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": ":zap: Beast Mode (Opus 4)", "emoji": True},
                            "value": "beast_mode",
                            "action_id": "enable_beast_mode",
                            "style": "danger",  # Change to danger to show it's active
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": ":white_check_mark: Normal Mode (Sonnet 4)",
                                "emoji": True,
                            },
                            "value": "normal_mode",
                            "action_id": "enable_normal_mode",
                        },
                    ],
                },
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": "Currently using: *:zap: Beast Mode* (Claude Opus 4)"}],
                },
            ],
            text="How can I help you?",
        )

        # Post a confirmation message in the thread
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=":zap: *Beast Mode Activated!* :zap:\nThis thread is now using Claude Opus 4 for maximum intelligence and capability.",
        )
    except Exception as e:
        logger.error(f"Failed to update message: {e}")

    logger.info(f"Beast mode enabled for thread {thread_ts} in channel {channel_id} by user {user_id}")


# Button action handler for normal mode
def handle_normal_mode_button(ack: Ack, body: Dict[str, Any], client: WebClient, logger: logging.Logger):
    """Handle the normal mode button click to switch back to Claude Sonnet 4."""
    ack()  # Acknowledge the action immediately

    # Extract necessary information from the body
    channel_id = body.get("channel", {}).get("id")
    thread_ts = body.get("message", {}).get("thread_ts") or body.get("message", {}).get("ts")
    user_id = body.get("user", {}).get("id")
    message_ts = body.get("message", {}).get("ts")

    # Validate required fields
    if not channel_id or not user_id or not thread_ts:
        logger.error(f"Missing required fields: channel_id={channel_id}, user_id={user_id}, thread_ts={thread_ts}")
        return

    # Remove the model preference for this thread (revert to default)
    if channel_id in thread_models and thread_ts in thread_models[channel_id]:
        del thread_models[channel_id][thread_ts]
        message = ":white_check_mark: Switched back to normal mode (Claude Sonnet 4)."
    else:
        message = ":information_source: This thread is already using normal mode (Claude Sonnet 4)."

    # Update the original message with new status
    try:
        client.chat_update(
            channel=channel_id,
            ts=message_ts,
            blocks=[
                {"type": "section", "text": {"type": "mrkdwn", "text": "How can I help you?"}},
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": ":zap: Beast Mode (Opus 4)", "emoji": True},
                            "value": "beast_mode",
                            "action_id": "enable_beast_mode",
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": ":white_check_mark: Normal Mode (Sonnet 4)",
                                "emoji": True,
                            },
                            "value": "normal_mode",
                            "action_id": "enable_normal_mode",
                            "style": "primary",  # Change to primary to show it's active
                        },
                    ],
                },
                {
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": "Currently using: *Normal Mode* (Claude Sonnet 4)"}],
                },
            ],
            text="How can I help you?",
        )

        # Post a confirmation message in the thread
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=message,
        )
    except Exception as e:
        logger.error(f"Failed to update message: {e}")

    logger.info(f"Normal mode restored for thread {thread_ts} in channel {channel_id} by user {user_id}")
