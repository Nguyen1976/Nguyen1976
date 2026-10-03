"""Renders svg/contribution-city.svg from data/calendar.json and refreshes its README alt text.

An isometric night skyline with one building per day of the last year: busier days are
taller and brighter. Run fetch.py first; this script only reads the data and draws.

Adapted from https://github.com/georgekobaidze/georgekobaidze (tools/profile/render.py),
shared by its author with "feel free to fork it and build your own skyline".
"""
import base64, datetime, hashlib, html, io, json, math, pathlib, re

from fontTools import subset
from fontTools.ttLib import TTFont

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DATA = HERE / "data"
OUT = ROOT / "svg" / "contribution-city.svg"
README = ROOT / "README.md"
FONT_DIR = HERE / "fonts"
CYAN, GREEN = "#00d9ff", "#3fb950"
W, H, M = 880, 720, 16     # width, height, transparent margin around the frame (room for the glow)
FL, FR = M, W - M          # frame left / right
FT, FB = M, H - M          # frame top / bottom
X = 52                     # text left edge
DY = 20                    # everything inside the frame sits this far below the top edge
e = html.escape


# ─────────────────────────────── frame ────────────────────────────────
def visible(markup):
    """The characters a piece of SVG markup actually displays (so the font subset never misses one)."""
    return html.unescape(re.sub(r"<[^>]+>", "", markup))


def faces(text, weights=(400, 700)):
    """JetBrains Mono, subset to the glyphs in use and embedded, so the SVG looks the same everywhere."""
    text += "0123456789"
    out = []
    for w in weights:
        f = TTFont(FONT_DIR / f"jetbrains-mono-latin-{w}-normal.woff2", recalcTimestamp=False)  # fixed timestamp keeps output byte-identical between runs
        o = subset.Options(); o.flavor = "woff2"; o.layout_features = []
        s = subset.Subsetter(o); s.populate(text=text); s.subset(f)
        b = io.BytesIO(); f.flavor = "woff2"; f.save(b)
        out.append(f"@font-face{{font-family:'JBM';font-weight:{w};src:url(data:font/woff2;base64,"
                   f"{base64.b64encode(b.getvalue()).decode()}) format('woff2')}}")
    return "".join(out)


BASE_CSS = f"""text{{font-family:'JBM',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:15px}}
.dim{{fill:#8b949e}}.cy{{fill:{CYAN}}}.fg{{fill:#c9d1d9}}.gr{{fill:{GREEN}}}.wh{{fill:#f0fbff}}
@keyframes fadein{{from{{opacity:0;transform:translateX(-6px)}}to{{opacity:1;transform:none}}}}
.ln{{animation:fadein .35s ease-out both}}"""

DEFS = f"""<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="{CYAN}" stroke-opacity=".06"/></pattern>
<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6"/></filter>
<filter id="g" x="-20%" y="-60%" width="140%" height="220%"><feGaussianBlur stdDeviation="4"/></filter>"""


