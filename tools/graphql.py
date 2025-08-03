"""
Simple GraphQL client module for making HTTP requests to GraphQL endpoints.
Designed for use with Linear API and other GraphQL services.
"""

import json
import requests
from typing import Dict, Any, Optional, Union


class GraphQLClient:
    """A simple GraphQL client that uses requests to communicate with GraphQL endpoints."""

    def __init__(self, endpoint: str, headers: Optional[Dict[str, str]] = None):
        """
        Initialize the GraphQL client.

        Args:
            endpoint: The GraphQL endpoint URL
            headers: Optional headers to include with requests (e.g., authorization)
        """
        self.endpoint = endpoint
        self.headers = headers or {}

        # Set default content type for GraphQL
        if "Content-Type" not in self.headers:
            self.headers["Content-Type"] = "application/json"

    def execute(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a GraphQL query.

        Args:
            query: The GraphQL query string
            variables: Optional variables for the query

        Returns:
            The response data from the GraphQL endpoint

        Raises:
            requests.RequestException: If the HTTP request fails
            ValueError: If the response contains GraphQL errors
        """
        payload: Dict[str, str | Dict[str, Any]] = {"query": query}

        if variables:
            payload["variables"] = variables

        response = requests.post(self.endpoint, json=payload, headers=self.headers)

        response.raise_for_status()

        result = response.json()

        # Check for GraphQL errors
        if "errors" in result:
            error_messages = [error.get("message", "Unknown error") for error in result["errors"]]
            raise ValueError(f"GraphQL errors: {', '.join(error_messages)}")

        return result

    def query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Any:
        """
        Execute a GraphQL query and return just the data portion.

        Args:
            query: The GraphQL query string
            variables: Optional variables for the query

        Returns:
            The data portion of the GraphQL response
        """
        result = self.execute(query, variables)
        return result.get("data")

    def set_auth_header(self, token: str, auth_type: str = "Bearer"):
        """
        Set authorization header for the client.

        Args:
            token: The authorization token
            auth_type: The type of authorization (default: 'Bearer')
        """
        self.headers["Authorization"] = f"{auth_type} {token}"


class LinearClient(GraphQLClient):
    """A specialized GraphQL client for Linear API."""

    def __init__(self, api_key: str):
        """
        Initialize the Linear client.

        Args:
            api_key: Linear API key
        """
        super().__init__(endpoint="https://api.linear.app/graphql", headers={"Authorization": api_key})

    def test_connection(self) -> Any:
        """
        Test the API connection with a simple query.

        Returns:
            Viewer data if connection is successful
        """
        query = """
        query TestConnection {
            viewer {
                id
                name
                email
            }
        }
        """
        return self.query(query)

    def get_issues(self, team_id: Optional[str] = None, limit: int = 50) -> Any:
        """
        Get issues from Linear with basic information.

        Args:
            team_id: Optional team ID to filter issues
            limit: Maximum number of issues to return

        Returns:
            Issues data from Linear
        """
        filter_str = ""
        variables: Dict[str, Any] = {"first": limit}

        if team_id:
            filter_str = "filter: { team: { id: { eq: $teamId } } }, "
            variables["teamId"] = team_id

        query = f"""
        query GetIssues($first: Int{', $teamId: String!' if team_id else ''}) {{
            issues({filter_str}first: $first) {{
                nodes {{
                    id
                    identifier
                    title
                    description
                    state {{
                        name
                        type
                    }}
                    assignee {{
                        name
                        email
                    }}
                    team {{
                        key
                        name
                    }}
                    createdAt
                    updatedAt
                }}
            }}
        }}
        """

        return self.query(query, variables)

    def get_in_progress_issues(self, limit: int = 200) -> Any:
        """
        Get all in-progress issues across all teams.

        Args:
            limit: Maximum number of issues to return

        Returns:
            In-progress issues data from Linear
        """
        query = """
        query GetInProgressIssues($first: Int) {
            issues(filter: { state: { type: { eq: "started" } } }, first: $first) {
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
                    updatedAt
                    comments {
                        nodes {
                            createdAt
                            body
                            user {
                                name
                            }
                        }
                    }
                }
            }
        }
        """

        return self.query(query, {"first": limit})

    def get_issues_by_date_range(
        self,
        start_date: str,
        end_date: str,
        team_id: Optional[str] = None,
        limit: int = 200,
    ) -> Dict[str, Any]:
        """
        Get issues within a date range with full details including comments.

        Args:
            start_date: Start date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)
            end_date: End date filter (ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ)
            team_id: Optional team ID to filter issues
            limit: Maximum number of issues to return

        Returns:
            Dictionary with issues grouped by assignee and date, ordered by date descending
        """
        # Build filter conditions
        filter_conditions = []

        if team_id:
            filter_conditions.append("team: { id: { eq: $teamId } }")

        # Date range filter is now required
        filter_conditions.append("createdAt: { gte: $startDate, lte: $endDate }")

        # Build filter string
        filter_str = ""
        if filter_conditions:
            filter_str = f"filter: {{ {', '.join(filter_conditions)} }}, "

        # Build variables
        variables: Dict[str, int | str] = {
            "first": limit,
            "startDate": self._format_date_for_graphql(start_date),
            "endDate": self._format_date_for_graphql(end_date),
        }
        query_params = ["$first: Int", "$startDate: DateTimeOrDuration!", "$endDate: DateTimeOrDuration!"]

        if team_id:
            variables["teamId"] = team_id
            query_params.append("$teamId: String!")

        query_params_str = ", ".join(query_params)

        query = f"""
        query GetIssuesWithStatusAndComments({query_params_str}) {{
            issues({filter_str}first: $first, orderBy: updatedAt) {{
                nodes {{
                    id
                    identifier
                    title
                    description
                    state {{
                        id
                        name
                        type
                    }}
                    assignee {{
                        id
                        name
                        email
                    }}
                    team {{
                        id
                        key
                        name
                    }}
                    priority
                    createdAt
                    updatedAt
                    archivedAt
                    comments {{
                        nodes {{
                            id
                            body
                            user {{
                                id
                                name
                                email
                            }}
                            createdAt
                            updatedAt
                        }}
                    }}
                }}
            }}
        }}
        """

        # Debug: print the generated query and variables
        # print("Generated Query:", query)
        # print("Variables:", variables)

        raw_data = self.query(query, variables)
        return self._group_issues_by_assignee_and_date(raw_data)

    def _format_date_for_graphql(self, date_str: str) -> str:
        """
        Format date string for GraphQL DateTime input.

        Args:
            date_str: Date string in various formats (YYYY-MM-DD, YYYY-MM-DDTHH:MM:SSZ, etc.)

        Returns:
            Properly formatted DateTime string for GraphQL
        """
        from datetime import datetime

        # Handle different date formats
        try:
            # Try parsing as ISO format first
            if "T" in date_str:
                if date_str.endswith("Z"):
                    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                else:
                    dt = datetime.fromisoformat(date_str)
            else:
                # Assume YYYY-MM-DD format, add time component with UTC timezone
                dt = datetime.fromisoformat(f"{date_str}T00:00:00+00:00")

            # Return in ISO format with Z suffix
            return dt.isoformat().replace("+00:00", "Z")
        except (ValueError, AttributeError):
            # If parsing fails, return original string and let GraphQL handle it
            return date_str

    def _group_issues_by_assignee_and_date(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Group issues by assignee and date, ordered by date descending.

        Args:
            raw_data: Raw GraphQL response data

        Returns:
            Dictionary with grouped and ordered issues
        """
        from datetime import datetime
        from collections import defaultdict

        if not raw_data or "issues" not in raw_data or "nodes" not in raw_data["issues"]:
            return {"grouped_issues": {}, "summary": {"total_issues": 0, "total_assignees": 0}}

        issues = raw_data["issues"]["nodes"]

        # Group by assignee
        grouped_by_assignee = defaultdict(list)

        for issue in issues:
            assignee_key = "Unassigned"
            if issue.get("assignee"):
                assignee_key = f"{issue['assignee']['name']} ({issue['assignee']['email']})"

            # Parse updated date for sorting
            updated_at = issue.get("updatedAt")
            if updated_at:
                try:
                    issue_date = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                    issue["parsed_date"] = issue_date
                except (ValueError, AttributeError):
                    issue["parsed_date"] = datetime.min
            else:
                issue["parsed_date"] = datetime.min

            grouped_by_assignee[assignee_key].append(issue)

        # Sort issues within each assignee group by date descending
        for assignee in grouped_by_assignee:
            grouped_by_assignee[assignee].sort(key=lambda x: x["parsed_date"], reverse=True)
            # Remove the temporary parsed_date field
            for issue in grouped_by_assignee[assignee]:
                del issue["parsed_date"]

        # Sort assignees by their most recent issue date
        sorted_assignees = sorted(
            grouped_by_assignee.items(),
            key=lambda x: max(
                [
                    (
                        datetime.fromisoformat(issue["updatedAt"].replace("Z", "+00:00"))
                        if issue.get("updatedAt")
                        else datetime.min
                    )
                    for issue in x[1]
                ]
            ),
            reverse=True,
        )

        # Create final grouped structure
        result = {
            "grouped_issues": dict(sorted_assignees),
            "summary": {
                "total_issues": len(issues),
                "total_assignees": len(grouped_by_assignee),
                "assignee_issue_counts": {
                    assignee: len(issues_list) for assignee, issues_list in grouped_by_assignee.items()
                },
            },
        }

        return result
