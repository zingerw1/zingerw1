#!/usr/bin/env python3
"""Render an animated Hack The Box stats card as a self-contained SVG.

Uses HTB's public profile endpoints (no token needed) and only the Python
standard library, so it runs as-is on a GitHub Actions runner.

    python3 scripts/htb_card.py <htb_user_id> <out_dir> [fallback_base_url]

Writes htb-card.svg and htb-badge.svg. If HTB can't be reached, the previously
published images are kept so the profile never shows a broken image.
"""
import base64
import datetime as dt
import json
import sys
import urllib.request
from html import escape

API = "https://labs.hackthebox.com/api"
UA = {"User-Agent": "Mozilla/5.0 (htb-card; github profile)", "Accept": "application/json"}

# Palette: HTB navy and lime, plus the difficulty colours HTB uses.
BG = "#0E1520"
PANEL = "#141D2B"
LINE = "#223047"
LIME = "#9FEF00"
FG = "#E8EEF6"
DIM = "#7F8EA3"
MUTED = "#4A5A72"
DIFF = {"Easy": "#9FEF00", "Medium": "#FFAF00", "Hard": "#FF3E3E", "Insane": "#B37FFF"}

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
    labs = get(f"/v4/profile/progress/prolab/{uid}")["profile"]["prolabs"]
    forts = get(f"/v4/profile/progress/fortress/{uid}")["profile"]["fortresses"]
    act = get(f"/v5/user/profile/activity/{uid}").get("data", [])

    avatar = None
    try:
        raw, ctype = get_bytes(p["avatar"])
        avatar = f"data:{ctype.split(';')[0]};base64,{base64.b64encode(raw).decode()}"
    except Exception:
        pass

    last = next((a for a in act if a.get("type") == "root"), act[0] if act else None)

    return {
        "name": p["name"],
        "rank": p["rank"],
        "next_rank": p.get("next_rank"),
        "rank_ownership": float(p.get("rank_ownership") or 0),
        "rank_requirement": float(p.get("rank_requirement") or 0),
        "ranking": p.get("ranking"),
        "country": p.get("country_code") or "",
        "team": (p.get("team") or {}).get("name"),
        "avatar": avatar,
        "user_owns": p["user_owns"],
        "system_owns": p["system_owns"],
        "bloods": p["user_bloods"] + p["system_bloods"] + p["challenge_bloods"],
        "level": xp["level"],
        "level_title": xp["levelTitle"],
        "level_grade": xp.get("levelGrade") or "",
        "level_xp": xp["levelExperiencePoints"],
        "level_need": xp["levelExperiencePoints"] + xp["experienceUntilNextLevel"],
        "total_xp": xp["totalExperiencePoints"],
        "streak": (xp.get("streakData") or {}).get("counter", 0),
        "machines": (mac["machine_owns"]["solved"], mac["machine_owns"]["total"]),
        "difficulty": [(d["name"], d["owned_machines"]) for d in mac["machine_difficulties"]],
        "challenges": (chal["challenge_owns"]["solved"], chal["challenge_owns"]["total"]),
        "sherlocks": (sher["challenge_owns"]["solved"], sher["challenge_owns"]["total"]),
        "cleared_kinds": [("lab", l["name"]) for l in labs if l["completion_percentage"] >= 100 and not l["mini"]]
        + [("mini", l["name"]) for l in labs if l["completion_percentage"] >= 100 and l["mini"]]
        + [("fort", f["name"]) for f in forts if f["completion_percentage"] >= 100],
        "last": last and {"name": last["name"], "type": last["type"], "date": last["ownDate"][:10]},
    }


def t(x, y, s, size=12, fill=FG, family=MONO, weight=400, anchor="start", extra=""):
    return (f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}" {extra}>{escape(str(s))}</text>')


