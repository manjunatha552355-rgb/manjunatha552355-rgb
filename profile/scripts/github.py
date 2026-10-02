"""Minimal GitHub API client — stdlib only, retries + rate-limit backoff, never logs the token."""
import json
import os
import time
import urllib.error
import urllib.request

API = "https://api.github.com"


def _token():
    for key in ("PROFILE_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(key):
            return os.environ[key]
    raise SystemExit("No token: set GITHUB_TOKEN (or PROFILE_TOKEN for private metadata).")


def request(method, path, body=None, tries=4):
    """Return (status, json). Retries 5xx/network errors and waits out rate limits (max 5 min)."""
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(tries):
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {_token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "profile-builder",
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return r.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            last = attempt == tries - 1
            limited = e.code == 429 or (e.code == 403 and (
                e.headers.get("Retry-After") or e.headers.get("X-RateLimit-Remaining") == "0"))
            if limited and not last:
                wait = int(e.headers.get("Retry-After") or 0) or \
                    int(e.headers.get("X-RateLimit-Reset", 0)) - int(time.time())
                if wait > 300:
                    raise SystemExit(f"Rate limited for {wait}s; aborting (previous outputs kept).")
                time.sleep(max(wait, 5) + 1)
                continue
            if e.code >= 500 and not last:
                time.sleep(2 ** attempt * 3)
                continue
            raise
        except urllib.error.URLError:
            if attempt == tries - 1:
                raise
            time.sleep(2 ** attempt * 3)


def graphql(query, **variables):
    _, out = request("POST", "/graphql", {"query": query, "variables": variables})
    if out.get("errors"):
        raise RuntimeError("GraphQL error: " + "; ".join(e.get("message", "?") for e in out["errors"]))
    return out["data"]


def commit_activity(full_name, tries=4):
    """52 weekly commit totals for the default branch, or None if GitHub is still computing them."""
    for _ in range(tries):
        status, data = request("GET", f"/repos/{full_name}/stats/commit_activity")
        if status == 200 and isinstance(data, list):
            return [w["total"] for w in data]
        time.sleep(4)  # 202 = stats being generated in the background
    return None
