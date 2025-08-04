# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Slack Assistant Bot** called "lebot" that integrates with Anthropic's Claude API to provide AI assistance directly in Slack workspaces. The bot leverages Slack's Assistant features to create natural conversational interfaces.

Key features:
- **Slack Assistant Integration**: Uses Slack's native Assistant API for seamless user interactions
- **Claude API Integration**: Powered by Claude Sonnet 4 for intelligent responses
- **Tool Integration**: Extensible architecture supporting tools like Linear API for project management
- **OAuth Support**: Supports both Socket Mode and OAuth installation flows

The architecture follows: **User ↔ Slack Assistant ↔ LLM (Claude) ↔ Tools**

## Key Architecture Components

### Core Application Structure
- **`app.py`**: Main entry point for Socket Mode - initializes Slack Bolt app with Socket Mode handler
- **`app_oauth.py`**: Alternative entry point for OAuth flow - includes installation store and OAuth settings
- **`slack_hook/`**: Main module containing Slack event handlers and LLM integration
  - **`__init__.py`**: Registers the assistant with the Slack app
  - **`assistant.py`**: Implements Slack Assistant event handlers using decorators
  - **`llm.py`**: LLM integration layer with Claude API and markdown-to-Slack formatting

### Tools and Integrations
- **`tools/`**: Core tools and libraries for bot functionality
  - **`graphql.py`**: Generic GraphQL client and specialized Linear API client
    - `GraphQLClient`: Base class for GraphQL API interactions
    - `LinearClient`: Pre-configured client for Linear project management with built-in methods:
      - `test_connection()`: Validates API connectivity
      - `get_issues()`: Fetches issues with optional team filtering
      - `get_in_progress_issues()`: Fetches all "started" state issues
      - `get_issues_by_date_range()`: Date-filtered queries with full details and comments
      - `query()`: Execute custom GraphQL queries

### Testing
- **`tests/`**: Test suite for various components
  - **`test_graphql_client.py`**: Tests for GraphQL/Linear client functionality
  - **`test_date_filter.py`**: Tests for date filtering in Linear queries
  - **`test_simple.py`**: Basic unit tests

### Configuration Files
- **`manifest.json`**: Slack app manifest defining capabilities, scopes, and event subscriptions
- **`pyproject.toml`**: Python project configuration (Black formatter, pytest settings)
- **`requirements.txt`**: Python dependencies
- **`.env.example`**: Template for environment variables

## Development Commands

```bash
# Setup (first time only)
python3 -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate
pip install -r requirements.txt

# Run the bot (always activate venv first)
source .venv/bin/activate
python3 app.py
```

### Required Environment Variables
Create a `.env` file based on `.env.example`:
```bash
# Copy the example file
cp .env.example .env
```

#### For Socket Mode (app.py):
```bash
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
ANTHROPIC_API_KEY=sk-ant-api03-your-api-key
LINEAR_OAUTH_KEY=lin_api_your_key  # Optional: for Linear integration
```

#### For OAuth Mode (app_oauth.py):
```bash
SLACK_CLIENT_ID=your-client-id
SLACK_CLIENT_SECRET=your-client-secret
SLACK_SIGNING_SECRET=your-signing-secret
ANTHROPIC_API_KEY=sk-ant-api03-your-api-key
LINEAR_OAUTH_KEY=lin_api_your_key  # Optional: for Linear integration
```

### Code Quality
```bash
source .venv/bin/activate
flake8 *.py && flake8 slack_hook/ && flake8 tools/  # Lint
black .                                              # Format
pytest                                               # Test
```

### IDE Integration (MCP Tools)
When working with Claude Code in VS Code, the following MCP (Model Context Protocol) tools are available:

#### `mcp__ide__getDiagnostics`
- **Purpose**: Get language server diagnostics (type hints, linting errors, etc.) from VS Code
- **Usage**: Check for type hint warnings, syntax errors, and other code issues
- **Example**:
  ```python
  # Check diagnostics for a specific file
  mcp__ide__getDiagnostics(uri="file:///path/to/file.py")

  # Check diagnostics for all open files
  mcp__ide__getDiagnostics()
  ```
- **Benefits**:
  - Catches type hint incompatibilities
  - Identifies unused imports and variables
  - Detects syntax errors before runtime
  - Ensures code quality and type safety

## Important Implementation Details

### Slack App Configuration
- App manifest in `manifest.json` defines:
  - Assistant feature with custom description
  - Required OAuth scopes: `assistant:write`, `channels:join`, `im:history`, `channels:history`, `groups:history`, `chat:write`
  - Event subscriptions: `assistant_thread_started`, `assistant_thread_context_changed`, `message.im`
  - Socket Mode enabled by default (can use OAuth mode with `app_oauth.py`)
  - Interactivity enabled for button actions