def bar(x, y, w, h, frac, color, delay, track=LINE):
    frac = max(0.0, min(1.0, frac))
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h / 2}" fill="{track}"/>'
            f'<rect class="grow" style="animation-delay:{delay:.2f}s" x="{x}" y="{y}" width="{max(w * frac, h):.1f}" '
            f'height="{h}" rx="{h / 2}" fill="{color}"/>')


def render(d):
    W, H = 860, 364
    out = []
    css = f"""
    .grow {{ transform-box: fill-box; transform-origin: left center; transform: scaleX(0);
             animation: grow 1.1s cubic-bezier(.2,.8,.2,1) forwards; }}
    @keyframes grow {{ to {{ transform: scaleX(1); }} }}
    .fade {{ opacity: 0; animation: fade .6s ease-out forwards; }}
    @keyframes fade {{ to {{ opacity: 1; }} }}
    .ring {{ transform-box: fill-box; transform-origin: center; animation: spin 14s linear infinite; }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    .pulse {{ animation: pulse 1.6s ease-in-out infinite; }}
    @keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: .25; }} }}
    .scan {{ animation: scan 7s linear infinite; }}
    @keyframes scan {{ 0% {{ transform: translateY(-80px); }} 100% {{ transform: translateY({H + 80}px); }} }}
    """

    # Frame, grid and scanline
    out.append(f'<rect width="{W}" height="{H}" rx="14" fill="{BG}"/>')
    out.append(f'<rect width="{W}" height="{H}" rx="14" fill="url(#grid)"/>')
    out.append(f'<rect class="scan" x="0" y="0" width="{W}" height="80" fill="url(#scan)"/>')
    out.append(f'<rect x="0" y="0" width="{W}" height="3" fill="url(#topline)"/>')

    # Avatar with rotating ring
    ax, ay, ar = 64, 72, 36
    if d["avatar"]:
        out.append(f'<image href="{d["avatar"]}" x="{ax - ar}" y="{ay - ar}" width="{ar * 2}" height="{ar * 2}" '
                   f'clip-path="url(#av)" preserveAspectRatio="xMidYMid slice"/>')
    else:
        out.append(f'<circle cx="{ax}" cy="{ay}" r="{ar}" fill="{PANEL}"/>')
        out.append(t(ax, ay + 8, d["name"][:1].upper(), 26, LIME, SANS, 700, "middle"))
    out.append(f'<circle class="ring" cx="{ax}" cy="{ay}" r="{ar + 6}" fill="none" stroke="{LIME}" '
               f'stroke-width="1.5" stroke-dasharray="3 7" stroke-linecap="round"/>')

    # Identity
    out.append(t(122, 62, d["name"], 26, FG, SANS, 700))
    sub = [d["rank"]]
    if d["ranking"]:
        sub.append(f"Global #{d['ranking']}")
    if d["country"]:
        sub.append(d["country"])
    out.append(t(123, 86, "  ·  ".join(sub), 12.5, DIM))
    if d["next_rank"] and d["rank_requirement"]:
        out.append(bar(123, 101, 150, 4, d["rank_ownership"] / d["rank_requirement"], "#9FEF00AA", 0.3))
        out.append(t(283, 106, f"{d['rank_ownership']:.0f}/{d['rank_requirement']:.0f}% to {d['next_rank']}", 10.5, MUTED))
    if d["team"]:
        out.append(t(123, 126, f"team {d['team']}", 11, MUTED))

    # Level block (right)
    rx = W - 32
    out.append(t(rx, 40, "LEVEL", 10.5, DIM, MONO, 600, "end", 'letter-spacing="2"'))
    out.append(t(rx, 82, d["level"], 44, LIME, SANS, 800, "end"))
    roman = {"1": "I", "2": "II", "3": "III"}
    grade = f" {roman.get(str(d['level_grade']), d['level_grade'])}" if d["level_grade"] else ""
    lvl_w = 250
    out.append(t(rx - 92, 66, f"{d['level_title'].upper()}{grade}", 13, FG, MONO, 700, "end", 'letter-spacing="1.5"'))
    out.append(t(rx - 92, 84, f"{d['total_xp']:,} XP total", 11, DIM, MONO, 400, "end"))
    out.append(bar(rx - lvl_w, 98, lvl_w, 6, d["level_xp"] / max(d["level_need"], 1), LIME, 0.2))
    out.append(t(rx - lvl_w, 120, f"{d['level_xp']:,} / {d['level_need']:,} xp", 10.5, DIM))
    out.append(t(rx, 120, f"lvl {d['level'] + 1}", 10.5, MUTED, MONO, 400, "end"))

    # Divider
    out.append(f'<rect x="28" y="146" width="{W - 56}" height="1" fill="{LINE}"/>')

    # Stat tiles
    tiles = [
        ("MACHINES", f"{d['machines'][0]}", f"/{d['machines'][1]}", d["machines"][0] / max(d["machines"][1], 1)),
        ("CHALLENGES", f"{d['challenges'][0]}", f"/{d['challenges'][1]}", d["challenges"][0] / max(d["challenges"][1], 1)),
        ("SHERLOCKS", f"{d['sherlocks'][0]}", f"/{d['sherlocks'][1]}", d["sherlocks"][0] / max(d["sherlocks"][1], 1)),
        ("USER · ROOT", f"{d['user_owns']}", f" · {d['system_owns']}", None),
        ("WEEK STREAK", f"{d['streak']}", " wks", None),
    ]
    tw = (W - 56 - 4 * 12) / 5
    for i, (label, big, small, frac) in enumerate(tiles):
        x = 28 + i * (tw + 12)
        y = 164
        out.append(f'<g class="fade" style="animation-delay:{0.15 + i * 0.08:.2f}s">')
        out.append(f'<rect x="{x:.1f}" y="{y}" width="{tw:.1f}" height="74" rx="9" fill="{PANEL}" stroke="{LINE}"/>')
        out.append(t(x + 14, y + 22, label, 10, DIM, MONO, 600, "start", 'letter-spacing="1.2"'))
        out.append(f'<text x="{x + 14:.1f}" y="{y + 52}" font-family="{SANS}" font-weight="800" font-size="24" fill="{FG}">'
                   f'{escape(big)}<tspan font-family="{MONO}" font-size="12" font-weight="400" fill="{MUTED}">{escape(small)}</tspan></text>')
        if frac is not None:
            out.append(bar(x + 14, y + 61, tw - 28, 3, frac, LIME, 0.4 + i * 0.08))
        out.append("</g>")

    # Machine difficulty split
    by = 274
    out.append(t(28, by, "MACHINES BY DIFFICULTY", 10, DIM, MONO, 600, "start", 'letter-spacing="1.2"'))
    total = sum(n for _, n in d["difficulty"]) or 1
    seg_w = 330
    x = 28
    for i, (name, n) in enumerate(d["difficulty"]):
        w = seg_w * n / total
        if w <= 0:
            continue
        out.append(f'<rect class="grow" style="animation-delay:{0.6 + i * 0.12:.2f}s" x="{x:.1f}" y="{by + 12}" '
                   f'width="{max(w - 3, 2):.1f}" height="8" rx="2" fill="{DIFF.get(name, LIME)}"/>')
        x += w
    lx = 28
    for name, n in d["difficulty"]:
        out.append(f'<circle cx="{lx + 4}" cy="{by + 38}" r="3.5" fill="{DIFF.get(name, LIME)}"/>')
        label = f"{name} {n}"
        out.append(t(lx + 12, by + 42, label, 11, DIM))
        lx += 12 + len(label) * 6.9 + 16

    # Cleared labs as chips
    cx0 = 400
    out.append(t(cx0, by, "CLEARED", 10, DIM, MONO, 600, "start", 'letter-spacing="1.2"'))
    cx, cy = cx0, by + 10
    for i, (kind, name) in enumerate(d["cleared_kinds"]):
        label = name.upper()
        w = len(label) * 6.9 + 22
        if cx + w > W - 28:
            cx, cy = cx0, cy + 26
            if cy > by + 40:
                break
        stroke = LIME if kind == "lab" else MUTED
        fill = "#9FEF0014" if kind == "lab" else PANEL
        out.append(f'<g class="fade" style="animation-delay:{0.7 + i * 0.06:.2f}s">'
                   f'<rect x="{cx:.1f}" y="{cy}" width="{w:.1f}" height="20" rx="10" fill="{fill}" stroke="{stroke}"/>'
                   f'{t(cx + w / 2, cy + 14, label, 10.5, LIME if kind == "lab" else FG, MONO, 600, "middle")}</g>')
        cx += w + 6

    # Footer
    fy = H - 16
    out.append(f'<circle class="pulse" cx="34" cy="{fy - 4}" r="3.5" fill="{LIME}"/>')
    if d["last"]:
        when = dt.date.fromisoformat(d["last"]["date"]).strftime("%b %d")
        out.append(t(46, fy, f"last pwn  {d['last']['name']} ({d['last']['type']})  ·  {when}", 10.5, DIM))
    out.append(t(W - 28, fy, f"hackthebox  ·  updated {dt.date.today().strftime('%b %d %Y')}", 10.5, MUTED, MONO, 400, "end"))

    defs = f"""
    <defs>
      <pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse">
        <path d="M24 0H0V24" fill="none" stroke="#ffffff" stroke-opacity="0.025"/>
      </pattern>
      <linearGradient id="scan" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="{LIME}" stop-opacity="0"/>
        <stop offset=".5" stop-color="{LIME}" stop-opacity="0.045"/>
        <stop offset="1" stop-color="{LIME}" stop-opacity="0"/>
      </linearGradient>
      <linearGradient id="topline" x1="0" x2="1">
        <stop offset="0" stop-color="{LIME}" stop-opacity="0"/>
        <stop offset=".5" stop-color="{LIME}" stop-opacity=".9"/>
        <stop offset="1" stop-color="{LIME}" stop-opacity="0"/>
      </linearGradient>
      <clipPath id="av"><circle cx="{ax}" cy="{ay}" r="{ar}"/></clipPath>
      <clipPath id="frame"><rect width="{W}" height="{H}" rx="14"/></clipPath>
    </defs>"""

    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
            f'role="img" aria-label="Hack The Box stats for {escape(d["name"])}">'
            f'<style>{css}</style>{defs}<g clip-path="url(#frame)">{"".join(out)}</g>'
            f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="14" fill="none" stroke="{LINE}"/></svg>\n')


