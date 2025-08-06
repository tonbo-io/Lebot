"""Async version of Claude LLM integration with cancellation support."""

import os
import re
import time
import json
import asyncio
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path

from anthropic import AsyncAnthropic
from slack_bolt.context.set_status.async_set_status import AsyncSetStatus


class AsyncClaude:
    """Async Claude client with cancellation support."""

    # Try to load system prompt from CLAUDE.md, fallback to default
    DEFAULT_SYSTEM_CONTENT = """
You're an assistant in a Slack workspace.
Users in the workspace will ask you to help them write something or to think better about a specific topic.
You'll respond to those questions in a professional way.
When a prompt has Slack's special syntax like <@USER_ID> or <#CHANNEL_ID>, you must keep them as-is in your response.
"""

    @classmethod
    def _load_system_prompt(cls) -> str:
        """Load system prompt from prompts/system.md if available and append today's date info."""
        base_prompt = ""
        try:
            # Get the project root directory (parent of slack_hook)
            current_dir = Path(__file__).parent
            project_root = current_dir.parent
            system_prompt_path = project_root / "prompts" / "system.md"

            if system_prompt_path.exists():
                with open(system_prompt_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    # Remove the first line if it's a markdown header
                    lines = content.split("\n")
                    if lines and lines[0].startswith("#"):
                        lines = lines[1:]
                    base_prompt = "\n".join(lines).strip()
            else:
                base_prompt = cls.DEFAULT_SYSTEM_CONTENT
        except Exception as e:
            print(f"Warning: Could not load system.md: {e}")
            base_prompt = cls.DEFAULT_SYSTEM_CONTENT

        # Append team member mapping if available from environment
        team_mapping_json = os.getenv("TEAM_MEMBER_MAPPING")
        if team_mapping_json:
            try:
                team_members = json.loads(team_mapping_json)

                # Build the team member table
                team_section = "\n\n## Our Folks\n"
                team_section += "| Linear Name | Linear Email | Slack User ID | Slack Mention | Slack Handle |\n"
                team_section += "|-------------|--------------|---------------|---------------|--------------|"

                for member in team_members:
                    team_section += (
                        f"\n| {member.get('linear_name', '')} | {member.get('linear_email', '')} | "
                        f"{member.get('slack_user_id', '')} | {member.get('slack_mention', '')} | "
                        f"{member.get('slack_handle', '')} |"
                    )

                base_prompt += team_section
            except (json.JSONDecodeError, TypeError) as e:
                print(f"Warning: Could not parse TEAM_MEMBER_MAPPING: {e}")

        # Append current date and time information (hour precision for caching)
        import datetime

        now = datetime.datetime.now().astimezone()
        # Round to hour precision for better cache utilization
        hour_precision = now.replace(minute=0, second=0, microsecond=0)
        date_info = f"\n\n**Current context**: {hour_precision.strftime('%A, %Y-%m-%d %H:00')} ({str(now.tzinfo)})"

        return base_prompt + date_info

    def __init__(self, api_key: Optional[str] = None):
        if api_key is None:
            api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        self.client = AsyncAnthropic(api_key=api_key)

    async def _process_stream_response(
        self,
        stream: Any,
        say: Any,
        set_status: AsyncSetStatus,
        tool_registry: Any,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Process streaming response, execute tools, and return content blocks and tool uses.

        Args:
            stream: Claude API stream
            say: Slack say function
            set_status: Status setter
            tool_registry: Tool registry for execution
            cancel_check: Optional function to check if cancelled

        Returns:
            Tuple of (content_blocks, tool_uses) where:
            - content_blocks: List of all content blocks for conversation history
            - tool_uses: List of tool uses with their results
        """
        # Buffers for accumulating content
        thinking_blocks = []  # Buffer thinking blocks until we start outputting
        text_blocks = []
        tool_use_blocks = []
        tool_uses = []

        # State tracking
        current_thinking = ""
        current_thinking_signature = None
        current_text = ""
        current_tool_use = None
        current_tool_input = ""
        thinking_sent = False  # Track if we've sent thinking blocks to Slack

        async for event in stream:
            # Check for cancellation
            if cancel_check and cancel_check():
                await stream.close()
                raise asyncio.CancelledError("Processing cancelled")

            if event.type == "thinking":
                # Accumulate thinking content
                current_thinking += event.thinking
                # Check if signature is provided with the thinking event
                if hasattr(event, "signature"):
                    current_thinking_signature = event.signature
                # Check in the snapshot which contains the accumulated state
                if hasattr(event, "snapshot") and hasattr(event.snapshot, "signature"):
                    current_thinking_signature = event.snapshot.signature

            elif event.type == "content_block_start":
                # Handle the start of a new content block
                if hasattr(event, "content_block") and hasattr(event.content_block, "type"):
                    if event.content_block.type == "thinking":
                        current_thinking = ""
                        # Extract signature if available at block start
                        if hasattr(event.content_block, "signature"):
                            current_thinking_signature = event.content_block.signature
                        # Reset signature if starting a new thinking block without one
                        elif not hasattr(event.content_block, "signature"):
                            current_thinking_signature = None
                    elif event.content_block.type == "text":
                        # If we have buffered thinking blocks, send them now
                        if thinking_blocks and not thinking_sent:
                            for thinking_block in thinking_blocks:
                                thinking_text = thinking_block["thinking"]
                                quoted_lines = [f"> {line}" for line in thinking_text.split("\n")]
                                quoted_text = "\n".join(quoted_lines)

                                signature = thinking_block.get("signature", "")
                                await say(
                                    text=quoted_text,
                                    attachments=[
                                        {
                                            "color": "#e0e0e0",  # Light gray for thinking
                                            "text": "",  # Empty text, just using for metadata
                                            "footer": f"thinking:{signature}" if signature else "thinking",
                                            "ts": int(time.time()),
                                        }
                                    ],
                                )
                            thinking_sent = True
                        current_text = ""
                    elif event.content_block.type == "tool_use":
                        current_tool_use = {
                            "id": event.content_block.id,
                            "name": event.content_block.name,
                        }
                        current_tool_input = ""

            elif event.type == "text":
                # Buffer text content instead of streaming immediately
                if event.text:
                    current_text += event.text

            elif event.type == "input_json":
                # Accumulate tool input JSON
                if event.partial_json:
                    current_tool_input += event.partial_json

            elif event.type == "content_block_stop":
                # Handle completion of a content block
                if hasattr(event, "content_block"):
                    block = event.content_block
                    if hasattr(block, "type"):
                        if block.type == "thinking":
                            # Get signature from the completed block
                            final_signature = current_thinking_signature
                            if hasattr(block, "signature"):
                                final_signature = block.signature

                            # Store completed thinking block with signature from server
                            thinking_block = {"type": "thinking", "thinking": current_thinking}
                            if final_signature:
                                thinking_block["signature"] = final_signature
                            thinking_blocks.append(thinking_block)
                            current_thinking = ""
                            current_thinking_signature = None

                        elif block.type == "text":
                            # Send the complete text block to Slack
                            if current_text:
                                formatted_text = self.markdown_to_slack(current_text)
                                await say(formatted_text)
                                # Store completed text block
                                text_blocks.append({"type": "text", "text": current_text})
                                current_text = ""

                        elif block.type == "tool_use":
                            # Execute the tool
                            if current_tool_use:
                                await set_status(f"using {current_tool_use['name']}...")

                                # Parse the accumulated JSON input
                                import json

                                try:
                                    tool_input = json.loads(current_tool_input) if current_tool_input else {}
                                except json.JSONDecodeError:
                                    tool_input = {}

                                # Execute tool
                                if hasattr(tool_registry, "async_execute_tool"):
                                    tool_result = await tool_registry.async_execute_tool(
                                        current_tool_use["name"], tool_input
                                    )
                                else:
                                    # Fallback to sync execution in thread pool
                                    tool_result = await asyncio.get_event_loop().run_in_executor(
                                        None, tool_registry.execute_tool, current_tool_use["name"], tool_input
                                    )

                                # Store tool use block for conversation history
                                tool_use_block = {
                                    "type": "tool_use",
                                    "id": current_tool_use["id"],
                                    "name": current_tool_use["name"],
                                    "input": tool_input,
                                }
                                tool_use_blocks.append(tool_use_block)

                                # Store tool use with result for follow-up
                                tool_uses.append(
                                    {
                                        "tool_use_id": current_tool_use["id"],
                                        "name": current_tool_use["name"],
                                        "input": tool_input,
                                        "result": tool_result,
                                    }
                                )

                                # Show tool usage in Slack
                                formatted_result = self.markdown_to_slack(tool_result)
                                color = "#ff0000" if "error" in tool_result.lower() else "#2eb886"

                                await say(
                                    text=f"*Tool: {current_tool_use['name']}*",
                                    attachments=[
                                        {
                                            "color": color,
                                            "title": f"Tool: {current_tool_use['name']}",
                                            "text": formatted_result,
                                            "footer": f"Tool ID: {current_tool_use['id']}",
                                            "ts": int(time.time()),
                                        }
                                    ],
                                )

                                current_tool_use = None
                                current_tool_input = ""

        # Send any remaining thinking blocks if they haven't been sent
        if thinking_blocks and not thinking_sent:
            for thinking_block in thinking_blocks:
                thinking_text = thinking_block["thinking"]
                quoted_lines = [f"> {line}" for line in thinking_text.split("\n")]
                quoted_text = "\n".join(quoted_lines)

                signature = thinking_block.get("signature", "")
                await say(
                    text=quoted_text,
                    attachments=[
                        {
                            "color": "#e0e0e0",
                            "text": "",
                            "footer": f"thinking:{signature}" if signature else "thinking",
                            "ts": int(time.time()),
                        }
                    ],
                )

        # Construct properly ordered content blocks for conversation history
        # CRITICAL: Thinking blocks MUST come first for assistant messages
        content_blocks = thinking_blocks + text_blocks + tool_use_blocks

        return content_blocks, tool_uses

    async def async_message(
        self,
        set_status: AsyncSetStatus,
        messages_in_thread: List[Dict[str, Any]],
        say: Any,
        tool_registry: Any,
        tools: Optional[List[Dict[str, Any]]] = None,
        system_content: Optional[str] = None,
        thinking_budget: int = 16384,
        model: str = "claude-sonnet-4-20250514",
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> None:
        """Send messages with interleaved thinking mode and optional tools.

        Args:
            set_status: Slack status setter
            messages_in_thread: Conversation messages
            say: Say function to stream content to Slack
            tools: Optional list of tool definitions
            tool_registry: Tool registry for executing tools
            system_content: Optional system prompt
            thinking_budget: Token budget for thinking
            model: Model to use
            cancel_check: Optional function to check if cancelled
        """
        if system_content is None:
            system_content = self._load_system_prompt()

        await set_status("is thinking...")

        messages = []
        messages.extend(messages_in_thread)

        # Get tool schemas dynamically from the registry
        tools_list = []
        if tool_registry:
            tools_list = tool_registry.get_tool_schemas()

        # Add any additional custom tools provided
        if tools:
            tools_list.extend(tools)

        # Prepare system prompt with cache control for the entire prompt
        # Since we use hour precision, the entire prompt can be cached
        system_with_cache = [{"type": "text", "text": system_content, "cache_control": {"type": "ephemeral"}}]  # Cache

        # Add cache control to tools if they exist
        # Tools typically don't change, so caching them saves tokens
        tools_with_cache = None
        if tools_list:
            tools_with_cache = [{**tool, "cache_control": {"type": "ephemeral"}} for tool in tools_list]

        # Prepare request parameters
        request_params = {
            "max_tokens": 8192,
            "messages": messages,
            "model": model,
            "system": system_with_cache,  # Use the cached system prompt
            "tools": tools_with_cache if tools_with_cache else tools_list,
            "extra_headers": {"anthropic-beta": "interleaved-thinking-2025-05-14"},
            "thinking": {"type": "enabled", "budget_tokens": thinking_budget},
        }

        # Check for cancellation before API call
        if cancel_check and cancel_check():
            raise asyncio.CancelledError("Request cancelled before API call")

        # Initial streaming response
        content_blocks = []
        tool_uses = []

        async with self.client.messages.stream(**request_params) as stream:
            # Process streaming response
            content_blocks, tool_uses = await self._process_stream_response(
                stream, say, set_status, tool_registry, cancel_check
            )

        if not content_blocks:
            await say("I'm distracted.")
            return

        # Continue processing while there are tool uses
        tool_round = 0

        while tool_uses:
            # Check for cancellation
            if cancel_check and cancel_check():
                raise asyncio.CancelledError("Request cancelled during tool processing")

            tool_round += 1
            await set_status(f"processing tool results (round {tool_round})...")

            # Add assistant message with all content blocks
            # Content blocks are already properly ordered (thinking first) from _process_stream_response
            messages.append({"role": "assistant", "content": content_blocks})

            # Add tool results as user message
            tool_result_content = []
            for tool_use in tool_uses:
                tool_result_content.append(
                    {"type": "tool_result", "tool_use_id": tool_use["tool_use_id"], "content": tool_use["result"]}
                )
            messages.append({"role": "user", "content": tool_result_content})

            # Get Claude's follow-up response
            follow_up_params = request_params.copy()
            # Create a fresh copy of messages to ensure proper structure
            follow_up_messages = []
            for msg in messages:
                if msg["role"] == "assistant" and isinstance(msg.get("content"), list):
                    # Ensure assistant messages have proper structure for thinking mode
                    # Reorder content to have thinking blocks first
                    content = msg["content"]
                    thinking_blocks = [block for block in content if block.get("type") == "thinking"]
                    text_blocks = [block for block in content if block.get("type") == "text"]
                    tool_use_blocks = [block for block in content if block.get("type") == "tool_use"]

                    # Only reorder if we have content blocks
                    if thinking_blocks or text_blocks or tool_use_blocks:
                        reordered_content = thinking_blocks + text_blocks + tool_use_blocks
                        follow_up_messages.append({"role": msg["role"], "content": reordered_content})
                    else:
                        follow_up_messages.append(msg)
                else:
                    follow_up_messages.append(msg)

            follow_up_params["messages"] = follow_up_messages

            # Stream follow-up response
            async with self.client.messages.stream(**follow_up_params) as stream:
                # Process follow-up response and check for more tool uses
                content_blocks, tool_uses = await self._process_stream_response(
                    stream, say, set_status, tool_registry, cancel_check
                )

    @staticmethod
    def markdown_to_slack(content: str) -> str:
        """Convert markdown to Slack-compatible mrkdwn format."""
        # First convert headers to bold text
        content = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", content, flags=re.MULTILINE)

        # Split the input string into parts based on code blocks and inline code
        parts = re.split(r"(?s)(```.+?```|`[^`\n]+?`)", content)

        # Apply the bold, italic, and strikethrough formatting to text not within code
        result = ""
        for part in parts:
            if part.startswith("```") or part.startswith("`"):
                result += part
            else:
                # Process formatting - order matters to avoid conflicts!
                # 1. Bold-italic (***) first - most specific pattern
                part = re.sub(r"\*\*\*(.+?)\*\*\*", r"_*\1*_", part)

                # 2. Italic (*) BEFORE bold (**) to avoid confusion after conversion
                # Match single asterisks that are not adjacent to other asterisks
                part = re.sub(r"(?<![*])\*([^*\n]+?)\*(?![*])", r"_\1_", part)

                # 3. Bold (**) - now safe to convert without affecting italic
                part = re.sub(r"\*\*(.+?)\*\*", r"*\1*", part)

                # 4. Alternative bold (__)
                part = re.sub(r"__(.+?)__", r"*\1*", part)

                # 5. Strikethrough (~~)
                part = re.sub(r"~~(.+?)~~", r"~\1~", part)

                result += part
        return result
