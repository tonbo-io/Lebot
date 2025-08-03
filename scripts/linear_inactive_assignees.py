#!/usr/bin/env python3
"""
Find team members who haven't updated their assigned issues in the last N days.

This script identifies assignees who have active issues but haven't made any
updates (status changes or comments) within the specified time period.

Usage:
    python linear_inactive_assignees.py --days 3
    python linear_inactive_assignees.py --days 7 --team-id "team-uuid"
"""

import argparse
import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict, Set, Optional, Any
from collections import defaultdict

# Add parent directory to path to import from tools
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.graphql import LinearClient

# Load environment variables from parent .env file
from dotenv import load_dotenv

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(parent_dir, ".env")
load_dotenv(dotenv_path)


def get_active_issues_by_assignee(
    linear: LinearClient, team_id: Optional[str] = None
) -> Dict[str, List[Dict[str, Any]]]:
    """Get all active issues grouped by assignee."""
    
    # GraphQL query to get active issues with assignee info
    query = """
    query GetActiveIssues($filter: IssueFilter) {
        issues(filter: $filter, first: 250) {
            nodes {
                id
                identifier
                title
                state {
                    name
                    type
                }
                assignee {
                    id
                    name
                    email
                }
                updatedAt
                createdAt
                history(first: 50) {
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
                comments(first: 50) {
                    nodes {
                        id
                        createdAt
                        user {
                            id
                            name
                        }
                    }
                }
            }
        }
    }
    """
    
    # Build filter for active issues (not completed/canceled)
    filter_dict: Dict[str, Any] = {
        "state": {
            "type": {
                "nin": ["completed", "canceled"]
            }
        }
    }
    
    if team_id:
        filter_dict["team"] = {"id": {"eq": team_id}}
    
    variables = {"filter": filter_dict}
    result = linear.query(query, variables)
    
    # Group issues by assignee
    issues_by_assignee: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    
    if "issues" in result:
        for issue in result["issues"]["nodes"]:
            if issue.get("assignee"):
                assignee_key = f"{issue['assignee']['name']}|{issue['assignee']['email']}"
                issues_by_assignee[assignee_key].append(issue)
    
    return dict(issues_by_assignee)


def find_last_activity_date(issue: Dict[str, Any], assignee_id: str) -> Optional[datetime]:
    """Find the last date when the assignee made any activity on the issue."""
    
    last_activity = None
    
    # Check issue update date (if it's a simple field update)
    updated_at = datetime.fromisoformat(issue["updatedAt"].replace("Z", "+00:00")).replace(tzinfo=None)
    
    # Check status changes
    if "history" in issue and issue["history"]["nodes"]:
        for history_item in issue["history"]["nodes"]:
            if history_item.get("fromState") and history_item.get("toState"):
                change_date = datetime.fromisoformat(
                    history_item["createdAt"].replace("Z", "+00:00")
                ).replace(tzinfo=None)
                
                if not last_activity or change_date > last_activity:
                    last_activity = change_date
    
    # Check comments by the assignee
    if "comments" in issue and issue["comments"]["nodes"]:
        for comment in issue["comments"]["nodes"]:
            # Only count comments from the assignee
            if comment.get("user") and comment["user"].get("id") == assignee_id:
                comment_date = datetime.fromisoformat(
                    comment["createdAt"].replace("Z", "+00:00")
                ).replace(tzinfo=None)
                
                if not last_activity or comment_date > last_activity:
                    last_activity = comment_date
    
    # Use the most recent activity
    if not last_activity or updated_at > last_activity:
        last_activity = updated_at
    
    return last_activity


