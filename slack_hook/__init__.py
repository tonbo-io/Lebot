from .assistant import create_assistant, handle_beast_mode_button, handle_normal_mode_button


def register(app, tool_registry):
    # Create assistant with tool registry
    assistant = create_assistant(tool_registry)

    app.assistant(assistant)
    # Register button action handlers
    app.action("enable_beast_mode")(handle_beast_mode_button)
    app.action("enable_normal_mode")(handle_normal_mode_button)
