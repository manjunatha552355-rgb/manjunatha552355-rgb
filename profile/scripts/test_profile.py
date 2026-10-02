"""Self-checks for the profile pipeline. Run: python -m unittest discover -s profile/scripts"""
import tomllib
import unittest
from datetime import date, timedelta

import analyze
import build

SECTIONS = ["Key Features", "Features", "What it does"]


def fake_repo(i, **kw):
    r = {"id": f"R{i}", "name": f"repo-{i}", "full_name": f"me/repo-{i}", "url": f"https://github.com/me/repo-{i}",
         "description": f"Project {i} | with a pipe <and> markup", "tagline": None, "visibility": "PUBLIC",
         "archived": i % 7 == 0, "fork": False, "language": "Python", "languages": {"Python": 1000 + i},
         "topics": ["llm"] if i % 2 else ["etl"], "stars": i, "forks": 0, "watchers": 0, "open_issues": 0,
         "open_prs": 0, "license": "MIT", "release": None, "homepage": None, "demo": None, "docs": None,
         "architecture": None, "created": "2026-01-01T00:00:00Z", "pushed": f"2026-0{1 + i % 9}-01T00:00:00Z",
         "branch": "main", "last_commit": "2026-05-01T00:00:00Z", "commits": i * 3,
         "features": [{"title": "Fast thing", "detail": "Does it quickly"}], "features_auto": [], "excerpt": "",
         "tech": ["PyTorch"], "override": {}, "weekly": [1, 0, 2, 3, 0, 5] * 8 + [1, 1, 1, 1]}
    r.update(kw)
    return r


def fake_user(days=365):
    start = date(2025, 10, 3)
    cal = [{"contributionDays": [{"date": (start + timedelta(d)).isoformat(), "contributionCount": d % 5}
                                 for d in range(w, min(w + 7, days))]} for w in range(0, days, 7)]
    return {"login": "me", "name": "Me", "createdAt": "2025-01-01T00:00:00Z", "followers": {"totalCount": 0},
            "contributionsCollection": {
                "totalCommitContributions": 10, "totalIssueContributions": 1, "totalPullRequestContributions": 2,
                "totalPullRequestReviewContributions": 0, "totalRepositoryContributions": 1,
                "restrictedContributionsCount": 0,
                "contributionCalendar": {"totalContributions": 99, "weeks": cal},
                "commitContributionsByRepository": [
                    {"repository": {"nameWithOwner": "other/secret", "isPrivate": True, "url": "", "owner": {"login": "other"}},
                     "contributions": {"totalCount": 3}},
                    {"repository": {"nameWithOwner": "other/public", "isPrivate": False, "url": "", "owner": {"login": "other"}},
                     "contributions": {"totalCount": 3}}],
                "pullRequestContributionsByRepository": []}}


class FeatureExtraction(unittest.TestCase):
    def test_bullets_emoji_bold_and_nested(self):
        md = ("# X\n## 🚀 Key Features\n- 🎙️ **Two modes** — meeting and ambient\n"
              "*   **Analysis**:\n    *   **VWAP**: trend\n    *   **RSI**: momentum\n"
              "```\n- not a feature\n```\n## Install\n- pip install x\n")
        f = analyze.extract_features(md, SECTIONS)
        self.assertEqual(f[0], {"title": "Two modes", "detail": "meeting and ambient"})
        self.assertEqual(f[1], {"title": "Analysis", "detail": "VWAP, RSI"})
        self.assertEqual(len(f), 2)

    def test_table_section(self):
        md = "## Features\n\n| Category | Details |\n|---|---|\n| **Eval** | LLM-as-judge |\n| **API** | FastAPI |\n"
        self.assertEqual([x["title"] for x in analyze.extract_features(md, SECTIONS)], ["Eval", "API"])

    def test_lead_table_fallback_needs_bold_labels(self):
        md = "# T\n\n| | |\n|---|---|\n| **Detects** | 39 rules |\n| plain | row |\n\n## Install\n"
        self.assertEqual(analyze.extract_features(md, SECTIONS), [{"title": "Detects", "detail": "39 rules"}])

    def test_nothing_invented(self):
        self.assertEqual(analyze.extract_features("# Title\n\nJust prose.\n## Usage\n- run it\n", SECTIONS), [])


