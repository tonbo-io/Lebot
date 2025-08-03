import re
import asyncio
import os
from typing import List, Dict, Optional

from claude_code_sdk import (
    ToolResultBlock,
    query,
    ClaudeCodeOptions,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
    ResultMessage,
)
from slack_bolt import SetStatus


class ClaudeCodeLLMNative:
    def __init__(self):
        # Claude Code SDK automatically uses ANTHROPIC_API_KEY from environment
        # Map Slack thread_id to Claude Code session_id
        self.thread_to_session: Dict[str, str] = {}
        # Set working directory to scripts/ for restricted access
        self.scripts_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts")

    def message(
        self,
        set_status: SetStatus,
        messages_in_thread: List[Dict[str, str]],
        say,
        thread_id: Optional[str] = None,
    ) -> Optional[str]:
        """Execute a prompt using Claude Code SDK with native session management."""
        set_status("is typing...")

        # Get the last user message (Claude Code handles conversation context internally)
        last_user_message = None
        for msg in reversed(messages_in_thread):
            if msg["role"] == "user":
                last_user_message = msg["content"]
                break

        if not last_user_message:
            return "I didn't receive a message to respond to."

        # Configure Claude Code options
        parent_dir = os.path.dirname(self.scripts_dir)
        options = ClaudeCodeOptions(
            # Set working directory to scripts/ for restricted access
            cwd=self.scripts_dir,
            # Add parent directory for broader read access to project files
            add_dirs=[parent_dir],
            # Allow tools for code-related tasks but restricted to scripts/ directory
            allowed_tools=["Read", "Bash(find:*)", "Bash(ls:*)", "Bash(source:*)", "Bash(python:*)", "WebFetch"],
            model="claude-sonnet-4-20250514",  # Use the latest model
        )

        # If we have a thread_id and a known session, resume it
        if thread_id and thread_id in self.thread_to_session:
            options.resume = self.thread_to_session[thread_id]

        # Run the async streaming query
        session_id = asyncio.run(self._async_stream_to_slack(last_user_message, options, say, set_status))

        # Store the session_id for this thread
        if thread_id and session_id:
            self.thread_to_session[thread_id] = session_id

        return None  # Responses were already sent via say()

    async def _async_stream_to_slack(
        self, prompt: str, options: ClaudeCodeOptions, say, set_status: SetStatus
    ) -> Optional[str]:
        """Stream responses directly to Slack as they arrive."""
        session_id = None
        has_content = False

        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        # Send each text block to Slack as it arrives
                        formatted_text = self.markdown_to_slack(block.text)
                        if formatted_text.strip():  # Only send non-empty messages
                            say(formatted_text)
                            has_content = True
                            # Update status to show we're still working
                            set_status("is thinking...")
                    elif isinstance(block, ToolUseBlock):
                        # Update status when using tools with details
                        tool_name = block.name.lower()
                        tool_input = block.input

                        if tool_name == "read":
                            file_path = tool_input.get("file_path", "")
                            set_status(f"is reading {file_path}...")
                        elif tool_name == "write":
                            file_path = tool_input.get("file_path", "")
                            set_status(f"is writing to {file_path}...")
                        elif tool_name == "bash":
                            command = tool_input.get("command", "")
                            # Truncate long commands for status display
                            if len(command) > 50:
                                command = command[:47] + "..."
                            set_status(f"is running: {command}")
                        else:
                            # For other tools, show a summary of inputs
                            input_summary = ", ".join(f"{k}={v}" for k, v in tool_input.items() if v)[:50]
                            if len(input_summary) > 47:
                                input_summary = input_summary[:47] + "..."
                            set_status(f"is using {tool_name}: {input_summary}")
                    elif isinstance(message, ToolResultBlock):
                        # Handle tool results if needed
                        if block.is_error:
                            say(f"Error in tool use: {block.content}")
                        else:
                            say(f"Tool result: {block.content}")

            elif isinstance(message, ResultMessage):
                # Capture the session_id from the result
                session_id = message.session_id

        # Clear status when done
        set_status("")

        # If no content was sent, send a default message
        if not has_content:
            say("I processed your request but didn't generate any response.")

        return session_id

    def clear_session(self, thread_id: str):
        """Clear the session mapping for a specific thread."""
        if thread_id in self.thread_to_session:
            del self.thread_to_session[thread_id]

    @staticmethod
    def markdown_to_slack(content: str) -> str:
        """Convert markdown to Slack-compatible mrkdwn format."""
        # First convert headers to bold text (before splitting by code blocks)
        # This ensures headers are converted even if they contain code
        content = re.sub(r'^#{1,6}\s+(.+)$', r'*\1*', content, flags=re.MULTILINE)
        
        # Split the input string into parts based on code blocks and inline code
        parts = re.split(r"(?s)(```.+?```|`[^`\n]+?`)", content)

        # Apply the bold, italic, and strikethrough formatting to text not within code
        result = ""
        for part in parts:
            if part.startswith("```") or part.startswith("`"):
                result += part
            else:
                for o, n in [
                    (
                        r"\*\*\*(?!\s)([^\*\n]+?)(?<!\s)\*\*\*",
                        r"_*\1*_",
                    ),  # ***bold italic*** to *_bold italic_*
                    (
                        r"(?<![\*_])\*(?!\s)([^\*\n]+?)(?<!\s)\*(?![\*_])",
                        r"_\1_",
                    ),  # *italic* to _italic_
                    (r"\*\*(?!\s)([^\*\n]+?)(?<!\s)\*\*", r"*\1*"),  # **bold** to *bold*
                    (r"__(?!\s)([^_\n]+?)(?<!\s)__", r"*\1*"),  # __bold__ to *bold*
                    (r"~~(?!\s)([^~\n]+?)(?<!\s)~~", r"~\1~"),  # ~~strike~~ to ~strike~
                ]:
                    part = re.sub(o, n, part)
                result += part
        return result
