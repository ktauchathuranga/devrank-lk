import os
import json
import time
import requests
from datetime import datetime, timezone

GH_TOKEN = os.environ.get("GH_TOKEN")
HEADERS = {
    "Authorization": f"bearer {GH_TOKEN}",
    "Content-Type": "application/json",
}
GRAPHQL_URL = "https://api.github.com/graphql"

# --- GraphQL query to fetch all user stats in one request ---
USER_QUERY = """
query($login: String!) {
  user(login: $login) {
    login
    name
    avatarUrl
    bio
    company
    websiteUrl
    location
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalRepositoriesWithContributedCommits
    }
    repositories(
      first: 100
      ownerAffiliations: OWNER
      isFork: false
      privacy: PUBLIC
      orderBy: { field: STARGAZERS, direction: DESC }
    ) {
      totalCount
      nodes {
        stargazerCount
        primaryLanguage { name }
      }
    }
  }
}
"""

def graphql_request(query, variables):
    """Make a GraphQL request with retry logic."""
    for attempt in range(3):
        try:
            response = requests.post(
                GRAPHQL_URL,
                headers=HEADERS,
                json={"query": query, "variables": variables},
                timeout=15,
            )
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 403:
                print(f"  Rate limited. Sleeping 60s...")
                time.sleep(60)
            else:
                print(f"  HTTP {response.status_code}: {response.text}")
        except Exception as e:
            print(f"  Request error (attempt {attempt+1}): {e}")
            time.sleep(5)
    return None


def fetch_user_stats(login):
    """Fetch stats for a single GitHub user."""
    result = graphql_request(USER_QUERY, {"login": login})

    if not result or "errors" in result:
        print(f"  Error fetching {login}: {result.get('errors') if result else 'No response'}")
        return None

    user = result.get("data", {}).get("user")
    if not user:
        print(f"  User not found: {login}")
        return None

    contributions = user["contributionsCollection"]
    repos = user["repositories"]["nodes"]

    total_stars = sum(r["stargazerCount"] for r in repos)

    # Find top languages
    lang_counts = {}
    for repo in repos:
        lang = repo.get("primaryLanguage")
        if lang:
            lang_counts[lang["name"]] = lang_counts.get(lang["name"], 0) + 1
    top_languages = sorted(lang_counts, key=lang_counts.get, reverse=True)[:3]

    # Composite score: weighted ranking metric
    commits = contributions["totalCommitContributions"]
    prs = contributions["totalPullRequestContributions"]
    issues = contributions["totalIssueContributions"]
    followers = user["followers"]["totalCount"]
    score = (commits * 3) + (prs * 5) + (issues * 2) + (total_stars * 4) + (followers * 1)

    return {
        "login": user["login"],
        "name": user["name"] or user["login"],
        "avatar_url": user["avatarUrl"],
        "bio": user["bio"] or "",
        "company": user["company"] or "",
        "website": user["websiteUrl"] or "",
        "location": user["location"] or "",
        "followers": followers,
        "commits_this_year": commits,
        "prs_this_year": prs,
        "issues_this_year": issues,
        "total_stars": total_stars,
        "public_repos": user["repositories"]["totalCount"],
        "repos_contributed_to": contributions["totalRepositoriesWithContributedCommits"],
        "top_languages": top_languages,
        "score": score,
        "github_url": f"https://github.com/{user['login']}",
    }


def main():
    # Load registered users list
    users_path = os.path.join(os.path.dirname(__file__), "..", "data", "users.json")
    with open(users_path, "r") as f:
        user_list = json.load(f)

    print(f"Fetching stats for {len(user_list)} users...")

    rankings = []
    for i, entry in enumerate(user_list):
        login = entry["github"] if isinstance(entry, dict) else entry
        print(f"[{i+1}/{len(user_list)}] Fetching: {login}")
        stats = fetch_user_stats(login)
        if stats:
            rankings.append(stats)
        time.sleep(0.5)  # be gentle with the API

    # Sort by raw score descending
    rankings.sort(key=lambda x: x["score"], reverse=True)

    # Normalize scores to 0–1000 (top scorer = 1000)
    max_score = rankings[0]["score"] if rankings else 1
    for i, user in enumerate(rankings):
        user["score"] = round((user["score"] / max_score) * 1000)
        user["rank"] = i + 1

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_users": len(rankings),
        "rankings": rankings,
    }

    out_path = os.path.join(os.path.dirname(__file__), "..", "data", "rankings.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nDone! {len(rankings)} users ranked. Saved to data/rankings.json")


if __name__ == "__main__":
    main()
