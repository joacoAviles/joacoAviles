#!/usr/bin/env python3
"""
JOACO / DEVELOPER HUB — generador del README de perfil.

Lee config.json + datos reales de la API de GitHub y escribe:
  assets/generated/*.svg   (cabecera, mapa, stats, stack + contribuciones, tarjetas, footer)
  README.md

Uso:
  python scripts/build.py              # datos reales (usa GITHUB_TOKEN / GH_TOKEN si existe)
  python scripts/build.py --demo       # datos de ejemplo, solo para previsualizar

Dependencias: solo librería estándar. Opcional: `pip install fonttools brotli`
para recortar las fuentes embebidas (SVGs ~4x más livianos) y medir texto exacto.
"""
import argparse, base64, datetime as dt, html, io, json, math, os, random, re, sys
import urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, "assets", "generated")
FONT_DIR = os.path.join(ROOT, "assets", "fonts")
DATA = os.path.join(ROOT, "scripts", "data")

# ─── paleta ────────────────────────────────────────────────────────────────
Y = "#F4C430"        # amarillo JOACO
BG = "#0A0A0A"
PANEL = "#0F0F0F"
LINE = "#242424"
TXT = "#EDEDED"
MUTED = "#8F8F8F"
DIM = "#5C5C5C"
LEVELS = ["#181818", "#3B3011", "#715812", "#B48B18", Y]

FONTS = {  # clave → (archivo, familia css)
    "d": ("archivo-black.woff2", "JDisplay"),
    "k": ("permanent-marker.woff2", "JMarker"),
    "m": ("jetbrains-mono.woff2", "JMono"),
    "mb": ("jetbrains-mono-bold.woff2", "JMonoB"),
    "s": ("inter.woff2", "JSans"),
    "sb": ("inter-bold.woff2", "JSansB"),
}

LANG_COLORS = {
    "Python": "#3572A5", "TypeScript": "#3178C6", "JavaScript": "#F1E05A", "Shell": "#89E051",
    "Go": "#00ADD8", "HTML": "#E34C26", "CSS": "#663399", "Rust": "#DEA584", "Dockerfile": "#384D54",
    "Vue": "#41B883", "PHP": "#4F5D95", "Java": "#B07219", "C++": "#F34B7D", "C": "#555555",
    "Jupyter Notebook": "#DA5B0B", "Kotlin": "#A97BFF", "Swift": "#F05138", "Ruby": "#701516",
    "PLpgSQL": "#336790", "HCL": "#844FBA", "C#": "#178600", "Dart": "#00B4AB", "Lua": "#000080",
}


# ─── utilidades ────────────────────────────────────────────────────────────
def esc(s):
    return html.escape(str(s), quote=True)


def load_json(name):
    with open(os.path.join(DATA, name)) as f:
        return json.load(f)


TOPO = load_json("topo.json")
ICONS = load_json("icons.json")

_fonts = {}


def _ttfont(key):
    if key not in _fonts:
        from fontTools.ttLib import TTFont
        _fonts[key] = TTFont(os.path.join(FONT_DIR, FONTS[key][0]))
    return _fonts[key]


def text_w(s, key, size, ls=0.0):
    """Ancho aproximado de un texto en px."""
    try:
        f = _ttfont(key)
        cmap, hmtx, upm = f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm
        w = sum(hmtx[cmap.get(ord(c), cmap.get(32))][0] for c in s)
        return w / upm * size + ls * len(s)
    except Exception:
        k = {"d": 0.78, "k": 0.62, "m": 0.6, "mb": 0.6, "s": 0.55, "sb": 0.58}[key]
        return len(s) * size * k + ls * len(s)


def wrap(s, key, size, width, max_lines=2):
    words, lines, cur = s.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if text_w(t, key, size) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while text_w(lines[-1] + "…", key, size) > width and " " in lines[-1]:
            lines[-1] = lines[-1].rsplit(" ", 1)[0]
        lines[-1] += "…"
    return lines


def font_css(keys, body):
    chars = set()
    for m in re.finditer(r">([^<>]+)<", body):
        chars |= set(html.unescape(m.group(1)))
    text = "".join(sorted(chars)) + " 0123456789.,·→↗"
    out = []
    for k in keys:
        fname, fam = FONTS[k]
        raw = open(os.path.join(FONT_DIR, fname), "rb").read()
        try:
            from fontTools import subset
            from fontTools.ttLib import TTFont
            f = TTFont(io.BytesIO(raw))
            opts = subset.Options()
            opts.flavor = "woff2"
            opts.layout_features = ["kern", "liga"]
            sub = subset.Subsetter(opts)
            sub.populate(text=text)
            sub.subset(f)
            buf = io.BytesIO()
            f.flavor = "woff2"
            f.save(buf)
            raw = buf.getvalue()
        except Exception:
            pass
        b64 = base64.b64encode(raw).decode()
        out.append(f"@font-face{{font-family:{fam};src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
        out.append(f".{k}{{font-family:{fam},ui-monospace,monospace}}")
    return "".join(out)


BASE_CSS = (
        "@keyframes fade{from{opacity:0}to{opacity:1}}"
    "@keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}"
    "@keyframes drift{from{transform:translate(0,0)}to{transform:translate(-22px,-10px)}}"
    "@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}"
    "@keyframes pulse{0%{opacity:.9;transform:scale(.6)}100%{opacity:0;transform:scale(2.6)}}"
    ".fade{animation:fade .9s ease both}.rise{animation:rise .8s cubic-bezier(.2,.7,.2,1) both}"
    ".drift{animation:drift 30s ease-in-out infinite alternate}"
    ".blink{animation:blink 1.1s steps(1) infinite}"
    ".pulse{transform-box:fill-box;transform-origin:center;animation:pulse 2.4s ease-out infinite}"
    "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
)


def svg(w, h, body, fonts, css="", title="", defs=""):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">'
        f"<title>{esc(title)}</title>"
        f"<style>{font_css(fonts, body)}{BASE_CSS}{css}</style>"
        f"<defs>{GRAY_FILTER}{defs}</defs>{body}</svg>"
    )


