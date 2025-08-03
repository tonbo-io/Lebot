#!/usr/bin/env python3
"""
Track Linear issue activity (status changes and comments) within a date range.

This script finds all issues that had status changes or new comments within
a specified date range and displays them with assignee, project, and initiative information.

Features:
- Shows issue title, assignee, and current status
- Displays associated project and initiative information
- Lists status changes within the specified date range
- Shows comments added within the date range
- Includes initiative descriptions when available and concise

Usage:
    python linear_activity_tracker.py --start-date 2024-01-01 --end-date 2024-01-07
    python linear_activity_tracker.py --days 7  # Last 7 days
    python linear_activity_tracker.py --start-date 2024-01-01  # From date to today
"""

import argparse
import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

# Add parent directory to path to import from tools
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.graphql import LinearClient

# Load environment variables from parent .env file
from dotenv import load_dotenv

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(parent_dir, ".env")
load_dotenv(dotenv_path)


def get_issues_with_activity(
    linear: LinearClient, start_date: str, end_date: str, team_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get all issues with activity (status changes or comments) in date range."""

    # Convert dates to ISO 8601 format with time
    start_iso = f"{start_date}T00:00:00.000Z"
    end_iso = f"{end_date}T23:59:59.999Z"

    # GraphQL query to get issues with history and comments
    query = """
    query GetIssuesWithActivity($filter: IssueFilter) {
        issues(filter: $filter, first: 250) {
            nodes {
                id
                title
                state {
                    name
                }
                assignee {
                    name
                    email
                }
                createdAt
                updatedAt
                project {
                    id
                    name
                    initiatives {
                        nodes {
                            id
                            name
                            description
                        }
                    }
                }
                history(first: 100) {
                    nodes {
                        id
                        createdAt
                        fromState {
                            name
                        }
                        toState {
                            name
                        }
                    }
                }
                comments(first: 100) {
                    nodes {
                        id
                        body
                        createdAt
                        updatedAt
                        user {
                            name
                            email
                        }
                    }
                }
            }
        }
    }
    """

    # Build filter - use only updatedAt for simplicity
    filter_dict: Dict[str, Any] = {"updatedAt": {"gte": start_iso, "lte": end_iso}}

    if team_id:
        filter_dict["team"] = {"id": {"eq": team_id}}

    variables = {"filter": filter_dict}

    result = linear.query(query, variables)

    # Check if the response has issues directly or nested under 'data'
    if "issues" in result:
        issues = result["issues"]["nodes"]
        print(f"Found {len(issues)} issues that were updated in the date range")
        return issues
    elif "data" in result and "issues" in result["data"]:
        issues = result["data"]["issues"]["nodes"]
        print(f"Found {len(issues)} issues that were updated in the date range")
        return issues

    print(f"DEBUG: Unexpected query result structure: {result.keys()}")
    return []


def filter_issues_with_activity_in_range(
    issues: List[Dict[str, Any]], start_datetime: datetime, end_datetime: datetime
) -> List[Dict[str, Any]]:
    """Filter issues that actually had activity in the date range."""

    active_issues = []

    for issue in issues:
        had_activity = False

        # Check for status changes in range
        if "history" in issue and issue["history"]["nodes"]:
            for history_item in issue["history"]["nodes"]:
                if history_item.get("fromState") and history_item.get("toState"):
                    change_date = datetime.fromisoformat(history_item["createdAt"].replace("Z", "+00:00"))
                    # Convert to naive datetime for comparison
                    change_date_naive = change_date.replace(tzinfo=None) if change_date.tzinfo else change_date
                    if start_datetime <= change_date_naive <= end_datetime:
                        had_activity = True
                        # Store the status change for later display
                        if "status_changes" not in issue:
                            issue["status_changes"] = []
                        issue["status_changes"].append(
                            {
                                "date": change_date_naive,
                                "from": history_item["fromState"]["name"],
                                "to": history_item["toState"]["name"],
                            }
                        )

        # Check for comments in range
        if "comments" in issue and issue["comments"]["nodes"]:
            filtered_comments = []
            for comment in issue["comments"]["nodes"]:
                comment_date = datetime.fromisoformat(comment["createdAt"].replace("Z", "+00:00"))
                # Convert to naive datetime for comparison
                comment_date_naive = comment_date.replace(tzinfo=None) if comment_date.tzinfo else comment_date
                if start_datetime <= comment_date_naive <= end_datetime:
                    had_activity = True
                    filtered_comments.append(comment)

            # Store filtered comments
            if filtered_comments:
                issue["filtered_comments"] = filtered_comments

        if had_activity:
            active_issues.append(issue)

    return active_issues


def format_issue_activity(issue: Dict[str, Any]) -> str:
    """Format an issue with its activity details."""

    output = []

    # Issue header
    assignee_info = "Unassigned"
    if issue.get("assignee"):
        assignee = issue["assignee"]
        assignee_info = f"{assignee.get('name', 'Unknown')} ({assignee.get('email', 'No email')})"

    output.append(f"\n📋 **{issue['title']}**")
    output.append(f"   👤 Assignee: {assignee_info}")
    output.append(f"   📊 Current Status: {issue['state']['name']}")
    
    # Project info
    if issue.get("project"):
        project = issue["project"]
        output.append(f"   📁 Project: {project['name']}")
        
        # Initiative info
        if project.get("initiatives") and project["initiatives"].get("nodes"):
            initiatives = project["initiatives"]["nodes"]
            if initiatives:
                initiative_names = [init["name"] for init in initiatives]
                if len(initiative_names) == 1:
                    output.append(f"   🎯 Initiative: {initiative_names[0]}")
                else:
                    output.append(f"   🎯 Initiatives: {', '.join(initiative_names)}")
                
                # Show initiative descriptions if they exist and are not too long
                for initiative in initiatives:
                    if initiative.get("description") and len(initiative["description"]) <= 100:
                        output.append(f"      └─ {initiative['description']}")

    # Status changes
    if issue.get("status_changes"):
        output.append("   \n   🔄 Status Changes (within date range):")
        for change in sorted(issue["status_changes"], key=lambda x: x["date"]):
            date_str = change["date"].strftime("%Y-%m-%d %H:%M")
            output.append(f"      • {date_str}: {change['from']} → {change['to']}")

    # Comments
    if issue.get("filtered_comments"):
        output.append("   \n   💬 Comments (within date range):")
        sorted_comments = sorted(issue["filtered_comments"], key=lambda x: x["createdAt"])
        
        for comment in sorted_comments:
            comment_date = datetime.fromisoformat(comment["createdAt"].replace("Z", "+00:00"))
            # Convert to naive for display
            comment_date_naive = comment_date.replace(tzinfo=None) if comment_date.tzinfo else comment_date
            date_str = comment_date_naive.strftime("%Y-%m-%d %H:%M")
            user_name = comment["user"]["name"] if comment.get("user") else "Unknown"

            # Show full content for all comments (no truncation)
            body = comment["body"]

            output.append(f"      • {date_str} by {user_name}:")
            # Indent comment body
            for line in body.split("\n"):
                output.append(f"        {line}")

    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(
        description="Track Linear issue activity (status changes and comments) within a date range."
    )
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD format)")
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD format)")
    parser.add_argument("--days", type=int, help="Alternative: number of days to look back from today")
    parser.add_argument("--team-id", help="Optional: filter by team ID")

    args = parser.parse_args()

    # Determine date range
    if args.days:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=args.days)
    elif args.start_date:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
        if args.end_date:
            end_date = datetime.strptime(args.end_date, "%Y-%m-%d")
        else:
            end_date = datetime.now()
    else:
        print("Error: Must specify either --days or --start-date")
        parser.print_help()
        sys.exit(1)

    # Add time components for full day coverage
    start_datetime = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_datetime = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)

    print(f"🔍 Scanning Linear activity from {start_datetime.strftime('%Y-%m-%d')} to {end_datetime.strftime('%Y-%m-%d')}")

    # Initialize Linear client
    api_key = os.getenv("LINEAR_OAUTH_KEY")
    if not api_key:
        print("Error: LINEAR_OAUTH_KEY environment variable not set")
        sys.exit(1)

    linear = LinearClient(api_key)

    # Test connection
    test_result = linear.test_connection()
    if "error" in test_result:
        print(f"Error connecting to Linear: {test_result['error']}")
        sys.exit(1)

    print("✅ Connected to Linear")

    # Get issues with potential activity
    print("📥 Fetching issues...")
    issues = get_issues_with_activity(
        linear, start_datetime.strftime("%Y-%m-%d"), end_datetime.strftime("%Y-%m-%d"), args.team_id
    )

    if not issues:
        print("No issues found with activity in the specified date range.")
        return

    print(f"Found {len(issues)} issues to analyze...")

    # Filter to only those with actual activity in range
    active_issues = filter_issues_with_activity_in_range(issues, start_datetime, end_datetime)

    if not active_issues:
        print("No issues had status changes or comments in the specified date range.")
        return

    print(f"\n📊 Found {len(active_issues)} issues with activity:\n")
    print("=" * 80)

    # Sort by most recent activity
    for issue in active_issues:
        print(format_issue_activity(issue))
        print("-" * 80)

    # Summary
    print("\n📈 Summary:")
    print(f"   • Total issues with activity: {len(active_issues)}")

    # Count by activity type
    status_change_count = sum(1 for i in active_issues if i.get("status_changes"))
    comment_count = sum(1 for i in active_issues if i.get("filtered_comments"))

    print(f"   • Issues with status changes: {status_change_count}")
    print(f"   • Issues with new comments: {comment_count}")


if __name__ == "__main__":
    main()
