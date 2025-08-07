# Lebot - AI-Powered Slack Assistant

A sophisticated Slack Assistant Bot that integrates with Anthropic's Claude API to provide intelligent AI assistance directly in Slack workspaces. Built with Python, Slack Bolt, and async architecture for high performance.

## Features

- **🤖 Slack Assistant Integration**: Native Slack Assistant API for seamless conversational interfaces
- **🧠 Claude AI Models**: 
  - **Normal Mode**: Claude Sonnet 4 (optimized for speed)
  - **Beast Mode**: Claude Opus 4 (maximum intelligence) - selectable via interactive buttons
- **🔧 Tool Integration**: Extensible architecture with built-in bash commands and Linear API integration
- **⚡ Real-time Streaming**: Async streaming responses with live status updates
- **💭 Thinking Mode**: Shows Claude's reasoning process with proper formatting
- **🛑 Emergency Stop**: Cancel long-running operations with stop button
- **📊 Linear Integration**: Query and manage Linear issues directly from Slack

## Quick Start

### Prerequisites
- Python 3.8+
- Slack workspace with admin permissions
- Anthropic API key
- Linear API key (optional)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/lebot.git
cd lebot
```

2. **Set up Python environment**
```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate
pip install -r requirements.txt
```

3. **Create Slack App**
   - Go to [api.slack.com/apps/new](https://api.slack.com/apps/new)
   - Choose "From an app manifest"
   - Copy contents of `manifest.json` and paste in the JSON tab
   - Click Create, then Install to Workspace

4. **Configure environment variables**
```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```bash
SLACK_BOT_TOKEN=xoxb-your-bot-token        # From OAuth & Permissions
SLACK_APP_TOKEN=xapp-your-app-token        # From Basic Information > App-Level Tokens
ANTHROPIC_API_KEY=sk-ant-api03-your-key    # From Anthropic Console
LINEAR_OAUTH_KEY=lin_api_your_key          # Optional: From Linear Settings
```

5. **Run the bot**

Using Slack CLI (recommended):
```bash
# Install Slack CLI if you haven't already
# Visit: https://api.slack.com/automation/cli/install

# Run the app with Slack CLI
slack run
```

Or run directly with Python:
```bash
python3 app.py
```

## Usage

1. **Start a conversation**: Click the ✨ Assistant button in any Slack channel or DM to start a new assistant thread
2. **Select AI model**: Use the interactive buttons in the greeting:
   - 🚀 **Normal Mode**: Fast responses with Claude Sonnet 4
   - 🦾 **Beast Mode**: Maximum capability with Claude Opus 4
3. **Ask questions**: Type naturally in the assistant thread - no @ mentions needed
4. **Use tools**: The bot can execute bash commands and query Linear issues

### Example Interactions

In an assistant thread, simply type:
```
Can you help me understand this Python error?
Show me all in-progress Linear issues
What issues were created this week?
Can you analyze our test coverage?
```

## Architecture

```
User ↔ Slack Assistant ↔ LLM (Claude) ↔ Tools
```

### Key Components

- **`app.py`**: Main entry point with async Slack Bolt app
- **`slack_hook/`**: Core Slack integration
  - `assistant.py`: Async event handlers with decorators
  - `claude.py`: Custom async Claude client with streaming
  - `conversation_manager.py`: Thread context management
  - `message_parser.py`: Parsing for thinking blocks and tool uses
- **`tools/`**: Extensible tool system
  - `graphql.py`: GraphQL client with Linear API integration

### Async Architecture

The entire application uses async/await for optimal performance:
- Non-blocking I/O operations
- Real-time streaming responses
- Concurrent tool execution
- Proper resource management

## Development

### Code Quality
```bash
# Linting
flake8 *.py && flake8 slack_hook/ && flake8 tools/

# Formatting (125 char line length)
black .

# Testing
pytest
```

### Linear API Usage

```python
from tools.graphql import LinearClient

# Initialize client
linear = LinearClient(os.getenv('LINEAR_OAUTH_KEY'))

# Get issues
issues = linear.get_issues(limit=50)
in_progress = linear.get_in_progress_issues()

# Query by date
from datetime import datetime, timedelta
weekly_issues = linear.get_issues_by_date_range(
    start_date=(datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
    end_date=datetime.now().strftime('%Y-%m-%d')
)
```

## Configuration

### Slack App Manifest
The `manifest.json` defines:
- Assistant feature with custom description
- Required OAuth scopes
- Event subscriptions
- Socket Mode configuration

### Environment Variables
See `.env.example` for all available options:
- `SLACK_BOT_TOKEN`: Bot user OAuth token
- `SLACK_APP_TOKEN`: App-level token for Socket Mode
- `ANTHROPIC_API_KEY`: Claude API key
- `LINEAR_OAUTH_KEY`: Linear API key (optional)

## Future Enhancements

See [`docs/claude-code-integration-architecture.md`](docs/claude-code-integration-architecture.md) for planned Claude Code integration that would add:
- File operations and code generation
- Dynamic script discovery and execution
- Sandboxed development environment
- Enhanced tool capabilities

## Troubleshooting

### Common Issues

1. **Bot not responding**: Check Socket Mode connection and app tokens
2. **Linear integration failing**: Verify API key and permissions
3. **Streaming issues**: Ensure async handlers are properly awaited
4. **Type errors**: Run `flake8` to check for type hint issues

### Debug Mode
Enable debug logging by setting:
```bash
export DEBUG=true
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Run tests and linting
4. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

- [Slack API Documentation](https://api.slack.com)
- [Anthropic Claude Documentation](https://docs.anthropic.com)
- [Linear API Documentation](https://linear.app/developers)

## Security

- Store all API keys in `.env` file
- Never commit credentials to version control
- Use environment variables for all sensitive data
- Review `manifest.json` OAuth scopes before deployment