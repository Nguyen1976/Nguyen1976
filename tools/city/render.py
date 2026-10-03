"""Renders svg/contribution-city.svg from data/calendar.json and refreshes its README alt text.

A 3D city on a floating slab, one building per day of the last year: busier days are
taller and brighter. Styled as a sibling of the github-readme-stats "tokyonight" cards
next to it on the profile. Run fetch.py first; this script only reads the data and draws.

The idea and the window/RNG approach come from https://github.com/georgekobaidze/georgekobaidze
(tools/profile/render.py), shared by its author with "feel free to fork it and build your own skyline".
"""
import datetime, hashlib, html, json, math, pathlib, re

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = HERE / "data"
OUT = ROOT / "svg" / "contribution-city.svg"
README = ROOT / "README.md"
e = html.escape

# tokyonight, exactly as github-readme-stats draws it
BG, BORDER, TITLE, TEXT, ICON = "#1a1b27", "#e4e2e2", "#70a5fd", "#38bdae", "#bf91f3"
FONT = "'Segoe UI', Ubuntu, \"Helvetica Neue\", Sans-Serif"
ROOFS = ["#34497f", "#4a6fd1", TITLE, ICON]          # activity level 1–4: navy → blue → purple
SLAB_TOP, SLAB_LEFT, SLAB_FRONT = "#24283b", "#1f2335", "#16161e"
LOT, WINDOW = "#2b3049", "#c0caf5"

# geometry: a 3/4 view where weeks run right and slightly up, weekdays run toward the viewer
W = 960                                    # card width; shown at ~744px so text matches the stats cards
U = (14.6, -4.1)                           # one week along the ground
V = (9.4, 6.4)                             # one weekday along the ground
INSET = .16                                # gap between buildings (the streets), in cells
HMAX = 128                                 # tallest building, px
SLAB_PAD, SLAB_T = .7, 20                  # slab margin (cells) and thickness (px)
SHADOW = (.034, .012)                      # shadow length per px of height, in (week, day) cells

ICONS = {   # octicons, 16px
    "commit": "M11.93 8.5a4.002 4.002 0 0 1-7.86 0H.75a.75.75 0 0 1 0-1.5h3.32a4.002 4.002 0 0 1 7.86 0h3.32a.75.75 0 0 1 0 1.5Zm-1.43-.75a2.5 2.5 0 1 0-5 0 2.5 2.5 0 0 0 5 0Z",
    "flame": "M9.533.753V.752c.217 2.385 1.463 3.626 2.653 4.81C13.37 6.74 14.498 7.863 14.498 10c0 3.5-3 6-6.5 6S1.5 13.512 1.5 10c0-1.298.536-2.56 1.425-3.286.376-.308.862 0 1.035.454C4.46 8.487 5.581 8.419 6 8c.282-.282.341-.811-.003-1.5C4.34 3.187 7.035.75 8.77.146c.39-.137.726.194.763.607ZM7.998 14.5c2.832 0 5-1.98 5-4.5 0-1.463-.68-2.19-1.879-3.383l-.036-.037c-1.013-1.008-2.3-2.29-2.834-4.434-.322.256-.63.579-.864.953-.432.696-.621 1.58-.046 2.73.473.947.67 2.284-.278 3.232-.61.61-1.545.84-2.403.633a2.79 2.79 0 0 1-1.436-.874A3.198 3.198 0 0 0 3 10c0 2.53 2.164 4.5 4.998 4.5Z",
    "calendar": "M4.75 0a.75.75 0 0 1 .75.75V2h5V.75a.75.75 0 0 1 1.5 0V2h1.25c.966 0 1.75.784 1.75 1.75v10.5A1.75 1.75 0 0 1 13.25 16H2.75A1.75 1.75 0 0 1 1 14.25V3.75C1 2.784 1.784 2 2.75 2H4V.75A.75.75 0 0 1 4.75 0ZM2.5 7.5v6.75c0 .138.112.25.25.25h10.5a.25.25 0 0 0 .25-.25V7.5Zm10.75-4H2.75a.25.25 0 0 0-.25.25V6h11V3.75a.25.25 0 0 0-.25-.25Z",
}


