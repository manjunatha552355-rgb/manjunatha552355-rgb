"""SVG components for the profile. Pure functions: data in, SVG string out.

GitHub renders README images through <img>, so: no scripts, no hover, no web fonts.
Motion is CSS-only, plays once on load, and is disabled under prefers-reduced-motion.
Every animated element is visible by default, so a renderer without CSS animation
still shows the complete, correct graphic."""
import math
from datetime import date
from xml.sax.saxutils import escape

FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,'Helvetica Neue',Arial,sans-serif"
INK, BODY, MUTED = "#17212B", "#46566A", "#7C8B9C"
LINE, SURFACE, TINT, TINT_LINE = "#E3EAF2", "#F7FAFD", "#EBF5FD", "#D3E7F7"
SKY, DEEP, SOFT = "#3B9BDB", "#1D6FB2", "#A9D4F2"
EASE = "cubic-bezier(.22,.61,.36,1)"

CSS = f"""
text{{font-family:{FONT};fill:{INK}}}
.e{{font-size:11px;font-weight:600;letter-spacing:.12em;fill:{DEEP}}}
.b{{fill:{BODY}}}.m{{fill:{MUTED}}}.n{{font-variant-numeric:tabular-nums}}
.in{{animation:in .9s {EASE} both}}
.grow{{transform-box:fill-box;transform-origin:left center;animation:grow 1.2s {EASE} both}}
.pop{{transform-box:fill-box;transform-origin:center;animation:pop .8s {EASE} both}}
.draw{{stroke-dasharray:1 1;animation:draw 1.8s cubic-bezier(.45,0,.25,1) both}}
.pulse{{transform-box:fill-box;transform-origin:center;animation:pulse 2.8s ease-out infinite}}
@keyframes in{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1;transform:none}}}}
@keyframes grow{{from{{transform:scaleX(0)}}to{{transform:none}}}}
@keyframes pop{{from{{opacity:0;transform:scale(.3)}}to{{opacity:1;transform:none}}}}
@keyframes draw{{from{{stroke-dashoffset:1}}to{{stroke-dashoffset:0}}}}
@keyframes pulse{{from{{opacity:.55;transform:scale(1)}}to{{opacity:0;transform:scale(2.8)}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}.pulse{{display:none}}}}
"""


# ── Primitives ──────────────────────────────────────────────────────────────

def esc(s):
    return escape(str(s), {'"': "&quot;"})


def fmt_date(iso):
    d = date.fromisoformat(iso[:10])
    return f"{d:%b} {d.day}, {d.year}"


def fmt_num(n):
    return f"{n / 1000:.1f}k".replace(".0k", "k") if n >= 10000 else f"{n:,}"


_NARROW, _WIDE = set("ijlI.,:;'|!()[] tf"), set("mwMW@%")


def text_width(s, size, bold=False):
    """Approximate rendered width for the system sans stack (no font metrics in Actions)."""
    w = sum(.28 if c in _NARROW else .80 if c in _WIDE else .63 if c.isupper() else
            .55 if c.isdigit() else .50 for c in str(s))
    return w * size * (1.1 if bold else 1)


def truncate(s, size, max_w, bold=False):
    s = str(s)
    if text_width(s, size, bold) <= max_w:
        return s
    while s and text_width(s + "…", size, bold) > max_w:
        s = s[:-1]
    return s.rstrip(" ,.;:-") + "…"


def wrap(s, size, max_w, max_lines, bold=False):
    lines, cur = [], ""
    for word in str(s).split():
        trial = f"{cur} {word}".strip()
        if text_width(trial, size, bold) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and text_width(last + "…", size, bold) > max_w:
            last = last[:-1]
        lines[-1] = last.rstrip(" ,.;:-") + "…"
    return [truncate(l, size, max_w, bold) for l in lines]


def text(x, y, s, size=13, cls="", weight=None, anchor=None, extra=""):
    attrs = f'x="{x:.1f}" y="{y:.1f}" font-size="{size}"'
    if cls:
        attrs += f' class="{cls}"'
    if weight:
        attrs += f' font-weight="{weight}"'
    if anchor:
        attrs += f' text-anchor="{anchor}"'
    return f"<text {attrs}{extra}>{esc(s)}</text>"


def anim(content, cls="in", delay=0.0):
    return f'<g class="{cls}" style="animation-delay:{delay:.2f}s">{content}</g>'


