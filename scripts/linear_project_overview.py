#!/usr/bin/env python3
"""
Analyze Linear issues grouped by project and initiative.

This script fetches issues and organizes them by their project and initiative
hierarchy, showing progress metrics and team distribution.

Usage:
    python linear_project_overview.py
    python linear_project_overview.py --team-id "team-uuid"
    python linear_project_overview.py --include-completed
"""

import argparse
import sys
import os
from typing import List, Dict, Optional, Any
from collections import defaultdict

# Add parent directory to path to import from tools
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.graphql import LinearClient

# Load environment variables from parent .env file
from dotenv import load_dotenv

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(parent_dir, ".env")
load_dotenv(dotenv_path)


def get_issues_with_projects(
    linear: LinearClient, team_id: Optional[str] = None, include_completed: bool = False
) -> List[Dict[str, Any]]:
    """Get all issues with project and initiative information."""

    # GraphQL query to get issues with project hierarchy
    query = """
    query GetIssuesWithProjects($filter: IssueFilter) {
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
                    name
                    email
                }
                team {
                    name
                }
                priority
                estimate
                project {
                    id
                    name
                    description
                    state
                    progress
                    targetDate
                    startedAt
                    completedAt
                }
                projectMilestone {
                    id
                    name
                    targetDate
                }
                createdAt
                updatedAt
                completedAt
            }
        }
    }
    """

    # Build filter
    filter_dict: Dict[str, Any] = {}
    
    if not include_completed:
        filter_dict["state"] = {"type": {"nin": ["completed", "canceled"]}}
    
    if team_id:
        filter_dict["team"] = {"id": {"eq": team_id}}

    variables = {"filter": filter_dict} if filter_dict else {}

    result = linear.query(query, variables)

    if "issues" in result:
        return result["issues"]["nodes"]
    elif "data" in result and "issues" in result["data"]:
        return result["data"]["issues"]["nodes"]

    return []