def frame_svg(body, *, title, desc, css="", defs=""):
    edge = f"M{FL} {FT}H{FR}V{FB}H{FL}Z"
    corners = (f'<path d="M{FL-7} {FT+18}V{FT-7}H{FL+18}"/><path d="M{FR-18} {FT-7}H{FR+7}V{FT+18}"/>'
               f'<path d="M{FL-7} {FB-18}V{FB+7}H{FL+18}"/><path d="M{FR-18} {FB+7}H{FR+7}V{FB-18}"/>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="t d">
<title id="t">{e(title)}</title>
<desc id="d">{e(desc)}</desc>
<style>
{faces(visible(body))}
{BASE_CSS}
{css}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
</style>
<defs>
{DEFS}
{defs}
</defs>
<path d="{edge}" fill="none" stroke="{CYAN}" stroke-width="3" opacity=".55" filter="url(#glow)"/>
<rect x="{FL}" y="{FT}" width="{FR-FL}" height="{FB-FT}" fill="#03040a"/>
<rect x="{FL}" y="{FT}" width="{FR-FL}" height="{FB-FT}" fill="url(#grid)"/>
<g transform="translate(0 {DY})">
{body}
</g>
<path d="{edge}" fill="none" stroke="{CYAN}" stroke-width="1.2"/>
<g fill="none" stroke="{CYAN}" stroke-width="2">{corners}</g>
</svg>
'''


def heading(y, name, counter):
    return f'''<text x="{X}" y="{y}" font-weight="700" fill="{CYAN}" filter="url(#g)" opacity=".8" style="font-size:20px">~/</text>
<text x="{X}" y="{y}" font-weight="700" style="font-size:20px"><tspan class="cy">~/</tspan><tspan class="wh">{e(name)}</tspan></text>
<text x="{FR-36}" y="{y}" text-anchor="end" letter-spacing="2" fill="#6e7681" style="font-size:12px">{e(counter)}</text>
<line x1="{X}" y1="{y+14}" x2="{FR-36}" y2="{y+14}" stroke="{CYAN}" stroke-opacity=".4"/>
<line x1="{X}" y1="{y+14}" x2="{X+120}" y2="{y+14}" stroke="{CYAN}" stroke-width="2"/>
<line x1="{X}" y1="{y+14}" x2="{X+120}" y2="{y+14}" stroke="{CYAN}" stroke-width="3" filter="url(#g)"/>'''


# ─────────────────────────── contribution city ────────────────────────
CITY_TW, CITY_TH = 25, 12.5                  # iso tile width / height
CITY_OX, CITY_OY = 152.5, 262                # grid origin
CITY_HMAX = 118                              # tallest building, px
ROOFS = ["#0c2d6b", "#1554c0", "#2f81f7", "#1fd5ff"]   # navy → electric blue
WIN_ON, WIN_ON_SIDE, WIN_OFF = "#7df9ff", "#4cc9f0", "#111827"


def _p(x, y):
    return f"{x:.1f},{y:.1f}"


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


def summary(days):
    total = sum(n for _, n in days)
    busiest_d, busiest_n = max(days, key=lambda t: t[1]) if days else (None, 0)
    return total, busiest_d, busiest_n, sum(1 for _, n in days if n)


def build_city(calendar, updated):
    days = [(datetime.date.fromisoformat(d), n) for d, n in calendar]
    counts = [n for _, n in days]
    total, busiest_d, busiest_n, active = summary(days)
    peak = max(counts) if counts else 0
    lv = _levels(counts)
    rnd = _rng(f"{updated}-{total}")
    start = days[0][0]

    cells = []
    for d, n in days:
        idx = (d - start).days
        cells.append((idx // 7, (d.weekday() + 1) % 7, n))      # week column, Sunday = 0
    cells.sort(key=lambda c: (c[0] + c[1], c[0]))                 # back to front

    shapes, flick = [], 0
    for w, dow, n in cells:
        cx = CITY_OX + (w - dow) * CITY_TW / 2
        cy = CITY_OY + (w + dow) * CITY_TH / 2
        L, R = (cx - CITY_TW / 2, cy), (cx + CITY_TW / 2, cy)
        T, B = (cx, cy - CITY_TH / 2), (cx, cy + CITY_TH / 2)
        if n == 0:
            shapes.append(f'<path d="M{_p(*T)}L{_p(*R)}L{_p(*B)}L{_p(*L)}Z" fill="#161b22" stroke="#0d1117" stroke-width=".6"/>')
            continue
        h = 8 + (CITY_HMAX - 8) * math.sqrt(n / peak)
        level = sum(n > t for t in lv)
        Tu, Ru, Bu, Lu = [(x, y - h) for x, y in (T, R, B, L)]
        shapes.append(f'<path d="M{_p(*L)}L{_p(*B)}L{_p(*Bu)}L{_p(*Lu)}Z" fill="#1a2440"/>'
                      f'<path d="M{_p(*B)}L{_p(*R)}L{_p(*Ru)}L{_p(*Bu)}Z" fill="#111831"/>'
                      f'<path d="M{_p(*Tu)}L{_p(*Ru)}L{_p(*Bu)}L{_p(*Lu)}Z" fill="{ROOFS[level]}"/>')
        on, side, off, fl = [], [], [], []
        for face, (a, b) in (("l", (L, B)), ("r", (B, R))):
            for r in range(int((h - 6) // 7)):
                v0 = 5 + r * 7
                for u0 in (.18, .58):
                    lit = next(rnd) < .55
                    if not lit and next(rnd) < .5:
                        continue
                    pts = [(a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u - v)
                           for u, v in ((u0, v0), (u0 + .26, v0), (u0 + .26, v0 + 3.2), (u0, v0 + 3.2))]
                    seg = "M" + "L".join(_p(*q) for q in pts) + "Z"
                    if not lit:
                        off.append(seg)
                    elif next(rnd) < .03:
                        fl.append((seg, face))
                    else:
                        (on if face == "l" else side).append(seg)
        if off:
            shapes.append(f'<path d="{"".join(off)}" fill="{WIN_OFF}"/>')
        if on:
            shapes.append(f'<path d="{"".join(on)}" fill="{WIN_ON}"/>')
        if side:
            shapes.append(f'<path d="{"".join(side)}" fill="{WIN_ON_SIDE}"/>')
        for seg, face in fl:
            flick += 1
            shapes.append(f'<path class="f{flick % 3}" d="{seg}" fill="{WIN_ON if face == "l" else WIN_ON_SIDE}"/>')

    # night sky in the empty top-right corner: stars, moon, a plane crossing
    stars = []
    for i in range(46):
        x, y = 470 + next(rnd) * 350, 118 + next(rnd) * 150
        if x > 700 and y < 215:           # keep the moon clear
            continue
        cls = f' class="s{i % 3}"' if i % 3 == 0 else ""
        stars.append(f'<circle{cls} cx="{x:.1f}" cy="{y:.1f}" r="{(.6, .8, 1.1)[i % 3]}" fill="#c9d1d9" opacity="{.35 + next(rnd) * .5:.2f}"/>')
    info = [f'<tspan class="cy" font-weight="700">{total:,}</tspan> contributions · last 365 days',
            f'busiest day <tspan class="fg">{busiest_d:%b} {busiest_d.day}</tspan> · {busiest_n}' if busiest_n else "",
            f'{active} active days']
    info_svg = "".join(f'<text x="{FR-36}" y="{300 + i*20}" text-anchor="end" class="dim" style="font-size:12px">{t}</text>'
                       for i, t in enumerate(info) if t)
    legend = "".join(f'<rect x="{X + 52 + i*16}" y="{642}" width="11" height="11" fill="{c}"/>'
                     for i, c in enumerate(["#161b22"] + ROOFS))
    body = heading(44, "contribution-city", f"// {updated}") + f'''
<g class="ln" style="animation-delay:.15s"><text x="{X}" y="96" class="dim"><tspan class="gr">$</tspan> render-city --last 365d <tspan fill="#484f58"># one building per day</tspan></text></g>
<g>{"".join(stars)}</g>
<circle cx="{FR-80}" cy="{160}" r="40" fill="url(#moonglow)"/>
<circle cx="{FR-80}" cy="{160}" r="14" fill="#e6edf3"/>
<circle cx="{FR-74}" cy="{155}" r="12.5" fill="#03040a"/>
<g class="plane"><g transform="translate(0 132)"><rect x="0" y="0" width="14" height="2" rx="1" fill="#484f58"/><circle class="bl" cx="0" cy="1" r="1.6" fill="#ff7b72"/><circle class="bl" cx="14" cy="1" r="1.6" fill="#f0f6fc" style="animation-delay:.7s"/></g></g>
{info_svg}
{"".join(shapes)}
<text x="{X}" y="{652}" class="dim" style="font-size:11px">quiet</text>{legend}<text x="{X + 52 + 5*16 + 6}" y="{652}" class="dim" style="font-size:11px">skyscraper</text>'''
    css = f"""@keyframes tw{{0%,100%{{opacity:.9}}50%{{opacity:.15}}}}
@keyframes fl{{0%,40%,100%{{opacity:1}}45%,60%{{opacity:.1}}}}
@keyframes blink{{0%,90%,100%{{opacity:0}}93%{{opacity:1}}}}
@keyframes fly{{from{{transform:translate({FL - 40}px,0)}}to{{transform:translate({FR + 40}px,-30px)}}}}
.s0{{animation:tw 3s infinite}}
.f0{{animation:fl 5s infinite}}.f1{{animation:fl 7s infinite 2s}}.f2{{animation:fl 9s infinite 4s}}
.plane{{animation:fly 26s linear infinite}}.bl{{animation:blink 1.4s infinite}}"""
    defs = '<radialGradient id="moonglow"><stop offset="0" stop-color="#f0f6fc" stop-opacity=".22"/><stop offset="1" stop-color="#f0f6fc" stop-opacity="0"/></radialGradient>'
    return frame_svg(body, title="Contribution city", desc=city_alt(days), css=css, defs=defs)


def city_alt(days):
    total, busiest_d, busiest_n, _ = summary(days)
    text = (f"Contribution city: an isometric night skyline with one building per day of the last year, "
            f"taller and brighter for busier days. {total:,} contributions")
    if busiest_n:
        text += f", busiest day {busiest_d:%B} {busiest_d.day} with {busiest_n}"
    return text + "."


def main():
    cal = json.loads((DATA / "calendar.json").read_text())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build_city(cal["days"], cal["updated"]))
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
