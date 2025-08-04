# Interleaved Thinking Integration

This document describes the implementation of Claude's interleaved thinking mode in the Slack bot, replacing the restricted Claude Code subprocess approach.

## Overview

The Slack bot now uses Claude's interleaved thinking API feature with custom tools instead of running Claude Code in a subprocess. This provides:

- **Better performance**: Native API calls instead of subprocess management
- **Cleaner architecture**: No complex session management or working directory manipulation
- **True sandboxing**: Tools define exactly what operations are allowed
- **Cost optimization**: Only pay for what you use

## Architecture

### Components

1. **Unified LLM Class** (`slack_hook/llm.py`)
   - `message_with_thinking()`: Always uses interleaved thinking mode
   - `message()`: Legacy method that redirects to `message_with_thinking()`
   - Consistent experience with optional tool usage

2. **Tool System** (`slack_hook/tools.py`)
   - Base `Tool` class for creating custom tools
   - `ToolRegistry` for managing available tools
   - Built-in tools:
     - `ReadProjectFile`: Read-only access to project files
     - `ManageScript`: Create/edit scripts in scripts/ directory
     - `LinearQuery`: Query Linear project management data

3. **Simplified Assistant** (`slack_hook/assistant.py`)
   - Always provides tools to the LLM
   - No routing logic needed - Claude decides when to use tools
   - Cleaner, more maintainable code

## Usage

### For Development (Offline)

Continue using Claude Code CLI directly:

```bash
cd /Users/gwo/Idea/lebot
claude
```

This gives you full access to the codebase for development tasks.

### For Slack Bot (Restricted Mode)

The bot always uses interleaved thinking mode with tools available. Claude intelligently decides when to use tools based on the request. No explicit detection logic needed - Claude handles it all.

## Implementation Details

### Interleaved Thinking API

```python
response = self.client.messages.create(
    model="claude-sonnet-4-20250514",
    messages=messages,
    tools=tools,
    extra_headers={"anthropic-beta": "interleaved-thinking-2025-05-14"},
    thinking={"type": "enabled", "budget_tokens": 8000},
)
```

### Tool Definition

```python
class ReadProjectFile(Tool):
    @property
    def name(self) -> str:
        return "read_project_file"
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path to file"}
            },
            "required": ["path"]
        }
```

### Tool Execution

When Claude uses a tool, the bot:
1. Receives a `ToolUseBlock` in the response
2. Executes the tool via the registry
3. Formats the result for Slack display

## Benefits

1. **No subprocess overhead**: Direct API calls are faster and more reliable
2. **Better error handling**: API errors are cleaner than subprocess failures
3. **Flexible tool system**: Easy to add new capabilities
4. **True sandboxing**: Tools explicitly define allowed operations
5. **Cost efficient**: Only uses advanced features when needed

## Future Enhancements

1. **Multi-turn tool conversations**: Allow Claude to use tool results and continue reasoning
2. **Streaming responses**: Stream long responses back to Slack
3. **Tool result caching**: Cache expensive operations like Linear queries
4. **Custom tool development**: Allow users to define their own tools