def group_by_hierarchy(issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Group issues by initiative -> project -> issues."""
    
    hierarchy = {
        "initiatives": defaultdict(lambda: {
            "name": "",
            "description": "",
            "target_date": None,
            "projects": defaultdict(lambda: {
                "name": "",
                "description": "",
                "state": "",
                "progress": 0,
                "target_date": None,
                "issues": [],
                "stats": {
                    "total": 0,
                    "completed": 0,
                    "in_progress": 0,
                    "backlog": 0,
                    "by_priority": defaultdict(int),
                    "by_assignee": defaultdict(int),
                    "total_estimate": 0
                }
            })
        }),
        "no_project": {
            "issues": [],
            "stats": {
                "total": 0,
                "completed": 0,
                "in_progress": 0,
                "backlog": 0,
                "by_priority": defaultdict(int),
                "by_assignee": defaultdict(int)
            }
        }
    }
    
    for issue in issues:
        if issue.get("project"):
            project = issue["project"]
            initiative_id = "no_initiative"
            initiative_name = "No Initiative"
            
            if project.get("initiative"):
                initiative = project["initiative"]
                initiative_id = initiative["id"]
                initiative_name = initiative["name"]
                hierarchy["initiatives"][initiative_id]["name"] = initiative_name
                hierarchy["initiatives"][initiative_id]["description"] = initiative.get("description", "")
                hierarchy["initiatives"][initiative_id]["target_date"] = initiative.get("targetDate")
            
            project_id = project["id"]
            proj_data = hierarchy["initiatives"][initiative_id]["projects"][project_id]
            proj_data["name"] = project["name"]
            proj_data["description"] = project.get("description", "")
            proj_data["state"] = project.get("state", "")
            proj_data["progress"] = project.get("progress", 0)
            proj_data["target_date"] = project.get("targetDate")
            
            proj_data["issues"].append(issue)
            update_stats(proj_data["stats"], issue)
        else:
            hierarchy["no_project"]["issues"].append(issue)
            update_stats(hierarchy["no_project"]["stats"], issue)
    
    return hierarchy


def update_stats(stats: Dict[str, Any], issue: Dict[str, Any]):
    """Update statistics for a collection of issues."""
    stats["total"] += 1
    
    state_type = issue["state"]["type"]
    if state_type == "completed":
        stats["completed"] += 1
    elif state_type == "started":
        stats["in_progress"] += 1
    else:
        stats["backlog"] += 1
    
    # Priority distribution
    priority = issue.get("priority", 0)
    priority_label = {0: "No priority", 1: "Urgent", 2: "High", 3: "Medium", 4: "Low"}.get(priority, "Unknown")
    stats["by_priority"][priority_label] += 1
    
    # Assignee distribution
    assignee = issue.get("assignee")
    assignee_name = assignee["name"] if assignee else "Unassigned"
    stats["by_assignee"][assignee_name] += 1
    
    # Estimate
    if "total_estimate" in stats and issue.get("estimate"):
        stats["total_estimate"] += issue["estimate"]


def format_hierarchy_output(hierarchy: Dict[str, Any]) -> str:
    """Format the hierarchy data for display."""
    output = []
    
    # Header
    output.append("\n📊 Linear Project & Initiative Overview")
    output.append("=" * 80)
    
    # Process initiatives
    for init_id, init_data in hierarchy["initiatives"].items():
        if not init_data["projects"]:
            continue
            
        if init_id != "no_initiative":
            output.append(f"\n🎯 Initiative: {init_data['name']}")
            if init_data["description"]:
                output.append(f"   {init_data['description']}")
            if init_data["target_date"]:
                output.append(f"   📅 Target: {init_data['target_date']}")
            output.append("")
        else:
            output.append("\n📂 Projects without Initiative")
            output.append("")
        
        # Process projects
        for _, proj_data in init_data["projects"].items():
            if not proj_data["issues"]:
                continue
                
            output.append(f"  📁 Project: {proj_data['name']}")
            if proj_data["description"]:
                output.append(f"     {proj_data['description']}")
            
            # Project metadata
            if proj_data["state"]:
                output.append(f"     State: {proj_data['state']}")
            if proj_data["progress"] is not None:
                output.append(f"     Progress: {proj_data['progress']:.0%}")
            if proj_data["target_date"]:
                output.append(f"     Target: {proj_data['target_date']}")
            
            # Issue stats
            stats = proj_data["stats"]
            output.append(f"\n     📊 Issues: {stats['total']} total")
            output.append(f"        ✅ Completed: {stats['completed']}")
            output.append(f"        🔄 In Progress: {stats['in_progress']}")
            output.append(f"        📋 Backlog: {stats['backlog']}")
            
            if stats["total_estimate"]:
                output.append(f"        ⏱️  Total Estimate: {stats['total_estimate']} points")
            
            # Priority breakdown
            output.append("\n     🎯 By Priority:")
            for priority, count in sorted(stats["by_priority"].items()):
                output.append(f"        • {priority}: {count}")
            
            # Top assignees
            output.append("\n     👥 By Assignee (top 5):")
            sorted_assignees = sorted(stats["by_assignee"].items(), key=lambda x: x[1], reverse=True)[:5]
            for assignee, count in sorted_assignees:
                output.append(f"        • {assignee}: {count} issues")
            
            output.append("")
    
    # Issues without projects
    if hierarchy["no_project"]["issues"]:
        output.append("\n❓ Issues without Project")
        stats = hierarchy["no_project"]["stats"]
        output.append(f"   Total: {stats['total']} issues")
        output.append(f"   • In Progress: {stats['in_progress']}")
        output.append(f"   • Backlog: {stats['backlog']}")
        output.append(f"   • Completed: {stats['completed']}")
    
    # Overall summary
    output.append("\n" + "=" * 80)
    output.append("📈 Overall Summary:")
    
    total_issues = sum(
        proj["stats"]["total"]
        for init in hierarchy["initiatives"].values()
        for proj in init["projects"].values()
    ) + hierarchy["no_project"]["stats"]["total"]
    
    total_projects = sum(
        len(init["projects"])
        for init in hierarchy["initiatives"].values()
        if init["projects"]
    )
    
    total_initiatives = len([
        init for init in hierarchy["initiatives"].values()
        if init["name"] and init["name"] != "No Initiative"
    ])
    
    output.append(f"   • Initiatives: {total_initiatives}")
    output.append(f"   • Projects: {total_projects}")
    output.append(f"   • Total Issues: {total_issues}")
    
    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Linear issues grouped by project and initiative."
    )
    parser.add_argument("--team-id", help="Optional: filter by team ID")
    parser.add_argument(
        "--include-completed",
        action="store_true",
        help="Include completed and canceled issues"
    )

    args = parser.parse_args()

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

    # Get issues with project data
    print("📥 Fetching issues with project information...")
    issues = get_issues_with_projects(linear, args.team_id, args.include_completed)

    if not issues:
        print("No issues found.")
        return

    print(f"Found {len(issues)} issues to analyze...")

    # Group by hierarchy
    hierarchy = group_by_hierarchy(issues)

    # Display results
    print(format_hierarchy_output(hierarchy))


if __name__ == "__main__":
    main()