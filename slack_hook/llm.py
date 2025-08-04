import os
import re
import time
from typing import List, Dict, Any, Optional
from pathlib import Path

from anthropic import Anthropic
from anthropic.types import TextBlock, ToolUseBlock, ThinkingBlock
from slack_bolt import SetStatus


class LLM:
    # Try to load system prompt from CLAUDE.md, fallback to default
    DEFAULT_SYSTEM_CONTENT = """
You're an assistant in a Slack workspace.
Users in the workspace will ask you to help them write something or to think better about a specific topic.
You'll respond to those questions in a professional way.
When a prompt has Slack's special syntax like <@USER_ID> or <#CHANNEL_ID>, you must keep them as-is in your response.
"""

    @classmethod
    def _load_system_prompt(cls) -> str:
        """Load system prompt from prompts/system.md if available."""
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
                    return "\n".join(lines).strip()
        except Exception as e:
            print(f"Warning: Could not load system.md: {e}")

        return cls.DEFAULT_SYSTEM_CONTENT

    def __init__(self, api_key: Optional[str] = None):
        if api_key is None:
            api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        self.client = Anthropic(api_key=api_key)

    def _process_response_content(
        self,
        response: Any,
        say: Any,
        set_status: SetStatus,
        tool_registry: Any,
    ) -> List[Dict[str, Any]]:
        """Process response content, execute tools, and return tool uses.

        Returns:
            List of tool uses with their results
        """
        tool_uses = []

        for content in response.content:
            if isinstance(content, ThinkingBlock):
                # Format thinking content as quoted text
                thinking_text = content.thinking
                quoted_lines = [f"> {line}" for line in thinking_text.split("\n")]
                quoted_text = "\n".join(quoted_lines)

                # Send thinking as plain quoted text
                # Store signature in attachment metadata for cleaner appearance
                say(
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
                formatted_text = LLM.markdown_to_slack(content.text)
                say(formatted_text)
            elif isinstance(content, ToolUseBlock):
                # Execute the tool
                set_status(f"using {content.name}...")
                tool_result = tool_registry.execute_tool(content.name, content.input)

                # Store tool use for potential follow-up
                tool_uses.append(
                    {"tool_use_id": content.id, "name": content.name, "input": content.input, "result": tool_result}
                )

                # Show tool usage in Slack using attachments for auto-collapse
                formatted_result = LLM.markdown_to_slack(tool_result)

                # Determine color based on tool result (simple heuristic)
                color = "#ff0000" if "error" in tool_result.lower() else "#2eb886"

                # Use attachment for tool results - auto-collapses if >700 chars or >5 lines
                say(
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

    def message(
        self,
        set_status: SetStatus,
        messages_in_thread: List[Dict[str, Any]],
        say: Any,
        tool_registry: Any,
        tools: Optional[List[Dict[str, Any]]] = None,
        system_content: Optional[str] = None,
        thinking_budget: int = 16384,  # Default budget for thinking mode
    ) -> None:
        """Send messages with interleaved thinking mode and optional tools.

        Args:
            set_status: Slack status setter
            messages_in_thread: Conversation messages
            say: Say function to stream content to Slack
            tools: Optional list of tool definitions
            tool_registry: Tool registry for executing tools
            system_content: Optional system prompt
            thinking_budget: Token budget for thinking (default 8000)
        """
        if system_content is None:
            system_content = self._load_system_prompt()

        set_status("is thinking...")

        messages = []
        messages.extend(messages_in_thread)

        # Get tool schemas dynamically from the registry
        tools_list = []
        if tool_registry:
            tools_list = tool_registry.get_tool_schemas()

        # Add any additional custom tools provided
        if tools:
            tools_list.extend(tools)

        # Prepare request parameters
        request_params = {
            "max_tokens": 16384,
            "messages": messages,
            "model": "claude-sonnet-4-20250514",
            "system": system_content,
            "tools": tools_list,
            "extra_headers": {"anthropic-beta": "interleaved-thinking-2025-05-14"},
            "thinking": {"type": "enabled", "budget_tokens": thinking_budget},
        }

        # Initial response
        response = self.client.messages.create(**request_params)

        if len(response.content) < 1:
            say("I'm distracted.")
            return

        # Process initial response
        tool_uses = self._process_response_content(response, say, set_status, tool_registry)

        # Continue processing while there are tool uses
        max_tool_rounds = 10  # Prevent infinite loops
        tool_round = 0

        while tool_uses and tool_round < max_tool_rounds:
            tool_round += 1
            set_status(f"processing tool results (round {tool_round})...")

            # Add assistant message with all content to conversation
            assistant_content = []
            for content in response.content:
                if isinstance(content, ThinkingBlock):
                    assistant_content.append(
                        {"type": "thinking", "thinking": content.thinking, "signature": content.signature}
                    )
                elif isinstance(content, TextBlock):
                    assistant_content.append({"type": "text", "text": content.text})
                elif isinstance(content, ToolUseBlock):
                    assistant_content.append(
                        {"type": "tool_use", "id": content.id, "name": content.name, "input": content.input}
                    )

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
            follow_up_params["messages"] = messages

            response = self.client.messages.create(**follow_up_params)

            # Process follow-up response and check for more tool uses
            tool_uses = self._process_response_content(response, say, set_status, tool_registry)

        if tool_round >= max_tool_rounds and tool_uses:
            say(":warning: Reached maximum tool execution rounds. Some tools may not have been executed.")

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
