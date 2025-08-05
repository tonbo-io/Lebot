"""Async hook registration for Slack app with conversation management."""

from .assistant import (
    create_assistant,
    create_beast_mode_handler,
    create_normal_mode_handler,
    create_emergency_stop_handler,
)
from .conversation_manager import ConversationManager
from .message_parser import parse_assistant_message
from .claude import AsyncClaude


async def register_async(app, tool_registry):
    """Register async handlers with the Slack app.

    Args:
        app: AsyncApp instance
        tool_registry: ToolRegistry instance
    """
    # Initialize components
    llm = AsyncClaude()
    conversation_manager = ConversationManager(parse_assistant_message)

    # Start conversation manager
    await conversation_manager.start()

    # Create assistant with dependencies
    assistant = create_assistant(tool_registry, conversation_manager, llm)

    # Register assistant
    app.assistant(assistant)

    # Register button handlers with conversation manager
    app.action("enable_beast_mode")(create_beast_mode_handler(conversation_manager))
    app.action("enable_normal_mode")(create_normal_mode_handler(conversation_manager))
    app.action("emergency_stop")(create_emergency_stop_handler(conversation_manager))

    # Store conversation manager for cleanup on shutdown
    app._conversation_manager = conversation_manager

    return conversation_manager
