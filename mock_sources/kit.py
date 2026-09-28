"""Design kit shared by every bundled demo website.

Each demo site has its own brand (name, logo, colours, navigation) but reuses one component library,
so the pages look like real consumer travel sites. Photos are replaced by generated SVG illustrations
(beaches, mountains, cities, forts, backwaters, islands, hotels) so the sites work fully offline.
"""
import hashlib
import random
from html import escape

from fastapi import Request
from fastapi.responses import HTMLResponse

# --------------------------------------------------------------------------- brands
BRANDS = {
    "skyroam": {"name": "SkyRoam", "suffix": "Travel", "brand": "#0b6e75", "brand2": "#064a50", "accent": "#ff7a1a",
                "tint": "#e6f4f3", "logo": "plane", "home": "/mock/travel",
                "nav": [("Flights", "/mock/travel"), ("Hotels", "/mock/travel/hotels?city=goa"),
                        ("Holidays", "/mock/offers/skyroam"), ("My trips", "/mock/travel/bookings")],
                "tagline": "Flights, stays and holidays at honest prices"},
    "tripnova": {"name": "TripNova", "suffix": "Holidays", "brand": "#5b3cc4", "brand2": "#3d2791", "accent": "#ff4f79",
                 "tint": "#efeafd", "logo": "star", "home": "/mock/offers/tripnova",
                 "nav": [("Holiday deals", "/mock/offers/tripnova"), ("Honeymoons", "/mock/offers/tripnova"),
                         ("Weekend trips", "/mock/offers/tripnova"), ("Contact", "/mock/offers/tripnova")],
                 "tagline": "Handpicked holidays since 2011"},
    "staybay": {"name": "StayBay", "suffix": "Hotels", "brand": "#1d4ed8", "brand2": "#1e3a8a", "accent": "#f59e0b",
                "tint": "#e8efff", "logo": "bed", "home": "/mock/hotels/goa",
                "nav": [("Goa", "/mock/hotels/goa"), ("Jaipur", "/mock/hotels/jaipur"), ("Dubai", "/mock/hotels/dubai")],
                "tagline": "Best rate guarantee on 40,000+ hotels"},
    "partnerhub": {"name": "PartnerHub", "suffix": "Supplier portal", "brand": "#0f766e", "brand2": "#134e4a", "accent": "#0ea5e9",
                   "tint": "#e7f5f3", "logo": "hub", "home": "/mock/partners",
                   "nav": [("Updates", "/mock/partners"), ("Rate plans", "/mock/partners"), ("Support", "/mock/partners")],
                   "tagline": "Notices from our hotel and airline partners"},
    "wanderlytics": {"name": "Wanderlytics", "suffix": "Insights", "brand": "#0f172a", "brand2": "#020617", "accent": "#22c55e",
                     "tint": "#eef2f7", "logo": "chart", "home": "/mock/trends",
                     "nav": [("Demand", "/mock/trends"), ("Events", "/mock/trends"), ("Methodology", "/mock/trends")],
                     "tagline": "Destination demand, updated daily"},
    "indirail": {"name": "IndiRail", "suffix": "Express", "brand": "#b42318", "brand2": "#7a1a12", "accent": "#fbbf24",
                 "tint": "#fdecea", "logo": "train", "home": "/mock/rail",
                 "nav": [("Book tickets", "/mock/rail"), ("PNR status", "/mock/rail"), ("Train schedule", "/mock/rail")],
                 "tagline": "Seat availability across 3,000+ trains"},
    "explorely": {"name": "Explorely", "suffix": "Experiences", "brand": "#c2410c", "brand2": "#7c2d12", "accent": "#16a34a",
                  "tint": "#fff1e8", "logo": "compass", "home": "/mock/activities/goa",
                  "nav": [("Goa", "/mock/activities/goa"), ("Jaipur", "/mock/activities/jaipur"), ("Dubai", "/mock/activities/dubai")],
                  "tagline": "Tours, tickets and things to do"},
    "stayverdict": {"name": "StayVerdict", "suffix": "Reviews", "brand": "#047857", "brand2": "#064e3b", "accent": "#f59e0b",
                    "tint": "#e7f6ef", "logo": "owl", "home": "/mock/reviews/sea-breeze-resort",
                    "nav": [("Hotels", "/mock/reviews/sea-breeze-resort"), ("Write a review", "/mock/reviews/sea-breeze-resort")],
                    "tagline": "Honest reviews from real travellers"},
    "travelsafe": {"name": "TravelSafe", "suffix": "Advisories", "brand": "#1f2937", "brand2": "#111827", "accent": "#dc2626",
                   "tint": "#f1f3f5", "logo": "shield", "home": "/mock/advisories",
                   "nav": [("Advisories", "/mock/advisories"), ("Visa rules", "/mock/advisories"), ("Emergency contacts", "/mock/advisories")],
                   "tagline": "Official-style travel advisories (demo data)"},
}

