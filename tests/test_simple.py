#!/usr/bin/env python3
"""
Simple test to debug Linear GraphQL query issues
"""

import os
from dotenv import load_dotenv
from tools.graphql_client import LinearClient


def test_simple_query():
    load_dotenv()
    api_key = os.getenv("LINEAR_API_KEY") or os.getenv("LINEAR_OAUTH_KEY")

    if not api_key:
        print("❌ No API key found")
        return

    linear = LinearClient(api_key)

    try:
        # Test 1: Connection test
        print("🧪 Testing connection...")
        result = linear.test_connection()
        print("✅ Connection successful")

        # Test 2: Simple issues query without date filter
        print("\n🧪 Testing simple issues query...")
        result = linear.get_issues(limit=5)
        print(f"✅ Simple query successful - found {len(result.get('issues', {}).get('nodes', []))} issues")

        # Test 3: Try the new method without date filters
        print("\n🧪 Testing new method without date filters...")
        result = linear.get_issues_with_status_and_comments(limit=5)
        summary = result.get("summary", {})
        print(
            f"✅ New method successful - {summary.get('total_issues', 0)} issues, {summary.get('total_assignees', 0)} assignees"
        )

        # Show some sample data
        grouped = result.get("grouped_issues", {})
        if grouped:
            for assignee, issues in list(grouped.items())[:2]:
                print(f"   📝 {assignee}: {len(issues)} issues")
                if issues:
                    issue = issues[0]
                    print(f"      - {issue.get('identifier', 'N/A')}: {issue.get('title', 'No title')[:50]}")
                    print(f"      - Status: {issue.get('state', {}).get('name', 'Unknown')}")
                    print(f"      - Updated: {issue.get('updatedAt', 'Unknown')[:19]}")

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_simple_query()
