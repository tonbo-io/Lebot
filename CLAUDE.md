# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Generic AI Agent Platform** called "lebot" that enables Claude Code to work as an AI agent through Slack, with dynamic tool creation and usage capabilities. The platform consists of:

1. **Core AI Agent**: Generic agent that can use and create tools dynamically
2. **Slack Interface**: User interaction layer via Slack bot
3. **Modular Tools**: Extensible tool ecosystem (Linear API, GitHub, databases, custom tools)

The architecture follows the pattern: **User ↔ Slack ↔ AI Agent ↔ Tools**

## Key Architecture Components

### Core Application Structure
- **`app.py`**: Main entry point that initializes the Slack Bolt app and starts the SocketModeHandler
- **`listeners/`**: Contains all event listeners and handlers organized by Slack Platform features
- **`listeners/assistant.py`**: Primary assistant implementation using Slack's Assistant middleware (recommended approach)
- **`listeners/events/`**: Alternative event-driven implementation (for reference/educational purposes)

### LLM Integration
- **`listeners/llm_caller.py`**: Contains `LLMCaller` class that handles communication with Anthropic's Claude API
- The class encapsulates API client initialization, message processing, and markdown-to-Slack formatting conversion
- Uses Claude Sonnet 4 model by default with configurable system prompts

### GraphQL Client
- **`graphql_client.py`**: Simple GraphQL client module for HTTP requests to GraphQL endpoints
- **`GraphQLClient`**: Generic GraphQL client that uses requests library with JSON format support
- **`LinearClient`**: Specialized client for Linear API with pre-configured endpoints and helper methods
- Supports query variables, error handling, and authentication
- Used for integrating with Linear's project management data

### Assistant Implementation Pattern
The codebase provides two approaches:
1. **Assistant Middleware** (recommended): Uses `@assistant.thread_started` and `@assistant.user_message` decorators
2. **Event Listeners** (educational): Manual event handling for `assistant_thread_started`, `assistant_thread_context_changed`, and `message` events

## Development Commands

### IMPORTANT: Always Activate Virtual Environment First
```bash
# ALWAYS activate the virtual environment before running any Python commands
source .venv/bin/activate  # On Windows: .\.venv\Scripts\Activate
```

### Setup and Installation
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .\.venv\Scripts\Activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Application
```bash
# ALWAYS activate virtual environment first
source .venv/bin/activate

# Start the bot (requires environment variables set)
python3 app.py
```

### Required Environment Variables
Create a `.env` file based on `.env.example`:
```bash
# Copy the example file
cp .env.example .env

# Edit the .env file with your actual tokens
SLACK_BOT_TOKEN=<your-bot-token>
SLACK_APP_TOKEN=<your-app-token>
ANTHROPIC_API_KEY=<your-anthropic-api-key>
LINEAR_API_KEY=<your-linear-api-key>  # Optional: for Linear integration
```

### Code Quality Commands
```bash
# ALWAYS activate virtual environment first
source .venv/bin/activate

# Linting
flake8 *.py

# Code formatting
black .

# Testing
pytest
```

## Important Implementation Details

### Slack App Configuration
- App manifest is defined in `manifest.json` with assistant features enabled
- Requires `assistant:write`, `channels:join`, `im:history`, `channels:history`, `groups:history`, and `chat:write` scopes
- Uses Socket Mode for real-time communication

### Message Flow
1. User sends message in assistant thread
2. `assistant.py` retrieves conversation history using `conversations_replies`
3. Messages are formatted and sent to `LLMCaller.call_llm()`
4. Claude API processes the request with system prompt
5. Response is converted from markdown to Slack mrkdwn format
6. Bot responds in the thread

### Code Formatting Configuration
- Black line length: 125 characters (configured in `pyproject.toml`)
- Pytest configuration includes debug logging to `logs/pytest.log`

## GraphQL Client Usage

### Basic Usage
```python
from graphql_client import LinearClient

# Initialize with Linear API key
linear = LinearClient('your_linear_api_key')

# Test connection
result = linear.test_connection()

# Get all issues
issues = linear.get_issues()

# Get issues for specific team
team_issues = linear.get_issues(team_id='team_uuid')

# Get teams
teams = linear.get_teams()

# Create new issue
new_issue = linear.create_issue(
    team_id='team_uuid',
    title='New issue',
    description='Description here',
    priority=2
)
```

### Important Notes
- Linear API keys should NOT include "Bearer" prefix in Authorization header
- Use team IDs (UUIDs) for filtering, not team keys
- The client handles JSON format HTTP queries and GraphQL variables automatically

## Security Considerations

- API keys are loaded from environment variables using python-dotenv for secure configuration
- Create a `.env` file (not committed to version control) with your actual API keys
- The `.env.example` file shows the required environment variables without exposing sensitive data
- Linear API keys should be stored securely and not committed to version control