def render_badge(d):
    """Compact badge: avatar, name, rank, level and a thin XP bar."""
    W, H = 420, 84
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
    parts = [(f"#{d['ranking']}", FG), (" · ", MUTED), (f"{d['machines'][0]}", FG),
             (" machines", DIM), (" · ", MUTED), (f"{d['sherlocks'][0]}", FG), (" sherlocks", DIM)]
    spans = "".join(f'<tspan fill="{c}">{escape(s)}</tspan>' for s, c in parts)
    o.append(f'<text x="82" y="55" font-family="{MONO}" font-size="10.5" xml:space="preserve">{spans}</text>')

    # XP bar to next level
    bx, bw = 82, 196
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

    Writes htb-card.svg and htb-badge.svg. If HTB can't be reached, copies the
    last published versions from fallback_base_url so nothing breaks.
    """
    uid, outdir = sys.argv[1], sys.argv[2].rstrip("/")
    fallback = sys.argv[3].rstrip("/") if len(sys.argv) > 3 else None
    files = {"htb-card.svg": render, "htb-badge.svg": render_badge}
    try:
        data = collect(uid)
        out = {name: fn(data) for name, fn in files.items()}
    except Exception as e:  # keep the last good images rather than publish nothing
        print(f"HTB fetch failed ({e}); keeping previous images", file=sys.stderr)
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
