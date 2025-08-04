from .assistant import create_assistant, handle_beast_command, handle_normal_command


def register(app, tool_registry):
    # Create assistant with tool registry
    assistant = create_assistant(tool_registry)
    
    app.assistant(assistant)
    # Register slash command handlers
    app.command("/beast")(handle_beast_command)
    app.command("/normal")(handle_normal_command)
