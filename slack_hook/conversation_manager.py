"""Coroutine-based conversation management for Slack threads."""

import asyncio
import logging
from typing import Dict, Optional, Any, List, Callable
from dataclasses import dataclass, field
import time

from slack_bolt import BoltContext
from slack_bolt.context.say.async_say import AsyncSay
from slack_bolt.context.set_status.async_set_status import AsyncSetStatus
from slack_sdk.web.async_client import AsyncWebClient


@dataclass
class ThreadContext:
    """Context for processing a thread message."""

    context: BoltContext
    client: AsyncWebClient
    say: AsyncSay
    set_status: AsyncSetStatus
    logger: logging.Logger

    @property
    def channel_id(self) -> Optional[str]:
        """Get channel ID from context."""
        return self.context.channel_id

    @property
    def thread_ts(self) -> Optional[str]:
        """Get thread timestamp from context."""
        return self.context.thread_ts

    @property
    def user_id(self) -> Optional[str]:
        """Get user ID from context."""
        return self.context.user_id


@dataclass
class ConversationState:
    """State for a single conversation thread."""

    channel_id: str
    thread_ts: str
    processing_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    task: Optional[asyncio.Task] = None
    is_active: bool = True
    is_processing: bool = False
    start_time: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    model: str = "claude-sonnet-4-20250514"
    current_context: Optional[ThreadContext] = None
    stop_message_ts: Optional[str] = None  # Track stop button message


