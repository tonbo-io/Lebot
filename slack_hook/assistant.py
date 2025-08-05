"""Async version of assistant handlers with coroutine-based conversation management."""

import logging
from typing import Any, Dict

from slack_bolt import BoltContext
from slack_bolt.middleware.assistant.async_assistant import AsyncAssistant
from slack_bolt.context.ack.async_ack import AsyncAck
from slack_bolt.context.say.async_say import AsyncSay
from slack_bolt.context.set_status.async_set_status import AsyncSetStatus
from slack_sdk.web.async_client import AsyncWebClient

from .conversation_manager import ConversationManager, ThreadContext
from .claude import AsyncClaude
from tools import ToolRegistry


def create_assistant(
    tool_registry: ToolRegistry, conversation_manager: ConversationManager, llm: AsyncClaude
) -> AsyncAssistant:
    """Factory function to create an async Assistant with conversation management.

    Args:
        tool_registry: The ToolRegistry instance to use for tool execution
        conversation_manager: The ConversationManager instance
        llm: The LLM instance (Claude)

    Returns:
        A configured Assistant instance
    """
    # Create assistant
    assistant = AsyncAssistant()

    @assistant.thread_started
    async def start_assistant_thread(
        say: AsyncSay,
        logger: logging.Logger,
    ):
        """Handle new assistant thread creation."""
        try:
            # Send greeting with model selection buttons
            await say(
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
                                "style": "primary",
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
            logger.exception(f"Failed to handle assistant_thread_started event: {e}")
            await say(f":warning: Something went wrong! ({e})")

    @assistant.user_message
    async def respond_in_assistant_thread(
        logger: logging.Logger,
        context: BoltContext,
        set_status: AsyncSetStatus,
        client: AsyncWebClient,
        say: AsyncSay,
    ):
        """Handle user messages in assistant thread."""
        if not context.channel_id:
            logger.error("Channel ID is None")
            await say(":warning: Something went wrong! (Channel ID is missing)")
            return

        if not context.thread_ts:
            logger.error("Thread timestamp is None")
            await say(":warning: Something went wrong! (Thread timestamp is missing)")
            return

        try:
            # Create thread context
            thread_context = ThreadContext(
                context=context,
                client=client,  # type: ignore
                say=say,  # type: ignore
                set_status=set_status,
                logger=logger,
            )

            # Process message through conversation manager
            await conversation_manager.process_thread_message(thread_context, tool_registry, llm)

        except Exception as e:
            logger.exception(f"Failed to handle user message: {e}")
            await say(f":warning: Something went wrong! ({e})")

    return assistant


def create_beast_mode_handler(conversation_manager: ConversationManager):
    """Create beast mode button handler with conversation manager."""

    async def handle_beast_mode_button(ack: AsyncAck, body: Dict[str, Any], client: AsyncWebClient, logger: logging.Logger):
        """Handle beast mode button click."""
        await ack()

        channel_id = body.get("channel", {}).get("id")
        thread_ts = body.get("message", {}).get("thread_ts") or body.get("message", {}).get("ts")
        user_id = body.get("user", {}).get("id")
        message_ts = body.get("message", {}).get("ts")

        if not channel_id or not user_id or not thread_ts:
            logger.error(f"Missing required fields: channel={channel_id}, user={user_id}, thread={thread_ts}")
            return

        # Set model preference in conversation manager
        conversation_manager.set_model_preference(channel_id, thread_ts, "claude-opus-4-20250514")

        # Update the message
        try:
            await client.chat_update(
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
                                "style": "danger",
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

            await client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=":zap: *Beast Mode Activated!* :zap:\nUsing Claude Opus 4 for maximum intelligence.",
            )
        except Exception as e:
            logger.error(f"Failed to update message: {e}")

    return handle_beast_mode_button


def create_normal_mode_handler(conversation_manager: ConversationManager):
    """Create normal mode button handler with conversation manager."""

    async def handle_normal_mode_button(ack: AsyncAck, body: Dict[str, Any], client: AsyncWebClient, logger: logging.Logger):
        """Handle normal mode button click."""
        await ack()

        channel_id = body.get("channel", {}).get("id")
        thread_ts = body.get("message", {}).get("thread_ts") or body.get("message", {}).get("ts")
        user_id = body.get("user", {}).get("id")
        message_ts = body.get("message", {}).get("ts")

        if not channel_id or not user_id or not thread_ts:
            logger.error(f"Missing required fields: channel={channel_id}, user={user_id}, thread={thread_ts}")
            return

        # Set model preference in conversation manager
        conversation_manager.set_model_preference(channel_id, thread_ts, "claude-sonnet-4-20250514")

        # Update the message
        try:
            await client.chat_update(
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
                                "style": "primary",
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

            await client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=":white_check_mark: Switched to normal mode (Claude Sonnet 4).",
            )
        except Exception as e:
            logger.error(f"Failed to update message: {e}")

    return handle_normal_mode_button


def create_emergency_stop_handler(conversation_manager: ConversationManager):
    """Create emergency stop handler with conversation manager."""

    async def handle_emergency_stop(ack: AsyncAck, body: Dict[str, Any], client: AsyncWebClient, logger: logging.Logger):
        """Handle emergency stop button click."""
        await ack()

        # Extract conversation ID from button value
        conv_id = body.get("actions", [{}])[0].get("value", "")
        if ":" not in conv_id:
            logger.error(f"Invalid conversation ID: {conv_id}")
            return

        channel_id, thread_ts = conv_id.split(":", 1)
        user_id = body.get("user", {}).get("id")

        cancelled = await conversation_manager.cancel_conversation(channel_id, thread_ts, user_id)

        if not cancelled:
            # Conversation not found or not active
            await client.chat_postMessage(
                channel=channel_id, thread_ts=thread_ts, text=":information_source: No active request to stop.", user=user_id
            )

        logger.info(f"Emergency stop triggered by {user_id} for {conv_id}")

    return handle_emergency_stop
