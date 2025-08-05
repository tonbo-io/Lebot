import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict
from .base import Tool
from .graphql import LinearClient


class Linear(Tool):
    """Linear tool for project management operations."""

    def __init__(self):
        """Initialize the Linear tool."""
        self.logger = logging.getLogger(__name__)
        self.client: Optional[LinearClient] = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize the Linear client with API key from environment."""
        api_key = os.getenv("LINEAR_OAUTH_KEY")
        if api_key:
            self.client = LinearClient(api_key)
            # Test connection
            test_result = self.client.test_connection()
            if "error" in test_result:
                self.logger.error(f"Failed to connect to Linear: {test_result['error']}")
                self.client = None
            else:
                self.logger.info("Successfully connected to Linear API")
        else:
            self.logger.warning("LINEAR_OAUTH_KEY not set - Linear tool will not be available")

    def get_schema(self) -> Dict[str, Any]:
        """Return the Linear tool schema for Anthropic's API."""
        return {
            "type": "custom",
            "name": "linear",
            "description": "Interact with Linear for project management - track activity, find inactive assignees, get project overviews",
            "input_schema": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["activity_tracker", "inactive_assignees", "project_overview"],
                        "description": "The Linear operation to perform",
                    },
                    "params": {
                        "type": "object",
                        "description": "Parameters specific to each operation",
                        "properties": {
                            "start_date": {
                                "type": "string",
                                "description": "Start date in YYYY-MM-DD format (for activity_tracker)",
                            },
                            "end_date": {
                                "type": "string",
                                "description": "End date in YYYY-MM-DD format (for activity_tracker)",
                            },
                            "days": {
                                "type": "integer",
                                "description": "Number of days to look back from today (for activity_tracker, inactive_assignees)",
                            },
                            "team_id": {
                                "type": "string",
                                "description": "Optional team ID to filter by",
                            },
                            "include_completed": {
                                "type": "boolean",
                                "description": "Include completed/canceled issues (for project_overview)",
                            },
                        },
                    },
                },
                "required": ["operation"],
            },
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute a Linear operation.

        Args:
            **kwargs: Keyword arguments:
                - operation (str): The operation to perform
                - params (Dict[str, Any]): Parameters for the operation

        Returns:
            Dict with the operation result
        """
        if not self.client:
            return {"error": "Linear client not initialized. Please set LINEAR_OAUTH_KEY environment variable."}

        operation = kwargs.get("operation", "")
        params = kwargs.get("params", {})

        operations = {
            "activity_tracker": self._track_activity,
            "inactive_assignees": self._find_inactive_assignees,
            "project_overview": self._get_project_overview,
        }

        if operation not in operations:
            return {"error": f"Unknown operation: {operation}"}

        try:
            return operations[operation](params)
        except Exception as e:
            self.logger.exception(f"Failed to execute Linear operation {operation}: {e}")
            return {"error": f"Failed to execute operation: {str(e)}"}

    def _track_activity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Track Linear issue activity within a date range.

        Args:
            params: Parameters including start_date, end_date, days, team_id

        Returns:
            Dict with activity report
        """
        # Determine date range
        if params.get("days"):
            end_date = datetime.now()
            start_date = end_date - timedelta(days=params["days"])
        elif params.get("start_date"):
            start_date = datetime.strptime(params["start_date"], "%Y-%m-%d")
            if params.get("end_date"):
                end_date = datetime.strptime(params["end_date"], "%Y-%m-%d")
            else:
                end_date = datetime.now()
        else:
            # Default to last 7 days
            end_date = datetime.now()
            start_date = end_date - timedelta(days=7)

        # Add time components for full day coverage
        start_datetime = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_datetime = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)

        # Get issues with activity
        issues = self._get_issues_with_activity(
            start_datetime.strftime("%Y-%m-%d"), end_datetime.strftime("%Y-%m-%d"), params.get("team_id")
        )

        if not issues:
            return {
                "report": f"No issues found with activity from {start_datetime.strftime('%Y-%m-%d')} to {end_datetime.strftime('%Y-%m-%d')}",
                "issues": [],
            }

        # Filter to only those with actual activity in range
        active_issues = self._filter_issues_with_activity_in_range(issues, start_datetime, end_datetime)

        if not active_issues:
            return {
                "report": f"No issues had status changes or comments from {start_datetime.strftime('%Y-%m-%d')} to {end_datetime.strftime('%Y-%m-%d')}",
                "issues": [],
            }

        # Format the report
        report_lines = []
        report_lines.append(
            f"📊 Linear Activity from {start_datetime.strftime('%Y-%m-%d')} to {end_datetime.strftime('%Y-%m-%d')}"
        )
        report_lines.append(f"Found {len(active_issues)} issues with activity:")
        report_lines.append("=" * 80)

        for issue in active_issues:
            report_lines.append(self._format_issue_activity(issue))
            report_lines.append("-" * 80)

        # Summary
        status_change_count = sum(1 for i in active_issues if i.get("status_changes"))
        comment_count = sum(1 for i in active_issues if i.get("filtered_comments"))

        report_lines.append("\n📈 Summary:")
        report_lines.append(f"   • Total issues with activity: {len(active_issues)}")
        report_lines.append(f"   • Issues with status changes: {status_change_count}")
        report_lines.append(f"   • Issues with new comments: {comment_count}")

        return {
            "report": "\n".join(report_lines),
            "issues": active_issues,
            "summary": {"total": len(active_issues), "status_changes": status_change_count, "comments": comment_count},
        }

    def _find_inactive_assignees(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Find team members who haven't updated their assigned issues.

        Args:
            params: Parameters including days, team_id

        Returns:
            Dict with inactive assignees report
        """
        days = params.get("days", 3)
        team_id = params.get("team_id")

        # Calculate cutoff date
        cutoff_date = datetime.now() - timedelta(days=days)

        # Get active issues by assignee
        issues_by_assignee = self._get_active_issues_by_assignee(team_id)

        if not issues_by_assignee:
            return {"report": "No active assigned issues found.", "assignees": []}

        # Find completely inactive assignees
        completely_inactive = []
        partially_active = []
        fully_active = []

        for assignee_key, issues in issues_by_assignee.items():
            name, email = assignee_key.split("|")
            assignee_id = issues[0]["assignee"]["id"]

            # Find the most recent activity across ALL issues
            most_recent_activity = None
            issue_activities = []

            for issue in issues:
                last_activity = self._find_last_activity_date(issue, assignee_id)
                if last_activity:
                    issue_activities.append(
                        {
                            "issue": issue,
                            "last_activity": last_activity,
                            "days_inactive": (datetime.now() - last_activity).days,
                        }
                    )

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
                    "issue_activities": sorted(issue_activities, key=lambda x: x["last_activity"], reverse=True),
                }

                if most_recent_activity < cutoff_date:
                    completely_inactive.append(assignee_data)
                else:
                    stale_count = sum(1 for ia in issue_activities if ia["last_activity"] < cutoff_date)
                    if stale_count > 0:
                        assignee_data["stale_count"] = stale_count
                        partially_active.append(assignee_data)
                    else:
                        fully_active.append(assignee_data)

        # Format the report
        report_lines = []
        report_lines.append(f"🔍 Assignees with NO issue updates since {cutoff_date.strftime('%Y-%m-%d')} ({days} days)")
        report_lines.append("=" * 80)

        if completely_inactive:
            report_lines.append(
                f"\n🚨 COMPLETELY INACTIVE - {len(completely_inactive)} assignees with NO updates in {days} days:\n"
            )

            # Sort by days inactive
            completely_inactive.sort(key=lambda x: x["days_inactive"], reverse=True)

            for assignee in completely_inactive:
                report_lines.append(f"👤 {assignee['name']} ({assignee['email']})")
                report_lines.append(f"   📊 Active issues: {assignee['total_active_issues']}")
                report_lines.append(
                    f"   ⏰ Last activity: {assignee['days_inactive']} days ago ({assignee['last_activity'].strftime('%Y-%m-%d')})"
                )
                report_lines.append(f"   🔴 ALL {assignee['total_active_issues']} issues are stale!")

                # Show a few example issues
                report_lines.append("\n   Example stale issues:")
                for item in assignee["issue_activities"][:3]:
                    issue = item["issue"]
                    report_lines.append(f"   • [{issue['identifier']}] {issue['title']}")
                    report_lines.append(
                        f"     Status: {issue['state']['name']} | Last update: {item['days_inactive']} days ago"
                    )

                if len(assignee["issue_activities"]) > 3:
                    report_lines.append(f"   ... and {len(assignee['issue_activities']) - 3} more issues")
                report_lines.append("")
        else:
            report_lines.append(f"\n✅ Good news! No one has been completely inactive for {days} days.")

        # Show partially active members if any
        if partially_active:
            report_lines.append(f"\n⚠️  PARTIALLY ACTIVE - {len(partially_active)} assignees with some stale issues:\n")

            for assignee in sorted(partially_active, key=lambda x: x["stale_count"], reverse=True)[:5]:
                report_lines.append(
                    f"👤 {assignee['name']} - {assignee['stale_count']}/{assignee['total_active_issues']} issues stale"
                )

        # Summary
        report_lines.append("\n" + "=" * 80)
        report_lines.append("📈 Summary:")
        report_lines.append(f"   • Completely inactive (no updates): {len(completely_inactive)}")
        report_lines.append(f"   • Partially active (some updates): {len(partially_active)}")
        report_lines.append(f"   • Fully active (all issues updated): {len(fully_active)}")
        report_lines.append(f"   • Total assignees checked: {len(issues_by_assignee)}")
        report_lines.append(f"   • Inactivity threshold: {days} days")

        return {
            "report": "\n".join(report_lines),
            "assignees": {
                "completely_inactive": completely_inactive,
                "partially_active": partially_active,
                "fully_active": fully_active,
            },
        }

    def _get_project_overview(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get overview of Linear projects and initiatives.

        Args:
            params: Parameters including team_id, include_completed

        Returns:
            Dict with project overview report
        """
        team_id = params.get("team_id")
        include_completed = params.get("include_completed", False)

        # Get issues with project data
        issues = self._get_issues_with_projects(team_id, include_completed)

        if not issues:
            return {"report": "No issues found.", "hierarchy": {}}

        # Group by hierarchy
        hierarchy = self._group_by_hierarchy(issues)

        # Format the report
        report_lines = []
        report_lines.append("\n📊 Linear Project & Initiative Overview")
        report_lines.append("=" * 80)

        # Process initiatives
        for init_id, init_data in hierarchy["initiatives"].items():
            if not init_data["projects"]:
                continue

            if init_id != "no_initiative":
                report_lines.append(f"\n🎯 Initiative: {init_data['name']}")
                if init_data["description"]:
                    report_lines.append(f"   {init_data['description']}")
                if init_data["target_date"]:
                    report_lines.append(f"   📅 Target: {init_data['target_date']}")
                report_lines.append("")
            else:
                report_lines.append("\n📂 Projects without Initiative")
                report_lines.append("")

            # Process projects
            for _, proj_data in init_data["projects"].items():
                if not proj_data["issues"]:
                    continue

                report_lines.append(f"  📁 Project: {proj_data['name']}")
                if proj_data["description"]:
                    report_lines.append(f"     {proj_data['description']}")

                # Project metadata
                if proj_data["state"]:
                    report_lines.append(f"     State: {proj_data['state']}")
                if proj_data["progress"] is not None:
                    report_lines.append(f"     Progress: {proj_data['progress']:.0%}")
                if proj_data["target_date"]:
                    report_lines.append(f"     Target: {proj_data['target_date']}")

                # Issue stats
                stats = proj_data["stats"]
                report_lines.append(f"\n     📊 Issues: {stats['total']} total")
                report_lines.append(f"        ✅ Completed: {stats['completed']}")
                report_lines.append(f"        🔄 In Progress: {stats['in_progress']}")
                report_lines.append(f"        📋 Backlog: {stats['backlog']}")

                if stats["total_estimate"]:
                    report_lines.append(f"        ⏱️  Total Estimate: {stats['total_estimate']} points")

                # Priority breakdown
                report_lines.append("\n     🎯 By Priority:")
                for priority, count in sorted(stats["by_priority"].items()):
                    report_lines.append(f"        • {priority}: {count}")

                # Top assignees
                report_lines.append("\n     👥 By Assignee (top 5):")
                sorted_assignees = sorted(stats["by_assignee"].items(), key=lambda x: x[1], reverse=True)[:5]
                for assignee, count in sorted_assignees:
                    report_lines.append(f"        • {assignee}: {count} issues")

                report_lines.append("")

        # Issues without projects
        if hierarchy["no_project"]["issues"]:
            report_lines.append("\n❓ Issues without Project")
            stats = hierarchy["no_project"]["stats"]
            report_lines.append(f"   Total: {stats['total']} issues")
            report_lines.append(f"   • In Progress: {stats['in_progress']}")
            report_lines.append(f"   • Backlog: {stats['backlog']}")
            report_lines.append(f"   • Completed: {stats['completed']}")

        # Overall summary
        report_lines.append("\n" + "=" * 80)
        report_lines.append("📈 Overall Summary:")

        total_issues = (
            sum(proj["stats"]["total"] for init in hierarchy["initiatives"].values() for proj in init["projects"].values())
            + hierarchy["no_project"]["stats"]["total"]
        )

        total_projects = sum(len(init["projects"]) for init in hierarchy["initiatives"].values() if init["projects"])

        total_initiatives = len(
            [init for init in hierarchy["initiatives"].values() if init["name"] and init["name"] != "No Initiative"]
        )

        report_lines.append(f"   • Initiatives: {total_initiatives}")
        report_lines.append(f"   • Projects: {total_projects}")
        report_lines.append(f"   • Total Issues: {total_issues}")

        return {"report": "\n".join(report_lines), "hierarchy": hierarchy}

    # Helper methods from the original scripts

    def _get_issues_with_activity(
        self, start_date: str, end_date: str, team_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all issues with activity in date range."""
        if not self.client:
            return []

        start_iso = f"{start_date}T00:00:00.000Z"
        end_iso = f"{end_date}T23:59:59.999Z"

        query = """
        query GetIssuesWithActivity($filter: IssueFilter) {
            issues(filter: $filter, first: 250) {
                nodes {
                    id
                    identifier
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

        filter_dict: Dict[str, Any] = {"updatedAt": {"gte": start_iso, "lte": end_iso}}

        if team_id:
            filter_dict["team"] = {"id": {"eq": team_id}}

        variables = {"filter": filter_dict}
        result = self.client.query(query, variables)

        if "issues" in result:
            return result["issues"]["nodes"]
        elif "data" in result and "issues" in result["data"]:
            return result["data"]["issues"]["nodes"]

        return []

    def _filter_issues_with_activity_in_range(
        self, issues: List[Dict[str, Any]], start_datetime: datetime, end_datetime: datetime
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
                        change_date_naive = change_date.replace(tzinfo=None) if change_date.tzinfo else change_date
                        if start_datetime <= change_date_naive <= end_datetime:
                            had_activity = True
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
                    comment_date_naive = comment_date.replace(tzinfo=None) if comment_date.tzinfo else comment_date
                    if start_datetime <= comment_date_naive <= end_datetime:
                        had_activity = True
                        filtered_comments.append(comment)

                if filtered_comments:
                    issue["filtered_comments"] = filtered_comments

            if had_activity:
                active_issues.append(issue)

        return active_issues

    def _format_issue_activity(self, issue: Dict[str, Any]) -> str:
        """Format an issue with its activity details."""
        output = []

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

            if project.get("initiatives") and project["initiatives"].get("nodes"):
                initiatives = project["initiatives"]["nodes"]
                if initiatives:
                    initiative_names = [init["name"] for init in initiatives]
                    if len(initiative_names) == 1:
                        output.append(f"   🎯 Initiative: {initiative_names[0]}")
                    else:
                        output.append(f"   🎯 Initiatives: {', '.join(initiative_names)}")

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
                comment_date_naive = comment_date.replace(tzinfo=None) if comment_date.tzinfo else comment_date
                date_str = comment_date_naive.strftime("%Y-%m-%d %H:%M")
                user_name = comment["user"]["name"] if comment.get("user") else "Unknown"

                body = comment["body"]
                output.append(f"      • {date_str} by {user_name}:")
                for line in body.split("\n"):
                    output.append(f"        {line}")

        return "\n".join(output)

    def _get_active_issues_by_assignee(self, team_id: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """Get all active issues grouped by assignee."""
        if not self.client:
            return {}

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

        filter_dict: Dict[str, Any] = {"state": {"type": {"nin": ["completed", "canceled"]}}}

        if team_id:
            filter_dict["team"] = {"id": {"eq": team_id}}

        variables = {"filter": filter_dict}
        result = self.client.query(query, variables)

        issues_by_assignee: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        if "issues" in result:
            for issue in result["issues"]["nodes"]:
                if issue.get("assignee"):
                    assignee_key = f"{issue['assignee']['name']}|{issue['assignee']['email']}"
                    issues_by_assignee[assignee_key].append(issue)

        return dict(issues_by_assignee)

    def _find_last_activity_date(self, issue: Dict[str, Any], assignee_id: str) -> Optional[datetime]:
        """Find the last date when the assignee made any activity on the issue."""
        last_activity = None

        updated_at = datetime.fromisoformat(issue["updatedAt"].replace("Z", "+00:00")).replace(tzinfo=None)

        # Check status changes
        if "history" in issue and issue["history"]["nodes"]:
            for history_item in issue["history"]["nodes"]:
                if history_item.get("fromState") and history_item.get("toState"):
                    change_date = datetime.fromisoformat(history_item["createdAt"].replace("Z", "+00:00")).replace(
                        tzinfo=None
                    )

                    if not last_activity or change_date > last_activity:
                        last_activity = change_date

        # Check comments by the assignee
        if "comments" in issue and issue["comments"]["nodes"]:
            for comment in issue["comments"]["nodes"]:
                if comment.get("user") and comment["user"].get("id") == assignee_id:
                    comment_date = datetime.fromisoformat(comment["createdAt"].replace("Z", "+00:00")).replace(tzinfo=None)

                    if not last_activity or comment_date > last_activity:
                        last_activity = comment_date

        # Use the most recent activity
        if not last_activity or updated_at > last_activity:
            last_activity = updated_at

        return last_activity

    def _get_issues_with_projects(
        self, team_id: Optional[str] = None, include_completed: bool = False
    ) -> List[Dict[str, Any]]:
        """Get all issues with project and initiative information."""
        if not self.client:
            return []

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

        filter_dict: Dict[str, Any] = {}

        if not include_completed:
            filter_dict["state"] = {"type": {"nin": ["completed", "canceled"]}}

        if team_id:
            filter_dict["team"] = {"id": {"eq": team_id}}

        variables = {"filter": filter_dict} if filter_dict else {}
        result = self.client.query(query, variables)

        if "issues" in result:
            return result["issues"]["nodes"]
        elif "data" in result and "issues" in result["data"]:
            return result["data"]["issues"]["nodes"]

        return []

    def _group_by_hierarchy(self, issues: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Group issues by initiative -> project -> issues."""
        hierarchy = {
            "initiatives": defaultdict(
                lambda: {
                    "name": "",
                    "description": "",
                    "target_date": None,
                    "projects": defaultdict(
                        lambda: {
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
                                "total_estimate": 0,
                            },
                        }
                    ),
                }
            ),
            "no_project": {
                "issues": [],
                "stats": {
                    "total": 0,
                    "completed": 0,
                    "in_progress": 0,
                    "backlog": 0,
                    "by_priority": defaultdict(int),
                    "by_assignee": defaultdict(int),
                },
            },
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
                self._update_stats(proj_data["stats"], issue)
            else:
                hierarchy["no_project"]["issues"].append(issue)
                self._update_stats(hierarchy["no_project"]["stats"], issue)

        return hierarchy

    def _update_stats(self, stats: Dict[str, Any], issue: Dict[str, Any]):
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
