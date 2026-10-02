"""Build the GitHub profile: fetch → analyze → render SVGs + README → validate → write.

  python profile/scripts/build.py             incremental refresh (needs GITHUB_TOKEN)
  python profile/scripts/build.py --full      re-read every README/manifest
  python profile/scripts/build.py --offline   re-render from profile/data/profile.json (no API)
"""
import argparse
import hashlib
import json
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import analyze
import svg

PROFILE = Path(__file__).resolve().parent.parent
ROOT = PROFILE.parent
CONFIG = PROFILE / "config" / "profile.toml"
DATA = PROFILE / "data" / "profile.json"
GEN = PROFILE / "generated"
TEMPLATE = PROFILE / "templates" / "README.md.tmpl"
SECRET = re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")


# ── Collect + analyze ───────────────────────────────────────────────────────

def _salt(cfg):
    """Cache key part: README analysis must re-run when its config or code changes."""
    blob = json.dumps([analyze.ANALYZER_VERSION, cfg["analysis"], cfg["technologies"]], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def collect(cfg, previous, full):
    import fetch
    login, rc, an = cfg["identity"]["login"], cfg["repos"], cfg["analysis"]
    techs, overrides = cfg["technologies"], cfg.get("projects", {})
    match_terms = {m.replace("_", "-") for t in techs.values() for m in t["match"]}
    raw = [r for r in fetch.list_repos(login, rc.get("include_private", False))
           if r["name"] not in rc.get("exclude", [])
           and (rc.get("include_forks") or not r["isFork"])
           and (rc.get("include_archived", True) or not r["isArchived"])
           and (rc.get("include_private") or not r["isPrivate"])]
    salt, prev = _salt(cfg), {r["id"]: r for r in previous.get("repos", [])}
    stale = [r["id"] for r in raw if full or prev.get(r["id"], {}).get("cache_key") != f"{r['pushedAt']}|{salt}"]
    details = fetch.repo_details(stale, an["manifests"]) if stale else {}
    print(f"{len(raw)} repositories · {len(stale)} re-analyzed · {len(raw) - len(stale)} from cache")

    repos = []
    for r in raw:
        if r["id"] in details:
            d = details[r["id"]]
            cached = {
                "features_auto": analyze.extract_features(d["readme"], an["feature_sections"], 12),
                "excerpt": analyze.readme_excerpt(d["readme"]),
                "manifest_hits": sorted({t.replace("_", "-") for t in analyze.manifest_tokens(d["manifests"])} & match_terms),
                "languages": d["languages"],
                "has_docs": d["has_docs"],
            }
        else:
            cached = {k: prev[r["id"]][k] for k in ("features_auto", "excerpt", "manifest_hits", "languages", "has_docs")}
        o = overrides.get(r["name"], {})
        topics = [t["topic"]["name"] for t in r["repositoryTopics"]["nodes"]]
        langs = {k: v for k, v in cached["languages"].items() if k not in an.get("ignore_languages", [])}
        evidence = set(cached["manifest_hits"]) | set(topics) | {k.lower() for k in langs}
        head = (r.get("defaultBranchRef") or {}).get("target") or {}
        rel = r.get("latestRelease")
        repos.append({
            "id": r["id"], "name": r["name"], "full_name": r["nameWithOwner"], "url": r["url"],
            "cache_key": f"{r['pushedAt']}|{salt}",
            "description": (r["description"] or "").strip(), "tagline": o.get("tagline"),
            "visibility": "PRIVATE" if r["isPrivate"] else "PUBLIC",
            "archived": r["isArchived"], "fork": r["isFork"],
            "language": (r.get("primaryLanguage") or {}).get("name"), "topics": topics,
            "stars": r["stargazerCount"], "forks": r["forkCount"], "watchers": r["watchers"]["totalCount"],
            "open_issues": r["issues"]["totalCount"], "open_prs": r["pullRequests"]["totalCount"],
            "license": None if not r["licenseInfo"] else
            "Custom" if r["licenseInfo"]["spdxId"] == "NOASSERTION" else r["licenseInfo"]["spdxId"],
            "release": {"tag": rel["tagName"], "date": rel["publishedAt"], "url": rel["url"]} if rel else None,
            "homepage": r["homepageUrl"] or None, "demo": o.get("demo") or r["homepageUrl"] or None,
            "docs": o.get("docs") or (f"{r['url']}/tree/HEAD/docs" if cached["has_docs"] else None),
            "architecture": o.get("architecture"),
            "created": r["createdAt"], "pushed": r["pushedAt"],
            "branch": (r.get("defaultBranchRef") or {}).get("name"),
            "last_commit": head.get("committedDate"), "commits": (head.get("history") or {}).get("totalCount", 0),
            "features": [{"title": f, "detail": ""} if isinstance(f, str) else f for f in o["features"]]
            if o.get("features") else cached["features_auto"][:an["max_features"]],
            "feature_source": "config" if o.get("features") else "readme",
            "tech": analyze.detect_tech(evidence, techs),
            "override": {k: o[k] for k in ("featured", "category") if k in o},
            **cached,
        })

    for p in repos:
        p["category"] = analyze.classify(p, cfg["categories"], cfg["classification"]["min_score"])
    featured = analyze.select_featured(repos, cfg["featured"]["count"], date.today())
    weekly = fetch.weekly_commits([p["full_name"] for p in repos if p["featured"]])
    for p in repos:
        p["weekly"] = weekly.get(p["full_name"]) or (prev.get(p["id"], {}).get("weekly") if p["featured"] else None)

    user = fetch.user_activity(login)
    return model(cfg, user, repos, featured)


def model(cfg, user, repos, featured):
    an = cfg["analysis"]
    public = [p for p in repos if p["visibility"] == "PUBLIC" and not p["fork"]]
    activity = analyze.activity_stats(user, cfg["identity"]["login"], cfg["repos"].get("include_private", False))
    cats = {}
    for p in sorted(repos, key=lambda p: p["pushed"], reverse=True):
        cats.setdefault(p["category"], []).append(p["name"])
    order = [c["name"] for c in cfg["categories"]] + ["Other"]
    categories = [{"name": n, "repos": cats[n]} for n in sorted(cats, key=lambda n: (order.index(n) if n in order else len(order), n))]
    events = []
    for p in repos:
        if p["last_commit"]:
            events.append({"date": p["last_commit"], "kind": "commit", "title": p["name"],
                           "detail": f"Latest commit on {p['branch']}" + (f" · {p['language']}" if p["language"] else "")})
        if p["release"]:
            events.append({"date": p["release"]["date"], "kind": "release", "title": p["name"],
                           "detail": f"Released {p['release']['tag']}"})
    events.sort(key=lambda e: e["date"], reverse=True)
    return {
        "schema": 1,
        "login": user["login"],
        "user": {"name": user["name"], "created": user["createdAt"], "followers": user["followers"]["totalCount"]},
        "repos": repos,
        "featured": featured,
        "categories": categories,
        "languages": analyze.language_mix(public, set(an.get("ignore_languages", []))),
        "tech": analyze.tech_groups(public, cfg["technologies"], cfg.get("stack", {}).get("declared", {})),
        "focus": analyze.focus_evidence(public, cfg.get("focus", [])),
        "activity": activity,
        "events": events[:6],
        "latest_activity": max((p["pushed"] for p in repos), default=None),
        "totals": {
            "public_repos": len(public),
            "stars": sum(p["stars"] for p in public),
            "forks": sum(p["forks"] for p in public),
            "commits": sum(p["commits"] for p in public),
            "licensed": sum(1 for p in public if p["license"] not in (None, "Custom")),
            "languages": len({l for p in public for l in p["languages"]}),
        },
    }


# ── Render ──────────────────────────────────────────────────────────────────

def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def alt(doc):
    return re.search(r'aria-label="([^"]*)"', doc).group(1)


def img(files, name, href=None):
    """<picture> serving the narrow variant on phones; GitHub keeps <source media>."""
    narrow = name.replace(".svg", "-m.svg")
    tag = (f'<picture><source media="(max-width: 600px)" srcset="profile/generated/{narrow}">'
           f'<img src="profile/generated/{name}" width="100%" alt="{alt(files[name])}"></picture>')
    return f'<a href="{href}">{tag}</a>' if href else tag


def md_cell(s, limit=None):
    s = analyze.clean(s or "")
    if limit and len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return s.replace("|", "\\|").replace("<", "&lt;")


def repo_table(repos):
    rows = ["| Repository | Description | Stack | Stars | Last commit |", "|---|---|---|--:|---|"]
    for p in repos:
        stack = " · ".join(([p["language"]] if p["language"] else []) + [t for t in p["tech"] if t != p["language"]][:2])
        flag = " <sub>ARCHIVED</sub>" if p["archived"] else " <sub>PRIVATE</sub>" if p["visibility"] == "PRIVATE" else ""
        rows.append(f"| [**{p['name']}**]({p['url']}){flag} | {md_cell(p.get('tagline') or p['description'], 110) or '—'} "
                    f"| {stack or '—'} | {p['stars']} | {svg.fmt_date(p['last_commit'] or p['pushed'])} |")
    return "\n".join(rows)


def render(m, cfg):
    ident, by_name = cfg["identity"], {p["name"]: p for p in m["repos"]}
    files = {}

    def put(name, fn, *args, **kw):
        files[name] = fn(*args, **kw, W=svg.WIDE)
        files[name.replace(".svg", "-m.svg")] = fn(*args, **kw, W=svg.NARROW)

    put("hero.svg", svg.hero, ident, m["repos"], m["latest_activity"])
    put("focus.svg", svg.focus, m["focus"])
    put("stack.svg", svg.stack, m["tech"], m["languages"])
    put("activity.svg", svg.activity, m["activity"])
    put("timeline.svg", svg.timeline, m["events"])
    put("distribution.svg", svg.distribution, m["languages"], m["categories"], m["totals"]["public_repos"])
    t, a = m["totals"], m["activity"]
    put("stats.svg", svg.strip, "ENGINEERING STATISTICS", [
        (str(t["public_repos"]), "Public repositories"), (svg.fmt_num(t["commits"]), "Commits (default branches)"),
        (svg.fmt_num(a["total"]), "Contributions · 12 mo"), (str(a["pull_requests"]), "Pull requests · 12 mo"),
        (str(t["stars"]), "Stars earned"), (str(t["languages"]), "Languages")])
    put("opensource.svg", svg.strip, "OPEN SOURCE", [
        (str(t["public_repos"]), "Public repositories"), (f"{t['licensed']}/{t['public_repos']}", "Open-source licensed"),
        (str(t["stars"]), "Stars"), (str(t["forks"]), "Forks"), (str(len(a["external_repos"])), "External repos contributed to")],
        note="Licensed = repository declares an SPDX license. External = commits or pull requests to repositories "
             "owned by others, last 12 months.",
        chips_label="Contributed to", chip_items=a["external_repos"])

    featured_md = []
    for name in m["featured"]:
        p = by_name[name]
        f = f"card-{slug(name)}.svg"
        put(f, svg.card, p)
        acts = [f'<a href="{p["url"]}"><b>Repository</b></a>']
        acts += [f'<a href="{u}">{l}</a>' for l, u in (("Live demo", p["demo"]), ("Documentation", p["docs"]),
                                                    ("Architecture", p["architecture"])) if u]
        if p["release"]:
            acts.append(f'<a href="{p["release"]["url"]}">Release {p["release"]["tag"]}</a>')
        featured_md.append(img(files, f, p["url"]) +
                           f'\n<p align="center"><sub>{" &nbsp;·&nbsp; ".join(acts)}</sub></p>\n')

    cap = cfg["explorer"]["max_per_category"]
    explorer, truncated = [], False
    for c in m["categories"]:
        items = [by_name[n] for n in c["repos"]]
        truncated |= len(items) > cap
        n = len(items)
        explorer.append(f"<details>\n<summary><b>{c['name']}</b> &nbsp;·&nbsp; {n} repositor{'y' if n == 1 else 'ies'}</summary>\n\n"
                        f"{repo_table(items[:cap])}\n\n</details>")
    explorer.append(f"\n<sub>{'Showing the most recent ' + str(cap) + ' per category. ' if truncated else ''}"
                    f'<a href="profile/CATALOG.md">Full repository catalog →</a></sub>')

    evidence = ["<details>\n<summary>Evidence behind the technology map</summary>\n",
                "| Technology | Area | Public repositories |", "|---|---|---|"]
    for g in m["tech"]:
        for tech in g["items"]:
            where = ", ".join(f"[{n}]({by_name[n]['url']})" for n in tech["repos"][:6]) or "Professional experience (configured)"
            if len(tech["repos"]) > 6:
                where += f" +{len(tech['repos']) - 6} more"
            evidence.append(f"| {tech['name']} | {g['group']} | {where} |")
    evidence.append("\n</details>")

    links = " &nbsp;·&nbsp; ".join(f'<a href="{l["url"]}"><b>{l["label"]}</b></a>' for l in cfg.get("links", []))
    website = next((l["url"] for l in cfg.get("links", []) if l["url"].startswith("http")), m["repos"][0]["url"] if m["repos"] else "#")
    latest = svg.fmt_date(m["latest_activity"]) if m["latest_activity"] else "—"
    slots = {
        "hero": img(files, "hero.svg", website),
        "links": links,
        "overview": " ".join(ident["overview"].split()),
        "focus": img(files, "focus.svg", "#repository-explorer"),
        "stack": img(files, "stack.svg") + "\n\n" + "\n".join(evidence),
        "featured": "\n".join(featured_md) or "_No public projects yet._",
        "opensource": img(files, "opensource.svg", "profile/CATALOG.md"),
        "explorer": "\n".join(explorer),
        "activity": img(files, "activity.svg") + "\n\n" +
                    img(files, "timeline.svg"),
        "statistics": img(files, "stats.svg") + "\n\n" +
                      img(files, "distribution.svg"),
        "connect": links,
        "latest": latest,
    }
    readme = TEMPLATE.read_text(encoding="utf-8")
    for k, v in slots.items():
        readme = readme.replace("{{" + k + "}}", v)

    catalog = ["# Repository Catalog", "",
               f"Every repository on the profile, grouped by category. Generated from the GitHub API — "
               f"latest activity {latest}. [← Back to profile](../README.md)", ""]
    for c in m["categories"]:
        catalog += [f"## {c['name']}", "", repo_table([by_name[n] for n in c["repos"]]), ""]
    return files, readme, "\n".join(catalog)


# ── Validate + write ────────────────────────────────────────────────────────

def validate(files, readme, catalog):
    problems = []
    for name, doc in files.items():
        try:
            ET.fromstring(doc)
        except ET.ParseError as e:
            problems.append(f"{name}: invalid SVG ({e})")
        if len(doc) > 200_000:
            problems.append(f"{name}: {len(doc)} bytes, too large")
    if "{{" in readme:
        problems.append("README: unresolved template slot " + re.search(r"\{\{\w*\}\}", readme).group(0))
    for ref in re.findall(r'(?:src|srcset)="profile/generated/([^"]+)"', readme):
        if ref not in files:
            problems.append(f"README references missing asset {ref}")
    for name, doc in [*files.items(), ("README.md", readme), ("CATALOG.md", catalog)]:
        if SECRET.search(doc):
            problems.append(f"{name}: contains something that looks like a GitHub token")
    if problems:
        raise SystemExit("Validation failed:\n  " + "\n  ".join(problems))


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.write_text(content, encoding="utf-8", newline="\n")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args(argv)
    cfg = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    previous = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {}
    if args.offline:
        if not previous:
            raise SystemExit("--offline needs an existing profile/data/profile.json")
        m = previous
    else:
        m = collect(cfg, previous, args.full)
    files, readme, catalog = render(m, cfg)
    validate(files, readme, catalog)
    data = json.dumps(m, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    if SECRET.search(data):
        raise SystemExit("Validation failed: data snapshot contains a token-like string")
    changed = [str(p.relative_to(ROOT)) for p, c in [(DATA, data), (ROOT / "README.md", readme),
                                                   (PROFILE / "CATALOG.md", catalog),
                                                   *[(GEN / n, d) for n, d in files.items()]] if write(p, c)]
    for old in GEN.glob("*.svg"):          # renamed / unfeatured repos leave stale cards behind
        if old.name not in files:
            old.unlink()
            changed.append(f"removed {old.relative_to(ROOT)}")
    print("\n".join(changed) if changed else "No changes.")


if __name__ == "__main__":
    sys.exit(main())
