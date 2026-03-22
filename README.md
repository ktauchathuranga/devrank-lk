# 🇱🇰 GitHub Sri Lanka — Developer Rankings

A weekly-updated leaderboard of Sri Lankan GitHub developers, ranked by open-source activity.

<p align="center">
  <img src="images/ss.png" alt="Screenshot of the website" width="800">
  <br>
  <em></em>
</p>

> [!NOTE]  
> **Live site →** [devrank-lk](https://ktauchathuranga.github.io/devrank-lk/)

---

## How it works

1. A list of Sri Lankan developers is maintained in [`data/users.json`](data/users.json)
2. Every Sunday, a GitHub Action runs a Python script that fetches each developer's stats via the GitHub GraphQL API
3. A `data/rankings.json` file is generated and committed
4. The static `index.html` reads `rankings.json` and renders the leaderboard

## Ranking Score

Developers are ranked by a composite score normalized to a **0–1000 scale** — the top developer always scores **1000**, and everyone else is scaled proportionally.

**Step 1 — Raw weighted score:**
```
raw = (commits × 3) + (PRs × 5) + (issues × 2) + (stars × 4) + (followers × 1)
```

**Step 2 — Normalize to 0–1000:**
```
score = round((raw / max_raw) × 1000)
```

| Metric | Weight | Notes |
|--------|--------|-------|
| Commits | × 3 | Current contribution year |
| Pull Requests | × 5 | Highest weight — collaboration matters most |
| Issues | × 2 | Community engagement |
| Stars | × 4 | Lifetime total across public repos |
| Followers | × 1 | Lowest weight |

---

## Add yourself to the rankings

1. Fork this repo
2. Open [`data/users.json`](data/users.json) and add your entry:
   - Find the **last line** that starts with `{` (the last person in the list)
   - Add a **comma** `,` at the end of that line
   - Then add your entry on a new line **before** the closing `]`

   **Example — before:**
   ```json
      { "github": "some-user", "note": "" }
   ]
   ```
   **Example — after:**
   ```json
      { "github": "some-user", "note": "" },
      { "github": "your-github-username", "note": "" }
   ]
   ```
   > **Important:** The comma after the previous entry is required. Without it you will get a JSON syntax error and your PR cannot be merged.

3. Open a Pull Request

---

## Setup (for repo owners)

### 1. Create a GitHub Personal Access Token

Go to **GitHub → Settings → Developer Settings → Personal Access Tokens → Fine-grained tokens**

Required scopes: `read:user`, `repo` (public only is fine)

### 2. Add it as a repository secret

Go to your repo → **Settings → Secrets and variables → Actions**

Create a secret named `GH_TOKEN` with your token value.

### 3. Enable GitHub Pages

Go to **Settings → Pages** → Source: `Deploy from branch` → Branch: `main` → Folder: `/ (root)`

### 4. Run manually to test

Go to **Actions → Update GitHub Rankings → Run workflow**

---

## Project structure

```
├── .github/
│   └── workflows/
│       └── update-rankings.yml   # Scheduled GitHub Action
├── data/
│   ├── users.json                # List of registered developers
│   └── rankings.json             # Auto-generated — do not edit
├── scripts/
│   └── fetch_data.py             # Fetches stats from GitHub API
├── index.html                    # The ranking page
└── README.md
```
