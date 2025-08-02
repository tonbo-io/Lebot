import os
import re
from typing import List, Dict

from anthropic import Anthropic
from dotenv import load_dotenv
from slack_bolt import SetStatus

load_dotenv()


class LLMCaller:
    DEFAULT_SYSTEM_CONTENT = """
You're an assistant in a Slack workspace.
Users in the workspace will ask you to help them write something or to think better about a specific topic.
You'll respond to those questions in a professional way.
When you include markdown text, convert them to Slack compatible ones.
When a prompt has Slack's special syntax like <@USER_ID> or <#CHANNEL_ID>, you must keep them as-is in your response.
"""

    def __init__(self, api_key: str = None):
        if api_key is None:
            api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        self.client = Anthropic(api_key=api_key)

    def call_llm(
        self,
        set_status: SetStatus,
        messages_in_thread: List[Dict[str, str]],
        system_content: str = None,
    ) -> str:
        if system_content is None:
            system_content = self.DEFAULT_SYSTEM_CONTENT

        set_status("is typing...")

        messages = []
        messages.extend(messages_in_thread)

        response = self.client.messages.create(
            max_tokens=4096, messages=messages, model="claude-sonnet-4-20250514", system=system_content
        )

        if len(response.content) < 1:
            return "I'm distracted."
        return LLMCaller.markdown_to_slack(response.content[0].text)

    @staticmethod
    def markdown_to_slack(content: str) -> str:
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
