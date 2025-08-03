# Slack Bot + Claude Code Integration Architecture

## Overview

This document outlines the architecture for integrating Claude Code as the execution engine for the Slack bot, enabling advanced code generation, file operations, and script execution capabilities within Slack conversations.

## Motivation

Rather than rebuilding Claude Code's capabilities from scratch (file access, script execution, code modification, tool usage), we leverage Claude Code directly as a service. This approach:

- Utilizes battle-tested, optimized code from Anthropic
- Maintains safety features and sandboxing
- Reduces maintenance burden
- Provides immediate access to all Claude Code features

## Architecture Design

### Core Components

```
┌─────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  Slack User │────▶│   Slack Bot      │────▶│  Claude Code    │
│             │◀────│   (Interface)    │◀────│  (Execution)    │
└─────────────┘      └──────────────────┘      └─────────────────┘
                            │                          │
                            ▼                         ▼
                     ┌───────────────┐          ┌──────────────┐
                     │ Context Store │          │   Scripts/   │
                     │   (Redis)     │          │    Tools     │
                     └───────────────┘          └──────────────┘
```

### Component Descriptions

1. **Slack Bot (Interface Layer)**
   - Receives messages from Slack users
   - Routes requests to appropriate handler (Claude API or Claude Code)
   - Formats responses for Slack display
   - Manages conversation threading

2. **Claude Code (Execution Layer)**
   - Handles code generation, file operations, script execution
   - Accesses the scripts/ directory for tool usage
   - Maintains conversation context
   - Executes in sandboxed environment

3. **Context Store**
   - Maps Slack thread IDs to Claude Code conversation IDs
   - Stores conversation history for context
   - Enables multi-turn interactions
   - Handles session cleanup

4. **Scripts/Tools Directory**
   - Contains executable Python scripts
   - Self-documenting with docstrings
   - Dynamically discoverable by Claude Code
   - No rigid schema definitions needed

## Dual-Role Architecture via Working Directory

Claude Code reads `CLAUDE.md` from the top-level directory where it's launched. This enables elegant role separation:

### 1. **Restricted Mode (via Slack Bot)**
```python
class ClaudeCodeExecutor:
    def execute(self, thread_id: str, prompt: str) -> str:
        # Launch Claude Code from scripts/ directory
        # It will read scripts/CLAUDE.md with restrictions
        subprocess.run(["claude", prompt], cwd="scripts/")
```
- **Working Directory**: `scripts/`
- **Context File**: `scripts/CLAUDE.md` (restricted instructions)
- **Permissions**: Can only create/modify files in `scripts/`
- **Can read**: Parent project files using `../` paths

### 2. **Developer Mode (via Terminal)**
```bash
# Launch from project root
cd /Users/gwo/Idea/lebot
claude
```
- **Working Directory**: Project root
- **Context File**: `CLAUDE.md` (full access instructions)
- **Permissions**: Full project access

### File Structure
```
/Users/gwo/Idea/lebot/
├── CLAUDE.md           # Full access (for dev mode)
├── scripts/
│   ├── CLAUDE.md       # Restricted access (for Slack bot)
│   └── *.py            # User-generated scripts
└── ...
```

This approach is:
- **Simple**: No file swapping or complex logic
- **Secure**: Claude Code's built-in behavior enforces boundaries
- **Reliable**: Based on working directory, not prompt engineering

## Implementation Plan

### Phase 1: Claude Code Executor Service

**File**: `claude_code_executor.py`

```python
class ClaudeCodeExecutor:
    """Manages Claude Code sessions using the Python SDK.

    IMPORTANT: This executor initializes Claude Code with scripts/ as the
    working directory, which contains its own CLAUDE.md with restricted
    permissions. This ensures Slack users can only modify files within
    the scripts/ directory.
    """

    def __init__(self, workspace_path: str, model: str = "opus-4"):
        self.workspace_path = workspace_path
        self.scripts_dir = os.path.join(workspace_path, "scripts")
        self.model = model
        self.sessions = {}  # thread_id -> ClaudeCodeSession

    async def execute(self, thread_id: str, prompt: str) -> str:
        """Execute a prompt in Claude Code and return the response.

        Uses the Claude Code Python SDK with scripts/ as working directory,
        causing it to read scripts/CLAUDE.md which enforces restrictions.
        """
        from claude_code import ClaudeCodeSession

        # Get or create session for this thread
        if thread_id not in self.sessions:
            self.sessions[thread_id] = ClaudeCodeSession(
                model=self.model,
                working_directory=self.scripts_dir  # Restricted to scripts/
            )

        session = self.sessions[thread_id]
        response = await session.send_message(prompt)
        return response.content

    def cleanup_session(self, thread_id: str):
        """Clean up Claude Code session for a thread."""
        if thread_id in self.sessions:
            self.sessions[thread_id].close()
            del self.sessions[thread_id]
```

Key features:
- **Uses Python SDK** for better integration and control
- **Restricted mode via working directory**: scripts/CLAUDE.md enforces limitations
- **Session management**: Maintains separate sessions per Slack thread
- **Async support**: Non-blocking execution for better performance
- **Dual-role architecture**:
  - Slack bot → working dir: `scripts/` (restricted)
  - Terminal → working dir: project root (full access)

### Phase 2: Slack Bot Enhancement

**Updates to**: `slack_hook/assistant.py`

