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

# Load ignored repos (with reasons) so we can exclude their contributions from scoring
IGNORED_REPOS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ignored_repos.json")
try:
    with open(IGNORED_REPOS_PATH, "r") as f:
        _ignored_list = json.load(f)
        IGNORED_REPOS = {item["full_name"].lower(): item.get("reason", "") for item in _ignored_list}
except Exception:
    IGNORED_REPOS = {}
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
            commitContributionsByRepository(maxRepositories: 100) {
                repository { nameWithOwner }
                contributions { totalCount }
            }
            pullRequestContributionsByRepository(maxRepositories: 100) {
                repository { nameWithOwner }
                contributions { totalCount }
            }
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

    # Calculate per-repository contributions and subtract ignored repos' contributions
    ignored_repos_used = {}
    ignored_commits_total = 0
    ignored_prs_total = 0
    commit_by_repo = contributions.get("commitContributionsByRepository") or []
    for item in commit_by_repo:
        repo_full = item.get("repository", {}).get("nameWithOwner", "").lower()
        cnt = item.get("contributions", {}).get("totalCount", 0)
        if repo_full in IGNORED_REPOS:
            ignored_commits_total += cnt
            ignored_repos_used.setdefault(repo_full, {"full_name": repo_full, "reason": IGNORED_REPOS.get(repo_full, ""), "commits": 0, "prs": 0})
            ignored_repos_used[repo_full]["commits"] += cnt

    pr_by_repo = contributions.get("pullRequestContributionsByRepository") or []
    for item in pr_by_repo:
        repo_full = item.get("repository", {}).get("nameWithOwner", "").lower()
        cnt = item.get("contributions", {}).get("totalCount", 0)
        if repo_full in IGNORED_REPOS:
            ignored_prs_total += cnt
            ignored_repos_used.setdefault(repo_full, {"full_name": repo_full, "reason": IGNORED_REPOS.get(repo_full, ""), "commits": 0, "prs": 0})
            ignored_repos_used[repo_full]["prs"] += cnt

    # convert ignored_repos_used to list
    ignored_repos_used = list(ignored_repos_used.values())

    total_stars = sum(r["stargazerCount"] for r in repos)

    # Find top languages
    lang_counts = {}
    for repo in repos:
        lang = repo.get("primaryLanguage")
        if lang:
            lang_counts[lang["name"]] = lang_counts.get(lang["name"], 0) + 1
    top_languages = sorted(lang_counts, key=lang_counts.get, reverse=True)[:3]

    # Composite score: weighted ranking metric
    raw_commits = contributions["totalCommitContributions"]
    commits = max(0, raw_commits - ignored_commits_total)
    raw_prs = contributions["totalPullRequestContributions"]
    prs = max(0, raw_prs - ignored_prs_total)
    issues = contributions["totalIssueContributions"]
    followers = user["followers"]["totalCount"]
    score = (commits * 3) + (prs * 5) + (issues * 2) + (total_stars * 4) + (followers * 1)

    SL_KEYWORDS = ["sri lanka", "colombo", "kandy", "galle", "matara", "negombo", "jaffna", "trincomalee", "lk", "ceylon", "sl"]
    location_str = (user["location"] or "").lower()
    location_verified = any(k in location_str for k in SL_KEYWORDS)
    if not location_verified:
        print(f"{login} has an unverified location: '{user['location'] or 'None'}'")

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
        "raw_commits_this_year": raw_commits,
        "prs_this_year": prs,
        "raw_prs_this_year": raw_prs,
        "ignored_repos": ignored_repos_used,
        
        "issues_this_year": issues,
        "total_stars": total_stars,
        "public_repos": user["repositories"]["totalCount"],
        "repos_contributed_to": contributions["totalRepositoriesWithContributedCommits"],
        "top_languages": top_languages,
        "location_verified": location_verified,
        "score": score,
        "github_url": f"https://github.com/{user['login']}",
    }


def main():
    # Load registered users list
    users_path = os.path.join(os.path.dirname(__file__), "..", "data", "users.json")
    with open(users_path, "r") as f:
        user_list = json.load(f)

    out_path = os.path.join(os.path.dirname(__file__), "..", "data", "rankings.json")
    prev_scores = {}
    if os.path.exists(out_path):
        with open(out_path, "r") as f:
            try:
                old = json.load(f)
                for u in old.get("rankings", []):
                    prev_scores[u["login"]] = {"score": u["score"], "rank": u["rank"]}
            except Exception:
                pass

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
        prev = prev_scores.get(user["login"], {})
        if prev:
            user["previous_score"] = prev.get("score")
            user["previous_rank"] = prev.get("rank")
        else:
            user["previous_score"] = None
            user["previous_rank"] = None

    print("Generating badges...")
    badges_dir = os.path.join(os.path.dirname(__file__), "..", "badges")
    os.makedirs(badges_dir, exist_ok=True)
    
    for user in rankings:
        rank = user["rank"]
        if rank == 1: color = "ffd700"      # Gold
        elif rank == 2: color = "c0c0c0"    # Silver
        elif rank == 3: color = "cd7f32"    # Bronze
        else: color = "10b981"              # Green for others

        url = f"https://img.shields.io/badge/DevRank--LK-%23{rank}-{color}?style=flat-square"
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                with open(os.path.join(badges_dir, f"{user['login']}.svg"), "w", encoding="utf-8") as bf:
                    bf.write(r.text)
        except Exception as e:
            print(f"  Failed badge for {user['login']}: {e}")

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_users": len(rankings),
        "rankings": rankings,
    }

    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nDone! {len(rankings)} users ranked. Saved to data/rankings.json")


if __name__ == "__main__":
    main()