class TechEvidence(unittest.TestCase):
    def test_infra_files_count_by_presence_only(self):
        tokens = analyze.manifest_tokens({"docker-compose.yml": "image: tensorflow/tensorflow\nsqlite:///x.db",
                                          "requirements.txt": "torch>=2.3  # tensorflow later\nnumpy\n",
                                          "package.json": '{"devDependencies": {"electron": "1", "@opentelemetry/api": "1"}}'})
        self.assertIn("docker-compose.yml", tokens)
        self.assertNotIn("tensorflow", tokens)
        self.assertNotIn("sqlite", tokens)
        self.assertTrue({"torch", "numpy", "electron", "opentelemetry"} <= tokens)

    def test_detect_tech(self):
        techs = {"PyTorch": {"group": "AI", "match": ["torch"]}, "Docker": {"group": "Ops", "match": ["docker-compose.yml"]}}
        self.assertEqual(analyze.detect_tech({"torch", "docker-compose.yml"}, techs), ["Docker", "PyTorch"])


class Classification(unittest.TestCase):
    cats = [{"name": "LLM", "topics": ["llm"], "keywords": ["language model"]},
            {"name": "Data", "topics": ["etl"], "keywords": ["pipeline"]}]

    def test_topic_beats_keyword_and_override_wins(self):
        r = fake_repo(1, topics=["llm"], description="data pipeline")
        self.assertEqual(analyze.classify(r, self.cats, 2), "LLM")
        r["override"] = {"category": "Data"}
        self.assertEqual(analyze.classify(r, self.cats, 2), "Data")

    def test_below_threshold_is_other(self):
        self.assertEqual(analyze.classify(fake_repo(1, topics=[], description="misc"), self.cats, 2), "Other")

    def test_featured_pins_and_excludes(self):
        repos = [fake_repo(i) for i in range(1, 6)]
        repos[4]["override"] = {"featured": True}
        repos[0]["override"] = {"featured": False}
        names = analyze.select_featured(repos, 2, date(2026, 10, 1))
        self.assertEqual(names[0], "repo-5")
        self.assertNotIn("repo-1", names)
        self.assertEqual(len(names), 2)


class Activity(unittest.TestCase):
    def test_streaks_tolerate_inactive_today(self):
        self.assertEqual(analyze.streaks([("a", 1), ("b", 2), ("c", 0), ("d", 1), ("e", 1), ("f", 0)]), (2, 2))

    def test_private_external_repos_hidden(self):
        stats = analyze.activity_stats(fake_user(), "me", include_private=False)
        self.assertEqual(stats["external_repos"], ["other/public"])


class RenderAtScale(unittest.TestCase):
    cfg = tomllib.loads(build.CONFIG.read_text(encoding="utf-8"))

    def render(self, n):
        repos = [fake_repo(i) for i in range(1, n + 1)]
        for r in repos:
            r["category"] = analyze.classify(r, self.cfg["categories"], 2)
        featured = analyze.select_featured(repos, 4, date(2026, 10, 1))
        m = build.model(self.cfg, fake_user(), repos, featured)
        files, readme, catalog = build.render(m, self.cfg)
        build.validate(files, readme, catalog)
        return files, readme, catalog

    def test_zero_one_and_many_repositories(self):
        for n in (0, 1, 300):
            with self.subTest(repos=n):
                files, readme, catalog = self.render(n)
                self.assertLess(len(readme), 60_000, "README must stay compact as repo count grows")
                self.assertEqual(sum(f.startswith("card-") for f in files), 2 * min(n, 4))
                if n:
                    self.assertIn("repo-1", catalog)
                self.assertNotIn("<and>", readme)

    def test_explorer_is_capped(self):
        _, readme, catalog = self.render(300)
        self.assertLess(readme.count("](https://github.com/me/repo-"), 120)
        self.assertEqual(catalog.count("](https://github.com/me/repo-"), 300)

    def test_validate_rejects_token_leak(self):
        files, readme, catalog = self.render(1)
        with self.assertRaises(SystemExit):
            build.validate(files, readme + "ghp_" + "a" * 36, catalog)


if __name__ == "__main__":
    unittest.main()
