#!/usr/bin/env python3
"""Render an animated Hack The Box badge as a self-contained SVG.

Uses HTB's public profile endpoints (no token needed) and only the Python
standard library, so it runs as-is on a GitHub Actions runner.

    python3 scripts/htb_card.py <htb_user_id> <out_dir> [fallback_base_url]

Writes htb-badge.svg. If HTB can't be reached, the previously published badge
is kept so the profile never shows a broken image.
"""
import base64
import json
import sys
import urllib.request
from html import escape

API = "https://labs.hackthebox.com/api"
UA = {"User-Agent": "Mozilla/5.0 (htb-badge; github profile)", "Accept": "application/json"}

# Palette: HTB navy and lime.
BG = "#0E1520"
PANEL = "#141D2B"
LINE = "#223047"
LIME = "#9FEF00"
FG = "#E8EEF6"
DIM = "#7F8EA3"
MUTED = "#4A5A72"

SANS = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'JetBrains Mono', Menlo, Consolas, 'DejaVu Sans Mono', monospace"


def get(path):
    req = urllib.request.Request(API + path, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def get_bytes(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read(), r.headers.get("Content-Type", "image/png")


def collect(uid):
    p = get(f"/v4/profile/{uid}")["profile"]
    xp = get(f"/experience/v1/account/{p['account_id']}")
    mac = get(f"/v4/profile/progress/machines/{uid}")["profile"]
    chal = get(f"/v4/profile/progress/challenges/{uid}")["profile"]
    sher = get(f"/v4/profile/progress/sherlocks/{uid}")["profile"]

    avatar = None
    try:
        raw, ctype = get_bytes(p["avatar"])
        avatar = f"data:{ctype.split(';')[0]};base64,{base64.b64encode(raw).decode()}"
    except Exception:
        pass

    return {
        "name": p["name"],
        "rank": p["rank"],
        "ranking": p.get("ranking"),
        "avatar": avatar,
        "level": xp["level"],
        "level_title": xp["levelTitle"],
        "level_grade": xp.get("levelGrade") or "",
        "level_xp": xp["levelExperiencePoints"],
        "level_need": xp["levelExperiencePoints"] + xp["experienceUntilNextLevel"],
        "machines": (mac["machine_owns"]["solved"], mac["machine_owns"]["total"]),
        "challenges": (chal["challenge_owns"]["solved"], chal["challenge_owns"]["total"]),
        "sherlocks": (sher["challenge_owns"]["solved"], sher["challenge_owns"]["total"]),
    }


def t(x, y, s, size=12, fill=FG, family=MONO, weight=400, anchor="start", extra=""):
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}" {extra}>{escape(str(s))}</text>')


def render_badge(d):
    """Compact badge: avatar, name, rank, level and a thin XP bar."""
    W, H = 510, 84
    roman = {"1": "I", "2": "II", "3": "III"}
    grade = roman.get(str(d["level_grade"]), str(d["level_grade"]))
    css = """
    .grow { transform-box: fill-box; transform-origin: left center; transform: scaleX(0);
            animation: grow 1.2s cubic-bezier(.2,.8,.2,1) .3s forwards; }
    @keyframes grow { to { transform: scaleX(1); } }
    .ring { transform-box: fill-box; transform-origin: center; animation: spin 12s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .pulse { animation: pulse 1.6s ease-in-out infinite; }
    @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .2; } }
    .sweep { animation: sweep 5s cubic-bezier(.6,0,.4,1) infinite; }
    @keyframes sweep { 0% { transform: translateX(-120px); } 100% { transform: translateX(520px); } }
    """
    o = []
    o.append(f'<rect width="{W}" height="{H}" rx="12" fill="{BG}"/>')
    o.append(f'<rect width="{W}" height="{H}" rx="12" fill="url(#bgrid)"/>')
    o.append(f'<rect class="sweep" x="0" y="0" width="90" height="2" fill="url(#bglint)"/>')

    ax, ay, ar = 42, 42, 23
    if d["avatar"]:
        o.append(f'<image href="{d["avatar"]}" x="{ax - ar}" y="{ay - ar}" width="{ar * 2}" height="{ar * 2}" '
                 f'clip-path="url(#bav)" preserveAspectRatio="xMidYMid slice"/>')
    else:
        o.append(f'<circle cx="{ax}" cy="{ay}" r="{ar}" fill="{PANEL}"/>')
    o.append(f'<circle class="ring" cx="{ax}" cy="{ay}" r="{ar + 5}" fill="none" stroke="{LIME}" '
             f'stroke-width="1.4" stroke-dasharray="2.5 6" stroke-linecap="round"/>')

    # Name and rank pill
    name = d["name"]
    o.append(t(82, 34, name, 17, FG, SANS, 700))
    px = 82 + len(name) * 9.6 + 10
    rank = d["rank"].upper()
    pw = len(rank) * 6.4 + 16
    o.append(f'<rect x="{px:.1f}" y="21" width="{pw:.1f}" height="17" rx="8.5" fill="#9FEF0014" stroke="{LIME}" stroke-opacity=".6"/>')
    o.append(t(px + pw / 2, 33, rank, 9.5, LIME, MONO, 700, "middle", 'letter-spacing=".6"'))

    # Stats line
    parts = [(f"#{d['ranking']}", FG), (" · ", MUTED), (f"{d['machines'][0]}", FG), (" machines", DIM), (" · ", MUTED),
             (f"{d['challenges'][0]}", FG), (" challenges", DIM), (" · ", MUTED),
             (f"{d['sherlocks'][0]}", FG), (" sherlocks", DIM)]
    spans = "".join(f'<tspan fill="{c}">{escape(s)}</tspan>' for s, c in parts)
    o.append(f'<text x="82" y="55" font-family="{MONO}" font-size="10.5" xml:space="preserve">{spans}</text>')

    # XP bar to next level
    bx, bw = 82, 306
    frac = max(0.0, min(1.0, d["level_xp"] / max(d["level_need"], 1)))
    o.append(f'<rect x="{bx}" y="64" width="{bw}" height="3" rx="1.5" fill="{LINE}"/>')
    o.append(f'<rect class="grow" x="{bx}" y="64" width="{max(bw * frac, 3):.1f}" height="3" rx="1.5" fill="{LIME}"/>')

    # Level block on the right
    o.append(f'<rect x="{W - 104}" y="14" width="1" height="{H - 28}" fill="{LINE}"/>')
    o.append(t(W - 50, 28, "LEVEL", 9, DIM, MONO, 600, "middle", 'letter-spacing="2"'))
    o.append(t(W - 50, 59, d["level"], 28, LIME, SANS, 800, "middle"))
    o.append(t(W - 50, 73, f"{d['level_title'].upper()} {grade}", 8.5, DIM, MONO, 600, "middle", 'letter-spacing=".5"'))
    o.append(f'<circle class="pulse" cx="{W - 80}" cy="25" r="2.6" fill="{LIME}"/>')

    defs = f"""<defs>
      <pattern id="bgrid" width="16" height="16" patternUnits="userSpaceOnUse">
        <path d="M16 0H0V16" fill="none" stroke="#ffffff" stroke-opacity="0.03"/></pattern>
      <linearGradient id="bglint" x1="0" x2="1">
        <stop offset="0" stop-color="{LIME}" stop-opacity="0"/><stop offset=".5" stop-color="{LIME}"/>
        <stop offset="1" stop-color="{LIME}" stop-opacity="0"/></linearGradient>
      <clipPath id="bav"><circle cx="{ax}" cy="{ay}" r="{ar}"/></clipPath>
      <clipPath id="bframe"><rect width="{W}" height="{H}" rx="12"/></clipPath>
    </defs>"""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
            f'role="img" aria-label="Hack The Box badge for {escape(d["name"])}">'
            f'<style>{css}</style>{defs}<g clip-path="url(#bframe)">{"".join(o)}</g>'
            f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="12" fill="none" stroke="{LINE}"/></svg>\n')


def main():
    """htb_card.py <htb_user_id> <out_dir> [fallback_base_url]

    Writes htb-badge.svg. If HTB can't be reached, copies the last published
    badge from fallback_base_url so nothing breaks.
    """
    uid, outdir = sys.argv[1], sys.argv[2].rstrip("/")
    fallback = sys.argv[3].rstrip("/") if len(sys.argv) > 3 else None
    files = {"htb-badge.svg": render_badge}
    try:
        data = collect(uid)
        out = {name: fn(data) for name, fn in files.items()}
    except Exception as e:  # keep the last good badge rather than publish nothing
        print(f"HTB fetch failed ({e}); keeping previous badge", file=sys.stderr)
        out = {}
        for name in files:
            try:
                out[name] = get_bytes(f"{fallback}/{name}")[0].decode() if fallback else None
            except Exception:
                out[name] = None
    for name, svg in out.items():
        if svg:
            with open(f"{outdir}/{name}", "w") as f:
                f.write(svg)
            print(f"wrote {outdir}/{name} ({len(svg) // 1024} KB)")


if __name__ == "__main__":
    main()
