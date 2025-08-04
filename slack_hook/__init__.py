from .assistant import assistant, handle_beast_command, handle_normal_command


def register(app):
    app.assistant(assistant)
    # Register slash command handlers
    app.command("/beast")(handle_beast_command)
    app.command("/normal")(handle_normal_command)
