"""Monitoring demo sites (competitor offers, hotel rates, campaign pages, partner feed, demand board).

A shared 'market clock' (tick) drives price, promotion and copy movement so consecutive runs have
something to detect. POST /mock/advance moves the market forward one day.

Built-in QA edge cases:
  * cookie consent banners on every site (the agent must dismiss them)
  * mixed price formats: '₹ 7,499', 'INR 7499', 'Rs.7,499/night', '7,499' (no currency)
  * StayBay's Goa page is redesigned every third day (class names change -> fallback selectors)
  * a duplicated offer card on TripNova, an offer withdrawn on odd days, a new launch from day 2
  * /mock/blocked returns 403, /mock/slow waits 3 seconds
"""
import asyncio
import time
from datetime import date, timedelta
from html import escape

from fastapi import APIRouter, HTTPException, Request

from mock_sources.kit import panorama, scene, scene_for, seeded, shell, stars

router = APIRouter(prefix="/mock", tags=["mock-sources"])
STATE = {"tick": 0, "advanced_at": time.time()}


def rng(*key):
    return seeded(*key)


def price_fmt(amount, style):
    a = f"{amount:,.0f}"
    return {0: f"₹ {a}", 1: f"INR {amount:.0f}", 2: f"Rs.{a}/night", 3: a}[style % 4]


@router.get("/state")
def state():
    return {"tick": STATE["tick"], "advanced_at": STATE["advanced_at"]}


@router.post("/advance")
def advance(steps: int = 1):
    STATE["tick"] += max(1, min(steps, 10))
    STATE["advanced_at"] = time.time()
    return state()


# --------------------------------------------------------------------------- competitor offers
COMPETITORS = {
    "tripnova": [("Goa Monsoon Escape", "Goa", 18999, "3N/4D · Flights + beach resort + breakfast"),
                 ("Kerala Backwaters 4N", "Kochi", 24999, "4N/5D · Houseboat night + Munnar tea estates"),
                 ("Dubai Shopping Fest", "Dubai", 45999, "4N/5D · Flights + 4★ hotel + desert safari"),
                 ("Manali Snow Weekend", "Manali", 12999, "2N/3D · Volvo + mountain cottage + Solang")],
    "skyroam": [("Bali Honeymoon 5N", "Bali", 62999, "5N/6D · Villa with private pool + candlelight dinner"),
                ("Jaipur Heritage Stay", "Jaipur", 9999, "2N/3D · Palace hotel + Amber Fort tour"),
                ("Andaman Dive Week", "Port Blair", 38999, "5N/6D · Havelock + 2 PADI dives")],
}
DISCOUNTS = ["10% off", "Flat ₹2,000 off", "Free airport transfer", "15% off"]