def main():
    parser = argparse.ArgumentParser(
        description="Find team members who haven't updated ANY of their assigned issues in N days."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=3,
        help="Number of days to check for complete inactivity (default: 3)"
    )
    parser.add_argument(
        "--team-id",
        help="Optional: filter by team ID"
    )
    
    args = parser.parse_args()
    
    # Calculate cutoff date
    cutoff_date = datetime.now() - timedelta(days=args.days)
    
    print(f"🔍 Finding assignees with NO issue updates since {cutoff_date.strftime('%Y-%m-%d')}")
    
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
    
    # Get active issues by assignee
    print("📥 Fetching active issues...")
    issues_by_assignee = get_active_issues_by_assignee(linear, args.team_id)
    
    if not issues_by_assignee:
        print("No active assigned issues found.")
        return
    
    print(f"Found {len(issues_by_assignee)} assignees with active issues")
    
    # Find completely inactive assignees
    completely_inactive = []
    partially_active = []
    fully_active = []
    
    for assignee_key, issues in issues_by_assignee.items():
        name, email = assignee_key.split("|")
        assignee_id = issues[0]["assignee"]["id"]  # Get assignee ID from first issue
        
        # Find the most recent activity across ALL issues
        most_recent_activity = None
        issue_activities = []
        
        for issue in issues:
            last_activity = find_last_activity_date(issue, assignee_id)
            if last_activity:
                issue_activities.append({
                    "issue": issue,
                    "last_activity": last_activity,
                    "days_inactive": (datetime.now() - last_activity).days
                })
                
                if not most_recent_activity or last_activity > most_recent_activity:
                    most_recent_activity = last_activity
        
        # Categorize assignee based on their most recent activity
        if most_recent_activity:
            days_since_last_activity = (datetime.now() - most_recent_activity).days
            
            assignee_data = {
                "name": name,
                "email": email,
                "total_active_issues": len(issues),
                "last_activity": most_recent_activity,
                "days_inactive": days_since_last_activity,
                "issue_activities": sorted(issue_activities, key=lambda x: x["last_activity"], reverse=True)
            }
            
            if most_recent_activity < cutoff_date:
                # This person hasn't updated ANY issue in the specified period
                completely_inactive.append(assignee_data)
            else:
                # This person has updated at least one issue recently
                stale_count = sum(1 for ia in issue_activities if ia["last_activity"] < cutoff_date)
                if stale_count > 0:
                    assignee_data["stale_count"] = stale_count
                    partially_active.append(assignee_data)
                else:
                    fully_active.append(assignee_data)
    
    # Display results
    print("\n" + "=" * 80)
    
    if completely_inactive:
        print(f"\n🚨 COMPLETELY INACTIVE - {len(completely_inactive)} assignees with NO updates in {args.days} days:\n")
        
        # Sort by days inactive
        completely_inactive.sort(key=lambda x: x["days_inactive"], reverse=True)
        
        for assignee in completely_inactive:
            print(f"👤 {assignee['name']} ({assignee['email']})")
            print(f"   📊 Active issues: {assignee['total_active_issues']}")
            print(f"   ⏰ Last activity: {assignee['days_inactive']} days ago ({assignee['last_activity'].strftime('%Y-%m-%d')})")
            print(f"   🔴 ALL {assignee['total_active_issues']} issues are stale!")
            
            # Show a few example issues
            print("\n   Example stale issues:")
            for item in assignee["issue_activities"][:3]:
                issue = item["issue"]
                print(f"   • [{issue['identifier']}] {issue['title']}")
                print(f"     Status: {issue['state']['name']} | Last update: {item['days_inactive']} days ago")
            
            if len(assignee["issue_activities"]) > 3:
                print(f"   ... and {len(assignee['issue_activities']) - 3} more issues")
            print()
    else:
        print(f"\n✅ Good news! No one has been completely inactive for {args.days} days.")
    
    # Show partially active members if any
    if partially_active:
        print(f"\n⚠️  PARTIALLY ACTIVE - {len(partially_active)} assignees with some stale issues:\n")
        
        for assignee in sorted(partially_active, key=lambda x: x["stale_count"], reverse=True)[:5]:
            print(f"👤 {assignee['name']} - {assignee['stale_count']}/{assignee['total_active_issues']} issues stale")
    
    # Summary
    print("\n" + "=" * 80)
    print("📈 Summary:")
    print(f"   • Completely inactive (no updates): {len(completely_inactive)}")
    print(f"   • Partially active (some updates): {len(partially_active)}")
    print(f"   • Fully active (all issues updated): {len(fully_active)}")
    print(f"   • Total assignees checked: {len(issues_by_assignee)}")
    print(f"   • Inactivity threshold: {args.days} days")


if __name__ == "__main__":
    main()