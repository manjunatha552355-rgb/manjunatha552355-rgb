"""Turn raw GitHub data into the profile data model: features, tech evidence,
categories, featured selection, language mix, contribution statistics."""
import json
import math
import re
import tomllib
from collections import Counter, defaultdict
from datetime import date, datetime, timezone

ANALYZER_VERSION = 2  # bump to invalidate cached README analysis

EMOJI = re.compile("[\U0001F000-\U0001FAFF←-⇿⌀-⏿☀-➿⬀-⯿️‍]")
BULLET = re.compile(r"^ ?(?:[-*+]|\d+\.)\s+(.*)")
NESTED = re.compile(r"^\s{2,}(?:[-*+]|\d+\.)\s+(.*)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
TABLE_SEP = re.compile(r"^\|?\s*:?-{2,}")


# ── Markdown helpers ────────────────────────────────────────────────────────

def clean(text):
    """Markdown/HTML/emoji → plain text."""
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\*\*|__|`|(?<!\w)\*(?!\s)|(?<=\S)\*(?!\w)", "", text)
    text = EMOJI.sub("", text)
    return re.sub(r"\s+", " ", text).strip(" -–—:|")


def _norm(heading):
    return re.sub(r"[^a-z ]", "", clean(heading).lower()).strip()


def _item(raw):
    """'**Title**: detail' / 'Title — detail' → {'title', 'detail'}."""
    raw = EMOJI.sub("", raw)
    m = re.match(r"^\s*\*\*(.+?)\*\*\s*[:—–-]?\s*(.*)$", raw)
    if m:
        return {"title": clean(m.group(1)), "detail": clean(m.group(2))}
    text = clean(raw)
    m = re.match(r"^(.{3,40}?)\s+[—–]\s+(.+)$", text) or re.match(r"^([^:]{3,40}):\s+(.+)$", text)
    return {"title": m.group(1), "detail": m.group(2)} if m else {"title": text, "detail": ""}


def _table_row(line):
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if len(cells) < 2 or not clean(cells[0]):
        return None
    return {"title": clean(cells[0]), "detail": clean(cells[1])}


def extract_features(md, sections, limit=4):
    """Capabilities from README sections named in `sections` (priority order).
    Fallback: a lead table (before the first ##) whose first column is bold labels.
    Only top-level bullets and table rows are used — nothing is invented."""
    wanted = [_norm(s) for s in sections]
    found = defaultdict(list)          # section index (len(wanted) = lead) → items
    current, level, in_code, table_head = len(wanted), 0, False, True
    for line in md.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            in_code = not in_code
            continue
        if in_code:
            continue
        h = HEADING.match(line)
        if h:
            lvl, name = len(h.group(1)), _norm(h.group(2))
            if current == len(wanted) and lvl >= 2:
                current = None              # lead section ends at the first ## heading
            if current is not None and current < len(wanted) and lvl <= level:
                current = None
            if current is None:
                current = next((i for i, w in enumerate(wanted) if name == w or name.endswith(" " + w)
                                or name.startswith(w + " ")), None)
                level = lvl
            table_head = True
            continue
        if current is None:
            continue
        stripped = line.strip()
        if stripped.startswith("|"):
            if TABLE_SEP.match(stripped):
                continue
            if table_head:                  # first row of each table is its header
                table_head = False
                continue
            row = _table_row(stripped)
            lead_ok = current < len(wanted) or stripped.lstrip("| ").startswith("**")
            if row and lead_ok:
                found[current].append(row)
            continue
        table_head = True
        if current >= len(wanted):
            continue
        b = BULLET.match(line)
        if b:
            item = _item(b.group(1))
            if len(item["title"]) >= 3 and not item["title"].startswith(("$", "pip ", "npm ")):
                found[current].append(item)
        elif (n := NESTED.match(line)) and found[current] and not found[current][-1]["detail"]:
            found[current][-1].setdefault("children", []).append(_item(n.group(1))["title"])
    for key in sorted(found):
        if found[key]:
            seen, out = set(), []
            for it in found[key]:
                children = it.pop("children", [])
                if not it["detail"] and children:        # "**Group**:" + nested bullets → list them
                    it["detail"] = ", ".join(children)
                if it["title"].lower() not in seen:
                    seen.add(it["title"].lower())
                    out.append(it)
            return out[:limit]
    return []


def readme_excerpt(md, chars=1200):
    """Plain prose from the README (no code, tables, headings) for keyword classification."""
    out, in_code = [], False
    for line in md.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            in_code = not in_code
            continue
        if in_code or line.lstrip().startswith(("#", "|", "<", "!")):
            continue
        out.append(line)
    return clean(" ".join(out))[:chars]


# ── Technology evidence ─────────────────────────────────────────────────────

REQ_NAME = re.compile(r"^\s*-?\s*([A-Za-z0-9][A-Za-z0-9._\-]*)")


def _req_names(lines):
    return {m.group(1).lower() for l in lines if (m := REQ_NAME.match(l.split("#")[0]))}


def manifest_tokens(manifests):
    """Dependency names from manifests, plus each manifest's path as a presence token.
    Infra files (Dockerfile, compose, workflows) count by presence only — their contents
    mention images/URIs that are not dependencies."""
    tokens = set()
    for path, text in manifests.items():
        tokens.add(path.lower())
        name = path.rsplit("/", 1)[-1].lower()
        try:
            if name == "package.json":
                pkg = json.loads(text)
                for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                    for dep in pkg.get(key, {}):
                        tokens.add(dep.lower())
                        tokens.update(p for p in dep.lower().lstrip("@").split("/") if p)
            elif name == "pyproject.toml":
                proj = tomllib.loads(text)
                deps = list(proj.get("project", {}).get("dependencies", []))
                for extra in proj.get("project", {}).get("optional-dependencies", {}).values():
                    deps += extra
                deps += list(proj.get("tool", {}).get("poetry", {}).get("dependencies", {}))
                tokens |= _req_names(deps)
            elif name in ("requirements.txt", "pipfile", "environment.yml"):
                tokens |= _req_names(text.splitlines())
            elif name.endswith((".gradle.kts", ".versions.toml", "go.mod", "cargo.toml")):
                tokens.update(re.findall(r"[a-z0-9][a-z0-9._\-]*", text.lower()))  # coordinates, low noise
        except (ValueError, tomllib.TOMLDecodeError):
            pass  # malformed manifest: presence token only
    return tokens


def detect_tech(evidence_tokens, technologies):
    """Tech names whose match terms intersect the evidence tokens."""
    norm = {t.replace("_", "-") for t in evidence_tokens}
    return sorted(name for name, spec in technologies.items()
                  if any(m.replace("_", "-") in norm for m in spec["match"]))


# ── Classification & featured selection ─────────────────────────────────────

def haystack(repo):
    """Text a repo is judged on: description, topics, every extracted feature, README prose."""
    feats = repo.get("features_auto") or repo["features"]
    return " ".join([repo["description"] or "", " ".join(repo["topics"]),
                     " ".join(f["title"] + " " + f["detail"] for f in feats + repo["features"]),
                     repo.get("excerpt", "")]).lower()


def _mentions(hay, keywords):
    return any(re.search(r"\b" + re.escape(k) + r"\b", hay) for k in keywords)


def classify(repo, categories, min_score):
    override = repo.get("override", {}).get("category")
    if override:
        return override
    topics, hay = set(repo["topics"]), haystack(repo)
    best, best_score = "Other", 0
    for cat in categories:
        score = 3 * len(topics & set(cat.get("topics", [])))
        score += sum(1 for k in cat.get("keywords", []) if re.search(r"\b" + re.escape(k) + r"\b", hay))
        score += 1 if repo["language"] in cat.get("languages", []) else 0
        if score > best_score:
            best, best_score = cat["name"], score
    return best if best_score >= min_score else "Other"


def featured_score(repo, today):
    """Completeness + recency + depth of work; popularity is a minor, log-damped signal."""
    if repo["fork"] or repo["archived"]:
        return -1.0
    days = (today - date.fromisoformat(repo["pushed"][:10])).days
    s = 3 if days <= 30 else 2 if days <= 90 else 1 if days <= 365 else 0
    s += 1.0 * bool(repo["description"]) + 0.3 * min(len(repo["topics"]), 5)
    s += 1.5 * bool(repo["features"]) + 0.5 * bool(repo["homepage"]) + 0.5 * bool(repo["license"])
    s += 0.5 * bool(repo["release"]) + math.log10(1 + repo["commits"])
    s += 0.5 * math.log2(1 + repo["stars"] + repo["forks"])
    return round(s, 3)


def select_featured(repos, count, today):
    for r in repos:
        r["score"] = featured_score(r, today)
    pinned = [r for r in repos if r.get("override", {}).get("featured") is True]
    pool = sorted((r for r in repos if r.get("override", {}).get("featured") is None and r["score"] >= 0),
                  key=lambda r: -r["score"])
    chosen = (pinned + pool)[:max(count, len(pinned))]
    for r in repos:
        r["featured"] = r in chosen
    return [r["name"] for r in chosen]


# ── Aggregates ──────────────────────────────────────────────────────────────

def language_mix(repos, ignore, top=6):
    total = Counter()
    for r in repos:
        if not r["fork"]:
            total.update({k: v for k, v in r["languages"].items() if k not in ignore})
    size = sum(total.values()) or 1
    items = [{"name": k, "bytes": v, "share": v / size} for k, v in total.most_common()]
    if len(items) > top:
        rest = sum(i["bytes"] for i in items[top:])
        items = items[:top] + [{"name": "Other", "bytes": rest, "share": rest / size}]
    return items


def streaks(days):
    """days: [(iso_date, count)] ascending. Current streak may end today or yesterday."""
    longest = run = 0
    for _, c in days:
        run = run + 1 if c else 0
        longest = max(longest, run)
    current = 0
    tail = list(days)
    if tail and tail[-1][1] == 0:
        tail = tail[:-1]                    # today not yet active doesn't break the streak
    for _, c in reversed(tail):
        if not c:
            break
        current += 1
    return current, longest


def activity_stats(user, own_login, include_private):
    c = user["contributionsCollection"]
    days = [(d["date"], d["contributionCount"])
            for w in c["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    current, longest = streaks(days)
    best = max(days, key=lambda d: d[1]) if days else ("", 0)

    def visible(entry):
        return include_private or not entry["repository"]["isPrivate"]

    external = sorted({e["repository"]["nameWithOwner"] for key in
                       ("commitContributionsByRepository", "pullRequestContributionsByRepository")
                       for e in c[key] if visible(e) and e["repository"]["owner"]["login"] != own_login})
    return {
        "total": c["contributionCalendar"]["totalContributions"],
        "commits": c["totalCommitContributions"],
        "pull_requests": c["totalPullRequestContributions"],
        "reviews": c["totalPullRequestReviewContributions"],
        "issues": c["totalIssueContributions"],
        "repos_created": c["totalRepositoryContributions"],
        "active_days": sum(1 for _, n in days if n),
        "current_streak": current,
        "longest_streak": longest,
        "best_day": {"date": best[0], "count": best[1]},
        "days": [list(d) for d in days],
        "external_repos": external,
    }


def tech_groups(repos, technologies, declared):
    """{group: [{name, repos:[...], declared:bool}]} ordered by config group order then evidence."""
    groups, order = defaultdict(list), []
    for name, spec in technologies.items():
        if spec["group"] not in order:
            order.append(spec["group"])
        users = [r["name"] for r in repos if name in r["tech"]]
        if users:
            groups[spec["group"]].append({"name": name, "repos": users, "declared": False})
    for group, names in declared.items():
        if group not in order:
            order.append(group)
        have = {t["name"] for t in groups[group]}
        groups[group] += [{"name": n, "repos": [], "declared": True} for n in names if n not in have]
    return [{"group": g, "items": sorted(groups[g], key=lambda t: (t["declared"], -len(t["repos"]), t["name"]))}
            for g in order if groups.get(g)]


def focus_evidence(repos, focus):
    out = []
    for f in focus:
        hits = [r["name"] for r in repos if set(r["topics"]) & set(f.get("topics", []))
                or r["category"] in f.get("categories", []) or _mentions(haystack(r), f.get("keywords", []))]
        out.append({**f, "repos": hits})
    return out


def now_utc():
    return datetime.now(timezone.utc)