@router.get("/offers/{competitor}")
def offers(competitor: str, request: Request):
    if competitor not in COMPETITORS:
        raise HTTPException(404, "Unknown competitor")
    t = STATE["tick"]
    lst = COMPETITORS[competitor]
    cards = []
    for i, (name, dest, base, desc) in enumerate(lst):
        r = rng(competitor, name, t)
        if competitor == "skyroam" and name.startswith("Andaman") and t % 2 == 1:
            continue  # withdrawn on odd days
        drift = 1 + r.choice([0, 0, 0, 0, -0.04, 0.06, -0.12]) if t else 1
        disc = DISCOUNTS[i % 4]
        if t and i == t % len(lst):
            disc = DISCOUNTS[(i + t) % 4]
        cta = "Grab the deal" if (t % 3 == 2 and i == 0) else "Book now"
        ext = 12 if (name.startswith("Dubai") and t >= 2) else 0
        valid = (date.today() + timedelta(days=30 + ext)).strftime("%d %b %Y")
        cards.append(_offer_card(i, name, dest, base * drift, desc, disc, valid, cta, base * 1.22, i))
    if competitor == "tripnova" and cards:
        cards.append(cards[0])  # duplicated card: the parser must de-duplicate
    if t >= 2 and competitor == "tripnova":
        cards.append(_offer_card("new", "Ladakh Bike Trip", "Leh", 27499, "6N/7D · Royal Enfield + camps at Pangong",
                                 "New launch", (date.today() + timedelta(days=20)).strftime("%d %b %Y"), "Book now", 31999, 0))
    body = f"""<section class="hero"><div class="art">{panorama('beach' if competitor == 'tripnova' else 'island', competitor)}</div>
<div class="in"><h1>Holiday deals you'll actually take</h1><p class="lead">Packages with flights, stays and transfers, priced per person. Updated every morning.</p></div></section>
<div class="container" style="margin-top:-70px;position:relative;z-index:2">
<div class="card" style="padding:14px 16px;margin-bottom:10px"><div class="row">
<span class="chip">🏖 Beaches</span><span class="chip">🏔 Mountains</span><span class="chip">💑 Honeymoon</span><span class="chip">🌆 International</span>
<span class="chip">⏱ Weekend</span><span class="muted" style="margin-left:auto">{len(cards)} packages</span></div></div>
<div class="section-title"><h2>Trending packages</h2><a href="#">View all</a></div>
<div class="grid g3">{''.join(cards)}</div></div>"""
    return shell(request, competitor, "Holiday deals", body, attrs=f'data-competitor="{competitor}"',
                 active="Holiday deals" if competitor == "tripnova" else "Holidays")


def _offer_card(idx, name, dest, price, desc, disc, valid, cta, was, style):
    return f"""<article class="card offer-card" data-offer="{idx}"><div class="img">{scene(scene_for(dest), name, dest)}<span class="badge discount">{escape(disc)}</span></div>
<div class="body"><div class="muted destination">{escape(dest)}</div><h3 class="offer-title" style="margin:2px 0 4px;font-size:18px">{escape(name)}</h3>
<div class="muted" style="min-height:40px">{escape(desc)}</div>
<div class="row between" style="margin-top:10px"><div><span class="was">₹{was:,.0f}</span><div class="price">{price_fmt(price, style)}</div><div class="muted">per person</div></div>
<a class="btn sm cta" href="#">{escape(cta)}</a></div>
<div class="muted validity" style="margin-top:8px">Valid till {valid}</div></div></article>"""


# --------------------------------------------------------------------------- StayBay hotel rates
HOTELS = {
    "goa": [("Sea Breeze Resort", 7499, "Calangute", ["Pool", "Beachfront", "Spa"]),
            ("Calangute Palms", 5299, "Calangute", ["Pool", "Free Wi-Fi"]),
            ("Fort Aguada Retreat", 14999, "Candolim", ["Sea view", "Spa", "Fine dining"])],
    "jaipur": [("Pink City Haveli", 4599, "Old City", ["Heritage", "Rooftop café"]),
               ("Amber Courtyard", 8999, "Amer", ["Pool", "Palace views"])],
    "dubai": [("Marina View Suites", 21999, "Dubai Marina", ["Infinity pool", "Gym"]),
              ("Deira Creek Inn", 9499, "Deira", ["Metro access", "Free Wi-Fi"])],
}


