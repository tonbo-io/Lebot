from .assistant import assistant


def register(app):
    app.assistant(assistant)
