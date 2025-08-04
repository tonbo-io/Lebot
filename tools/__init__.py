import logging
from typing import Dict, Any, Optional, List

from .graphql import GraphQLClient, LinearClient
from .bash import Bash
from .slack import Slack


class ToolRegistry:
    """Registry for managing and executing tools requested by the LLM."""

    def __init__(self, slack_client=None):
        """Initialize the tool registry with available tools.

        Args:
            slack_client: Optional Slack WebClient instance for Slack operations
        """
        self.logger = logging.getLogger(__name__)
        self.tools = {}
        self.slack_client = slack_client
        self._initialize_tools()

    def _initialize_tools(self):
        """Initialize all available tools."""
        # Initialize bash tool
        self.tools["bash"] = Bash(timeout=30)

        # Initialize slack tool if client is available
        if self.slack_client:
            self.tools["slack"] = Slack(self.slack_client)
            self.logger.info("Initialized tool registry with bash and slack tools")
        else:
            self.logger.info("Initialized tool registry with bash tool (no slack client provided)")

    def execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Execute a tool with the given input.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Input parameters for the tool

        Returns:
            String representation of the tool output
        """
        if tool_name not in self.tools:
            error_msg = f"Unknown tool: {tool_name}"
            self.logger.error(error_msg)
            return f"Error: {error_msg}"

        try:
            if tool_name == "bash":
                # Extract bash tool parameters
                command = tool_input.get("command", "")
                restart = tool_input.get("restart", False)

                if not command and not restart:
                    return "Error: No command provided"

                # Execute the bash command
                result = self.tools["bash"].execute(command=command, restart=restart)

                # Format the output
                output_parts = []

                if result.get("stdout"):
                    output_parts.append(f"```\n{result['stdout']}\n```")

                if result.get("stderr"):
                    output_parts.append(f"**Error output:**\n```\n{result['stderr']}\n```")

                if result.get("error"):
                    output_parts.append(f"**Execution error:** {result['error']}")

                if result.get("exit_code", 0) != 0:
                    output_parts.append(f"**Exit code:** {result['exit_code']}")

                return "\n\n".join(output_parts) if output_parts else "Command executed successfully (no output)"

            elif tool_name == "slack":
                # Extract slack tool parameters
                operation = tool_input.get("operation")
                params = tool_input.get("params", {})

                if not operation:
                    return "Error: No operation specified"

                # Execute the slack operation
                result = self.tools["slack"].execute(operation=operation, params=params)

                # Format the output
                if "error" in result:
                    return f"**Error:** {result['error']}"

                # Format based on operation type
                if operation == "list_channels":
                    channels = result.get("channels", [])
                    output = f"Found {result.get('count', 0)} channels:\n\n"
                    for ch in channels[:20]:  # Limit to 20 for readability
                        output += f"• **{ch['name']}** (ID: {ch['id']})\n"
                        if ch.get("topic"):
                            output += f"  Topic: {ch['topic']}\n"
                    if len(channels) > 20:
                        output += f"\n... and {len(channels) - 20} more"
                    return output

                elif operation == "send_message":
                    return f"Message sent successfully to {result.get('channel', 'unknown')} (ts: {result.get('ts', '')})"

                elif operation in ["lookup_user", "get_user_info"]:
                    return (
                        f"**User:** {result.get('real_name', 'Unknown')} (@{result.get('name', '')})\n"
                        f"**Email:** {result.get('email', 'N/A')}\n"
                        f"**ID:** {result.get('id', 'N/A')}"
                    )

                elif operation == "get_channel_info":
                    return (
                        f"**Channel:** {result.get('name', 'Unknown')} (ID: {result.get('id', '')})\n"
                        f"**Private:** {result.get('is_private', False)}\n"
                        f"**Members:** {result.get('num_members', 0)}\n"
                        f"**Topic:** {result.get('topic', 'None')}"
                    )

                # Default formatting
                return str(result)

            # Default case for other tools
            return f"Tool {tool_name} not implemented"

        except Exception as e:
            error_msg = f"Failed to execute tool {tool_name}: {e}"
            self.logger.exception(error_msg)
            return f"Error: {error_msg}"

    def get_available_tools(self) -> Dict[str, str]:
        """Get a list of available tools and their descriptions.

        Returns:
            Dict mapping tool names to descriptions
        """
        tools = {"bash": "Execute bash commands with persistent session"}
        if "slack" in self.tools:
            tools["slack"] = "Interact with Slack workspace - list channels, send messages, lookup users"
        return tools

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get tool schemas for all registered tools.

        Returns:
            List of tool schemas in Anthropic's format
        """
        schemas = []
        for tool_name, tool_instance in self.tools.items():
            if hasattr(tool_instance, "get_schema"):
                schemas.append(tool_instance.get_schema())
        return schemas


__all__ = ["GraphQLClient", "LinearClient", "Bash", "Slack", "ToolRegistry"]