@router.get("/hotels/{city}")
def hotels(city: str, request: Request, stay: str | None = None):
    if city not in HOTELS:
        raise HTTPException(404, "Unknown city")
    t = STATE["tick"]
    stay = stay or (date.today() + timedelta(days=14)).isoformat()
    redesigned = city == "goa" and t % 3 == 2
    rows = []
    for i, (name, base, area, amen) in enumerate(HOTELS[city]):
        r = rng(city, name, stay, t)
        mult = 1 + r.choice([-0.08, -0.03, 0, 0, 0.01, 0.05, 0.15]) if t else 1
        left = r.choice([0, 1, 2, 4, 8, 12]) if t else 8
        avail = "Sold out" if left == 0 else f"Only {left} rooms left" if left <= 3 else f"{left} rooms available"
        price = price_fmt(base * mult, i + t)
        score = round(3.8 + rng(name).random() * 1.1, 1)
        img = scene("hotel", name)
        amen_html = "".join(f'<span class="chip" style="padding:3px 9px;font-size:12.5px">{a}</span>' for a in amen)
        avail_cls = "red" if left == 0 else "amber" if left <= 3 else "green"
        grid = "display:grid;grid-template-columns:260px 1fr 200px;margin-bottom:14px"
        if redesigned:  # new front-end release: different class names, same look
            rows.append(f"""<section class="card property-card" data-hotel style="{grid}">
<div class="img" style="aspect-ratio:auto">{img}</div><div class="body"><h3 class="property-title" style="margin:0 0 4px">{name}</h3>
<div class="muted">{area} · {stars(score)} {score}</div><div class="row" style="margin-top:10px">{amen_html}</div></div>
<div class="body" style="text-align:right;border-left:1px solid #edf0f4"><span class="rate-amount price">{price}</span><div class="muted">per night</div>
<em class="status badge {avail_cls}" style="font-style:normal;margin:8px 0">{avail}</em><div><a class="btn sm brand" href="#">See rooms</a></div></div></section>""")
        else:
            rows.append(f"""<div class="card hotel" style="{grid}">
<div class="img" style="aspect-ratio:auto">{img}</div><div class="body"><h3 class="hotel-name" style="margin:0 0 4px">{name}</h3>
<div class="muted">{area} · {stars(score)} {score}</div><div class="row" style="margin-top:10px">{amen_html}</div>
<div class="muted occupancy" style="margin-top:10px">2 adults, 1 room</div></div>
<div class="body" style="text-align:right;border-left:1px solid #edf0f4"><div class="price">{price}</div><div class="muted">per night</div>
<div class="availability badge {avail_cls}" style="margin:8px 0">{avail}</div><div><a class="btn sm brand" href="#">See rooms</a></div></div></div>""")
    body = f"""<div class="container"><div class="card" style="padding:16px 18px;margin-bottom:18px"><div class="row between">
<div><div class="muted">Destination</div><b style="font-size:20px">{city.title()}</b></div><div><div class="muted">Check-in</div><b>{stay}</b></div>
<div><div class="muted">Guests</div><b>2 adults · 1 room</b></div><a class="btn brand" href="#">Modify search</a></div></div>
<div class="layout"><aside class="sidebar"><h4>Filter by</h4><label><input type="checkbox"> Free cancellation</label><label><input type="checkbox"> Breakfast included</label>
<label><input type="checkbox"> Pay at hotel</label><hr><h4>Star rating</h4><label><input type="checkbox"> 5 stars</label><label><input type="checkbox"> 4 stars</label><label><input type="checkbox"> 3 stars</label></aside>
<div><div class="toolbar"><b>{len(rows)} properties in {city.title()}</b><span class="muted">Prices include taxes</span></div>{''.join(rows)}</div></div></div>"""
    return shell(request, "staybay", f"Hotels in {city.title()}", body, attrs=f'data-city="{city}" data-stay-date="{stay}"', active=city.title())


# --------------------------------------------------------------------------- SkyRoam campaign landing pages
CAMPAIGNS = {
    "summer-sale": [("Summer Sale: up to 40% off", "Flights + hotels bundled for less", "Explore deals", "hero-top"),
                    ("Summer Sale extended!", "Extra 5% off with UPI payments", "Shop the sale", "hero-top"),
                    ("Last 48 hours of Summer Sale", "Extra 5% off with UPI payments", "Shop the sale", "banner-mid")],
    "diwali-getaways": [("Diwali Getaways", "Festive stays from ₹3,999", "Plan my trip", "hero-top"),
                        ("Diwali Getaways", "Festive stays from ₹3,499", "Plan my trip", "hero-top")],
}


