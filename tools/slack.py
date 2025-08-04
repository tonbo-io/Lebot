import logging
from typing import Dict, Any
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from .base import Tool


class Slack(Tool):
    """Unified Slack tool for workspace interactions."""

    def __init__(self, client: WebClient):
        """Initialize the Slack tool with a WebClient instance.

        Args:
            client: Slack WebClient instance
        """
        self.client = client
        self.logger = logging.getLogger(__name__)

    def get_schema(self) -> Dict[str, Any]:
        """Return the Slack tool schema for Anthropic's API."""
        return {
            "type": "custom",
            "name": "slack",
            "description": "Interact with Slack workspace - list channels, send messages, lookup users",
            "input_schema": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["list_channels", "send_message", "lookup_user", "get_channel_info", "get_user_info"],
                        "description": "The Slack operation to perform",
                    },
                    "params": {
                        "type": "object",
                        "description": "Parameters specific to each operation",
                        "properties": {
                            "include_private": {
                                "type": "boolean",
                                "description": "Include private channels (for list_channels)",
                            },
                            "pattern": {"type": "string", "description": "Filter pattern (for list_channels)"},
                            "channel": {"type": "string", "description": "Channel name or ID (for send_message)"},
                            "user": {
                                "type": "string",
                                "description": "User email, ID, or name (for send_message, lookup_user)",
                            },
                            "text": {"type": "string", "description": "Message text (for send_message)"},
                            "thread_ts": {
                                "type": "string",
                                "description": "Thread timestamp for replies (for send_message)",
                            },
                            "channel_id": {"type": "string", "description": "Channel ID (for get_channel_info)"},
                            "user_id": {"type": "string", "description": "User ID (for get_user_info)"},
                            "email": {"type": "string", "description": "User email (for lookup_user)"},
                            "name": {"type": "string", "description": "User name (for lookup_user)"},
                        },
                    },
                },
                "required": ["operation"],
            },
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute a Slack operation based on the operation name.

        Args:
            **kwargs: Keyword arguments:
                - operation (str): The operation to perform
                - params (Dict[str, Any]): Parameters for the operation

        Returns:
            Dict with the operation result
        """
        operation = kwargs.get("operation", "")
        params = kwargs.get("params", {})
        operations = {
            "list_channels": self._list_channels,
            "get_channel_info": self._get_channel_info,
            "send_message": self._send_message,
            "lookup_user": self._lookup_user,
            "get_user_info": self._get_user_info,
        }

        if operation not in operations:
            return {"error": f"Unknown operation: {operation}"}

        try:
            return operations[operation](params)
        except SlackApiError as e:
            self.logger.error(f"Slack API error: {e}")
            return {"error": f"Slack API error: {e.response['error']}"}
        except Exception as e:
            self.logger.exception(f"Failed to execute Slack operation {operation}: {e}")
            return {"error": f"Failed to execute operation: {str(e)}"}

    def _list_channels(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List channels in the workspace.

        Args:
            params: Dict with optional keys:
                - include_private (bool): Include private channels
                - pattern (str): Filter channels by name pattern

        Returns:
            Dict with channels list or error
        """
        include_private = params.get("include_private", False)
        pattern = params.get("pattern", "").lower()

        try:
            # Get all public channels (and private if requested)
            types = "public_channel"
            if include_private:
                types = "public_channel,private_channel"

            response = self.client.conversations_list(
                types=types,
                exclude_archived=True,
                limit=1000,
            )

            channels = []
            for channel in response.get("channels", []):
                # Filter by pattern if provided
                if pattern and pattern not in channel["name"].lower():
                    continue

                channels.append(
                    {
                        "id": channel["id"],
                        "name": channel["name"],
                        "is_private": channel.get("is_private", False),
                        "num_members": channel.get("num_members", 0),
                        "topic": channel.get("topic", {}).get("value", ""),
                        "purpose": channel.get("purpose", {}).get("value", ""),
                    }
                )

            return {
                "channels": channels,
                "count": len(channels),
                "total_available": response.get("response_metadata", {}).get("next_cursor") is not None,
            }

        except SlackApiError:
            raise

    def _get_channel_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed information about a channel.

        Args:
            params: Dict with required key:
                - channel_id (str): The channel ID

        Returns:
            Dict with channel info or error
        """
        channel_id = params.get("channel_id")
        if not channel_id:
            return {"error": "channel_id is required"}

        try:
            response = self.client.conversations_info(channel=channel_id)
            if not response:
                return {"error": "Failed to get channel info"}

            # Type guard: ensure channel exists
            if "channel" not in response:
                return {"error": "No channel data in response"}

            channel = response["channel"]
            if not channel:
                return {"error": "Channel data is empty"}

            # Get nested topic and purpose values safely
            topic_obj = channel.get("topic")
            topic_value = topic_obj.get("value", "") if isinstance(topic_obj, dict) else ""
            purpose_obj = channel.get("purpose")
            purpose_value = purpose_obj.get("value", "") if isinstance(purpose_obj, dict) else ""

            return {
                "id": channel.get("id", ""),
                "name": channel.get("name", ""),
                "is_private": channel.get("is_private", False),
                "is_archived": channel.get("is_archived", False),
                "created": channel.get("created", 0),
                "creator": channel.get("creator", ""),
                "topic": topic_value,
                "purpose": purpose_value,
                "num_members": channel.get("num_members", 0),
            }

        except SlackApiError:
            raise

    def _send_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send a message to a channel or user.

        Args:
            params: Dict with keys:
                - channel (str): Channel name/ID (optional if user is provided)
                - user (str): User email or ID (optional if channel is provided)
                - text (str): Message text (required)
                - thread_ts (str): Thread timestamp for replies (optional)

        Returns:
            Dict with message info or error
        """
        channel = params.get("channel")
        user = params.get("user")
        text = params.get("text", "")
        thread_ts = params.get("thread_ts")

        if not text:
            return {"error": "text is required"}

        if not channel and not user:
            return {"error": "Either channel or user must be provided"}

        try:
            # Determine the target
            target = None

            if channel:
                # Handle channel name with or without #
                if channel.startswith("#"):
                    channel = channel[1:]
                # Try to find the channel
                channels_response = self.client.conversations_list(types="public_channel,private_channel")
                for ch in channels_response.get("channels", []):
                    if ch["name"] == channel or ch["id"] == channel:
                        target = ch["id"]
                        break
                if not target:
                    return {"error": f"Channel '{channel}' not found"}

            elif user:
                # Look up user by email or ID
                if "@" in user:
                    # It's an email
                    users_response = self.client.users_lookupByEmail(email=user)
                    if users_response and "user" in users_response:
                        user_data = users_response["user"]
                        if user_data:
                            target = user_data["id"]
                else:
                    # It might be a user ID or display name
                    if user.startswith("U"):
                        # Looks like a user ID
                        target = user
                    else:
                        # Try to find by display name
                        users_response = self.client.users_list()
                        for u in users_response.get("members", []):
                            if u.get("real_name", "").lower() == user.lower() or u.get("name", "").lower() == user.lower():
                                target = u["id"]
                                break
                        if not target:
                            return {"error": f"User '{user}' not found"}

                # For DMs, we need to open a conversation first
                if target:
                    dm_response = self.client.conversations_open(users=target)
                    if dm_response and "channel" in dm_response:
                        channel_data = dm_response["channel"]
                        if channel_data:
                            target = channel_data["id"]

            # Send the message
            if not target:
                return {"error": "Could not determine target channel or user"}
            response = self.client.chat_postMessage(channel=target, text=text, thread_ts=thread_ts)

            return {
                "ok": response["ok"],
                "channel": response["channel"],
                "ts": response["ts"],
                "message": {"text": text, "thread_ts": thread_ts},
            }

        except SlackApiError:
            raise

    def _lookup_user(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Look up a user by email or name.

        Args:
            params: Dict with optional keys:
                - email (str): User's email
                - name (str): User's display name or username

        Returns:
            Dict with user info or error
        """
        email = params.get("email")
        name = params.get("name", "").lower()

        if not email and not name:
            return {"error": "Either email or name must be provided"}

        try:
            if email:
                # Direct lookup by email
                response = self.client.users_lookupByEmail(email=email)
                if response and "user" in response:
                    user = response["user"]
                    if user:
                        return self._format_user_info(user)
                return {"error": "User not found"}

            else:
                # Search by name
                response = self.client.users_list()
                for user in response.get("members", []):
                    if user.get("deleted", False) or user.get("is_bot", False):
                        continue

                    if (
                        user.get("real_name", "").lower() == name
                        or user.get("name", "").lower() == name
                        or user.get("profile", {}).get("display_name", "").lower() == name
                    ):
                        return self._format_user_info(user)

                return {"error": f"User with name '{params.get('name')}' not found"}

        except SlackApiError:
            raise

    def _get_user_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get detailed information about a user.

        Args:
            params: Dict with required key:
                - user_id (str): The user ID

        Returns:
            Dict with user info or error
        """
        user_id = params.get("user_id")
        if not user_id:
            return {"error": "user_id is required"}

        try:
            response = self.client.users_info(user=user_id)
            if response and "user" in response:
                user = response["user"]
                if user:
                    return self._format_user_info(user)
            return {"error": "User not found"}

        except SlackApiError:
            raise

    def _format_user_info(self, user: Dict[str, Any]) -> Dict[str, Any]:
        """Format user information consistently.

        Args:
            user: Raw user data from Slack API

        Returns:
            Formatted user info dict
        """
        profile = user.get("profile", {})
        return {
            "id": user["id"],
            "name": user.get("name", ""),
            "real_name": user.get("real_name", ""),
            "display_name": profile.get("display_name", ""),
            "email": profile.get("email", ""),
            "is_admin": user.get("is_admin", False),
            "is_owner": user.get("is_owner", False),
            "is_bot": user.get("is_bot", False),
            "status_text": profile.get("status_text", ""),
            "status_emoji": profile.get("status_emoji", ""),
            "tz": user.get("tz", ""),
        }