def chip(x, y, label, size=12, h=26, fill=TINT, stroke=TINT_LINE, color=DEEP, suffix="", dashed=False):
    """Pill with optional muted suffix. Returns (svg, width)."""
    pad = 11
    tw = text_width(label, size, True)
    sw = text_width(suffix, size - 1) + 6 if suffix else 0
    w = tw + sw + pad * 2
    dash = ' stroke-dasharray="3 3"' if dashed else ""
    out = (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h}" rx="{h / 2:.1f}" fill="{fill}" '
           f'stroke="{stroke}"{dash}/>'
           + text(x + pad, y + h / 2 + size * .36, label, size, weight=560, extra=f' fill="{color}"'))
    if suffix:
        out += text(x + pad + tw + 6, y + h / 2 + size * .36, suffix, size - 1, "m n")
    return out, w


def frame(x, y, w, h, r=18, fill="#FFFFFF"):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{LINE}" '
            f'filter="url(#sh)"/>')


def document(w, h, body, label, defs=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{esc(label)}"><title>{esc(label)}</title>'
            f'<defs><filter id="sh" x="-5%" y="-10%" width="110%" height="130%">'
            f'<feDropShadow dx="0" dy="4" stdDeviation="7" flood-color="#1D4E7A" flood-opacity=".07"/></filter>'
            f'{defs}</defs><style>{CSS}</style>{body}</svg>')


# Icons — 14px, stroked, drawn from geometry so no third-party icon assets are needed.
def icon(kind, x, y, color=MUTED):
    s = f'fill="none" stroke="{color}" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"'
    cx, cy = x + 7, y + 7
    if kind == "star":
        pts = " ".join(f"{cx + (6.5 if i % 2 == 0 else 2.8) * math.sin(i * math.pi / 5):.2f},"
                       f"{cy - (6.5 if i % 2 == 0 else 2.8) * math.cos(i * math.pi / 5):.2f}" for i in range(10))
        return f'<polygon points="{pts}" {s}/>'
    if kind == "fork":
        return (f'<circle cx="{x + 3.5}" cy="{y + 2.5}" r="1.8" {s}/><circle cx="{x + 10.5}" cy="{y + 2.5}" r="1.8" {s}/>'
                f'<circle cx="{cx}" cy="{y + 12}" r="1.8" {s}/>'
                f'<path d="M{x + 3.5} {y + 4.3}v1.7a2 2 0 0 0 2 2h3a2 2 0 0 0 2-2v-1.7M{cx} {y + 8}v2.2" {s}/>')
    if kind == "commit":
        return f'<circle cx="{cx}" cy="{cy}" r="2.8" {s}/><path d="M{x} {cy}h4.2M{x + 9.8} {cy}H{x + 14}" {s}/>'
    if kind == "clock":
        return f'<circle cx="{cx}" cy="{cy}" r="6" {s}/><path d="M{cx} {cy - 3.2}V{cy}l2.2 1.6" {s}/>'
    if kind == "law":
        return f'<path d="M{cx} {y + 1}v12M{x + 3} {y + 13}h8M{x + 1.5} {y + 4}h11M{x + 1.5} {y + 4}l-1.5 4h3zM{x + 12.5} {y + 4}l-1.5 4h3z" {s}/>'
    return ""


# ── Layout widths ───────────────────────────────────────────────────────────
# Every component renders at WIDE (desktop) and NARROW (phones, served via
# <picture media="(max-width: 600px)">). Narrow layouts reflow — single column,
# stacked panels, fewer calendar weeks — instead of shrinking text to illegibility.
WIDE, NARROW = 840, 420


def _flow_chips(items, x0, y, x_max, size=12, h=26, gap=8, row_gap=8, max_rows=None, **kw):
    """Lay chips left→right with wrapping. Returns (svg list, bottom y)."""
    out, cx, cy, rows = [], x0, y, 1
    for label, suffix in items:
        w = text_width(label, size, True) + (text_width(suffix, size - 1) + 6 if suffix else 0) + 22
        if cx + w > x_max and cx > x0:
            if max_rows and rows >= max_rows:
                break
            cx, cy, rows = x0, cy + h + row_gap, rows + 1
        c, w = chip(cx, cy, label, size, h, suffix=suffix, **kw)
        out.append(c)
        cx += w + gap
    return out, cy + h