@router.get("/campaign/{slug}")
def campaign(slug: str, request: Request):
    if slug not in CAMPAIGNS:
        raise HTTPException(404, "Unknown campaign")
    v = CAMPAIGNS[slug]
    h, o, c, pos = v[min(STATE["tick"], len(v) - 1)]
    valid = (date.today() + timedelta(days=10)).strftime("%d %b %Y")
    deals = [("Goa", "₹ 3,299"), ("Jaipur", "₹ 2,899"), ("Dubai", "₹ 11,499"), ("Bali", "₹ 18,999")]
    tiles = "".join(f"""<div class="card"><div class="img">{scene(scene_for(d), d + slug, d)}</div><div class="body row between">
<div><b>{d}</b><div class="muted">Stays from</div></div><b style="font-size:18px">{p}</b></div></div>""" for d, p in deals)
    body = f"""<main data-campaign="{slug}"><section class="hero" data-position="{pos}" style="min-height:420px">
<div class="art" style="opacity:.55">{panorama('beach' if slug == 'summer-sale' else 'heritage', slug)}</div>
<div class="in" style="padding-bottom:90px"><span class="badge" style="margin-bottom:14px">Limited period</span>
<h1 class="headline" style="font-size:52px">{escape(h)}</h1><p class="offer-text lead" style="font-size:21px">{escape(o)}</p>
<div class="row" style="margin-top:22px"><a class="cta button btn lg" href="#">{escape(c)}</a><span class="validity" style="font-weight:700;background:rgba(255,255,255,.18);padding:10px 16px;border-radius:10px">Ends {valid}</span></div></div></section>
<div class="container"><div class="grid g4" style="margin-top:-60px;position:relative;z-index:2">
<div class="card" style="padding:18px"><b>No-cost EMI</b><div class="muted">On 12 bank cards</div></div>
<div class="card" style="padding:18px"><b>Free cancellation</b><div class="muted">On 8,000+ hotels</div></div>
<div class="card" style="padding:18px"><b>UPI cashback</b><div class="muted">Up to ₹750</div></div>
<div class="card" style="padding:18px"><b>Price drop protection</b><div class="muted">We refund the difference</div></div></div>
<div class="section-title"><h2>Sale picks</h2></div><div class="grid g4">{tiles}</div></div></main>"""
    return shell(request, "skyroam", h, body, ribbon="🎉 Sale prices are live · Offers applied automatically at checkout")


# --------------------------------------------------------------------------- PartnerHub updates
PARTNER_FEED = [
    ("Sea Breeze Resort", "Pool renovation", "Main pool closed for renovation until month end. Guests get complimentary access to the sister property.", "Operations"),
    ("Pink City Haveli", "New cancellation policy", "Free cancellation window changes from 48h to 24h for all rate plans.", "Policy"),
    ("Marina View Suites", "Rate parity update", "Weekend BAR rates revised for the next quarter; parity check requested.", "Pricing"),
    ("Calangute Palms", "Monsoon package", "Monsoon package with free breakfast and late checkout is now live.", "Offers"),
]
CAT_BADGE = {"Operations": "amber", "Policy": "red", "Pricing": "soft", "Offers": "green"}