LOGOS = {
    "plane": '<path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5z" fill="currentColor"/>',
    "star": '<path d="M12 2l2.9 6.6L22 9.3l-5.4 4.8L18.2 21 12 17.3 5.8 21l1.6-6.9L2 9.3l7.1-.7z" fill="currentColor"/>',
    "bed": '<path d="M3 7v11h2v-2h14v2h2v-6a4 4 0 0 0-4-4h-7v6H5V7zm4 6a2 2 0 1 0 0-4 2 2 0 0 0 0 4z" fill="currentColor"/>',
    "hub": '<circle cx="12" cy="12" r="3" fill="currentColor"/><circle cx="4" cy="6" r="2" fill="currentColor"/><circle cx="20" cy="6" r="2" fill="currentColor"/><circle cx="12" cy="21" r="2" fill="currentColor"/><path d="M5.5 7l4.5 3.5M18.5 7L14 10.5M12 15v4" stroke="currentColor" stroke-width="2"/>',
    "chart": '<path d="M4 20V10h3v10zm6 0V4h3v16zm6 0v-7h3v7z" fill="currentColor"/>',
    "train": '<path d="M6 3h12a3 3 0 0 1 3 3v9a3 3 0 0 1-3 3l2 3h-2.5l-2-3h-7l-2 3H4l2-3a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3zm0 3v5h12V6zm1.5 8a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3zm9 0a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3z" fill="currentColor"/>',
    "compass": '<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2" fill="none"/><path d="M15.5 8.5l-2 5-5 2 2-5z" fill="currentColor"/>',
    "owl": '<circle cx="8" cy="11" r="3.2" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="16" cy="11" r="3.2" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="8" cy="11" r="1.2" fill="currentColor"/><circle cx="16" cy="11" r="1.2" fill="currentColor"/><path d="M4 6l3 2M20 6l-3 2M11 16l1 1.5 1-1.5" stroke="currentColor" stroke-width="2" fill="none"/>',
    "shield": '<path d="M12 2l8 3v6c0 5-3.4 9.3-8 11-4.6-1.7-8-6-8-11V5z" fill="currentColor"/><path d="M11 7h2v6h-2zm0 8h2v2h-2z" fill="#fff"/>',
}

