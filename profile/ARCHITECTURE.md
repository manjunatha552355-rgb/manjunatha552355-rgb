# How this profile works

This GitHub profile is generated, not hand-written. A small Python pipeline reads the GitHub API, analyzes every public repository, and renders the README plus a set of SVG components. GitHub Actions runs it daily. A new repository, a changed description or a new release shows up on the profile without anyone editing the README.

```
GitHub GraphQL/REST API ──► fetch.py ──► analyze.py ──► svg.py + build.py ──► README.md
                              │             │                                  profile/generated/*.svg
                              │             └─ features, categories, tech,     profile/CATALOG.md
                              │                featured score, activity stats  profile/data/profile.json
                              └─ incremental: README/manifests re-read only
                                 for repos whose pushedAt changed
```

## Layout

| Path | Role |
|---|---|
| `README.md` | Generated presentation layer. Do not edit it directly. |
| `profile/config/profile.toml` | **The only hand-maintained data**: identity, links, focus areas, classification rules, technology map, per-project overrides. |
| `profile/templates/README.md.tmpl` | Section order and static wording. Dynamic content goes into `{{slots}}`. |
| `profile/scripts/github.py` | Stdlib-only API client: retries, rate-limit back-off. It never prints the token. |
| `profile/scripts/fetch.py` | GraphQL queries: repository list (paginated, 100 per page), per-repo details in batches, contribution calendar, weekly commit stats. |
| `profile/scripts/analyze.py` | Feature extraction, technology evidence, classification, featured scoring, language mix, streaks. |
| `profile/scripts/svg.py` | SVG components, each rendered at 840 px (desktop) and 420 px (phone). |
| `profile/scripts/build.py` | Orchestration, README rendering, validation, write-if-changed. |
| `profile/scripts/test_profile.py` | Self-checks, run before every build in CI. |
| `profile/data/profile.json` | Generated data snapshot. It is also the cache, and a stable JSON source for any external site. |
| `profile/generated/` | Generated SVGs. `*-m.svg` files are the phone variants. |
| `.github/workflows/refresh-profile.yml` | Daily, manual and push-triggered refresh. |

There are no third-party dependencies and no external image services, so nothing breaks when a stats service goes down.

## How the data is derived

- **Repositories** are discovered through the API. New, renamed, archived, or re-described repos and visibility changes all propagate on the next run. The cache is keyed by the GraphQL node id, so renames keep their cache. Cards for renamed or unfeatured repos are deleted automatically.
- **Key capabilities** come from each README:
  - top-level bullets and table rows under headings named in `analysis.feature_sections` (Features, Key Features, What it does, …);
  - otherwise, a lead table with bold labels.
  If nothing qualifies, the card shows no capabilities. Nothing is invented. Curated text goes in `[projects.<name>].features`.
- **Technologies** need evidence from one of three sources:
  - dependency names parsed from `requirements.txt`, `pyproject.toml`, `package.json` or Gradle files;
  - repository topics;
  - GitHub's language detection.
  Infra files (Dockerfile, compose, workflows) count by presence only. Experience without a public repository can be listed under `[stack.declared]`, where it is labeled "Professional experience".
- **Categories** come from a score: topic match ×3, keyword match ×1, language ×1. A repo below `min_score` lands in *Other*. Override per project with `category = "..."`.
- **Featured projects**: pinned projects come first. Remaining slots are filled by a score built from recency, completeness (description, topics, README features, license, homepage, release) and commit depth. Stars and forks are a minor log-scaled signal, never the main one.
- **Activity** comes from the GitHub contribution calendar for the last 12 months. Private repository names are never shown unless `include_private = true`.

## GitHub rendering constraints

GitHub README rendering cannot run JavaScript and strips `style` and `class` attributes. This design works within those limits:

- **Motion** is CSS inside the SVGs: one-time entrance fades, line drawing, bar growth. It is disabled under `prefers-reduced-motion`. Every element is visible by default, so a renderer without animation still shows the complete graphic.
- **No hover effects.** SVGs inside `<img>` receive no pointer events. Interaction is done with real links: each card links to its repository, with an action row (Repository · Live demo · Documentation · Architecture · Release) below it.
- **Expandable sections** use native `<details>` (Repository Explorer, technology evidence).
- **Phones** get a reflowed 420 px layout through `<picture><source media="(max-width: 600px)">`, which GitHub preserves.
- **Fonts** use the system stack. Text widths are estimated conservatively, and long text is wrapped or truncated with an ellipsis.

## Setup

1. The workflow uses the built-in `GITHUB_TOKEN`, so no setup is needed for public data.
2. *Optional:* add a read-only personal access token for your account as the repository secret `PROFILE_TOKEN`. Queries then run as you, so contribution totals can include private work (counts only, never names). Private repository *metadata* appears only if you also set `include_private = true`, which makes those names public on your profile.
3. Run **Actions → Refresh profile → Run workflow** once, or wait for the daily run.

To run locally:

```bash
GITHUB_TOKEN=$(gh auth token) python profile/scripts/build.py          # incremental
GITHUB_TOKEN=$(gh auth token) python profile/scripts/build.py --full   # ignore cache
python profile/scripts/build.py --offline                              # re-render from the snapshot, no API
python -m unittest discover -s profile/scripts                         # self-checks
```

Requires Python 3.11+ (for `tomllib`). Nothing needs to be installed.

## Customization

| Change | Where |
|---|---|
| Name, roles, headline, overview, links | `[identity]`, `[[links]]` |
| Pin or hide a featured project, override its category, tagline, capabilities or links | `[projects.<repo-name>]` |
| Number of featured cards, explorer rows per category | `[featured]`, `[explorer]` |
| Hide repositories, include forks or archived repos | `[repos]` |
| Categories and their matching rules | `[[categories]]` |
| Engineering Focus tiles | `[[focus]]` |
| Recognized technologies | `[technologies]` |
| Section order and wording | `profile/templates/README.md.tmpl` |
| Colors, type scale, motion | constants at the top of `profile/scripts/svg.py` |

A push that changes config, scripts or the template triggers a rebuild.

## Maintenance

- **Normal repository changes need no action.** The daily run picks them up and commits only when output actually changed.
- **Cache:** README analysis is reused while a repo's `pushedAt` is unchanged and the analysis config hash still matches. Use `--full`, or the workflow's *full* input, after changing extraction logic. Alternatively, bump `ANALYZER_VERSION` in `analyze.py`.
- **Failures:** validation runs before anything is written. It checks that every SVG is well-formed XML, that no template slots are unresolved, that all referenced assets exist, and that the output contains no token-like strings. A failed run leaves the last good profile in place.
- **Rate limits:** a full refresh of hundreds of repositories costs a handful of GraphQL calls (100 repos per page, details in batches of 10). The client waits out rate limits of up to 5 minutes and aborts beyond that.
- **Scale:** the README shows at most `max_per_category` rows per category, and `profile/CATALOG.md` lists everything. Tests render 0, 1 and 300 repositories and check that the README stays compact.