@router.get("/partners")
def partners(request: Request):
    t = STATE["tick"]
    items = PARTNER_FEED[: 2 + min(t, 2)]
    cards = []
    for i, (p, title, text, cat) in enumerate(items):
        d = date.today() - timedelta(days=6 - i)
        body_text = text if not (t >= 3 and i == 0) else text.replace("month end", "the 15th")
        initials = "".join(w[0] for w in p.split()[:2])
        cards.append(f"""<article class="card update" data-partner="{escape(p)}" style="padding:18px;margin-bottom:14px">
<div class="row between"><div class="row"><span style="width:42px;height:42px;border-radius:50%;background:var(--tint);color:var(--brand);display:grid;place-items:center;font-weight:800">{initials}</span>
<div><div style="font-weight:700">{escape(p)}</div><time class="muted" datetime="{d.isoformat()}">{d.strftime('%d %b %Y')}</time></div></div>
<span class="category badge {CAT_BADGE[cat]}">{cat}</span></div>
<h3 style="margin:12px 0 6px;font-size:18px">{escape(title)}</h3><p style="margin:0;color:#394452">{escape(body_text)}</p>
<div class="row" style="margin-top:12px"><a class="btn sm ghost" href="#">Acknowledge</a><a class="btn sm ghost" href="#" style="border-color:#d6dbe2;color:#394452">Open ticket</a></div></article>""")
    body = f"""<div class="container"><div class="layout"><aside class="sidebar"><h4>Channels</h4>
<label><input type="checkbox" checked> Operations</label><label><input type="checkbox" checked> Policy</label><label><input type="checkbox" checked> Pricing</label><label><input type="checkbox" checked> Offers</label>
<hr><div class="muted">Unread notices</div><b style="font-size:28px">{len(items)}</b></aside>
<div><div class="toolbar"><h2 style="margin:0">Partner updates</h2><span class="muted">Newest first</span></div>{''.join(reversed(cards))}</div></div></div>"""
    return shell(request, "partnerhub", "Partner updates", body, active="Updates")


# --------------------------------------------------------------------------- Wanderlytics demand board
TRENDS = [("Goa", 72, "Sunburn Festival"), ("Manali", 55, ""), ("Dubai", 64, "Shopping Festival"),
          ("Bali", 48, ""), ("Jaipur", 41, "Literature Festival")]


@router.get("/trends")
def trends(request: Request):
    t = STATE["tick"]
    rows, vals = "", []
    for d, base, ev in TRENDS:
        r = rng("trend", d, t)
        v = int(base * (1 + r.choice([-0.18, -0.05, 0, 0, 0.05, 0.25]))) if t else base
        vals.append(v)
        arrow = "rising" if v > base else "falling" if v < base else "flat"
        colour = {"rising": "#16a34a", "falling": "#dc2626", "flat": "#64748b"}[arrow]
        rows += (f'<tr class="signal"><td class="dest" style="font-weight:700">{d}</td><td class="index" style="font-weight:800;font-size:18px">{v}</td>'
                 f'<td class="event">{ev}</td><td class="trend" style="color:{colour};font-weight:700">{arrow}</td>'
                 f'<td style="width:34%"><div style="height:10px;border-radius:5px;background:#eef2f7"><div style="height:10px;border-radius:5px;width:{min(v, 100)}%;background:{colour}"></div></div></td></tr>')
    top = TRENDS[vals.index(max(vals))][0]
    body = f"""<div class="container"><div class="grid g4" style="margin-bottom:18px">
<div class="card" style="padding:18px"><div class="muted">Hottest destination</div><b style="font-size:26px">{top}</b></div>
<div class="card" style="padding:18px"><div class="muted">Average demand index</div><b style="font-size:26px">{sum(vals) // len(vals)}</b></div>
<div class="card" style="padding:18px"><div class="muted">Events tracked</div><b style="font-size:26px">{sum(1 for x in TRENDS if x[2])}</b></div>
<div class="card" style="padding:18px"><div class="muted">Data refreshed</div><b style="font-size:26px">Day {t}</b></div></div>
<div class="card"><div class="body"><h2 style="margin:0 0 4px">Destination demand signals</h2><div class="muted">Search index (0–100) for Indian travellers, next 60 days</div></div>
<table class="tbl"><thead><tr><th>Destination</th><th>Index</th><th>Event</th><th>Trend</th><th>Demand</th></tr></thead><tbody>{rows}</tbody></table></div></div>"""
    return shell(request, "wanderlytics", "Demand signals", body, active="Demand")


@router.get("/blocked")
def blocked():
    raise HTTPException(403, "Access denied by source")


@router.get("/slow")
async def slow(request: Request):
    await asyncio.sleep(3)
    return shell(request, "wanderlytics", "Slow page", '<div class="container"><h1>Eventually loaded</h1></div>')