GRAY_FILTER = (
    '<filter id="gray" color-interpolation-filters="sRGB">'
    '<feColorMatrix type="saturate" values="0"/>'
    '<feComponentTransfer><feFuncR type="linear" slope="1.25" intercept="-.12"/>'
    '<feFuncG type="linear" slope="1.25" intercept="-.12"/><feFuncB type="linear" slope="1.25" intercept="-.12"/>'
    "</feComponentTransfer></filter>"
)


def T(x, y, s, cls="s", size=12, fill=None, ls=0, anchor="start", extra=""):
    f = f' fill="{fill or TXT}"' 
    l = f' letter-spacing="{ls}"' if ls else ""
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" font-size="{size}"{f}{l}{a} {extra}>{esc(s)}</text>'


def topo(key, op=0.08, major_op=0.16, scale=1.0, w=None, h=None):
    t = TOPO[key]
    minor = "".join(p["d"] for p in t["paths"] if not p["major"])
    major = "".join(p["d"] for p in t["paths"] if p["major"])
    sx = (w or t["w"]) / t["w"] * scale
    sy = (h or t["h"]) / t["h"] * scale
    ox = (w or t["w"]) * (1 - scale) / 2
    oy = (h or t["h"]) * (1 - scale) / 2
    return (
        f'<g transform="translate({ox:.1f},{oy:.1f}) scale({sx:.3f},{sy:.3f})"><g class="drift" fill="none" stroke="#fff" stroke-linejoin="round">'
        f'<path d="{minor}" stroke-opacity="{op}" stroke-width=".8" vector-effect="non-scaling-stroke"/>'
        f'<path d="{major}" stroke-opacity="{major_op}" stroke-width="1.1" vector-effect="non-scaling-stroke"/></g></g>'
    )


def photo_uri(rel):
    if not rel:
        return None
    p = os.path.join(ROOT, rel)
    if not os.path.isfile(p):
        return None
    ext = os.path.splitext(p)[1].lower().lstrip(".")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "jpeg")
    return f"data:image/{mime};base64," + base64.b64encode(open(p, "rb").read()).decode()


def photo(uri, x, y, w, h, mid, fade="left", op=0.6):
    """Foto en blanco y negro con degradado hacia el fondo."""
    if fade == "left":
        grad = f'<linearGradient id="g{mid}" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".45" stop-color="#fff" stop-opacity="1"/></linearGradient>'
    elif fade == "bottom":
        grad = f'<linearGradient id="g{mid}" x1="0" x2="0" y1="0" y2="1"><stop offset=".55" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity=".35"/></linearGradient>'
    else:
        grad = f'<linearGradient id="g{mid}"><stop offset="0" stop-color="#fff"/></linearGradient>'
    defs = grad + f'<mask id="m{mid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" fill="url(#g{mid})"/></mask>'
    body = (
        f'<image href="{uri}" x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice" '
        f'filter="url(#gray)" mask="url(#m{mid})" opacity="{op}"/>'
    )
    return defs, body


