import os
import logging
import asyncio
import signal
from dotenv import load_dotenv

# Load environment variables before any other imports
load_dotenv()

from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.app.async_app import AsyncApp

from slack_hook.hook import register_async
from tools import ToolRegistry


class LebotApp:
    """Main application class that manages the async Slack app and conversation manager."""

    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        # Initialize Slack app
        self.app = AsyncApp(token=os.environ.get("SLACK_BOT_TOKEN"))

        # Initialize ToolRegistry with Slack client
        self.tool_registry = ToolRegistry(slack_client=self.app.client)

        # Conversation manager will be set during registration
        self.conversation_manager = None

        # Socket mode handler
        self.handler = None

    async def start(self):
        """Start the application."""
        # Register listeners and get conversation manager
        self.conversation_manager = await register_async(self.app, self.tool_registry)

        # Create socket mode handler
        self.handler = AsyncSocketModeHandler(self.app, os.environ.get("SLACK_APP_TOKEN"))

        # Setup signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))

        try:
            self.logger.info("Starting Lebot...")
            await self.handler.start_async()
        except Exception as e:
            self.logger.error(f"Error during operation: {e}")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Gracefully shutdown the application."""
        self.logger.info("Performing graceful shutdown...")

        # Stop conversation manager
        if self.conversation_manager:
            await self.conversation_manager.stop()
            self.logger.info("Conversation manager stopped")

        # Stop socket mode handler
        if self.handler:
            await self.handler.close_async()
            self.logger.info("Socket mode handler closed")

        self.logger.info("Shutdown complete")


async def main():
    """Main entry point."""
    app = LebotApp()
    await app.start()


if __name__ == "__main__":
    asyncio.run(main())
