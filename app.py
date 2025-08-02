import os
import logging
from dotenv import load_dotenv

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from slack_hook import register

# Load environment variables
load_dotenv()

# Initialization
logging.basicConfig(level=logging.DEBUG)
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

# Register Listeners
register(app)

# Start Bolt app
if __name__ == "__main__":
    SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN")).start()