# ─────────────────────────────── helpers ──────────────────────────────
def mix(c1, c2, t):
    """Blend two #rrggbb colours: t=0 gives c1, t=1 gives c2."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _rng(seed):
    """Tiny deterministic PRNG, so the same data always draws the same windows."""
    state = int(hashlib.sha256(seed.encode()).hexdigest()[:16], 16)
    while True:
        state = (state * 6364136223846793005 + 1442695040888963407) % 2**64
        yield (state >> 11) / 2**53


def _levels(counts):
    """GitHub-style quartile thresholds over the non-zero days."""
    nz = sorted(c for c in counts if c > 0)
    if not nz:
        return [1, 1, 1]
    q = lambda f: nz[min(len(nz) - 1, int(len(nz) * f))]
    return [q(.25), q(.5), q(.75)]


def path(*pts):
    return "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z"


def up(p, h):
    return p[0], p[1] - h


def hull(pts):
    """Convex hull (monotone chain), for building shadows."""
    pts = sorted(set(pts))
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return lo[:-1] + hi[:-1]


def summary(days):
    total = sum(n for _, n in days)
    busiest_d, busiest_n = max(days, key=lambda t: t[1]) if days else (None, 0)
    return total, busiest_d, busiest_n, sum(1 for _, n in days if n)


# ──────────────────────────────── city ────────────────────────────────
def build_city(name, calendar, updated):
    days = [(datetime.date.fromisoformat(d), n) for d, n in calendar]
    counts = [n for _, n in days]
    total, busiest_d, busiest_n, active = summary(days)
    peak = max(counts) if counts else 0
    lv = _levels(counts)
    rnd = _rng(f"{updated}-{total}")
    start = days[0][0]
    weeks = (days[-1][0] - start).days // 7 + 1

    # place the slab: centred, with room above its back edge for the tallest building
    left = -SLAB_PAD * (U[0] + V[0])
    right = (weeks + SLAB_PAD) * U[0] + (7 + SLAB_PAD) * V[0]
    ox = (W - (right - left)) / 2 - left + 12
    oy = 34 + HMAX + (weeks + SLAB_PAD) * -U[1] + SLAB_PAD * V[1]
    P = lambda a, b: (ox + a * U[0] + b * V[0], oy + a * U[1] + b * V[1])
    bottom = P(-SLAB_PAD, 7 + SLAB_PAD)[1] + SLAB_T
    H = int(math.ceil(bottom + 34))

    # the slab: top, lit left side, darker front side, and a soft shadow beneath
    s0, s1 = -SLAB_PAD, weeks + SLAB_PAD
    t0, t1 = -SLAB_PAD, 7 + SLAB_PAD
    top = [P(s0, t0), P(s1, t0), P(s1, t1), P(s0, t1)]
    down = lambda p: (p[0], p[1] + SLAB_T)
    outline = [top[0], top[1], top[2], down(top[2]), down(top[3]), down(top[0])]
    slab = (f'<path d="{path(*((x, y + 16) for x, y in outline))}" fill="#000" opacity=".5" filter="url(#soft)"/>'
            f'<path d="{path(top[0], top[3], down(top[3]), down(top[0]))}" fill="{SLAB_LEFT}"/>'
            f'<path d="{path(top[3], top[2], down(top[2]), down(top[3]))}" fill="{SLAB_FRONT}"/>'
            f'<path d="{path(*top)}" fill="{SLAB_TOP}"/>'
            f'<path d="M{top[0][0]:.1f},{top[0][1]:.1f}L{top[3][0]:.1f},{top[3][1]:.1f}L{top[2][0]:.1f},{top[2][1]:.1f}" '
            f'fill="none" stroke="#3b4261" stroke-width="1"/>')

    # month names painted on the slab's front side
    un = math.hypot(*U)
    months, seen = [], set()
    for d, _ in days:
        if d.day <= 7 and (d.year, d.month) not in seen and (d - start).days // 7 < weeks - 1:
            seen.add((d.year, d.month))
            x, y = P((d - start).days // 7 + .5, t1)
            months.append(f'<text transform="matrix({U[0]/un:.4f} {U[1]/un:.4f} 0 1 {x:.1f} {y + SLAB_T * .72:.1f})" '
                          f'class="mo">{d:%b}</text>')

    cells = []
    for d, n in days:
        idx = (d - start).days
        cells.append((idx // 7, (d.weekday() + 1) % 7, n, d))      # week, weekday (Sunday = 0)
    cells.sort(key=lambda c: (P(c[0], c[1])[1], c[0]))                 # back to front

    lots, shadows, blocks = [], [], []
    beacon = ""
    for w, dow, n, d in cells:
        a0, a1, b0, b1 = w + INSET, w + 1 - INSET, dow + INSET, dow + 1 - INSET
        A, Bk, C, D = P(a0, b0), P(a1, b0), P(a1, b1), P(a0, b1)   # back-left, back-right, front-right, front-left
        if n == 0:
            lots.append(path(A, Bk, C, D))
            continue
        h = 6 + (HMAX - 6) * math.sqrt(n / peak)
        level = sum(n > t for t in lv)
        roof = ROOFS[level]
        sa, sb = SHADOW[0] * h, SHADOW[1] * h
        shadows.append(path(*hull([A, Bk, C, D] + [P(a + sa, b + sb) for a, b in ((a0, b0), (a1, b0), (a1, b1), (a0, b1))])))

        parts = [f'<path d="{path(A, D, up(D, h), up(A, h))}" fill="url(#l{level})"/>',      # lit left face
                 f'<path d="{path(D, C, up(C, h), up(D, h))}" fill="url(#f{level})"/>',      # front face
                 f'<path d="{path(*(up(p, h) for p in (A, Bk, C, D)))}" fill="{roof}"/>',
                 f'<path d="M{up(A, h)[0]:.1f},{up(A, h)[1]:.1f}L{up(D, h)[0]:.1f},{up(D, h)[1]:.1f}L{up(C, h)[0]:.1f},{up(C, h)[1]:.1f}" '
                 f'fill="none" stroke="{mix(roof, "#ffffff", .35)}" stroke-width=".8" opacity=".8"/>']
        # windows: a grid on both visible faces, more of them lit on busier days
        lit_p = .25 + .15 * level
        wins = []
        for (p0, p1), cols in (((A, D), (.3,)), ((D, C), (.2, .58))):
            for r in range(int((h - 7) // 7)):
                v0 = 5 + r * 7
                for u0 in cols:
                    if next(rnd) > lit_p:
                        continue
                    du = .22 if len(cols) == 2 else .4
                    q = [(p0[0] + (p1[0] - p0[0]) * u, p0[1] + (p1[1] - p0[1]) * u - v)
                         for u, v in ((u0, v0 + 3), (u0 + du, v0 + 3), (u0 + du, v0), (u0, v0))]
                    wins.append(path(*q))
        if wins:
            parts.append(f'<path d="{"".join(wins)}" fill="{WINDOW}" opacity="{.45 + .12 * level:.2f}"/>')
        blocks.append(f'<g class="b" style="animation-delay:{.25 + w * .022:.3f}s">{"".join(parts)}</g>')

        if (d, n) == (busiest_d, busiest_n) and not beacon:
            tip = up(((A[0] + C[0]) / 2, (A[1] + C[1]) / 2), h)
            beacon = (f'<g class="b" style="animation-delay:{.25 + w * .022:.3f}s">'
                      f'<line x1="{tip[0]:.1f}" y1="{tip[1]:.1f}" x2="{tip[0]:.1f}" y2="{tip[1] - 14:.1f}" stroke="{mix(ICON, BG, .3)}" stroke-width="1.2"/>'
                      f'<circle class="beacon" cx="{tip[0]:.1f}" cy="{tip[1] - 15:.1f}" r="6" fill="{ICON}" opacity=".5" filter="url(#glow)"/>'
                      f'<circle class="beacon" cx="{tip[0]:.1f}" cy="{tip[1] - 15:.1f}" r="2.2" fill="#f5e9ff"/></g>')

    # stats, set like the stats card rows: purple icon, teal label, bold value
    rows = [("commit", "Contributions (last year):", f"{total:,}"),
            ("flame", "Busiest day:", f"{busiest_d:%b} {busiest_d.day} · {busiest_n}" if busiest_n else "—"),
            ("calendar", "Active days:", f"{active}")]
    sx, sy = W - 330, H - 34 - 25 * len(rows) + 6
    stats = "".join(
        f'<g class="fade" style="animation-delay:{.45 + i * .15:.2f}s" transform="translate({sx} {sy + i * 25})">'
        f'<svg x="0" y="0" width="16" height="16" viewBox="0 0 16 16"><path fill="{ICON}" fill-rule="evenodd" d="{ICONS[icon]}"/></svg>'
        f'<text class="stat" x="25" y="12.5">{e(label)}</text><text class="stat bold" x="215" y="12.5">{e(value)}</text></g>'
        for i, (icon, label, value) in enumerate(rows))

    grads = "".join(
        f'<linearGradient id="l{i}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{mix(r, BG, .25)}"/><stop offset="1" stop-color="{mix(r, BG, .72)}"/></linearGradient>'
        f'<linearGradient id="f{i}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{mix(r, BG, .55)}"/><stop offset="1" stop-color="{mix(r, BG, .85)}"/></linearGradient>'
        for i, r in enumerate(ROOFS))
    desc = city_alt(days)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d">
<title id="t">{e(name)}'s Contribution City</title>
<desc id="d">{e(desc)}</desc>
<style>
.header{{font:600 18px {FONT};fill:{TITLE}}}
.sub{{font:400 13px {FONT};fill:{TEXT};opacity:.75}}
.stat{{font:600 14px {FONT};fill:{TEXT}}}.bold{{font-weight:700}}
.mo{{font:600 10px {FONT};fill:{TEXT};opacity:.55}}
@keyframes fadeIn{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes rise{{from{{transform:scaleY(0)}}to{{transform:scaleY(1)}}}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.25}}}}
.fade{{animation:fadeIn .6s ease-in-out both}}
.b{{transform-box:fill-box;transform-origin:50% 100%;animation:rise .7s cubic-bezier(.2,.8,.2,1) both}}
.beacon{{animation:pulse 1.8s ease-in-out infinite}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
</style>
<defs>
<filter id="soft" x="-10%" y="-50%" width="120%" height="200%"><feGaussianBlur stdDeviation="9"/></filter>
<filter id="glow" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="3"/></filter>
<clipPath id="ground"><path d="{path(*top)}"/></clipPath>
{grads}
</defs>
<rect x="0.5" y="0.5" rx="4.5" width="{W - 1}" height="{H - 1}" fill="{BG}" stroke="{BORDER}"/>
<g class="fade"><text class="header" x="25" y="35">{e(name)}'s Contribution City</text>
<text class="sub" x="25" y="57">one building per day · taller and brighter on busier days</text></g>
{slab}
{"".join(months)}
<path d="{"".join(lots)}" fill="{LOT}"/>
<g class="fade" style="animation-delay:1.2s"><path d="{"".join(shadows)}" fill="#0b0c14" opacity=".55" clip-path="url(#ground)"/></g>
{"".join(blocks)}
{beacon}
{stats}
</svg>
'''


def city_alt(days):
    total, busiest_d, busiest_n, active = summary(days)
    text = (f"Contribution city: a 3D skyline with one building per day of the last year, "
            f"taller and brighter for busier days. {total:,} contributions over {active} active days")
    if busiest_n:
        text += f", busiest day {busiest_d:%B} {busiest_d.day} with {busiest_n}"
    return text + "."


def main():
    cal = json.loads((DATA / "calendar.json").read_text())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build_city(cal.get("name") or "Nguyen1976", cal["days"], cal["updated"]))
    print(f"wrote {OUT.relative_to(ROOT)}")

    # keep the README alt text in step with today's numbers, for screen readers
    alt = e(city_alt([(datetime.date.fromisoformat(d), n) for d, n in cal["days"]]), quote=True)
    s = README.read_text()
    s, n = re.subn(r'(<img src="\./svg/contribution-city\.svg"[^>]*?alt=")[^"]*(")',
                   lambda m: m.group(1) + alt + m.group(2), s)
    if n:
        README.write_text(s)
        print("README alt text updated")


if __name__ == "__main__":
    main()