def kfmt(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1000:
        return f"{n/1000:.1f}k".replace(".0k", "k")
    return str(n)


def smooth(pts):
    d = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f"C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}"
    return d


def dot_title(x, y, label, blink=False):
    cls = ' class="blink"' if blink else ""
    return f'<circle cx="{x}" cy="{y-4}" r="4" fill="{Y}"{cls}/>' + T(x + 14, y, label, "mb", 11.5, TXT, 3.6)


# ─── datos ─────────────────────────────────────────────────────────────────
def http(url, token=None, data=None, accept="application/vnd.github+json"):
    h = {"User-Agent": "joaco-profile-builder", "Accept": accept}
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8")
    return json.loads(body) if accept.endswith("json") else body


def fetch(cfg, token):
    u = cfg["username"]
    user = http(f"https://api.github.com/users/{u}", token)
    repos, page = [], 1
    while True:
        batch = http(f"https://api.github.com/users/{u}/repos?per_page=100&type=owner&page={page}", token)
        repos += batch
        if len(batch) < 100:
            break
        page += 1
    own = [r for r in repos if not r.get("fork")]

    lang_size = {}
    for r in own:
        if r.get("language"):
            lang_size[r["language"]] = lang_size.get(r["language"], 0) + max(r.get("size", 0), 1)
    top_langs = [k for k, _ in sorted(lang_size.items(), key=lambda kv: -kv[1])[:3]]

    projects = {}
    for p in cfg["projects"]:
        if p.get("repo"):
            try:
                projects[p["repo"]] = http(f"https://api.github.com/repos/{p['repo']}", token)
            except urllib.error.HTTPError:
                projects[p["repo"]] = None

    return {
        "public_repos": user.get("public_repos", len(repos)),
        "followers": user.get("followers", 0),
        "following": user.get("following", 0),
        "created_at": user["created_at"],
        "stars": sum(r.get("stargazers_count", 0) for r in own),
        "repo_dates": sorted(r["created_at"] for r in own),
        "repo_stars": [(r["created_at"], r.get("stargazers_count", 0)) for r in own],
        "top_langs": top_langs,
        "calendar": fetch_calendar(u, token),
        "projects": projects,
        "demo": False,
    }


def fetch_calendar(u, token):
    """Contribuciones del último año. GraphQL con token; si no, la página pública."""
    if token:
        try:
            q = ("query($l:String!){user(login:$l){contributionsCollection{contributionCalendar{"
                 "totalContributions weeks{contributionDays{date contributionCount contributionLevel}}}}}}")
            res = http("https://api.github.com/graphql", token,
                       data=json.dumps({"query": q, "variables": {"l": u}}).encode())
            cal = res["data"]["user"]["contributionsCollection"]["contributionCalendar"]
            lv = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
            days = [(d["date"], d["contributionCount"], lv.get(d["contributionLevel"], 0))
                    for w in cal["weeks"] for d in w["contributionDays"]]
            return {"total": cal["totalContributions"], "days": days}
        except Exception as e:
            print("graphql falló, uso página pública:", e, file=sys.stderr)
    page = http(f"https://github.com/users/{u}/contributions", accept="text/html")
    days = []
    for tag in re.findall(r"<td[^>]+ContributionCalendar-day[^>]*>", page):
        d = re.search(r'data-date="([\d-]+)"', tag)
        l = re.search(r'data-level="(\d)"', tag)
        if d:
            days.append((d.group(1), None, int(l.group(1)) if l else 0))
    days.sort()
    m = re.search(r"([\d,\.]+)\s+contributions?\s+in the last year", page)
    total = int(re.sub(r"[^\d]", "", m.group(1))) if m else 0
    return {"total": total, "days": days}


def demo_data(cfg):
    rnd = random.Random(4)
    today = dt.date.today()
    start = today - dt.timedelta(days=today.weekday() + 1 + 52 * 7)
    days = []
    for i in range((today - start).days + 1):
        d = start + dt.timedelta(days=i)
        lvl = rnd.choices([0, 1, 2, 3, 4], [50, 20, 15, 10, 5])[0]
        days.append((d.isoformat(), lvl * 3, lvl))
    dates = sorted(f"{y}-0{rnd.randint(1,9)}-1{rnd.randint(0,9)}T00:00:00Z"
                   for y in range(2018, today.year + 1) for _ in range(rnd.randint(1, 5)))
    return {
        "public_repos": len(dates), "followers": 128, "following": 64, "created_at": "2016-03-01T00:00:00Z",
        "stars": 342, "repo_dates": dates, "repo_stars": [(d, rnd.randint(0, 40)) for d in dates],
        "top_langs": ["Python", "TypeScript", "Shell"],
        "calendar": {"total": sum(d[1] for d in days), "days": days},
        "projects": {p["repo"]: {"stargazers_count": rnd.randint(2, 90), "forks_count": rnd.randint(0, 12),
                                 "language": ["TypeScript", "Python", "Shell", "Python"][i % 4],
                                 "html_url": f"https://github.com/{p['repo']}"}
                     for i, p in enumerate(cfg["projects"]) if p.get("repo")},
        "demo": True,
    }


def demo_badge(w):
    return f'<g opacity=".9"><rect x="{w-92}" y="10" width="80" height="18" rx="4" fill="#3a0d0d" stroke="#ff5b5b"/>' + \
        T(w - 52, 23, "DEMO DATA", "mb", 9, "#ff8a8a", 1.5, "middle") + "</g>"


# ─── piezas ────────────────────────────────────────────────────────────────
def build_header(cfg):
    W, H = 1000, 300
    defs, body = "", []
    body.append(f'<rect width="{W}" height="{H}" fill="{BG}"/>')
    uri = photo_uri(cfg.get("photos", {}).get("header"))
    if uri:
        d, b = photo(uri, 430, 0, 570, H, "h", "left", 0.62)
        defs += d
        body.append(b)
    body.append(topo("header", 0.075, 0.15, 1.06, W, H))
    defs += (f'<radialGradient id="vig" cx=".38" cy=".5" r=".85"><stop offset=".55" stop-color="{BG}" stop-opacity="0"/>'
             f'<stop offset="1" stop-color="{BG}" stop-opacity=".95"/></radialGradient>'
             f'<linearGradient id="scan" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="{Y}" stop-opacity="0"/>'
             f'<stop offset="1" stop-color="{Y}" stop-opacity=".09"/></linearGradient>')
    body.append(f'<rect width="{W}" height="{H}" fill="url(#vig)"/>')
    body.append(f'<rect class="scan" x="0" y="-40" width="{W}" height="40" fill="url(#scan)"/>')

    loc = cfg["location"]
    body.append(f'<g class="fade" style="animation-delay:.2s">{T(36, 132, loc["lat"], "m", 10.5, MUTED, 2)}{T(36, 150, loc["lon"], "m", 10.5, MUTED, 2)}</g>')

    name = cfg["name"]
    size = 104
    nw = text_w(name, "d", size)
    x0, base = 168, 162
    body.append(f'<g transform="translate({x0},{base}) skewX(-10)"><text class="d rise" font-size="{size}" fill="{TXT}" x="0" y="0">{esc(name)}</text></g>')
    bar = f'<polygon class="bar" points="{x0+6},{base+16} {x0+nw+8},{base+16} {x0+nw+4},{base+30} {x0+2},{base+30}" fill="{Y}"/>'
    body.append(bar)
    tag = "  /  ".join(cfg["tagline"])
    body.append(f'<g class="fade" style="animation-delay:.9s">{T(x0+4, base+64, tag, "m", 11.5, "#CFCFCF", 6.2)}</g>')

    mx = x0 + nw + 34
    mot = cfg["motto"]
    body.append(
        f'<g transform="translate({mx},{base-58}) rotate(-13)"><g class="stamp">'
        + T(0, 0, mot[0], "k", 40, Y) + T(16, 40, mot[1], "k", 40, Y) + "</g></g>"
    )

    lx = 872
    for i, word in enumerate(cfg["loop"]):
        body.append(f'<g class="rise" style="animation-delay:{1.3 + i*0.25:.2f}s">{T(lx, 96 + i*23, word, "mb", 11.5, TXT, 5.6)}</g>')
    ly = 96 + len(cfg["loop"]) * 23
    body.append(f'<rect class="fade" style="animation-delay:2.4s" x="{lx}" y="{ly-6}" width="22" height="4" fill="{Y}"/>')
    body.append(f'<rect class="blink" x="{lx+28}" y="{ly-12}" width="7" height="12" fill="{Y}" opacity=".9"/>')
    body.append(f'<line x1="0" y1="{H-0.5}" x2="{W}" y2="{H-0.5}" stroke="{LINE}"/>')

    css = (
        "@keyframes bar{from{transform:scaleX(0)}to{transform:scaleX(1)}}"
        ".bar{transform-box:fill-box;transform-origin:left center;animation:bar .9s .45s cubic-bezier(.7,0,.2,1) both}"
        "@keyframes stamp{0%{opacity:0;transform:scale(1.6)}60%{opacity:1;transform:scale(.94)}100%{transform:scale(1)}}"
        ".stamp{transform-box:fill-box;transform-origin:center;animation:stamp .55s 1.05s ease-out both}"
        "@keyframes scan{from{transform:translateY(0)}to{transform:translateY(" + str(H + 40) + "px)}}"
        ".scan{animation:scan 7s linear infinite}"
    )
    return svg(W, H, "".join(body), ["d", "k", "m", "mb"], css, f"{name} — {tag}", defs)


def build_route(cfg, data):
    W, H = 1000, 340
    body, defs = [], ""
    defs += f'<clipPath id="pc"><rect x="1" y="1" width="{W-2}" height="{H-2}" rx="12"/></clipPath>'
    defs += '<filter id="glow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="4"/></filter>'
    body.append(f'<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="12" fill="{PANEL}" stroke="{LINE}"/>')
    body.append(f'<g clip-path="url(#pc)">{topo("map", 0.08, 0.17, 1.05, W, H)}')
    body.append(f'<circle cx="560" cy="175" r="250" fill="none" stroke="#fff" stroke-opacity=".07" stroke-dasharray="2 6"/>')
    body.append(f'<circle cx="560" cy="175" r="150" fill="none" stroke="#fff" stroke-opacity=".05"/>')
    for (cx, cy) in [(44, 106), (300, 70), (590, 300), (700, 196), (905, 60), (870, 270)]:
        body.append(f'<path d="M{cx-7} {cy}H{cx+7}M{cx} {cy-7}V{cy+7}" stroke="#fff" stroke-opacity=".28"/>')
    body.append("</g>")

    body.append(dot_title(30, 40, "LIVE SYSTEM", blink=True))
    if data.get("demo"):
        body.append(demo_badge(W - 40))

    # norte + escala
    body.append(T(966, 40, "N", "mb", 11, TXT, 0, "middle"))
    ticks = "".join(f'<path d="M966 {y}h{6 if i % 2 else 10}" stroke="#fff" stroke-opacity=".5"/>' for i, y in enumerate(range(52, 150, 12)))
    body.append(f'<path d="M966 50V150" stroke="#fff" stroke-opacity=".5"/>{ticks}')

    loc = cfg["location"]
    for i, s in enumerate([loc["lat"], loc["lon"], loc["label"]]):
        body.append(T(30, 252 + i * 17, s, "m", 10, MUTED, 2))
    for i, s in enumerate(cfg["tagline"] + [" ".join(cfg["motto"])]):
        body.append(T(968, 238 + i * 15, s, "m", 8.5, DIM, 2.4, "end"))
    body.append(f'<path d="M776 {H-24}H812" stroke="{Y}" stroke-width="2"/>' + T(968, H - 20, cfg["route_caption"], "m", 8.5, MUTED, 3.2, "end"))

    # ruta
    nodes = [(250, 252), (408, 132), (540, 214), (668, 84), (836, 168)]
    rnd = random.Random(9)
    pts = [nodes[0]]
    for a, b in zip(nodes, nodes[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        nx, ny = -dy / L, dx / L
        for t in (0.3, 0.55, 0.8):
            off = rnd.uniform(-14, 14)
            pts.append((a[0] + dx * t + nx * off, a[1] + dy * t + ny * off))
        pts.append(b)
    d = smooth(pts)
    body.append(f'<path d="{d}" fill="none" stroke="{Y}" stroke-opacity=".22" stroke-width="2"/>')
    body.append(f'<path class="draw" d="{d}" pathLength="1" fill="none" stroke="{Y}" stroke-width="7" stroke-opacity=".35" filter="url(#glow)"/>')
    body.append(f'<path id="route" class="draw" d="{d}" pathLength="1" fill="none" stroke="{Y}" stroke-width="2.4" stroke-linecap="round"/>')
    body.append(f'<circle r="4.5" fill="#fff"><animateMotion dur="9s" repeatCount="indefinite" keyPoints="0;1;1" keyTimes="0;.6;1" calcMode="linear"><mpath href="#route" xlink:href="#route"/></animateMotion></circle>')

    labels = cfg["route"]
    offs = [(-16, -12, "end"), (14, -16, "start"), (14, 24, "start"), (16, -14, "start"), (-6, -38, "start")]
    for i, ((x, y), lab, (ox, oy, an)) in enumerate(zip(nodes, labels, offs)):
        last = i == len(nodes) - 1
        if last:
            body.append(f'<circle class="pulse" cx="{x}" cy="{y}" r="9" fill="none" stroke="{Y}" stroke-width="1.5"/>')
            body.append(f'<circle class="pulse" style="animation-delay:1.2s" cx="{x}" cy="{y}" r="9" fill="none" stroke="{Y}" stroke-width="1.5"/>')
            body.append(f'<circle cx="{x}" cy="{y}" r="13" fill="{Y}" fill-opacity=".18"/>')
        body.append(f'<circle cx="{x}" cy="{y}" r="6" fill="{PANEL}" stroke="{Y}" stroke-width="2.4"/><circle cx="{x}" cy="{y}" r="2.6" fill="{Y}"/>')
        words = lab["label"].split(" ")
        if last and len(words) > 1:
            txt = T(x + ox, y + oy, words[0], "mb", 10.5, TXT, 2.4, an) + T(x + ox, y + oy + 14, " ".join(words[1:]), "mb", 10.5, TXT, 2.4, an)
        else:
            txt = T(x + ox, y + oy, lab["label"], "mb", 10.5, TXT, 2.4, an)
        body.append(f'<g class="fade" style="animation-delay:{0.4 + i*0.9:.1f}s">{txt}</g>')

    css = (
        "@keyframes draw{0%{stroke-dasharray:1;stroke-dashoffset:1}60%,92%{stroke-dasharray:1;stroke-dashoffset:0;opacity:1}100%{stroke-dasharray:1;stroke-dashoffset:0;opacity:0}}"
        ".draw{stroke-dasharray:1;animation:draw 9s ease-in-out infinite}"
    )
    return svg(W, H, "".join(body), ["m", "mb"], css, "Live system: ideas → build → automate → deploy → next project", defs)


def build_stats(cfg, data):
    W, H, gap = 1000, 112, 14
    tw = (W - gap * 3) / 4
    now = dt.datetime.now(dt.timezone.utc)
    created = dt.datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
    years = max(1, int((now - created).days // 365.25))

    def spark_bars(vals, x, y, w, h):
        if not vals:
            return ""
        mx = max(vals) or 1
        n = len(vals)
        bw = w / n * 0.62
        out = ""
        for i, v in enumerate(vals):
            bh = max(2, v / mx * h)
            op = 0.35 + 0.65 * (i + 1) / n
            out += f'<rect x="{x + i * w / n:.1f}" y="{y + h - bh:.1f}" width="{bw:.1f}" height="{bh:.1f}" fill="#BDBDBD" fill-opacity="{op:.2f}"/>'
        return out

    def spark_line(vals, x, y, w, h):
        if len(vals) < 2:
            return ""
        mx, mn = max(vals), min(vals)
        rng = (mx - mn) or 1
        pts = [(x + i * w / (len(vals) - 1), y + h - (v - mn) / rng * h) for i, v in enumerate(vals)]
        return f'<path d="{smooth(pts)}" fill="none" stroke="#CFCFCF" stroke-width="1.4"/>'

    # repos creados por año
    by_year = {}
    for d in data["repo_dates"]:
        by_year[d[:4]] = by_year.get(d[:4], 0) + 1
    ys = list(range(max(created.year, now.year - 11), now.year + 1))
    repo_bars = [by_year.get(str(y), 0) for y in ys]
    # estrellas acumuladas por fecha de creación del repo
    acc, cum = 0, []
    for _, s in sorted(data["repo_stars"]):
        acc += s
        cum.append(acc)
    # actividad semanal (calendario)
    days = data["calendar"]["days"]
    weekly = [sum(lv for _, _, lv in days[i:i + 7]) for i in range(0, len(days), 7)][-26:]

    tiles = [
        ("repo", kfmt(data["public_repos"]), "PUBLIC REPOS", spark_bars(repo_bars, 0, 0, 82, 30)),
        ("star", kfmt(data["stars"]), "TOTAL STARS", spark_line(cum[-24:] if len(cum) > 1 else [0, 0], 0, 0, 82, 28)),
        ("users", kfmt(data["followers"]), "FOLLOWERS", spark_line(weekly, 0, 0, 82, 26)),
        ("clock", str(years), "YEARS ON GITHUB", "".join(
            f'<rect x="{i * 82 / years:.1f}" y="{14 if i < years - 1 else 4}" width="{max(2, 82 / years - 3):.1f}" height="{14 if i < years - 1 else 24}" fill="{Y if i == years - 1 else "#BDBDBD"}" fill-opacity="{1 if i == years - 1 else 0.25 + 0.5 * i / years:.2f}"/>'
            for i in range(years))),
    ]
    icons = {
        "repo": T(0, 13, ">_", "mb", 15, Y),
        "star": f'<path d="M8 0l2.4 5.1 5.6.7-4.1 3.9 1 5.5L8 12.5 3.1 15.2l1-5.5L0 5.8l5.6-.7z" fill="{Y}"/>',
        "users": f'<g fill="none" stroke="{Y}" stroke-width="1.6"><circle cx="6" cy="4.5" r="3.4"/><path d="M0.5 15c.4-3.6 2.6-5.6 5.5-5.6s5.1 2 5.5 5.6"/><path d="M11.5 1.6a3.3 3.3 0 0 1 0 6.1M13.4 9.8c1.6.7 2.6 2.4 2.8 5"/></g>',
        "clock": f'<g fill="none" stroke="{Y}" stroke-width="1.6"><circle cx="8" cy="8" r="7"/><path d="M8 3.6V8l3 2"/></g>',
    }
    body = []
    for i, (ic, num, lab, spark) in enumerate(tiles):
        x = i * (tw + gap)
        sub = ""
        if ic == "users":
            sub = T(x + tw - 18, 96, f"{kfmt(data['following'])} following", "m", 9, DIM, 0.5, "end")
        body.append(
            f'<g class="rise" style="animation-delay:{0.1 + i * 0.12:.2f}s">'
            f'<rect x="{x + .5:.1f}" y=".5" width="{tw - 1:.1f}" height="{H - 1}" rx="10" fill="{PANEL}" stroke="{LINE}"/>'
            f'<g transform="translate({x + 20:.1f},18)">{icons[ic]}</g>'
            + T(x + 20, 70, num, "sb", 30, TXT)
            + T(x + 20, 94, lab, "m", 9.5, MUTED, 2.8)
            + f'<g transform="translate({x + tw - 104:.1f},{50 if ic != "users" else 40})">{spark}</g>'
            + sub + "</g>"
        )
    if data.get("demo"):
        body.append(demo_badge(W))
    return svg(W, H, "".join(body), ["m", "mb", "sb"], "", "GitHub stats")


def build_panel(cfg, data):
    W, H = 1000, 210
    LW = 424
    RX = LW + 14
    RW = W - RX
    body = []
    # stack
    body.append(f'<rect x=".5" y=".5" width="{LW - 1}" height="{H - 1}" rx="10" fill="{PANEL}" stroke="{LINE}"/>')
    body.append(dot_title(22, 34, "TECH STACK") + T(LW - 22, 34, "//", "mb", 12, MUTED, 0, "end"))
    top = set(data.get("top_langs", []))
    x, y = 22, 56
    for i, it in enumerate(cfg["stack"]):
        hl = it.get("highlight") or (it.get("lang") in top)
        icon = ICONS.get(it.get("icon", ""))
        tw_ = text_w(it["name"], "s", 12)
        cw = tw_ + 26 + (18 if icon else 0)
        if x + cw > LW - 22:
            x, y = 22, y + 36
        stroke = Y if hl else "#333"
        fill = "rgba(244,196,48,.10)" if hl else "#151515"
        tcol = "#F7DB82" if hl else "#D6D6D6"
        g = f'<rect x="{x}" y="{y}" width="{cw:.1f}" height="27" rx="13.5" fill="{fill}" stroke="{stroke}"/>'
        tx = x + 13
        if icon:
            g += f'<path transform="translate({x + 12},{y + 7.5}) scale(.5)" d="{icon}" fill="{Y if hl else "#BDBDBD"}"/>'
            tx += 18
        g += T(tx, y + 17.6, it["name"], "s", 12, tcol)
        body.append(f'<g class="rise" style="animation-delay:{0.15 + i * 0.05:.2f}s">{g}</g>')
        x += cw + 8
    # contribuciones
    body.append(f'<rect x="{RX + .5}" y=".5" width="{RW - 1}" height="{H - 1}" rx="10" fill="{PANEL}" stroke="{LINE}"/>')
    body.append(dot_title(RX + 22, 34, "CONTRIBUTIONS"))
    total = data["calendar"]["total"]
    body.append(f'<text x="{W - 22}" y="34" text-anchor="end" font-size="13"><tspan class="sb" fill="{TXT}">{esc(f"{total:,}")}</tspan><tspan class="s" fill="{MUTED}"> contributions</tspan></text>')
    days = data["calendar"]["days"]
    if days:
        first = dt.date.fromisoformat(days[0][0])
        lead = (first.weekday() + 1) % 7  # domingo = 0
        cells = [None] * lead + days
        weeks = math.ceil(len(cells) / 7)
        gx, gy = RX + 50, 70
        pitch = min(9.6, (RW - 50 - 22) / weeks)
        cs = pitch - 1.9
        months, last_m = [], None
        rects = []
        for i, c in enumerate(cells):
            if c is None:
                continue
            w, wd = divmod(i, 7)
            dd = dt.date.fromisoformat(c[0])
            if dd.day <= 7 and wd == 0 and dd.month != last_m:
                months.append((w, dd.strftime("%b")))
                last_m = dd.month
            col = LEVELS[c[2]]
            rects.append(f'<rect x="{gx + w * pitch:.1f}" y="{gy + wd * pitch:.1f}" width="{cs:.1f}" height="{cs:.1f}" rx="1.6" fill="{col}" style="animation-delay:{w * 0.014:.2f}s"/>')
        body.append(f'<g class="cells">{"".join(rects)}</g>')
        for w, m in months:
            if w < weeks - 2:
                body.append(T(gx + w * pitch, gy - 10, m, "s", 9.5, MUTED))
        for wd, lab in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
            body.append(T(RX + 22, gy + wd * pitch + cs - 0.5, lab, "s", 9.5, MUTED))
        ly = gy + 7 * pitch + 30
        body.append(T(gx, ly, "Less", "s", 9.5, MUTED))
        for i, c in enumerate(LEVELS):
            body.append(f'<rect x="{gx + 30 + i * 13}" y="{ly - 9}" width="10" height="10" rx="1.6" fill="{c}" stroke="#2c2c2c" stroke-width=".6"/>')
        body.append(T(gx + 30 + 5 * 13 + 4, ly, "More", "s", 9.5, MUTED))
        body.append(T(W - 22, ly, "últimos 12 meses", "m", 9, DIM, 1, "end"))
    if data.get("demo"):
        body.append(demo_badge(W))
    css = ".cells rect{animation:fade .5s ease both}"
    return svg(W, H, "".join(body), ["m", "mb", "s", "sb"], css, "Tech stack y contribuciones")


def build_section(label, right):
    W, H = 1000, 44
    body = dot_title(4, 28, label) + T(W - 26, 28, right, "s", 12.5, MUTED, 0, "end") + \
        f'<path d="M{W-18} 24h10M{W-12} 19l5 5-5 5" fill="none" stroke="{MUTED}" stroke-width="1.4"/>'
    return svg(W, H, body, ["mb", "s"], "", label)


def build_card(cfg, p, repo, idx, demo=False):
    W, H = 480, 300
    IW, IH = W - 24, 158
    body, defs = [], ""
    defs += f'<clipPath id="ic"><rect x="12" y="12" width="{IW}" height="{IH}" rx="8"/></clipPath>'
    defs += f'<linearGradient id="sh" x1="0" x2="0" y1="0" y2="1"><stop offset=".45" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".7"/></linearGradient>'
    body.append(f'<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="12" fill="{PANEL}" stroke="{LINE}"/>')
    body.append('<g clip-path="url(#ic)">')
    body.append(f'<rect x="12" y="12" width="{IW}" height="{IH}" fill="#121212"/>')
    uri = photo_uri(p.get("image"))
    if uri:
        d, b = photo(uri, 12, 12, IW, IH, f"c{idx}", None, 0.92)
        defs += d
        body.append(b)
        body.append(f'<rect x="12" y="12" width="{IW}" height="{IH}" fill="url(#sh)"/>')
    else:
        body.append(f'<g transform="translate(12,12)">{topo("card", 0.12, 0.24, 1.08, IW, IH)}</g>')
        num = p.get("index", f"{idx:02d}")
        body.append(f'<text x="{12 + IW - 22}" y="{12 + IH - 16}" text-anchor="end" class="d" font-size="104" fill="none" stroke="{Y}" stroke-opacity=".85" stroke-width="1.4" transform="skewX(-8)" transform-origin="{12 + IW} {12 + IH}">{esc(num)}</text>')
        rnd = random.Random(idx)
        pts = [(30, 140), (90 + rnd.randint(-20, 20), 110), (150, 120 + rnd.randint(-20, 20)), (210, 80), (270 + rnd.randint(-15, 15), 70)]
        body.append(f'<path class="draw" d="{smooth(pts)}" pathLength="1" fill="none" stroke="{Y}" stroke-width="2" stroke-linecap="round"/>')
        body.append(f'<circle cx="{pts[-1][0]}" cy="{pts[-1][1]}" r="4" fill="{Y}"/><circle class="pulse" cx="{pts[-1][0]}" cy="{pts[-1][1]}" r="6" fill="none" stroke="{Y}"/>')
        body.append(T(30, 36, f"PROJECT / {num}", "m", 9, MUTED, 3))
    body.append("</g>")
    body.append(f'<path d="M{W-42} 40l14-14M{W-38} 26h10v10" fill="none" stroke="#fff" stroke-width="2"/>')

    body.append(T(24, 200, p["title"], "sb", 19, TXT))
    desc = p.get("description") or (repo or {}).get("description") or ""
    for i, line in enumerate(wrap(desc, "s", 13, W - 48)):
        body.append(T(24, 224 + i * 18, line, "s", 13, MUTED))

    fy = 280
    if repo:
        x = 24
        lang = repo.get("language")
        if lang:
            body.append(f'<circle cx="{x + 5}" cy="{fy - 4.5}" r="5" fill="{LANG_COLORS.get(lang, "#9A9A9A")}"/>')
            body.append(T(x + 16, fy, lang, "s", 12, "#BDBDBD"))
            x += 16 + text_w(lang, "s", 12) + 26
        body.append(f'<path transform="translate({x},{fy - 11}) scale(.8)" d="M8 0l2.4 5.1 5.6.7-4.1 3.9 1 5.5L8 12.5 3.1 15.2l1-5.5L0 5.8l5.6-.7z" fill="none" stroke="#BDBDBD" stroke-width="1.4"/>')
        body.append(T(x + 18, fy, kfmt(repo.get("stargazers_count", 0)), "s", 12, "#BDBDBD"))
        x += 18 + text_w(kfmt(repo.get("stargazers_count", 0)), "s", 12) + 22
        body.append(f'<g transform="translate({x},{fy - 11})" fill="none" stroke="#BDBDBD" stroke-width="1.4"><circle cx="3" cy="2.5" r="2"/><circle cx="11" cy="2.5" r="2"/><circle cx="7" cy="11.5" r="2"/><path d="M3 4.5v1.5c0 1.5 1 2 2.5 2h3c1.5 0 2.5-.5 2.5-2V4.5M7 8v1.5"/></g>')
        body.append(T(x + 20, fy, kfmt(repo.get("forks_count", 0)), "s", 12, "#BDBDBD"))
    else:
        host = re.sub(r"^https?://", "", p.get("url", "")).rstrip("/")
        body.append(T(24, fy, ("→ " + host) if host else "EN CONSTRUCCIÓN", "m", 10, Y if host else DIM, 1.5))
    if demo:
        body.append(demo_badge(W))
    css = ("@keyframes draw{0%{stroke-dashoffset:1}50%,100%{stroke-dashoffset:0}}"
           ".draw{stroke-dasharray:1;animation:draw 6s ease-in-out infinite alternate}")
    return svg(W, H, "".join(body), ["d", "m", "s", "sb"], css, p["title"], defs)


def build_footer(cfg):
    W, H = 1000, 250
    f = cfg["footer"]
    body, defs = [], ""
    body.append(f'<rect width="{W}" height="{H}" rx="12" fill="{BG}" stroke="{LINE}"/>')
    defs += f'<clipPath id="fc"><rect x="1" y="1" width="{W-2}" height="{H-2}" rx="12"/></clipPath>'
    body.append('<g clip-path="url(#fc)">')
    uri = photo_uri(cfg.get("photos", {}).get("footer"))
    if uri:
        d, b = photo(uri, 540, 0, 460, H, "f", "left", 0.7)
        defs += d
        body.append(b)
    body.append(topo("footer", 0.06, 0.12, 1.06, W, H))
    body.append("</g>")
    for i, s in enumerate(f["list"]):
        body.append(f'<g class="rise" style="animation-delay:{0.1 + i * 0.12:.2f}s">{T(36, 96 + i * 22, f"{i+1:02d}", "m", 10, DIM, 2)}{T(66, 96 + i * 22, s, "m", 10.5, "#CFCFCF", 4.2)}</g>')
    cx = 330
    body.append(f'<g transform="translate({cx},80) rotate(-7)">')
    for i, s in enumerate(f["shout"]):
        body.append(f'<g class="rise" style="animation-delay:{0.4 + i * 0.22:.2f}s">{T(i * 14, i * 40, s, "k", 38, TXT)}</g>')
    n = len(f["shout"])
    body.append(f'<path class="ul" d="M{(n-1)*14+4} {(n-1)*40+16}c40-4 90-6 150-3" fill="none" stroke="{Y}" stroke-width="5" stroke-linecap="round" pathLength="1"/>')
    body.append("</g>")
    sx = 850
    body.append(f'<g transform="translate({sx},88) rotate(-16)"><g class="stamp">')
    for i, s in enumerate(f["stamp"]):
        body.append(T(i * 6, i * 30, s, "k", 26, "#E6E6E6", 0, "middle"))
    body.append(f'<rect x="{-20 + len(f["stamp"]) * 6}" y="{len(f["stamp"]) * 30 - 10}" width="34" height="5" fill="{Y}"/></g></g>')
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    body.append(T(36, H - 20, cfg["location"]["label"], "m", 9, DIM, 4))
    body.append(T(W - 28, H - 20, f"LAST SYNC {stamp} · GITHUB ACTIONS", "m", 8.5, DIM, 2.4, "end"))
    css = ("@keyframes ul{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}"
           ".ul{stroke-dasharray:1;animation:ul .7s 1.4s ease-out both}"
           "@keyframes stamp{0%{opacity:0;transform:scale(1.6)}60%{opacity:1;transform:scale(.94)}100%{transform:scale(1)}}"
           ".stamp{transform-box:fill-box;transform-origin:center;animation:stamp .55s 1.7s ease-out both}")
    return svg(W, H, "".join(body), ["k", "m"], css, " ".join(f["shout"]), defs)


# ─── README ────────────────────────────────────────────────────────────────
def build_readme(cfg, data):
    u = cfg["username"]
    g = "assets/generated"
    L = ["<!-- Generado por scripts/build.py — edita config.json, no este archivo. -->", ""]
    L.append(f'<p align="center"><img src="{g}/header.svg" width="100%" alt="{esc(cfg["name"])} — {esc(" / ".join(cfg["tagline"]))}"></p>')
    L.append("")
    L.append(f'<p align="center"><b>{esc(cfg["intro"])}</b><br><sub>{esc(cfg["intro_sub"])}</sub></p>')
    L.append("")
    L.append(f'<p align="center"><img src="{g}/route.svg" width="100%" alt="Live system: ideas, build, automate, deploy, next project"></p>')
    linked = [r for r in cfg["route"] if r.get("url")]
    if linked:
        L.append('<p align="center"><sub>' + " &nbsp;→&nbsp; ".join(
            f'<a href="{esc(r["url"])}"><code>{esc(r["label"])}</code></a>' if r.get("url") else f'<code>{esc(r["label"])}</code>'
            for r in cfg["route"]) + "</sub></p>")
    L.append("")
    L.append(f'<p align="center"><img src="{g}/stats.svg" width="100%" alt="GitHub stats"></p>')
    L.append(f'<p align="center"><img src="{g}/panel.svg" width="100%" alt="Tech stack y contribuciones"></p>')
    L.append("")
    L.append(f'<a href="https://github.com/{u}?tab=repositories&sort=stargazers"><img src="{g}/projects-title.svg" width="100%" alt="Featured projects"></a>')
    L.append("")
    cards = []
    for i, p in enumerate(cfg["projects"], 1):
        repo = data["projects"].get(p.get("repo"))
        href = p.get("url") or (repo or {}).get("html_url") or f"https://github.com/{u}"
        cards.append(f'<a href="{esc(href)}"><img src="{g}/project-{i:02d}.svg" width="49%" alt="{esc(p["title"])}"></a>')
    for i in range(0, len(cards), 2):
        L.append('<p align="center">' + "\n".join(cards[i:i + 2]) + "</p>")
    L.append("")
    L.append(f'<p align="center"><img src="{g}/footer.svg" width="100%" alt="{esc(" ".join(cfg["footer"]["shout"]))}"></p>')
    if cfg.get("links"):
        L.append("")
        L.append('<p align="center"><sub>' + " &nbsp;·&nbsp; ".join(
            f'<a href="{esc(l["url"])}">{esc(l["label"])}</a>' for l in cfg["links"]) + "</sub></p>")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="datos de ejemplo (no publicar)")
    ap.add_argument("--out", default=None, help="carpeta de salida (por defecto el repo)")
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    data = demo_data(cfg) if a.demo else fetch(cfg, token)

    out_root = a.out or ROOT
    gen = os.path.join(out_root, "assets", "generated")
    os.makedirs(gen, exist_ok=True)
    files = {
        "header.svg": build_header(cfg),
        "route.svg": build_route(cfg, data),
        "stats.svg": build_stats(cfg, data),
        "panel.svg": build_panel(cfg, data),
        "projects-title.svg": build_section("FEATURED PROJECTS", "Most stars"),
        "footer.svg": build_footer(cfg),
    }
    for i, p in enumerate(cfg["projects"], 1):
        files[f"project-{i:02d}.svg"] = build_card(cfg, p, data["projects"].get(p.get("repo")), i, data.get("demo"))
    for name, content in files.items():
        with open(os.path.join(gen, name), "w", encoding="utf-8") as fh:
            fh.write(content)
        print(f"  {name:22s} {len(content)/1024:7.1f} KB")
    with open(os.path.join(out_root, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(build_readme(cfg, data))
    print("README.md listo", "(DEMO)" if data.get("demo") else "")


if __name__ == "__main__":
    main()