class ConversationManager:
    """Manages conversation coroutines for all Slack threads."""

    def __init__(self, parse_assistant_message: Callable):
        self.conversations: Dict[str, ConversationState] = {}
        self.parse_assistant_message = parse_assistant_message
        self.logger = logging.getLogger(__name__)
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()  # For thread-safe operations

    def _get_key(self, channel_id: str, thread_ts: str) -> str:
        """Generate unique key for a conversation."""
        return f"{channel_id}:{thread_ts}"

    async def start(self):
        """Start the conversation manager and cleanup task."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self.logger.info("ConversationManager started")

    async def stop(self):
        """Stop all conversations and cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Cancel all active conversations
        tasks = []
        async with self._lock:
            for conv in self.conversations.values():
                if conv.task and not conv.task.done():
                    conv.task.cancel()
                    tasks.append(conv.task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self.logger.info("ConversationManager stopped")

    async def _cleanup_loop(self):
        """Periodically clean up inactive conversations."""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                await self._cleanup_inactive_conversations()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in cleanup loop: {e}")

    async def _cleanup_inactive_conversations(self, max_idle_time: int = 3600):
        """Remove conversations that have been idle for too long."""
        current_time = time.time()
        to_remove = []

        async with self._lock:
            for key, conv in self.conversations.items():
                if not conv.is_processing and (current_time - conv.last_activity) > max_idle_time:
                    if conv.task and not conv.task.done():
                        conv.task.cancel()
                    to_remove.append(key)

        for key in to_remove:
            async with self._lock:
                if key in self.conversations:
                    del self.conversations[key]
            self.logger.info(f"Removed inactive conversation: {key}")

    async def process_thread_message(self, thread_context: ThreadContext, tool_registry: Any, llm: Any):
        """Process a message in a thread - main entry point."""
        if not thread_context.channel_id or not thread_context.thread_ts:
            thread_context.logger.error("Missing channel_id or thread_ts")
            await thread_context.say(":warning: Missing thread information")
            return

        key = self._get_key(thread_context.channel_id, thread_context.thread_ts)

        # Get or create conversation state
        async with self._lock:
            if key not in self.conversations:
                conv = ConversationState(channel_id=thread_context.channel_id, thread_ts=thread_context.thread_ts)
                self.conversations[key] = conv

                # Start the conversation coroutine
                conv.task = asyncio.create_task(
                    self._conversation_loop(conv, tool_registry, llm), name=f"conversation-{key}"
                )
                thread_context.logger.info(f"Created new conversation: {key}")
            else:
                conv = self.conversations[key]

        # Queue the context for processing
        await conv.processing_queue.put(thread_context)
        conv.last_activity = time.time()

    async def _conversation_loop(self, conv: ConversationState, tool_registry: Any, llm: Any):
        """Main coroutine loop for a single conversation."""
        self.logger.info(f"Starting conversation loop for {conv.channel_id}:{conv.thread_ts}")

        try:
            while conv.is_active:
                thread_context = None  # Initialize to avoid unbound variable
                try:
                    # Wait for next context with timeout
                    thread_context = await asyncio.wait_for(conv.processing_queue.get(), timeout=3600)  # 1 hour timeout

                    conv.is_processing = True
                    conv.current_context = thread_context
                    conv.last_activity = time.time()

                    # Process the thread
                    await self._process_thread(conv, thread_context, tool_registry, llm)

                except asyncio.TimeoutError:
                    self.logger.info(f"Conversation {conv.channel_id}:{conv.thread_ts} timed out")
                    break

                except asyncio.CancelledError:
                    self.logger.info(f"Conversation {conv.channel_id}:{conv.thread_ts} cancelled")
                    if conv.current_context:
                        await conv.current_context.say(":octagonal_sign: **Request cancelled**")
                    raise

                except Exception as e:
                    self.logger.error(f"Error in conversation loop: {e}", exc_info=True)
                    if thread_context:
                        await thread_context.say(f":warning: Error: {str(e)}")

                finally:
                    conv.is_processing = False
                    conv.current_context = None

        except asyncio.CancelledError:
            raise
        finally:
            conv.is_active = False
            self.logger.info(f"Conversation loop ended for {conv.channel_id}:{conv.thread_ts}")

    async def _process_thread(self, conv: ConversationState, thread_context: ThreadContext, tool_registry: Any, llm: Any):
        """Process a thread by fetching all messages and calling LLM."""
        await thread_context.set_status("is thinking...")

        # Show processing indicator with stop button
        stop_message = await thread_context.say(
            blocks=[
                {"type": "section", "text": {"type": "mrkdwn", "text": ":hourglass_flowing_sand: Processing..."}},
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": ":octagonal_sign: Stop", "emoji": True},
                            "value": f"{conv.channel_id}:{conv.thread_ts}",
                            "action_id": "emergency_stop",
                            "style": "danger",
                        }
                    ],
                },
            ],
            text="Processing...",
        )

        if stop_message and "ts" in stop_message:
            conv.stop_message_ts = stop_message["ts"]

        try:
            # Fetch all thread messages (following the current pattern)
            messages_in_thread = await self._fetch_thread_messages(thread_context)

            # Check model preference
            model = conv.model

            # Create cancel check function
            def cancel_check():
                return not conv.is_active

            # Debug log messages before sending
            self.logger.debug(f"Sending {len(messages_in_thread)} messages to Claude")
            for i, msg in enumerate(messages_in_thread):
                self.logger.debug(f"Message {i}: role={msg['role']}")
                if msg["role"] == "assistant" and isinstance(msg.get("content"), list):
                    for j, block in enumerate(msg["content"]):
                        self.logger.debug(f"  Block {j}: type={block.get('type')}")

            # Call async LLM
            await llm.async_message(
                set_status=thread_context.set_status,
                messages_in_thread=messages_in_thread,
                say=thread_context.say,
                tool_registry=tool_registry,
                model=model,
                cancel_check=cancel_check,
            )

            # Remove stop button on success
            if conv.stop_message_ts:
                await thread_context.client.chat_delete(channel=conv.channel_id, ts=conv.stop_message_ts)
                conv.stop_message_ts = None

        except asyncio.CancelledError:
            # Remove stop button and show cancelled message
            if conv.stop_message_ts:
                await thread_context.client.chat_delete(channel=conv.channel_id, ts=conv.stop_message_ts)
            raise

        except Exception:
            # Remove stop button on error
            if conv.stop_message_ts:
                try:
                    await thread_context.client.chat_delete(channel=conv.channel_id, ts=conv.stop_message_ts)
                except Exception:
                    pass
            raise

    async def _fetch_thread_messages(self, thread_context: ThreadContext) -> List[Dict[str, Any]]:
        """Fetch all messages in a thread with pagination support."""
        messages_in_thread: List[Dict[str, Any]] = []
        all_messages: List[Dict[str, Any]] = []
        cursor = None

        # Keep fetching until we have all messages
        while True:
            params = {
                "channel": thread_context.channel_id,
                "ts": thread_context.thread_ts,
                "limit": 10,  # Max allowed per request
            }

            if cursor:
                params["cursor"] = cursor

            replies = await thread_context.client.conversations_replies(**params)
            messages = replies.get("messages", [])

            if messages:
                all_messages.extend(messages)

            # Check if there are more messages
            response_metadata = replies.get("response_metadata", {})
            cursor = response_metadata.get("next_cursor")

            if not cursor:
                break

        # Sort messages by timestamp
        all_messages.sort(key=lambda m: float(m.get("ts", 0)))

        # Parse messages into conversation format
        for message in all_messages:
            if message.get("bot_id") is None:
                # User message
                messages_in_thread.append({"role": "user", "content": message["text"]})
            else:
                # Bot message - but only include if it's actually from Claude
                # Skip known non-Claude messages
                text = message.get("text", "")

                # Skip empty messages
                if not text:
                    continue

                # Skip greeting messages
                if text == "How can I help you?":
                    continue

                # Skip stop/status messages
                if text.startswith(":octagonal_sign:") or text.startswith(":information_source:"):
                    continue

                # Skip mode switch messages
                if "Mode Activated" in text or "Switched to normal mode" in text or "Switched back to normal mode" in text:
                    continue

                # Skip hourglass/processing messages
                if text == "Processing...":
                    continue

                # Skip processing indicator messages (they have blocks with buttons)
                blocks = message.get("blocks", [])
                if blocks and any(block.get("type") == "actions" for block in blocks):
                    continue

                # Assistant message - parse to recover thinking blocks
                attachments = message.get("attachments", [])
                parse_result = self.parse_assistant_message(text, attachments)

                # Handle the two possible return types
                if isinstance(parse_result, tuple):
                    content_blocks, tool_results = parse_result
                    if content_blocks:
                        messages_in_thread.append({"role": "assistant", "content": content_blocks})

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
                elif parse_result:
                    messages_in_thread.append({"role": "assistant", "content": parse_result})

        return messages_in_thread

    async def cancel_conversation(self, channel_id: str, thread_ts: str, user_id: str) -> bool:
        """Cancel an active conversation."""
        key = self._get_key(channel_id, thread_ts)

        async with self._lock:
            if key not in self.conversations:
                return False

            conv = self.conversations[key]

            # Check if conversation is processing
            if not conv.is_processing:
                return False

            # Mark as inactive
            conv.is_active = False

            # Cancel the task
            if conv.task and not conv.task.done():
                self.logger.info(f"Cancelling conversation {key} by user {user_id}")
                conv.task.cancel()

                # Post cancellation message
                if conv.current_context:
                    await conv.current_context.client.chat_postMessage(
                        channel=channel_id, thread_ts=thread_ts, text=f":octagonal_sign: Stopped by <@{user_id}>"
                    )

                return True

        return False

    def set_model_preference(self, channel_id: str, thread_ts: str, model: str):
        """Set the model preference for a conversation."""
        key = self._get_key(channel_id, thread_ts)
        if key in self.conversations:
            self.conversations[key].model = model
            self.logger.info(f"Set model {model} for conversation {key}")

    def get_active_conversations(self) -> Dict[str, ConversationState]:
        """Get all active conversations."""
        return {k: v for k, v in self.conversations.items() if v.is_active and v.is_processing}