# --------------------------------------------------------------------------- base CSS
BASE_CSS = """
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;font:15px/1.5 "Segoe UI",system-ui,-apple-system,Roboto,"Helvetica Neue",Arial,sans-serif;color:#18212b;background:#f5f7fa}
a{color:var(--brand)}img,svg{max-width:100%}
.topbar{background:var(--brand2);color:#fff;font-size:12.5px}
.topbar .in{max-width:1180px;margin:0 auto;padding:6px 24px;display:flex;justify-content:space-between;opacity:.9}
header.site{background:#fff;border-bottom:1px solid #e6e9ee;position:sticky;top:0;z-index:20}
header.site .in{max-width:1180px;margin:0 auto;padding:12px 24px;display:flex;align-items:center;gap:28px}
.logo{display:flex;align-items:center;gap:9px;text-decoration:none;color:#18212b}
.logo .mark{width:36px;height:36px;border-radius:10px;background:var(--brand);color:#fff;display:grid;place-items:center}
.logo .mark svg{width:22px;height:22px}
.logo b{font-size:21px;letter-spacing:-.3px}.logo span{color:var(--brand);font-weight:600;font-size:15px}
header.site nav{display:flex;gap:4px;flex:1}
header.site nav a{padding:8px 13px;border-radius:8px;color:#394452;text-decoration:none;font-weight:600;font-size:14.5px}
header.site nav a:hover,header.site nav a.on{background:var(--tint);color:var(--brand)}
.hdr-actions{display:flex;gap:10px;align-items:center;font-size:14px;color:#56606c}
.hdr-actions .pill{border:1px solid #d6dbe2;border-radius:20px;padding:6px 14px;font-weight:600;color:#18212b;text-decoration:none}
.container{max-width:1180px;margin:0 auto;padding:24px}
.hero{position:relative;color:#fff;background:linear-gradient(120deg,var(--brand2),var(--brand));overflow:hidden}
.hero .in{max-width:1180px;margin:0 auto;padding:44px 24px 110px;position:relative;z-index:1}
.hero h1{font-size:40px;line-height:1.1;margin:0 0 10px;letter-spacing:-.8px;max-width:18ch}
.hero p.lead{font-size:18px;opacity:.92;margin:0;max-width:52ch}
.hero .art{position:absolute;inset:0;opacity:.35;display:flex}
.hero .art svg{flex:1;min-width:0;height:100%}
.searchbox{background:#fff;color:#18212b;border-radius:16px;box-shadow:0 14px 40px rgba(15,23,42,.18);padding:20px;margin:-86px auto 0;max-width:1132px;position:relative;z-index:2}
.tabs{display:flex;gap:6px;margin-bottom:14px}
.tabs a{padding:9px 16px;border-radius:10px;text-decoration:none;color:#394452;font-weight:700;font-size:14px;background:#f1f4f8}
.tabs a.on{background:var(--brand);color:#fff}
.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;align-items:end}
.field label{display:block;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#6b7684;margin-bottom:5px}
.field input,.field select{width:100%;padding:12px 13px;border:1.5px solid #d6dbe2;border-radius:10px;font:inherit;font-size:16px;font-weight:600;background:#fff;color:#18212b}
.field input:focus,.field select:focus{outline:none;border-color:var(--brand);box-shadow:0 0 0 3px var(--tint)}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;background:var(--accent);color:#fff;border:0;border-radius:10px;padding:13px 22px;font:inherit;font-weight:800;font-size:15px;cursor:pointer;text-decoration:none;white-space:nowrap}
.btn:hover{filter:brightness(1.06)}.btn.brand{background:var(--brand)}.btn.ghost{background:#fff;color:var(--brand);border:1.5px solid var(--brand)}
.btn.lg{padding:15px 30px;font-size:17px}.btn.sm{padding:8px 14px;font-size:13.5px}
.section-title{display:flex;justify-content:space-between;align-items:end;margin:34px 0 14px}
.section-title h2{font-size:24px;margin:0;letter-spacing:-.3px}.section-title a{font-weight:700;text-decoration:none}
.grid{display:grid;gap:18px}.g3{grid-template-columns:repeat(auto-fill,minmax(270px,1fr))}.g4{grid-template-columns:repeat(auto-fill,minmax(220px,1fr))}
.card{background:#fff;border-radius:14px;box-shadow:0 1px 2px rgba(15,23,42,.06),0 4px 14px rgba(15,23,42,.05);overflow:hidden;border:1px solid #edf0f4}
.card .img{aspect-ratio:16/10;position:relative;overflow:hidden;background:var(--tint)}
.card .img svg{width:100%;height:100%;display:block}
.card .body{padding:14px 16px 16px}
.badge{display:inline-block;background:var(--accent);color:#fff;font-weight:800;font-size:12px;padding:4px 9px;border-radius:6px}
.badge.soft{background:var(--tint);color:var(--brand)}.badge.green{background:#dcfce7;color:#166534}.badge.red{background:#fee2e2;color:#991b1b}.badge.amber{background:#fef3c7;color:#92400e}
.img .badge{position:absolute;top:12px;left:12px}
.muted{color:#6b7684;font-size:13.5px}.small{font-size:13px}
.price{font-size:22px;font-weight:800;letter-spacing:-.3px}
.was{color:#8a94a1;text-decoration:line-through;font-size:13.5px;margin-right:6px}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.between{justify-content:space-between}
.stars{color:#f59e0b;letter-spacing:1px}
.chip{display:inline-flex;align-items:center;gap:5px;border:1px solid #d6dbe2;border-radius:20px;padding:6px 12px;font-size:13.5px;font-weight:600;background:#fff}
.layout{display:grid;grid-template-columns:260px 1fr;gap:22px;align-items:start}
.sidebar{background:#fff;border-radius:14px;border:1px solid #edf0f4;padding:16px;position:sticky;top:80px}
.sidebar h4{margin:0 0 10px;font-size:14px;text-transform:uppercase;letter-spacing:.5px;color:#6b7684}
.sidebar label{display:flex;gap:9px;align-items:center;padding:6px 0;font-weight:600;font-size:14.5px;cursor:pointer}
.sidebar input[type=checkbox]{width:18px;height:18px;accent-color:var(--brand)}
.sidebar hr{border:0;border-top:1px solid #edf0f4;margin:12px 0}
.toolbar{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap}
.toolbar select{padding:9px 12px;border:1.5px solid #d6dbe2;border-radius:10px;font:inherit;font-weight:600;background:#fff}
.pagination{display:flex;gap:6px;justify-content:center;margin:26px 0}
.pagination a,.pagination span{min-width:40px;text-align:center;padding:9px 13px;border-radius:10px;background:#fff;border:1px solid #d6dbe2;text-decoration:none;color:#18212b;font-weight:700}
.pagination .current{background:var(--brand);border-color:var(--brand);color:#fff}
.pagination .next{padding:9px 16px}
footer.site{background:#0f172a;color:#cbd5e1;margin-top:50px}
footer.site .in{max-width:1180px;margin:0 auto;padding:36px 24px;display:grid;grid-template-columns:1.4fr repeat(3,1fr);gap:24px;font-size:14px}
footer.site h5{color:#fff;margin:0 0 10px;font-size:14px}footer.site a{color:#cbd5e1;text-decoration:none;display:block;padding:3px 0}
footer.site .legal{border-top:1px solid #1e293b;text-align:center;padding:14px;font-size:12.5px;color:#94a3b8}
.cookie-banner{position:fixed;left:20px;right:20px;bottom:20px;max-width:760px;margin:0 auto;background:#fff;color:#18212b;border-radius:14px;box-shadow:0 20px 50px rgba(15,23,42,.3);padding:16px 18px;display:flex;gap:16px;align-items:center;z-index:100;border:1px solid #e6e9ee}
.cookie-banner p{margin:0;font-size:14px;flex:1}
#cookie-overlay{position:fixed;inset:0;background:rgba(15,23,42,.5);z-index:99;display:flex;align-items:flex-end;justify-content:center}
#cookie-overlay .cookie-banner{position:relative;left:auto;right:auto;bottom:24px}
.ribbon{background:var(--tint);color:var(--brand2);font-weight:700;text-align:center;padding:9px;font-size:14px}
.steps-bar{display:flex;gap:8px;margin-bottom:18px;font-size:13.5px;font-weight:700;color:#8a94a1}
.steps-bar span{padding:6px 12px;border-radius:20px;background:#eef1f5}.steps-bar span.on{background:var(--brand);color:#fff}
table.tbl{width:100%;border-collapse:collapse;background:#fff}
table.tbl th{text-align:left;font-size:12.5px;text-transform:uppercase;letter-spacing:.5px;color:#6b7684;padding:12px 14px;border-bottom:1px solid #edf0f4}
table.tbl td{padding:13px 14px;border-bottom:1px solid #f1f4f8}
@media(max-width:860px){.layout{grid-template-columns:1fr}.sidebar{position:static}header.site nav{display:none}
 footer.site .in{grid-template-columns:1fr 1fr}.hero h1{font-size:30px}}
"""


