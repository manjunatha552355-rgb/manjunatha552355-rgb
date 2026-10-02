"""Collect raw data from GitHub. Repository details are fetched incrementally:
a cheap paginated metadata query for every repo, then README/manifests/languages
only for repos whose pushedAt (or the analysis config) changed since last run."""
from datetime import datetime, timedelta, timezone

import github

REPO_FIELDS = """
  id name nameWithOwner description url homepageUrl isPrivate isArchived isFork
  stargazerCount forkCount watchers { totalCount }
  issues(states: OPEN) { totalCount } pullRequests(states: OPEN) { totalCount }
  createdAt pushedAt primaryLanguage { name }
  repositoryTopics(first: 20) { nodes { topic { name } } }
  licenseInfo { spdxId name }
  latestRelease { tagName name publishedAt url }
  defaultBranchRef { name target { ... on Commit { committedDate history { totalCount } } } }
"""

LIST_QUERY = """
query($login: String!, $cursor: String, $privacy: RepositoryPrivacy) {
  user(login: $login) {
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER, privacy: $privacy,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes { %s }
    }
  }
}""" % REPO_FIELDS

USER_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    login name createdAt followers { totalCount }
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions totalIssueContributions totalPullRequestContributions
      totalPullRequestReviewContributions totalRepositoryContributions restrictedContributionsCount
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
      commitContributionsByRepository(maxRepositories: 25) {
        repository { nameWithOwner isPrivate url owner { login } } contributions { totalCount } }
      pullRequestContributionsByRepository(maxRepositories: 25) {
        repository { nameWithOwner isPrivate url stargazerCount owner { login } } contributions { totalCount } }
    }
  }
}"""


def _detail_query(manifests):
    blobs = "\n".join(
        f'm{i}: object(expression: "HEAD:{path}") {{ __typename ... on Blob {{ text }} }}'
        for i, path in enumerate(manifests))
    return """
query($ids: [ID!]!) {
  nodes(ids: $ids) { ... on Repository {
    id
    languages(first: 12, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name } } }
    readme: object(expression: "HEAD:README.md") { ... on Blob { text } }
    readmeLower: object(expression: "HEAD:readme.md") { ... on Blob { text } }
    docs: object(expression: "HEAD:docs") { __typename }
    %s
  } }
}""" % blobs


def list_repos(login, include_private):
    repos, cursor = [], None
    while True:
        data = github.graphql(LIST_QUERY, login=login, cursor=cursor,
                              privacy=None if include_private else "PUBLIC")
        page = data["user"]["repositories"]
        repos += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return repos
        cursor = page["pageInfo"]["endCursor"]


def repo_details(ids, manifests, batch=10):
    """README text, manifests and languages for the given repo node ids."""
    query, out = _detail_query(manifests), {}
    for i in range(0, len(ids), batch):
        for node in github.graphql(query, ids=ids[i:i + batch])["nodes"]:
            if not node:
                continue
            readme = (node.get("readme") or node.get("readmeLower") or {}).get("text") or ""
            files = {path: (node.get(f"m{j}") or {}) for j, path in enumerate(manifests)}
            out[node["id"]] = {
                "readme": readme,
                "has_docs": bool(node.get("docs")),
                "manifests": {p: f.get("text") or "" for p, f in files.items() if f},
                "languages": {e["node"]["name"]: e["size"] for e in node["languages"]["edges"]},
            }
    return out


def user_activity(login, now=None):
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(days=364)
    return github.graphql(USER_QUERY, login=login,
                          **{"from": start.isoformat(), "to": now.isoformat()})["user"]


def weekly_commits(full_names):
    """{name: [52 weekly totals]} for featured repos; repos still computing are omitted."""
    out = {}
    for name in full_names:
        weeks = github.commit_activity(name)
        if weeks is not None:
            out[name] = weeks
    return out
