"""
Test file demonstrating usage of the GraphQL client.
"""

from tools.graphql_client import GraphQLClient, LinearClient


def test_basic_graphql_client():
    """Example of using the basic GraphQL client."""
    # Example with a public GraphQL API (replace with actual endpoint)
    client = GraphQLClient("https://api.github.com/graphql")

    # You would set your GitHub token like this:
    # client.set_auth_header('your_github_token')

    query = """
    query {
        viewer {
            login
            name
        }
    }
    """

    # This would work with a valid token
    # result = client.query(query)
    # print(result)


def test_linear_client():
    """Example of using the Linear client."""
    # Initialize with Linear API key (replace with actual key)
    # linear = LinearClient('your_linear_api_key')

    # Get authenticated user info
    # viewer = linear.get_viewer()
    # print("Viewer:", viewer)

    # Get all teams
    # teams = linear.get_teams()
    # print("Teams:", teams)

    # Get issues for a specific team (use team ID, not key)
    # issues = linear.get_issues(team_id='team_uuid_here', limit=10)
    # print("Issues:", issues)

    # Get a specific issue by ID
    # issue = linear.get_issue_by_id('issue_uuid_here')
    # print("Issue:", issue)

    # Create a new issue
    # new_issue = linear.create_issue(
    #     team_id='team_uuid_here',
    #     title='New issue from API',
    #     description='Created via GraphQL client',
    #     priority=2
    # )
    # print("Created issue:", new_issue)

    print("Linear client ready to use - uncomment and add your API key")


def test_custom_query():
    """Example of using custom GraphQL queries with variables."""
    # linear = LinearClient('your_linear_api_key')

    # Query issues by state type
    custom_query = """
    query GetIssuesByState($stateType: String!) {
        issues(filter: { state: { type: { eq: $stateType } } }, first: 10) {
            nodes {
                id
                identifier
                title
                state {
                    id
                    name
                    type
                }
                assignee {
                    name
                }
                team {
                    key
                    name
                }
            }
        }
    }
    """

    variables = {"stateType": "started"}

    # result = linear.query(custom_query, variables)
    # print("Issues in started state:", result)

    # Query team by key (use this to get team ID for other queries)
    team_query = """
    query GetTeamByKey($key: String!) {
        teams(filter: { key: { eq: $key } }) {
            nodes {
                id
                key
                name
                description
                issueCount
            }
        }
    }
    """

    team_variables = {"key": "ENG"}

    # team_result = linear.query(team_query, team_variables)
    # print("Team by key:", team_result)

    print("Custom query examples ready - uncomment and add your API key")


if __name__ == "__main__":
    print("GraphQL Client Test Examples")
    print("=" * 40)

    test_basic_graphql_client()
    test_linear_client()
    test_custom_query()