1. **Request Classification**
   ```python
   def should_use_claude_code(message: str) -> bool:
       """Determine if request should be routed to Claude Code."""
       code_indicators = [
           "create a script",
           "write code",
           "modify the file",
           "run the script",
           "analyze the codebase",
           "git commit",
           "execute",
           "implement"
       ]
       return any(indicator in message.lower() for indicator in code_indicators)
   ```

2. **Request Routing**
   ```python
   if should_use_claude_code(user_message):
       response = claude_code_executor.execute(thread_id, user_message)
   else:
       response = llm_caller.call_llm(set_status, messages_in_thread)
   ```

### Phase 3: Context Management

**File**: `context_manager.py`

```python
class ContextManager:
    """Manages conversation context between Slack and Claude Code."""

    def __init__(self, redis_client):
        self.redis = redis_client

    def save_context(self, thread_id: str, messages: List[Dict]):
        """Save conversation context for a thread."""
        # Implementation...

    def get_context(self, thread_id: str) -> List[Dict]:
        """Retrieve conversation context for a thread."""
        # Implementation...

    def map_thread_to_session(self, thread_id: str, session_id: str):
        """Map Slack thread to Claude Code session."""
        # Implementation...
```

### Phase 4: Output Processing

**File**: `output_formatter.py`

```python
class OutputFormatter:
    """Formats Claude Code output for Slack display."""

    @staticmethod
    def format_for_slack(claude_output: str) -> str:
        """Convert Claude Code output to Slack mrkdwn format."""
        # Handle code blocks: ```language -> ```
        # Handle file paths: /path/to/file -> `file`
        # Handle long outputs: truncate with "Show more..."
        # Convert terminal colors to emoji indicators
        return formatted_output

    @staticmethod
    def chunk_response(response: str, max_length: int = 3000) -> List[str]:
        """Split long responses into Slack-friendly chunks."""
        # Implementation...
```

## Request Flow Examples

### Example 1: Simple Question
```
User: "What's the difference between async and sync in Python?"
Flow: Slack → Bot → Claude API → Response → Slack
Decision: No code execution needed, use standard Claude API
```

### Example 2: Code Generation
```
User: "Create a script to analyze our Linear issues from last week"
Flow: Slack → Bot → Claude Code → Creates script → Tests it → Response → Slack
Decision: Requires file creation and execution, use Claude Code
```

### Example 3: Multi-turn Coding
```
User: "Now add a feature to export the results to CSV"
Flow: Slack → Bot → Context Lookup → Claude Code (existing session) → Modifies script → Response → Slack
Decision: Continues existing Claude Code session with context
```

## Configuration

### Environment Variables

```bash
# Claude Code Configuration
CLAUDE_CODE_PATH=/usr/local/bin/claude      # Path to Claude Code CLI
CLAUDE_CODE_MODEL=opus-4                     # Model to use
CLAUDE_CODE_TIMEOUT=300                      # Max execution time (seconds)
CLAUDE_CODE_MAX_MEMORY=1GB                   # Memory limit
WORKSPACE_PATH=/opt/slack-bot/workspace      # Working directory for Claude Code

# Context Storage
REDIS_URL=redis://localhost:6379/0           # Redis for context storage
CONTEXT_TTL=3600                             # Context expiry (seconds)

# Existing Configuration
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
ANTHROPIC_API_KEY=sk-ant-api03-...
```

### Claude Code Settings

Create `.claude/settings.json` in the workspace:
```json
{
  "model": "opus-4",
  "tools": {
    "enabled": true,
    "directory": "./scripts"
  },
  "safety": {
    "file_operations": "sandbox",
    "network_access": "restricted"
  }
}
```

## Security Considerations

1. **Sandboxing**
   - Claude Code runs in isolated environment
   - Limited file system access (workspace only)
   - Network restrictions

2. **Resource Limits**
   - CPU time limits per request
   - Memory usage caps
   - Output size restrictions

3. **Authentication**
   - Slack app verification
   - User permission checks
   - API key management

4. **Audit Trail**
   - Log all Claude Code executions
   - Track file modifications
   - Monitor resource usage

## Deployment Considerations

### Docker Deployment
```dockerfile
FROM python:3.11-slim

# Install Claude Code CLI
RUN curl -fsSL https://claude.ai/install.sh | sh

# Install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application code
COPY . /app
WORKDIR /app

# Create workspace directory
RUN mkdir -p /workspace

CMD ["python", "app.py"]
```

### Monitoring

1. **Metrics to Track**
   - Request routing (Claude API vs Claude Code)
   - Claude Code execution time
   - Error rates
   - Resource usage

2. **Alerts**
   - Failed Claude Code executions
   - Timeout errors
   - High resource usage
   - Context storage issues

## Future Enhancements

1. **Advanced Features**
   - Scheduled script execution
   - Collaborative coding sessions
   - Git integration for version control
   - Custom tool development workflow

2. **Performance Optimizations**
   - Claude Code instance pooling
   - Predictive session management
   - Output caching

3. **User Experience**
   - Interactive code editing
   - Progress indicators for long operations
   - Rich media responses (images, charts)

## Migration Path

1. **Phase 1**: Deploy Claude Code executor alongside existing bot
2. **Phase 2**: Route select requests to Claude Code (opt-in)
3. **Phase 3**: Expand routing logic based on usage patterns
4. **Phase 4**: Full integration with fallback to Claude API

## Conclusion

This architecture leverages Claude Code's powerful capabilities while maintaining a simple Slack interface. By treating Claude Code as a service rather than rebuilding its features, we achieve a robust, maintainable solution that can evolve with user needs.
