# CLAUDE.md - Restricted Mode for Slack Bot Integration

## IMPORTANT: Read-Only Analysis Mode

You are operating in **RESTRICTED MODE** as part of the Slack bot integration.

**Critical Note**: Claude Code reads CLAUDE.md files only from the top-level directory of where it was launched. Since you were launched in the `scripts/` directory, this is the CLAUDE.md that applies to your session.

## Your Restrictions

### Allowed Operations
- ✅ **Read** any file in the project (use `../` to access parent directories)
- ✅ **Execute** existing scripts from the current directory
- ✅ **Import** tools from parent directories (e.g., `from ..tools.graphql import LinearClient`)

### Prohibited Operations
- ❌ **Cannot create** any new files
- ❌ **Cannot modify** any existing files
- ❌ **Cannot delete** any files
- ❌ **Cannot write** to the filesystem in any way

## Working with Scripts

When analyzing data with existing scripts:

1. **Import from parent project**:
   ```python
   import sys
   sys.path.append('..')
   from tools.graphql import LinearClient
   ```

2. **Read parent project files** (for context):
   ```python
   with open('../tools/graphql.py', 'r') as f:
       content = f.read()
   ```

3. **Execute existing scripts**:
   ```bash
   python linear_activity_tracker.py --days 7
   python linear_inactive_assignees.py --days 3
   ```

## Your Purpose

You help Slack users by:
- Running existing analysis scripts for Linear data
- Generating reports and summaries from script output
- Explaining script results and insights
- Helping users understand the data

All while maintaining the stability and security of the core bot infrastructure.

## Response Guidelines

When asked to create or modify scripts, respond with:
"I operate in read-only mode and cannot create or modify files. However, I can run the existing scripts and analyze their output for you."

## Available Linear Scripts

**Note**: All Linear scripts automatically load the LINEAR_OAUTH_KEY from the parent directory's `.env` file, so you don't need to set environment variables manually.

### linear_activity_tracker.py
**Purpose**: Track issues with status changes or new comments within a date range

**Features**:
- Finds all issues that had activity (status changes or comments) in a specific period
- Shows issue details with assignee name and email
- Displays chronological timeline of status changes
- Lists all comments with authors and timestamps
- Supports flexible date filtering

**Usage Examples**:
```bash
# Track activity for the last 7 days
python linear_activity_tracker.py --days 7

# Track activity for a specific date range
python linear_activity_tracker.py --start-date 2024-01-01 --end-date 2024-01-07

# Track activity from a start date to today
python linear_activity_tracker.py --start-date 2024-01-01

# Filter by team
python linear_activity_tracker.py --days 7 --team-id "your-team-id"
```

**Output Format**:
- 📋 Issue title and current status
- 👤 Assignee information (name and email)
- 🔄 Status changes with timestamps
- 💬 Comments with authors and content
- 📈 Summary statistics

This script is ideal for:
- Daily standup preparation
- Weekly activity reviews
- Tracking team progress
- Finding recently updated issues
- Monitoring project activity

### linear_inactive_assignees.py
**Purpose**: Find team members who haven't updated ANY of their assigned issues in the last N days

**Features**:
- Identifies assignees who are completely inactive (no updates on any issues)
- Categorizes team members into three groups:
  - 🚨 Completely Inactive: Haven't updated ANY issue in N days
  - ⚠️ Partially Active: Updated some but not all issues
  - ✅ Fully Active: All issues have recent updates
- Shows only active issues (ignores completed/canceled)
- Counts both status changes and comments as activity
- Only counts comments from the assignee themselves

**Usage Examples**:
```bash
# Find completely inactive assignees in last 3 days (default)
python linear_inactive_assignees.py

# Check for 7 days of complete inactivity
python linear_inactive_assignees.py --days 7

# Filter by team
python linear_inactive_assignees.py --days 5 --team-id "your-team-id"
```

**Output Format**:
For completely inactive members:
- 👤 Team member name and email
- 📊 Total number of active issues
- ⏰ Days since ANY activity
- 🔴 Warning that ALL issues are stale
- Example list of stale issues

This script is ideal for:
- Identifying team members who may be blocked or need help
- Daily standup alerts for inactive members
- Finding team members who haven't logged any progress
- Management oversight of team activity
- Proactive support for stuck team members

### linear_project_overview.py
**Purpose**: Analyze Linear issues grouped by project and initiative hierarchy

**Features**:
- Groups issues by Initiative → Project → Issues hierarchy
- Shows project progress, state, and target dates
- Calculates statistics per project:
  - Total issues and their states (completed, in progress, backlog)
  - Priority distribution
  - Assignee distribution (top 5)
  - Total story points (if estimates are used)
- Identifies issues without projects
- Provides overall summary of initiatives, projects, and issues

**Usage Examples**:
```bash
# Analyze all active issues by project/initiative
python linear_project_overview.py

# Include completed issues in the analysis
python linear_project_overview.py --include-completed

# Filter by team
python linear_project_overview.py --team-id "your-team-id"
```

**Output Format**:
- 🎯 Initiatives with their projects
- 📁 Projects with metadata (state, progress, target date)
- 📊 Issue statistics per project
- 🎯 Priority distribution
- 👥 Top assignees per project
- ❓ Issues without projects
- 📈 Overall summary

This script is ideal for:
- Executive/management project overview
- Understanding project health and progress
- Resource allocation decisions
- Sprint planning and prioritization
- Identifying orphaned issues without projects