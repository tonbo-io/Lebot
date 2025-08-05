"""Async version of Claude LLM integration with cancellation support."""

import os
import re
import time
import json
import asyncio
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path

from anthropic import AsyncAnthropic
from anthropic.types import TextBlock, ToolUseBlock, ThinkingBlock
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
                    team_section += f"\n| {member.get('linear_name', '')} | {member.get('linear_email', '')} | {member.get('slack_user_id', '')} | {member.get('slack_mention', '')} | {member.get('slack_handle', '')} |"

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

    async def _process_response_content(
        self,
        response: Any,
        say: Any,
        set_status: AsyncSetStatus,
        tool_registry: Any,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> List[Dict[str, Any]]:
        """Process response content, execute tools, and return tool uses.

        Args:
            response: Claude API response
            say: Slack say function
            set_status: Status setter
            tool_registry: Tool registry for execution
            cancel_check: Optional function to check if cancelled

        Returns:
            List of tool uses with their results
        """
        tool_uses = []

        for content in response.content:
            # Check for cancellation
            if cancel_check and cancel_check():
                raise asyncio.CancelledError("Processing cancelled")

            if isinstance(content, ThinkingBlock):
                # Format thinking content as quoted text
                thinking_text = content.thinking
                quoted_lines = [f"> {line}" for line in thinking_text.split("\n")]
                quoted_text = "\n".join(quoted_lines)

                # Send thinking as plain quoted text
                await say(
                    text=quoted_text,
                    attachments=[
                        {
                            "color": "#e0e0e0",  # Light gray for thinking
                            "text": "",  # Empty text, just using for metadata
                            "footer": f"thinking:{content.signature}",
                            "ts": int(time.time()),
                        }
                    ],
                )
            elif isinstance(content, TextBlock):
                # Convert and send each text block immediately
                formatted_text = self.markdown_to_slack(content.text)
                await say(formatted_text)
            elif isinstance(content, ToolUseBlock):
                # Execute the tool
                await set_status(f"using {content.name}...")

                # Execute tool (assuming tool registry has async support)
                if hasattr(tool_registry, "async_execute_tool"):
                    tool_result = await tool_registry.async_execute_tool(content.name, content.input)
                else:
                    # Fallback to sync execution in thread pool
                    tool_result = await asyncio.get_event_loop().run_in_executor(
                        None, tool_registry.execute_tool, content.name, content.input
                    )

                # Store tool use for potential follow-up
                tool_uses.append(
                    {"tool_use_id": content.id, "name": content.name, "input": content.input, "result": tool_result}
                )

                # Show tool usage in Slack using attachments for auto-collapse
                formatted_result = self.markdown_to_slack(tool_result)

                # Determine color based on tool result (simple heuristic)
                color = "#ff0000" if "error" in tool_result.lower() else "#2eb886"

                # Use attachment for tool results - auto-collapses if >700 chars or >5 lines
                await say(
                    text=f"*Tool: {content.name}*",  # Fallback for notifications
                    attachments=[
                        {
                            "color": color,
                            "title": f"Tool: {content.name}",
                            "text": formatted_result,
                            "footer": f"Tool ID: {content.id}",
                            "ts": int(time.time()),
                        }
                    ],
                )

        return tool_uses

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

        # Initial response
        response = await self.client.messages.create(**request_params)

        if len(response.content) < 1:
            await say("I'm distracted.")
            return

        # Process initial response
        tool_uses = await self._process_response_content(response, say, set_status, tool_registry, cancel_check)

        # Continue processing while there are tool uses
        tool_round = 0

        while tool_uses:
            # Check for cancellation
            if cancel_check and cancel_check():
                raise asyncio.CancelledError("Request cancelled during tool processing")

            tool_round += 1
            await set_status(f"processing tool results (round {tool_round})...")

            # Add assistant message with all content to conversation
            # First, collect all content blocks by type
            thinking_blocks = []
            text_blocks = []
            tool_use_blocks = []

            for content in response.content:
                if isinstance(content, ThinkingBlock):
                    thinking_blocks.append(
                        {"type": "thinking", "thinking": content.thinking, "signature": content.signature}
                    )
                elif isinstance(content, TextBlock):
                    text_blocks.append({"type": "text", "text": content.text})
                elif isinstance(content, ToolUseBlock):
                    tool_use_blocks.append(
                        {"type": "tool_use", "id": content.id, "name": content.name, "input": content.input}
                    )

            # Construct assistant content with thinking blocks first (required for thinking mode)
            assistant_content = thinking_blocks + text_blocks + tool_use_blocks
            messages.append({"role": "assistant", "content": assistant_content})

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

            response = await self.client.messages.create(**follow_up_params)

            # Process follow-up response and check for more tool uses
            tool_uses = await self._process_response_content(response, say, set_status, tool_registry, cancel_check)

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