# ── Hero ────────────────────────────────────────────────────────────────────

def hero(identity, repos, latest_activity, W=WIDE):
    wide = W >= 700
    x0 = 48 if wide else 28
    text_w = 420 if wide else W - 2 * x0
    body = [f'<circle cx="{W - 120}" cy="40" r="{W * .36:.0f}" fill="url(#glow)"/>']
    if latest_activity:   # live freshness indicator — the only looping element
        body.append(f'<circle cx="{x0 + 5}" cy="54" r="4" fill="{SKY}" class="pulse"/>'
                    f'<circle cx="{x0 + 5}" cy="54" r="4" fill="{SKY}"/>'
                    + text(x0 + 18, 58, f"Latest activity · {fmt_date(latest_activity)}", 11.5, "m"))
    size = 44 if wide else 34
    name = text(x0, 58 + size + 10, identity["name"], size, weight=700, extra=f' letter-spacing="{-size * .02:.1f}"')
    y = 58 + size + 10 + 34
    lines = wrap(identity["headline"], 15.5, text_w, 3)
    head = "".join(text(x0, y + i * 22, l, 15.5, "b") for i, l in enumerate(lines))
    chips, bottom = _flow_chips([(r, "") for r in identity["roles"]], x0, y + (len(lines) - 1) * 22 + 22,
                                x0 + text_w + 20)
    body += [anim(name, delay=.05), anim(head, delay=.15), anim("".join(chips), delay=.3)]
    if wide:
        H = max(300, bottom + 40)
        body.append(constellation(repos, 640, 146, 76))
    else:
        r = 70
        body.append(constellation(repos, W / 2, bottom + 36 + r, r))
        H = bottom + 36 + 2 * r + 64
    label = f"{identity['name']} — {', '.join(identity['roles'])}. {identity['headline']}"
    defs = (f'<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFFFFF"/>'
            f'<stop offset="1" stop-color="#F2F8FD"/></linearGradient>'
            f'<radialGradient id="glow"><stop offset="0" stop-color="{TINT}" stop-opacity=".9"/>'
            f'<stop offset="1" stop-color="{TINT}" stop-opacity="0"/></radialGradient>'
            f'<clipPath id="clip"><rect x="8" y="8" width="{W - 16}" height="{H - 16}" rx="22"/></clipPath>')
    bg = frame(8, 8, W - 16, H - 16, 22, "url(#bg)")
    return document(W, H, bg + f'<g clip-path="url(#clip)">{body[0]}</g>' + "".join(body[1:]), label, defs)


def constellation(repos, cx, cy, r, limit=14):
    """Repositories on a ring, linked when they share topics or technologies.
    Node size = commit depth; dark nodes = featured. Real data, drawn in on load."""
    nodes = sorted((p for p in repos if not p["fork"]), key=lambda p: -p["score"])[:limit]
    if not nodes:
        return ""
    n = len(nodes)
    pos = [(cx + r * math.cos(-math.pi / 2 + 2 * math.pi * i / n),
            cy + r * math.sin(-math.pi / 2 + 2 * math.pi * i / n)) for i in range(n)]
    out = [f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{TINT_LINE}" stroke-dasharray="2 5"/>']
    for i in range(n):
        for j in range(i + 1, n):
            shared = len(set(nodes[i]["topics"]) & set(nodes[j]["topics"])) + \
                len(set(nodes[i]["tech"]) & set(nodes[j]["tech"]))
            if shared:
                (x1, y1), (x2, y2) = pos[i], pos[j]
                qx, qy = cx + ((x1 + x2) / 2 - cx) * .25, cy + ((y1 + y2) / 2 - cy) * .25
                out.append(f'<path d="M{x1:.1f} {y1:.1f}Q{qx:.1f} {qy:.1f} {x2:.1f} {y2:.1f}" pathLength="1" '
                           f'fill="none" stroke="{SKY}" stroke-opacity="{min(.2 + .08 * shared, .6):.2f}" '
                           f'stroke-width="{.8 + .3 * min(shared, 4):.1f}" class="draw" '
                           f'style="animation-delay:{.4 + .05 * len(out):.2f}s"/>')
    show_all = n <= 10
    for i, (p, (x, y)) in enumerate(zip(nodes, pos)):
        rad = 3.5 + min(5.0, math.log2(1 + p["commits"]) / 1.6)
        fill = DEEP if p["featured"] else SOFT
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rad:.1f}" fill="{fill}" stroke="#FFFFFF" '
                   f'stroke-width="2" class="pop" style="animation-delay:{.2 + .06 * i:.2f}s"/>')
        if show_all or p["featured"]:
            a = -math.pi / 2 + 2 * math.pi * i / n
            dx, dy = math.cos(a), math.sin(a)
            anchor = "start" if dx > .3 else "end" if dx < -.3 else "middle"
            lx, ly = x + dx * (rad + 7), y + dy * (rad + 9) + 4
            out.append(anim(text(lx, ly, truncate(p["name"], 10.5, 86), 10.5, "m", anchor=anchor), delay=.6 + .05 * i))
    out.append(anim(text(cx, cy + r + 46, "Public repositories · linked by shared topics & stack",
                         10.5, "m", anchor="middle"), delay=1.0))
    return "".join(out)


