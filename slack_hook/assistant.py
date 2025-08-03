import logging
from typing import List, Dict
from slack_bolt import Assistant, BoltContext, Say, SetSuggestedPrompts, SetStatus
from slack_bolt.context.get_thread_context import GetThreadContext
from slack_sdk import WebClient

from .claude_code_llm_native import ClaudeCodeLLMNative

# Refer to https://tools.slack.dev/bolt-python/concepts/assistant/ for more details
assistant = Assistant()
llm = ClaudeCodeLLMNative()


# This listener is invoked when a human user opened an assistant thread
@assistant.thread_started
def start_assistant_thread(
    say: Say,
    _get_thread_context: GetThreadContext,
    _set_suggested_prompts: SetSuggestedPrompts,
    logger: logging.Logger,
):
    try:
        say("How can I help you?")
    except Exception as e:
        logger.exception(f"Failed to handle an assistant_thread_started event: {e}", e)
        say(f":warning: Something went wrong! ({e})")


# This listener is invoked when the human user sends a reply in the assistant thread
@assistant.user_message
def respond_in_assistant_thread(
    _payload: dict,
    logger: logging.Logger,
    context: BoltContext,
    set_status: SetStatus,
    _get_thread_context: GetThreadContext,
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

    replies = client.conversations_replies(
        channel=context.channel_id,
        ts=context.thread_ts,
        oldest=context.thread_ts,
        limit=10,
    )
    messages_in_thread: List[Dict[str, str]] = []
    messages = replies.get("messages")
    if messages is not None:
        for message in messages:
            role = "user" if message.get("bot_id") is None else "assistant"
            messages_in_thread.append({"role": role, "content": message["text"]})
    try:
        # Pass thread_ts as the thread_id for session management and say function for streaming
        returned_message = llm.message(set_status, messages_in_thread, thread_id=context.thread_ts, say=say)
        # If returned_message is None, responses were already sent via streaming
        if returned_message:
            say(returned_message)
    except Exception as e:
        logger.exception(f"Failed to handle a user message event: {e}")
        say(f":warning: Something went wrong! ({e})")