### Message Flow
1. User opens a new assistant thread or sends a message
2. Slack triggers `@assistant.thread_started` or `@assistant.user_message` handlers
   - On thread start: Bot displays greeting with model selection buttons
   - Button clicks trigger `enable_beast_mode` or `enable_normal_mode` actions
3. Handler retrieves thread history via `conversations_replies` API
4. Messages are formatted as a conversation array (role: user/assistant)
   - Assistant messages are parsed to recover thinking blocks and tool uses
   - Tool results are properly separated into user messages with `tool_result` blocks
   - Thinking blocks are reordered to appear first (required by Claude's thinking mode)
5. `LLM.message()` sends conversation to Claude API with system prompt
6. Claude's response is processed:
   - Thinking blocks are displayed as quoted text with metadata
   - Text content is converted from markdown to Slack mrkdwn format
   - Tool uses trigger tool execution with results shown in attachments
7. If tools were used, the system automatically:
   - Sends tool results back to Claude
   - Processes any additional tool uses in follow-up responses
   - Continues until no more tools are needed (max 10 rounds)
8. Bot posts all responses back to the thread in real-time

### Code Formatting Configuration
- Black line length: 125 characters (configured in `pyproject.toml`)
- Pytest configuration includes debug logging to `logs/pytest.log`

## Linear Tools Usage

### Using LinearClient for GraphQL Queries
```python
from tools.graphql import LinearClient

# Initialize with Linear API key
linear = LinearClient('your_linear_api_key')

# Test connection
result = linear.test_connection()

# Get basic issues
issues = linear.get_issues(limit=50)
team_issues = linear.get_issues(team_id='team_uuid', limit=50)

# Get in-progress issues
in_progress = linear.get_in_progress_issues()

# Get issues by date range
from datetime import datetime, timedelta
end_date = datetime.now()
start_date = end_date - timedelta(days=7)
weekly_issues = linear.get_issues_by_date_range(
    start_date=start_date.strftime('%Y-%m-%d'),
    end_date=end_date.strftime('%Y-%m-%d'),
    team_id='team_uuid',  # optional
    limit=200
)

# Custom GraphQL queries
custom_query = """
query GetMyCustomData {
    issues(filter: { priority: { gte: 2 } }) {
        nodes {
            id
            title
            priority
        }
    }
}
"""
result = linear.query(custom_query)
```


### Important Notes
- **Linear API Docs**: https://linear.app/developers | [GraphQL Explorer](https://studio.apollographql.com/public/Linear-API/variant/current/explorer)
- Security: Store API keys in `.env` file (see `.env.example`), never commit to version control

## Assistant Implementation
- **Models**:
  - Default: Claude Sonnet 4 (`claude-sonnet-4-20250514`)
  - Beast Mode: Claude Opus 4 (`claude-opus-4-20250514`) - available via interactive buttons
- **Model Selection**: Interactive buttons in the initial greeting allow switching between models
  - Normal Mode button: Uses Claude Sonnet 4 (default, optimized for speed)
  - Beast Mode button: Activates Claude Opus 4 (maximum intelligence and capability)
  - Model preference is stored per thread and persists throughout the conversation
- **Features**:
  - Thread context with full conversation history
  - Status updates ("is thinking...", "using tool_name...", "processing tool results...")
  - Markdown to Slack mrkdwn conversion
  - Thinking mode with quoted text display and metadata tracking
  - Tool execution with bash commands (built-in)
  - Multi-round tool execution support (handles tools that use other tools)
  - Automatic error detection and color-coded tool results
- **Preserves**: Slack mentions `<@USER_ID>` and channels `<#CHANNEL_ID>`
- **Tool Results**: Auto-collapse in Slack when >700 chars or >5 lines

## Tool Architecture
- **Core Tools** (`tools/`): GraphQL client infrastructure
- **Scripts** (`scripts/`): Standalone executables for Linear analysis

## Future Architecture: Claude Code Integration

There is a comprehensive plan to enhance the Slack bot with Claude Code's advanced capabilities (file operations, code generation, script execution). This would transform the bot from a simple conversational assistant into a powerful development tool.

**See**: [`docs/claude-code-integration-architecture.md`](docs/claude-code-integration-architecture.md) for the detailed integration plan.

Key benefits of this architecture:
- Leverages Claude Code's existing capabilities instead of rebuilding them
- Enables dynamic script discovery and execution
- Maintains conversation context across Slack threads
- Provides safe, sandboxed execution environment