def _logo_svg(kind):
    return f'<svg viewBox="0 0 24 24" aria-hidden="true">{LOGOS[kind]}</svg>'


def shell(request: Request, site: str, title: str, body: str, *, attrs: str = "", active: str | None = None,
          consent: str = "banner", ribbon: str | None = None) -> HTMLResponse:
    """Render a full page in a brand's chrome. consent: 'banner' (non-blocking), 'overlay' (blocks clicks), 'none'."""
    b = BRANDS[site]
    cookie_name = f"consent_{site}"
    accepted = request.cookies.get(cookie_name) == "1"
    js_accept = (f"document.cookie='{cookie_name}=1;path=/';"
                 "var o=document.getElementById('cookie-overlay')||document.getElementById('cookie-banner');if(o)o.remove();")
    banner = (f'<div class="cookie-banner" id="cookie-banner" role="dialog" aria-label="Cookie consent"><p><b>We value your privacy.</b> '
              f'{b["name"]} uses cookies to personalise offers and measure traffic.</p>'
              f'<button class="btn sm ghost" type="button" onclick="{js_accept}">Manage</button>'
              f'<button id="accept-cookies" class="btn sm brand" type="button" onclick="{js_accept}">Accept all</button></div>')
    cookie = "" if accepted or consent == "none" else (f'<div id="cookie-overlay">{banner}</div>' if consent == "overlay" else banner)
    nav = "".join(f'<a href="{h}" class="{"on" if l == active else ""}">{l}</a>' for l, h in b["nav"])
    css_vars = f":root{{--brand:{b['brand']};--brand2:{b['brand2']};--accent:{b['accent']};--tint:{b['tint']}}}"
    footer_cols = [("Company", ["About us", "Careers", "Press", "Investor relations"]),
                   ("Support", ["Help centre", "Cancellations", "Refund status", "Contact us"]),
                   ("Explore", ["Top destinations", "Travel guides", "Gift cards", "Offers"])]
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} | {b['name']} {b['suffix']}</title><style>{css_vars}{BASE_CSS}</style></head>
<body {attrs}><div class="topbar"><div class="in"><span>{b['tagline']}</span><span>24×7 support · 1800-000-000 (demo)</span></div></div>
<header class="site"><div class="in"><a class="logo" href="{b['home']}"><span class="mark">{_logo_svg(b['logo'])}</span><b>{b['name']}</b><span>{b['suffix']}</span></a>
<nav>{nav}</nav><div class="hdr-actions"><span>₹ INR</span><a class="pill" href="{b['home']}">Log in</a></div></div></header>
{f'<div class="ribbon">{ribbon}</div>' if ribbon else ''}
{body}
<footer class="site"><div class="in"><div><a class="logo" href="{b['home']}" style="color:#fff"><span class="mark">{_logo_svg(b['logo'])}</span><b>{b['name']}</b></a>
<p style="margin-top:12px">{b['tagline']}.</p></div>{''.join(f"<div><h5>{h}</h5>{''.join(f'<a href=#>{x}</a>' for x in items)}</div>" for h, items in footer_cols)}</div>
<div class="legal">© 2026 {b['name']} {b['suffix']} · Fictional demo website bundled with the Web Ops Agent. No real bookings, payments or personal data.</div></footer>
{cookie}</body></html>""")


# --------------------------------------------------------------------------- illustrations
SCENE_FOR = {"goa": "beach", "kochi": "backwaters", "kerala": "backwaters", "dubai": "desert", "manali": "snow",
             "bali": "island", "jaipur": "heritage", "port blair": "island", "andaman": "island", "leh": "mountains",
             "ladakh": "mountains", "mumbai": "city", "delhi": "heritage", "udaipur": "heritage", "munnar": "forest",
             "shimla": "snow", "singapore": "city", "maldives": "island", "agra": "heritage", "rishikesh": "forest",
             "pune": "city", "bengaluru": "city", "chennai": "beach", "kolkata": "city", "varanasi": "heritage"}


def scene_for(place: str) -> str:
    p = (place or "").lower()
    for k, v in SCENE_FOR.items():
        if k in p:
            return v
    return "city"


def scene(kind: str, seed: str = "", label: str | None = None) -> str:
    """Return an inline SVG illustration (viewBox 400x250)."""
    r = random.Random(f"{kind}|{seed}")
    uid = hashlib.md5(f"{kind}{seed}{r.random()}".encode()).hexdigest()[:8]
    sky = {"beach": ("#7dd3fc", "#fde68a"), "island": ("#38bdf8", "#bae6fd"), "mountains": ("#60a5fa", "#e0f2fe"),
           "snow": ("#93c5fd", "#f1f5f9"), "desert": ("#fb923c", "#fde68a"), "city": ("#312e81", "#f472b6"),
           "heritage": ("#f472b6", "#fed7aa"), "backwaters": ("#86efac", "#e0f2fe"), "forest": ("#a7f3d0", "#ecfccb"),
           "hotel": ("#7dd3fc", "#e0f2fe"), "train": ("#fcd34d", "#fef3c7"), "activity": ("#fdba74", "#fef3c7")}[kind]
    g = (f'<defs><linearGradient id="s{uid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{sky[0]}"/>'
         f'<stop offset="1" stop-color="{sky[1]}"/></linearGradient>'
         f'<linearGradient id="w{uid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0ea5e9"/><stop offset="1" stop-color="#0369a1"/></linearGradient></defs>'
         f'<rect width="400" height="250" fill="url(#s{uid})"/>')
    sx, sy = r.randint(60, 340), r.randint(40, 90)
    sun = f'<circle cx="{sx}" cy="{sy}" r="{r.randint(20, 30)}" fill="#fff7cc" opacity=".9"/>'
    clouds = "".join(f'<g fill="#fff" opacity=".75"><ellipse cx="{x}" cy="{y}" rx="30" ry="10"/><ellipse cx="{x + 18}" cy="{y - 7}" rx="18" ry="10"/></g>'
                     for x, y in [(r.randint(20, 360), r.randint(25, 80)) for _ in range(2)])

    def palm(x, y, s=1.0):
        return (f'<g transform="translate({x},{y}) scale({s})"><path d="M0 0 C 4 -30, 8 -55, 2 -80" stroke="#7c4a1e" stroke-width="6" fill="none"/>'
                + "".join(f'<path d="M2 -80 q {dx} {dy} {dx * 2} {dy * 2.2}" stroke="#15803d" stroke-width="7" fill="none" stroke-linecap="round"/>'
                          for dx, dy in [(-22, 4), (22, 4), (-14, 14), (16, 14), (0, -8)]) + "</g>")

    body = ""
    if kind in ("beach", "island"):
        body = (sun + clouds + f'<rect y="140" width="400" height="70" fill="url(#w{uid})"/>'
                + "".join(f'<path d="M{x} {y} q 12 -6 24 0 t 24 0" stroke="#e0f2fe" stroke-width="2" fill="none" opacity=".7"/>'
                          for x, y in [(r.randint(0, 360), r.randint(150, 200)) for _ in range(6)]))
        if kind == "beach":
            body += '<path d="M0 200 Q 200 170 400 205 V250 H0z" fill="#fcd9a5"/>' + palm(60, 215, 1.1) + palm(330, 222, .9)
        else:
            body += ('<ellipse cx="260" cy="175" rx="110" ry="22" fill="#fde68a"/><path d="M190 175 q 70 -40 140 0z" fill="#16a34a"/>'
                     + palm(250, 170, .8) + palm(290, 172, .7)
                     + "".join(f'<g transform="translate({x},185)"><rect x="-2" y="0" width="3" height="18" fill="#7c4a1e"/><rect x="12" y="0" width="3" height="18" fill="#7c4a1e"/>'
                               f'<path d="M-6 2 L 7 -12 L 20 2z" fill="#a16207"/><rect x="-4" y="2" width="22" height="8" fill="#fbbf24"/></g>' for x in (40, 80, 120)))
    elif kind in ("mountains", "snow"):
        body = sun + clouds
        for i, (base, col) in enumerate([(150, "#64748b"), (175, "#475569"), (205, "#334155")]):
            pts, x = [f"0,{250}"], 0
            while x < 420:
                pts.append(f"{x},{base - r.randint(40, 110) if i < 2 else base - r.randint(10, 40)}")
                x += r.randint(60, 110)
                pts.append(f"{x},{base}")
            pts.append("420,250")
            body += f'<polygon points="{" ".join(pts)}" fill="{col}"/>'
        body += '<path d="M0 215 Q 200 190 400 220 V250 H0z" fill="#f8fafc"/>' if kind == "snow" else '<path d="M0 225 Q 200 205 400 230 V250 H0z" fill="#65a30d"/>'
        body += "".join(f'<path d="M{x} 230 l 10 -30 l 10 30z" fill="#166534"/>' for x in range(10, 400, r.randint(28, 45)))
        if kind == "snow":
            body += "".join(f'<circle cx="{r.randint(0, 400)}" cy="{r.randint(0, 200)}" r="1.8" fill="#fff"/>' for _ in range(40))
    elif kind == "desert":
        body = (sun + '<path d="M0 170 Q 100 130 220 170 T 400 160 V250 H0z" fill="#f59e0b"/><path d="M0 200 Q 140 170 260 205 T 400 195 V250 H0z" fill="#d97706"/>'
                + "".join(f'<rect x="{x}" y="{200 - h}" width="{w}" height="{h}" fill="#78350f" opacity=".55"/>'
                          for x, w, h in [(250, 14, 120), (268, 10, 90), (282, 18, 70), (305, 8, 105)])
                + '<path d="M255 80 l 2 -30 l 2 30z" fill="#78350f" opacity=".55"/>')
    elif kind == "city":
        body = '<circle cx="320" cy="60" r="18" fill="#fef3c7"/>'
        x = 0
        while x < 400:
            w, h = r.randint(26, 50), r.randint(60, 170)
            body += f'<rect x="{x}" y="{250 - h}" width="{w}" height="{h}" fill="#1e1b4b"/>'
            for wy in range(250 - h + 8, 245, 12):
                for wx in range(x + 5, x + w - 6, 9):
                    if r.random() < .45:
                        body += f'<rect x="{wx}" y="{wy}" width="4" height="5" fill="#fde68a"/>'
            x += w + r.randint(2, 6)
    elif kind == "heritage":
        body = (sun + '<path d="M0 200 H400 V250 H0z" fill="#b45309"/>'
                '<g fill="#9a3412"><rect x="90" y="120" width="220" height="80"/><rect x="70" y="95" width="40" height="105"/><rect x="290" y="95" width="40" height="105"/>'
                '<circle cx="200" cy="112" r="38"/><rect x="195" y="58" width="10" height="20"/><circle cx="90" cy="92" r="16"/><circle cx="310" cy="92" r="16"/></g>'
                + "".join(f'<path d="M{x} 200 v-30 a 10 10 0 0 1 20 0 v30z" fill="#fde68a" opacity=".8"/>' for x in range(110, 300, 32)))
    elif kind == "backwaters":
        body = (sun + clouds + '<path d="M0 150 Q 200 130 400 150 V250 H0z" fill="#15803d"/><path d="M0 175 Q 200 160 400 180 V250 H0z" fill="url(#w' + uid + ')"/>'
                + palm(40, 160, .9) + palm(90, 158, .75) + palm(350, 162, .85)
                + '<g transform="translate(180,190)"><path d="M-50 0 q 50 25 100 0z" fill="#7c2d12"/><path d="M-38 0 q 38 -32 76 0z" fill="#a16207"/></g>')
    elif kind == "forest":
        body = sun + clouds + '<path d="M0 170 Q 200 140 400 175 V250 H0z" fill="#4d7c0f"/>' + "".join(
            f'<path d="M{x} {y} l 14 -40 l 14 40z" fill="{r.choice(["#166534", "#15803d", "#14532d"])}"/>'
            for x, y in [(r.randint(-10, 390), r.randint(185, 245)) for _ in range(26)])
    elif kind == "hotel":
        hue = r.choice(["#f8fafc", "#fef3c7", "#e0e7ff", "#fce7f3"])
        body = (sun + clouds + f'<rect x="90" y="60" width="220" height="150" rx="4" fill="{hue}" stroke="#cbd5e1"/>'
                + "".join(f'<rect x="{x}" y="{y}" width="18" height="16" rx="2" fill="#7dd3fc"/>' for y in range(75, 190, 26) for x in range(108, 300, 30))
                + '<rect x="185" y="175" width="30" height="35" fill="#475569"/><rect x="40" y="215" width="320" height="22" rx="10" fill="#22d3ee"/>'
                + palm(55, 212, .8) + palm(345, 214, .8))
    elif kind in ("train", "activity"):
        body = sun + clouds + '<path d="M0 190 Q 200 170 400 195 V250 H0z" fill="#84cc16"/>'
        if kind == "train":
            body += ('<rect x="0" y="206" width="400" height="6" fill="#57534e"/>'
                     + "".join(f'<g transform="translate({x},160)"><rect width="90" height="44" rx="8" fill="#b42318"/>'
                               + "".join(f'<rect x="{wx}" y="8" width="14" height="12" rx="2" fill="#fef3c7"/>' for wx in (8, 28, 48, 68))
                               + '<circle cx="18" cy="46" r="6" fill="#1c1917"/><circle cx="72" cy="46" r="6" fill="#1c1917"/></g>' for x in (20, 116, 212, 308)))
        else:
            body += palm(70, 200, .9) + '<circle cx="250" cy="120" r="34" fill="#ef4444"/><path d="M216 120 q 34 70 68 0" fill="#ef4444"/><rect x="244" y="150" width="12" height="16" fill="#78350f"/>'
    if label:
        body += f'<text x="16" y="236" font-family="Segoe UI,system-ui,sans-serif" font-size="18" font-weight="700" fill="#fff" stroke="rgba(0,0,0,.35)" stroke-width="3" paint-order="stroke">{escape(label)}</text>'
    return f'<svg viewBox="0 0 400 250" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{escape(label or kind)}">{g}{body}</svg>'


def panorama(kind: str, seed: str = "") -> str:
    """Three illustrations side by side so wide hero banners keep natural proportions."""
    kinds = kind if isinstance(kind, (list, tuple)) else [kind] * 3
    return "".join(scene(k, f"{seed}{i}") for i, k in enumerate(kinds))


def stars(n: float) -> str:
    full = int(round(n))
    return f'<span class="stars" aria-label="{n} out of 5">{"★" * full}{"☆" * (5 - full)}</span>'


def seeded(*k):
    return random.Random("|".join(map(str, k)))
