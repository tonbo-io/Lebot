#!/usr/bin/env python3
"""
Test script for the updated get_issues_with_status_and_comments method
with date range filtering for the last 3 days.
"""

import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from tools.graphql import LinearClient


def test_date_range_filtering():
    """Test the date range filtering functionality."""

    # Load environment variables
    load_dotenv()

    # Get Linear API key from environment
    api_key = os.getenv("LINEAR_API_KEY") or os.getenv("LINEAR_OAUTH_KEY")
    if not api_key:
        print("❌ LINEAR_API_KEY or LINEAR_OAUTH_KEY not found in environment variables")
        print("Please set your Linear API key in .env file")
        return

    print("🔗 Initializing Linear client...")
    linear = LinearClient(api_key)

    # Test connection first
    try:
        print("🧪 Testing connection...")
        viewer = linear.test_connection()
        if viewer and "viewer" in viewer:
            print(f"✅ Connected as: {viewer['viewer'].get('name', 'Unknown')}")
        else:
            print("❌ Connection test failed")
            return
    except Exception as e:
        print(f"❌ Connection failed: {str(e)}")
        return

    # Calculate date range for last 3 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=3)

    # Format dates for the API
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    print(f"\n📅 Fetching issues updated within last 3 days:")
    print(f"   Start date: {start_date_str}")
    print(f"   End date: {end_date_str}")

    try:
        # Test the method with date range filtering
        print("\n🔍 Calling get_issues_by_date_range with date filter...")
        result = linear.get_issues_by_date_range(start_date=start_date_str, end_date=end_date_str, limit=50)

        # Display results
        print(f"\n📊 Results Summary:")
        summary = result.get("summary", {})
        print(f"   Total issues: {summary.get('total_issues', 0)}")
        print(f"   Total assignees: {summary.get('total_assignees', 0)}")

        grouped_issues = result.get("grouped_issues", {})

        if not grouped_issues:
            print("   No issues found in the specified date range")
            return

        print(f"\n👥 Issues by Assignee (last 3 days):")
        for assignee, issues in grouped_issues.items():
            print(f"\n  📝 {assignee} ({len(issues)} issues):")

            for issue in issues[:3]:  # Show first 3 issues per assignee
                status = issue.get("state", {}).get("name", "Unknown")
                updated_at = issue.get("updatedAt", "Unknown")
                comments_count = len(issue.get("comments", {}).get("nodes", []))

                print(f"    • {issue.get('identifier', 'N/A')}: {issue.get('title', 'No title')[:50]}...")
                print(f"      Status: {status} | Updated: {updated_at[:10]} | Comments: {comments_count}")

                # Show recent comments if any
                comments = issue.get("comments", {}).get("nodes", [])
                if comments:
                    latest_comment = comments[0]  # Comments should be ordered by date
                    comment_user = latest_comment.get("user", {}).get("name", "Unknown")
                    comment_date = latest_comment.get("createdAt", "Unknown")[:10]
                    comment_preview = latest_comment.get("body", "")[:100]
                    print(f"      Latest comment by {comment_user} ({comment_date}): {comment_preview}...")

            if len(issues) > 3:
                print(f"    ... and {len(issues) - 3} more issues")

        print(f"\n✅ Test completed successfully!")

        # Additional test: Try with different date formats
        print(f"\n🔬 Testing with ISO datetime format...")
        iso_start = start_date.isoformat() + "Z"
        iso_end = end_date.isoformat() + "Z"

        result_iso = linear.get_issues_by_date_range(start_date=iso_start, end_date=iso_end, limit=10)

        print(f"   ISO format test - Total issues: {result_iso.get('summary', {}).get('total_issues', 0)}")

    except Exception as e:
        print(f"❌ Error during testing: {str(e)}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_date_range_filtering()
