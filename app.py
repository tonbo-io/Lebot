import os
import logging
from dotenv import load_dotenv

# Load environment variables before any other imports
load_dotenv()

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from slack_hook import register
from tools import ToolRegistry

# Initialization
logging.basicConfig(level=logging.DEBUG)
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

# Initialize ToolRegistry with Slack client
tool_registry = ToolRegistry(slack_client=app.client)

# Register Listeners
register(app, tool_registry)

# Start Bolt app
if __name__ == "__main__":
    SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN")).start()