# ── Engineering Focus ───────────────────────────────────────────────────────

def focus(areas, W=WIDE):
    cols, gap = (3, 16) if W >= 700 else (1, 12)
    tw = (W - 16 - gap * (cols - 1)) / cols
    th = 142 if cols > 1 else 128
    rows = math.ceil(len(areas) / cols)
    H = 16 + rows * th + (rows - 1) * gap
    out = []
    for i, a in enumerate(areas):
        x, y = 8 + (i % cols) * (tw + gap), 8 + (i // cols) * (th + gap)
        tile = [frame(x, y, tw, th, 16),
                f'<rect x="{x + 22}" y="{y + 22}" width="22" height="3" rx="1.5" fill="{SKY}" class="grow" '
                f'style="animation-delay:{.3 + .08 * i:.2f}s"/>',
                text(x + 52, y + 27, f"{i + 1:02d}", 11, "e n"),
                text(x + 22, y + 56, truncate(a["title"], 16, tw - 44, True), 16, weight=650)]
        tile += [text(x + 22, y + 80 + k * 19, l, 13, "b") for k, l in enumerate(wrap(a["summary"], 13, tw - 44, 2))]
        if a["repos"]:
            n = len(a["repos"])
            tile.append("".join(f'<circle cx="{x + 25 + k * 9}" cy="{y + th - 22}" r="3" fill="{SKY}"/>'
                                for k in range(min(n, 5))) +
                        text(x + 25 + min(n, 5) * 9 + 4, y + th - 18,
                             f"{n} public repositor{'y' if n == 1 else 'ies'}", 11.5, "m"))
        out.append(anim("".join(tile), delay=.08 * i))
    label = "Engineering focus: " + "; ".join(f"{a['title']} ({len(a['repos'])} repositories)" for a in areas)
    return document(W, H, "".join(out), label)


# ── Technology Ecosystem ────────────────────────────────────────────────────

def stack(groups, languages, W=WIDE):
    wide = W >= 700
    x_label, x_max = (36, W - 32)
    x0 = 196 if wide else x_label
    rows = []
    if languages:
        rows.append(("Languages", [(l["name"], f"{l['share'] * 100:.0f}%", False) for l in languages if l["name"] != "Other"]))
    rows += [(g["group"], [(t["name"], str(len(t["repos"])) if t["repos"] else "", t["declared"]) for t in g["items"]])
             for g in groups]
    out, y, k = [], 34, 0
    for gi, (group, items) in enumerate(rows):
        if gi:
            out.append(f'<line x1="{x_label}" y1="{y - 12}" x2="{x_max}" y2="{y - 12}" stroke="{LINE}"/>')
        out.append(anim(text(x_label, y + 17 if wide else y + 8, group.upper(), 11, "e"), delay=.06 * gi))
        cx, cy = x0, y if wide else y + 22
        for name, suffix, declared in items:
            w = text_width(name, 12.5, True) + (text_width(suffix, 11.5) + 6 if suffix else 0) + 22
            if cx + w > x_max and cx > x0:
                cx, cy = x0, cy + 36
            c, w = chip(cx, cy, name, 12.5, 28, fill="#FFFFFF" if declared else TINT, suffix=suffix,
                        dashed=declared, color=INK)
            out.append(anim(c, delay=.06 * gi + .025 * k))
            cx += w + 8
            k += 1
        y = cy + 28 + 34
    note = "Evidence: repository topics, dependency manifests and GitHub language data. Number = public repositories."
    if any(d for _, items in rows for *_, d in items):
        note = "Dashed = professional experience (configured). " + note
    note_lines = wrap(note, 11, x_max - x_label, 3)
    out += [text(x_label, y - 6 + i * 15, l, 11, "m") for i, l in enumerate(note_lines)]
    H = y + 14 + (len(note_lines) - 1) * 15
    label = "Technology ecosystem. " + " ".join(f"{g}: {', '.join(n for n, *_ in items)}." for g, items in rows)
    return document(W, H, frame(8, 8, W - 16, H - 16, 20) + "".join(out), label)


# ── Project card ────────────────────────────────────────────────────────────

def card(p, W=WIDE):
    wide = W >= 700
    x0 = 40 if wide else 28
    inner = W - 2 * x0
    out = []
    pills, px = [], W - x0
    for label, strong in ([("Archived", False)] if p["archived"] else []) + \
            [("Private" if p["visibility"] == "PRIVATE" else "Public", False)] + \
            ([(p["release"]["tag"], True)] if p.get("release") else []):
        w = text_width(label, 11.5, True) + 22
        px -= w
        c, _ = chip(px, 34, label, 11.5, 24, fill=TINT if strong else "#FFFFFF",
                    stroke=TINT_LINE if strong else LINE, color=DEEP if strong else BODY)
        pills.append(c)
        px -= 8
    out.append(text(x0, 51, truncate(p["category"].upper(), 11, px - x0 - 12), 11, "e"))
    out += pills
    size = 25 if wide else 22
    out.append(text(x0, 90, truncate(p["name"], size, inner, True), size, weight=700, extra=' letter-spacing="-0.4"'))
    y = 120
    for l in wrap(p.get("tagline") or p["description"] or "", 15 if wide else 14, inner, 2 if wide else 3):
        out.append(text(x0, y, l, 15 if wide else 14, "b"))
        y += 22 if wide else 20
    if p["features"]:
        y += 12
        cols = 2 if wide else 1
        colw = (inner - 32 * (cols - 1)) / cols
        feats = p["features"][:4]
        for r in range(0, len(feats), cols):
            row_h = 0
            for c, f in enumerate(feats[r:r + cols]):
                fx = x0 + c * (colw + 32)
                block = [f'<rect x="{fx}" y="{y - 10}" width="3" height="14" rx="1.5" fill="{SKY}"/>',
                         text(fx + 13, y + 1, truncate(f["title"], 13.5, colw - 13, True), 13.5, weight=620)]
                lines = wrap(f["detail"], 12.5, colw - 13, 2) if f["detail"] else []
                block += [text(fx + 13, y + 20 + k * 18, l, 12.5, "b") for k, l in enumerate(lines)]
                out.append(anim("".join(block), delay=.25 + .08 * (r + c)))
                row_h = max(row_h, 22 + len(lines) * 18)
            y += row_h + 10
    tech = ([p["language"]] if p["language"] else []) + [t for t in p["tech"] if t != p["language"]]
    if tech:
        chips, bottom = _flow_chips([(t, "") for t in tech], x0, y + 8, x0 + inner, 12, 24,
                                    max_rows=1 if wide else 2, color=INK)
        out.append(anim("".join(chips), delay=.5))
        y = bottom
    y += 22
    out.append(f'<line x1="{x0}" y1="{y}" x2="{x0 + inner}" y2="{y}" stroke="{LINE}"/>')
    y += 30
    stats = [("star", f"{fmt_num(p['stars'])} star{'s' * (p['stars'] != 1)}"),
             ("fork", f"{fmt_num(p['forks'])} fork{'s' * (p['forks'] != 1)}"),
             ("commit", f"{fmt_num(p['commits'])} commit{'s' * (p['commits'] != 1)}"),
             ("clock", f"Updated {fmt_date(p['last_commit'] or p['pushed'])}")]
    if p["license"]:
        stats.append(("law", p["license"] + (" license" if p["license"] == "Custom" else "")))
    sx = x0
    for kind, label in stats:
        w = 20 + text_width(label, 12.5) + 22
        if sx + w - 22 > x0 + inner:
            sx, y = x0, y + 24
        out.append(icon(kind, sx, y - 11) + text(sx + 20, y, label, 12.5, "b n"))
        sx += w
    weekly = p.get("weekly") or []
    if sum(1 for w in weekly if w) >= 4:
        if wide and sx < x0 + inner - 170:
            out.append(sparkline(weekly, x0 + inner - 150, y - 22, 150, 26))
        else:
            y += 44
            out.append(sparkline(weekly, x0, y - 22, inner, 26))
    H = y + 32
    label = f"{p['name']}: {p.get('tagline') or p['description'] or ''} " + \
            " ".join(f"{f['title']}." for f in p["features"]) + f" {p['stars']} stars, {p['commits']} commits."
    return document(W, H, frame(8, 8, W - 16, H - 16, 20) + "".join(out), label)


def sparkline(values, x, y, w, h):
    top = max(values) or 1
    step = w / (len(values) - 1)
    pts = [(x + i * step, y + h - v / top * h) for i, v in enumerate(values)]
    line = "M" + " L".join(f"{a:.1f} {b:.1f}" for a, b in pts)
    area = line + f" L{x + w:.1f} {y + h} L{x} {y + h} Z"
    return (f'<path d="{area}" fill="{TINT}" class="in" style="animation-delay:.6s"/>'
            f'<path d="{line}" pathLength="1" fill="none" stroke="{SKY}" stroke-width="1.6" class="draw" '
            f'style="animation-delay:.5s"/>' + text(x + w, y - 6, "Commits · 52 weeks", 10, "m", anchor="end"))


# ── Distribution: languages + categories ────────────────────────────────────

def bars(x, y, w, items, delay=0.0, label_w=104):
    """Ranked horizontal bars, single hue, direct labels. items: [(label, value, value_label)]."""
    top = max((v for _, v, _ in items), default=1) or 1
    out, track = [], w - label_w - 46
    for i, (label, value, vlabel) in enumerate(items):
        ry = y + i * 30
        out.append(text(x, ry + 4, truncate(label, 12.5, label_w - 6), 12.5, "b"))
        out.append(f'<rect x="{x + label_w}" y="{ry - 5}" width="{track}" height="8" rx="4" fill="{SURFACE}"/>')
        out.append(f'<rect x="{x + label_w}" y="{ry - 5}" width="{max(track * value / top, 4):.1f}" height="8" rx="4" '
                   f'fill="{SKY}" class="grow" style="animation-delay:{delay + .07 * i:.2f}s"/>')
        out.append(text(x + w, ry + 4, vlabel, 12, "m n", anchor="end"))
    return "".join(out)


def distribution(languages, categories, repo_count, W=WIDE):
    langs = [(l["name"], l["share"], f"{l['share'] * 100:.1f}%") for l in languages]
    cats = [(c["name"], len(c["repos"]), str(len(c["repos"]))) for c in categories]
    note = (f"Code share by bytes (GitHub Linguist) across {repo_count} public repositories. "
            "Categories from topics, README content and configuration.")
    if W >= 700:
        rows = max(len(langs), len(cats), 1)
        H = 104 + rows * 30 + 30
        out = [text(40, 52, "LANGUAGES · SHARE OF CODE", 11, "e"), bars(40, 86, 360, langs, .1),
               f'<line x1="420" y1="40" x2="420" y2="{H - 56}" stroke="{LINE}"/>',
               text(450, 52, "PROJECTS BY CATEGORY", 11, "e"), bars(450, 86, 350, cats, .3, label_w=150),
               text(40, H - 30, note, 11, "m")]
    else:
        x, w = 28, W - 56
        y2 = 86 + len(langs) * 30 + 30
        note_lines = wrap(note, 11, w, 3)
        H = y2 + 34 + len(cats) * 30 + 10 + len(note_lines) * 15 + 24
        out = [text(x, 52, "LANGUAGES · SHARE OF CODE", 11, "e"), bars(x, 86, w, langs, .1),
               f'<line x1="{x}" y1="{y2 - 18}" x2="{x + w}" y2="{y2 - 18}" stroke="{LINE}"/>',
               text(x, y2 + 8, "PROJECTS BY CATEGORY", 11, "e"), bars(x, y2 + 42, w, cats, .3, label_w=150)]
        out += [text(x, H - 26 - (len(note_lines) - 1 - i) * 15, l, 11, "m") for i, l in enumerate(note_lines)]
    label = ("Languages: " + ", ".join(f"{n} {v}" for n, _, v in langs) +
             ". Projects by category: " + ", ".join(f"{n} {v}" for n, _, v in cats) + ".")
    return document(W, H, frame(8, 8, W - 16, H - 16, 20) + "".join(out), label)


# ── Timeline ────────────────────────────────────────────────────────────────

def timeline(events, W=WIDE):
    wide = W >= 700
    x_l, row = (40, 58) if wide else (28, 62)
    if not events:
        return document(W, 100, frame(8, 8, W - 16, 84, 20) + text(x_l, 58, "No recent public activity.", 13, "m"),
                        "No recent activity")
    H = 64 + len(events) * row
    lx = 186 if wide else x_l + 6
    out = [frame(8, 8, W - 16, H - 16, 20), text(x_l, 52, "RECENT ACTIVITY", 11, "e"),
           f'<path d="M{lx} 84 V{84 + (len(events) - 1) * row}" pathLength="1" stroke="{TINT_LINE}" '
           f'stroke-width="2" class="draw" style="animation-delay:.1s"/>']
    for i, e in enumerate(events):
        y = 84 + i * row
        release = e["kind"] == "release"
        dot = (f'<circle cx="{lx}" cy="{y}" r="6" fill="#FFFFFF" stroke="{SKY if release else SOFT}" stroke-width="2"/>'
               + (f'<circle cx="{lx}" cy="{y}" r="2.5" fill="{SKY}"/>' if release else ""))
        out.append(anim(dot, "pop", .2 + .1 * i))
        tx = lx + 24 if wide else lx + 20
        detail = e["detail"] if wide else f"{fmt_date(e['date'])} · {e['detail']}"
        content = ((text(x_l, y + 4, fmt_date(e["date"]), 12, "m n") if wide else "") +
                   text(tx, y + 2, truncate(e["title"], 14, W - tx - x_l, True), 14, weight=640) +
                   text(tx, y + 21, truncate(detail, 12.5, W - tx - x_l), 12.5, "b"))
        out.append(anim(content, delay=.25 + .1 * i))
    label = "Recent activity: " + "; ".join(f"{fmt_date(e['date'])} {e['title']} — {e['detail']}" for e in events)
    return document(W, H, "".join(out), label)


# ── Stat strips (Engineering Statistics, Open Source) ───────────────────────

def strip(eyebrow, metrics, note="", chips_label="", chip_items=(), W=WIDE):
    """Headline numbers (one row on desktop, a 3-column grid on phones), optional chip row and note."""
    wide = W >= 700
    x_l = 40 if wide else 28
    per_row = len(metrics) if wide else 3
    mw = (W - 2 * x_l) / per_row
    two = any(len(wrap(l, 11.5, mw - 24, 2)) > 1 for _, l in metrics)
    row_h = 70 if two else 56
    out = [text(x_l, 52, eyebrow, 11, "e")]
    for i, (value, label) in enumerate(metrics):
        col, r = i % per_row, i // per_row
        x, y = x_l + col * mw, 102 + r * row_h
        if col:
            out.append(f'<line x1="{x - 16}" y1="{y - 26}" x2="{x - 16}" y2="{y + (34 if two else 20)}" stroke="{LINE}"/>')
        lines = "".join(text(x, y + 20 + k * 15, l, 11.5, "m") for k, l in enumerate(wrap(label, 11.5, mw - 24, 2)))
        out.append(anim(text(x, y, value, 30 if wide else 26, "n", weight=650, extra=' letter-spacing="-0.6"') + lines,
                        delay=.1 + .07 * i))
    y = 102 + (math.ceil(len(metrics) / per_row) - 1) * row_h + (63 if two else 48)
    if chip_items:
        out.append(text(x_l, y + 17, chips_label, 12, "b"))
        chips, bottom = _flow_chips([(c, "") for c in chip_items], x_l + text_width(chips_label, 12) + 14, y,
                                    W - x_l, 12, 26, max_rows=2, color=INK)
        out.append(anim("".join(chips), delay=.5))
        y = bottom + 18
    if note:
        for l in wrap(note, 11, W - 2 * x_l, 3):
            out.append(text(x_l, y + 6, l, 11, "m"))
            y += 15
        y += 7
    H = y + 12
    label = f"{eyebrow.title()}: " + ", ".join(f"{l} {v}" for v, l in metrics) + \
            (f". {chips_label} {', '.join(chip_items)}" if chip_items else "")
    return document(W, H, frame(8, 8, W - 16, H - 16, 20) + "".join(out), label)
