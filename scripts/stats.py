"""Builds assets/stats.svg: a self-hosted GitHub stats card in the profile's own style.

No third-party services and no dependencies (stdlib only).
- Contributions: GraphQL (when GITHUB_TOKEN is set, e.g. in GitHub Actions) or the public
  contributions calendar as a fallback.
- Languages: public, non-fork repositories via the REST API.

Usage: python scripts/stats.py <github-username> <output.svg>
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.request
from xml.sax.saxutils import escape

USER = sys.argv[1]
OUT = sys.argv[2]
TOKEN = os.environ.get("GITHUB_TOKEN", "")
# Repos left out of the language chart (e.g. course notes with vendored C/C++ libraries)
EXCLUDE = {x.strip() for x in os.environ.get("STATS_EXCLUDE", "Arduino").split(",") if x.strip()}
UA = {"User-Agent": "profile-stats-script"}


def get(url, accept="application/vnd.github+json"):
    h = dict(UA, Accept=accept)
    if TOKEN and "api.github.com" in url:
        h["Authorization"] = f"Bearer {TOKEN}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
        return r.read().decode("utf-8")


def calendar():
    """Returns list of (date, count) for the last year."""
    if TOKEN:
        q = {"query": "query($l:String!){user(login:$l){contributionsCollection{contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}",
             "variables": {"l": USER}}
        req = urllib.request.Request("https://api.github.com/graphql", data=json.dumps(q).encode(),
                                     headers=dict(UA, Authorization=f"Bearer {TOKEN}", **{"Content-Type": "application/json"}))
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
        weeks = d["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
        return [(x["date"], x["contributionCount"]) for w in weeks for x in w["contributionDays"]]
    h = get(f"https://github.com/users/{USER}/contributions", accept="text/html")
    ids = dict((i, d) for d, i in re.findall(r'data-date="(\d{4}-\d\d-\d\d)"[^>]*id="(contribution-day-component-[\d-]+)"', h))
    days = []
    for i, tip in re.findall(r'<tool-tip[^>]*for="(contribution-day-component-[\d-]+)"[^>]*>([^<]+)</tool-tip>', h):
        m = re.match(r"(\d+) contribution", tip.strip())
        if i in ids:
            days.append((ids[i], int(m.group(1)) if m else 0))
    return sorted(days)


def languages():
    repos = json.loads(get(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner"))
    total = {}
    for r in repos:
        if r.get("fork") or r["name"] == USER or r["name"] in EXCLUDE:
            continue
        for lang, n in json.loads(get(r["languages_url"])).items():
            total[lang] = total.get(lang, 0) + n
    s = sum(total.values()) or 1
    top = sorted(total.items(), key=lambda kv: -kv[1])[:5]
    return [(k, v / s) for k, v in top], len([r for r in repos if not r.get("fork")])


def streaks(days):
    longest = cur = 0
    for _, c in days:
        cur = cur + 1 if c > 0 else 0
        longest = max(longest, cur)
    return longest


days = calendar()
total = sum(c for _, c in days)
active = sum(1 for _, c in days if c > 0)
longest = streaks(days)
weeks = [sum(c for _, c in days[i:i + 7]) for i in range(0, len(days), 7)][-52:]
langs, nrepos = languages()

W, H = 1000, 236
FONT = "'Segoe UI', Inter, 'Helvetica Neue', Arial, sans-serif"
MONO = "'JetBrains Mono', 'Cascadia Code', Consolas, 'SFMono-Regular', Menlo, monospace"
STYLE = """<style>
.bg{fill:#0b1220}.line{stroke:#24324d}.fg{fill:#e6edf7}.mut{fill:#93a4bf}.dim{fill:#5b6b86}
.or{fill:#ff8a3d}.sk{fill:#4cc3ff}.gr{fill:#3ddc97}.track{fill:#1b2740}
@media (prefers-color-scheme: light){.bg{fill:#f7f9fc}.line{stroke:#d5deeb}.fg{fill:#0f1a2c}.mut{fill:#4a5b77}.dim{fill:#8a9ab3}
.or{fill:#e8650f}.sk{fill:#0b84c6}.gr{fill:#14a06b}.track{fill:#dde5f0}}
text{font-family:%s}.mono{font-family:%s}</style>""" % (FONT, MONO)

b = [f'<rect class="bg" width="{W}" height="{H}" rx="18"/>',
     f'<rect class="line" fill="none" x=".5" y=".5" width="{W-1}" height="{H-1}" rx="18"/>']
# left: numbers
b.append('<text class="dim mono" x="32" y="40" font-size="12">// last 12 months</text>')
b.append(f'<text class="fg" x="30" y="104" font-size="54" font-weight="800">{total:,}</text>')
b.append('<text class="mut" x="32" y="130" font-size="15">contributions</text>')
stats = [(str(active), "active days", "sk"), (f"{longest}d", "longest streak", "or"), (str(nrepos), "public repos", "gr")]
for i, (v, lab, c) in enumerate(stats):
    y = 166 + i * 0  # single row
    x = 32 + i * 96
    b.append(f'<text class="{c}" x="{x}" y="176" font-size="22" font-weight="700">{escape(v)}</text>')
    b.append(f'<text class="dim" x="{x}" y="196" font-size="12">{escape(lab)}</text>')
# middle: weekly bars
mx, my, mw, mh = 340, 52, 380, 130
b.append(f'<text class="dim mono" x="{mx}" y="40" font-size="12">// weekly activity</text>')
peak = max(weeks) if weeks and max(weeks) > 0 else 1
bw = mw / max(len(weeks), 1)
for i, v in enumerate(weeks):
    hh = max(2.0, v / peak * mh)
    cls = "or" if i >= len(weeks) - 4 else "sk"
    b.append(f'<rect class="{cls if v else "track"}" x="{mx + i*bw:.1f}" y="{my + mh - hh:.1f}" width="{bw-2:.1f}" height="{hh:.1f}" rx="1.5"/>')
b.append(f'<text class="dim mono" x="{mx}" y="{my+mh+22}" font-size="11">12 months ago</text>')
b.append(f'<text class="dim mono" x="{mx+mw}" y="{my+mh+22}" font-size="11" text-anchor="end">this week</text>')
# right: languages
lx, lw = 760, 208
b.append(f'<text class="dim mono" x="{lx}" y="40" font-size="12">// public code by language</text>')
colors = ["sk", "or", "gr", "sk", "or"]
for i, (lang, frac) in enumerate(langs):
    y = 66 + i * 32
    b.append(f'<text class="fg" x="{lx}" y="{y}" font-size="13" font-weight="600">{escape(lang)}</text>')
    b.append(f'<text class="mut mono" x="{lx+lw}" y="{y}" font-size="12" text-anchor="end">{frac*100:.0f}%</text>')
    b.append(f'<rect class="track" x="{lx}" y="{y+7}" width="{lw}" height="6" rx="3"/>')
    b.append(f'<rect class="{colors[i]}" x="{lx}" y="{y+7}" width="{max(4, lw*frac):.1f}" height="6" rx="3"/>')
b.append(f'<text class="dim mono" x="{W-24}" y="{H-14}" font-size="10" text-anchor="end">updated {dt.date.today().isoformat()}</text>')

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
       f'aria-label="{total} contributions in the last year"><title>GitHub activity</title>{STYLE}{"".join(b)}</svg>')
os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(svg)
print(f"total={total} active={active} longest={longest} repos={nrepos} langs={[(k, round(v*100)) for k, v in langs]}")
