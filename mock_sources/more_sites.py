"""More demo websites for additional workflow examples.

  /mock/rail                IndiRail Express: train search with per-class seat availability (AVL / RAC / WL)
  /mock/activities/{city}   Explorely: tours and tickets with category filter, sort and pagination
  /mock/reviews/{hotel}     StayVerdict: hotel reviews; new reviews appear as the market clock moves
  /mock/advisories          TravelSafe: country advisories whose levels and visa rules change
  /mock                     Directory of every bundled demo website
"""
import asyncio
import hashlib
from datetime import date, timedelta
from html import escape
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from mock_sources.kit import panorama, BRANDS, scene, scene_for, seeded, shell, stars
from mock_sources.router import STATE

router = APIRouter(prefix="/mock", tags=["demo-more-sites"])
DELAY = 0.4
STATIONS = ["Pune", "Mumbai", "Delhi", "Jaipur", "Bengaluru", "Chennai", "Kolkata", "Goa (Madgaon)", "Ahmedabad", "Varanasi"]


# ============================================================================ IndiRail
@router.get("/rail", response_class=HTMLResponse)
async def rail_home(request: Request):
    d = (date.today() + timedelta(days=14)).isoformat()
    dl = "".join(f'<option value="{s}">' for s in STATIONS)
    body = f"""<section class="hero"><div class="art">{panorama('train', 'rail')}</div><div class="in">
<h1>Book train tickets</h1><p class="lead">Live seat availability for Sleeper, 3A, 2A and 1A across 3,000+ trains.</p></div></section>
<div class="container" style="padding-top:0"><div class="searchbox"><form id="rail-search" action="/mock/rail/trains" method="get"><datalist id="stations">{dl}</datalist>
<div class="fields"><div class="field"><label for="rail-from">From station</label><input id="rail-from" name="from" list="stations" required autocomplete="off"></div>
<div class="field"><label for="rail-to">To station</label><input id="rail-to" name="to" list="stations" required autocomplete="off"></div>
<div class="field"><label for="rail-date">Journey date</label><input id="rail-date" name="date" type="date" value="{d}"></div>
<div class="field"><label for="rail-class">Class</label><select id="rail-class" name="cls"><option value="SL">Sleeper (SL)</option><option value="3A" selected>AC 3 Tier (3A)</option><option value="2A">AC 2 Tier (2A)</option><option value="1A">First AC (1A)</option></select></div>
<div class="field"><button id="find-trains" class="btn lg" type="submit" style="width:100%">Find trains</button></div></div></form></div>
<div class="grid g4" style="margin-top:22px"><div class="card" style="padding:16px"><b>🎫 PNR status</b><div class="muted">Track waitlist confirmation</div></div>
<div class="card" style="padding:16px"><b>🍱 Order food</b><div class="muted">Delivered to your seat</div></div><div class="card" style="padding:16px"><b>⏱ Running status</b><div class="muted">Live train location</div></div>
<div class="card" style="padding:16px"><b>↩ Tatkal</b><div class="muted">Opens 10:00 one day before</div></div></div></div>"""
    return shell(request, "indirail", "Book train tickets", body, active="Book tickets")


def _trains(frm, to, day):
    t = STATE["tick"]
    names = ["Deccan Queen", "Rajdhani Express", "Shatabdi Express", "Duronto Express", "Garib Rath", "Jan Shatabdi", "Superfast Mail"]
    out = []
    for i, n in enumerate(names):
        r = seeded(frm, to, day, n)
        no = 12000 + int(hashlib.md5(f"{frm}{to}{n}".encode()).hexdigest(), 16) % 8000
        dep = (5 + i * 3 + r.randint(0, 2)) % 24
        dur = r.randint(6, 22) * 60 + r.choice([0, 15, 30, 45])
        arr = (dep * 60 + dur) % (24 * 60)
        classes = {}
        for c, mult in [("SL", 1), ("3A", 2.6), ("2A", 3.7), ("1A", 6.2)]:
            seats = seeded(frm, to, day, n, c, t).randint(-40, 90)
            av = f"AVL {seats}" if seats > 10 else f"RAC {max(1, seats + 10)}" if seats > 0 else f"WL {abs(seats) + 1}"
            fare = round((380 + dur * 0.9) * mult * (1 + seeded(n, c, t).choice([0, 0, 0.05, 0.1]) if t else 1), -1)
            classes[c] = (av, fare)
        out.append({"name": n, "no": str(no), "dep": f"{dep:02d}:{(i * 13) % 60:02d}", "arr": f"{arr // 60:02d}:{arr % 60:02d}",
                    "dur": f"{dur // 60}h {dur % 60}m", "classes": classes, "days": "Daily" if i % 2 == 0 else "Mon, Wed, Fri"})
    return out


@router.get("/rail/trains", response_class=HTMLResponse)
async def rail_results(request: Request, to: str = "", cls: str = "3A"):
    await asyncio.sleep(DELAY)
    q = dict(request.query_params)
    frm, day = q.get("from", ""), q.get("date") or (date.today() + timedelta(days=14)).isoformat()
    cards = []
    for tr in _trains(frm, to, day):
        chips = ""
        for c, (av, fare) in tr["classes"].items():
            colour = "#166534" if av.startswith("AVL") else "#92400e" if av.startswith("RAC") else "#991b1b"
            bg = "#dcfce7" if av.startswith("AVL") else "#fef3c7" if av.startswith("RAC") else "#fee2e2"
            sel = " selected" if c == cls else ""
            chips += (f'<div class="class-avail{sel}" data-class="{c}" style="border:{"2px solid var(--brand)" if sel else "1px solid #e6e9ee"};border-radius:10px;padding:8px 10px;min-width:110px;background:{bg if sel else "#fff"}">'
                      f'<div class="row between"><b class="cls">{c}</b><span class="class-fare" style="font-weight:700">₹ {fare:,.0f}</span></div>'
                      f'<div class="avail" style="color:{colour};font-weight:800">{av}</div></div>')
        cards.append(f"""<div class="card train-card" style="padding:18px 20px;margin-bottom:12px">
<div class="row between"><div><b class="train-name" style="font-size:18px">{tr['name']}</b> <span class="train-no muted">#{tr['no']}</span><div class="muted small">Runs {tr['days']}</div></div>
<div class="row" style="gap:18px"><div style="text-align:center"><b class="depart" style="font-size:20px">{tr['dep']}</b><div class="muted">{escape(frm)}</div></div>
<div class="duration muted">— {tr['dur']} —</div><div style="text-align:center"><b class="arrive" style="font-size:20px">{tr['arr']}</b><div class="muted">{escape(to)}</div></div></div></div>
<div class="row" style="margin-top:14px">{chips}</div></div>""")
    body = f"""<div style="background:var(--brand2);color:#fff"><div class="container" style="padding:16px 24px"><div class="row between">
<div><b style="font-size:20px">{escape(frm)} → {escape(to)}</b><div style="opacity:.85">{day} · class {cls}</div></div><a class="btn" href="/mock/rail">Modify</a></div></div></div>
<div class="container"><div class="toolbar"><b>{len(cards)} trains</b><span class="muted">AVL = available · RAC = reservation against cancellation · WL = waitlist</span></div>{''.join(cards)}</div>"""
    return shell(request, "indirail", f"{frm} to {to} trains", body, attrs=f'data-route="{escape(frm)}-{escape(to)}" data-date="{day}" data-travel-class="{cls}"', active="Book tickets")


# ============================================================================ Explorely activities
ACTIVITIES = {
    "goa": [("Dudhsagar Waterfall Jeep Safari", "tours", 8), ("Scuba Diving at Grande Island", "water", 6), ("Sunset Dolphin Cruise", "water", 2),
            ("Old Goa Heritage Walk", "tours", 3), ("Parasailing at Calangute", "water", 1), ("Spice Plantation Tour with Lunch", "food", 5),
            ("Goan Cooking Class", "food", 3), ("Night Market Food Crawl", "food", 3), ("Kayaking in Sal Backwaters", "water", 3),
            ("Casino Cruise Entry", "nightlife", 4), ("Chapora Fort Sunset Trek", "tours", 2), ("Island Hopping by Speedboat", "water", 5)],
    "jaipur": [("Amber Fort Elephant-free Tour", "tours", 4), ("Hot Air Balloon Ride", "adventure", 3), ("Chokhi Dhani Dinner", "food", 4),
               ("Block Printing Workshop", "tours", 3), ("Nahargarh Sunset Trek", "adventure", 3), ("Street Food Walk", "food", 3),
               ("City Palace Skip-the-line", "tours", 2), ("Jeep Safari Jhalana", "adventure", 3)],
    "dubai": [("Desert Safari with BBQ Dinner", "adventure", 6), ("Burj Khalifa Level 124", "tours", 2), ("Dhow Cruise Marina", "water", 2),
              ("Skydive over the Palm", "adventure", 3), ("Museum of the Future", "tours", 2), ("Global Village Entry", "nightlife", 4),
              ("Aquaventure Waterpark", "water", 6), ("Old Dubai Food Tour", "food", 4)],
}
CATEGORIES = [("all", "All experiences"), ("tours", "Tours and sightseeing"), ("water", "Water sports"), ("adventure", "Adventure"),
              ("food", "Food and drink"), ("nightlife", "Nightlife")]


@router.get("/activities/{city}", response_class=HTMLResponse)
async def activities(city: str, request: Request, category: str = "all", sort: str = "popular"):
    await asyncio.sleep(DELAY)
    t = STATE["tick"]
    pg = int(request.query_params.get("page", 1))
    base = ACTIVITIES.get(city, ACTIVITIES["goa"])
    items = []
    for i, (name, cat, hrs) in enumerate(base):
        r = seeded(city, name)
        price = round(r.randint(8, 60) * 100 * (1 + seeded(city, name, t).choice([0, 0, -0.1, 0.08, 0.15]) if t else 1), -1)
        items.append({"name": name, "cat": cat, "hours": hrs, "price": price, "rating": round(4.0 + r.random() * .9, 1),
                      "reviews": r.randint(40, 5200), "free": i % 4 != 3, "bestseller": i % 5 == 0})
    if category != "all":
        items = [x for x in items if x["cat"] == category]
    if sort == "price":
        items.sort(key=lambda x: x["price"])
    elif sort == "rating":
        items.sort(key=lambda x: -x["rating"])
    per = 6
    pages = max(1, -(-len(items) // per))
    pg = max(1, min(pg, pages))
    shown = items[(pg - 1) * per: pg * per]
    qp = {"category": category, "sort": sort}
    cards = "".join(f"""<article class="card activity-card"><div class="img">{scene('activity' if x['cat'] in ('adventure', 'nightlife') else scene_for(city), x['name'])}
{'<span class="badge">Bestseller</span>' if x['bestseller'] else ''}</div><div class="body"><div class="muted small">{dict(CATEGORIES)[x['cat']]}</div>
<h3 class="activity-name" style="margin:3px 0 6px;font-size:17px">{escape(x['name'])}</h3>
<div class="row small"><span class="activity-duration">⏱ {x['hours']} hours</span>{'<span class="free-cancel badge green">Free cancellation</span>' if x['free'] else '<span class="free-cancel badge red">Non-refundable</span>'}</div>
<div class="row between" style="margin-top:10px"><div><b class="rating">{x['rating']}</b> {stars(x['rating'])} <span class="reviews-count muted">({x['reviews']:,})</span></div>
<div style="text-align:right"><div class="muted small">from</div><div class="price">₹ {x['price']:,.0f}</div></div></div></div></article>""" for x in shown)
    pager = "".join(f'<span class="current">{p}</span>' if p == pg else f'<a href="?{urlencode({**qp, "page": p})}">{p}</a>' for p in range(1, pages + 1))
    if pg < pages:
        pager += f'<a class="next" href="?{urlencode({**qp, "page": pg + 1})}">Next ›</a>'
    body = f"""<section class="hero"><div class="art">{panorama(scene_for(city), city + 'act')}</div><div class="in" style="padding-bottom:60px">
<h1>Things to do in {escape(city.title())}</h1><p class="lead">Instant confirmation · Skip the line · Local guides</p></div></section>
<div class="container"><form id="activity-filters" method="get" class="toolbar card" style="padding:12px 16px">
<label class="row" style="gap:8px;font-weight:600">Category <select id="category" name="category" onchange="this.form.submit()">{''.join(f'<option value="{v}" {"selected" if v == category else ""}>{l}</option>' for v, l in CATEGORIES)}</select></label>
<label class="row" style="gap:8px;font-weight:600">Sort by <select id="sort" name="sort" onchange="this.form.submit()">{''.join(f'<option value="{v}" {"selected" if v == sort else ""}>{l}</option>' for v, l in [("popular", "Most popular"), ("price", "Lowest price"), ("rating", "Top rated")])}</select></label>
<span class="muted">{len(items)} experiences</span></form>
<div class="grid g3">{cards or '<div class="card" style="padding:30px">No experiences in this category.</div>'}</div><div class="pagination">{pager}</div></div>"""
    return shell(request, "explorely", f"Things to do in {city.title()}", body, attrs=f'data-city="{escape(city)}"', active=city.title())


# ============================================================================ StayVerdict reviews
REVIEWERS = ["Ananya R.", "Rahul M.", "Sophie L.", "Vikram S.", "Priya K.", "Daniel O.", "Meera J.", "Arjun P.", "Fatima Z.", "Kabir D.", "Neha T.", "Tom W."]
REVIEW_BANK = [
    (5, "Perfect beach getaway", "Staff went out of their way for our anniversary. Breakfast spread was excellent and the pool is spotless."),
    (4, "Great location, small rooms", "Two minutes to the beach and lots of cafés nearby. Rooms are compact but clean."),
    (2, "Noisy at night", "Music from the neighbouring shack until 2 am. Front desk offered earplugs but no room change."),
    (5, "Best stay in Goa", "Sea-view room was worth every rupee. Housekeeping twice a day."),
    (3, "Average value", "Nice property but the pool was under renovation and we were not told at booking."),
    (1, "Booking not honoured", "Our prepaid booking was missing at check-in and we waited 90 minutes for a room."),
    (4, "Family friendly", "Kids loved the pool and the evening activities. Food is a bit pricey."),
    (5, "Would come back", "Quiet, green and friendly. The spa is a must."),
    (2, "AC not working", "AC failed on the second night; maintenance fixed it only the next afternoon."),
    (4, "Good for work trips", "Fast Wi-Fi and a proper desk. Airport pickup was on time."),
]


@router.get("/reviews/{hotel}", response_class=HTMLResponse)
async def reviews(hotel: str, request: Request, sort: str = "newest"):
    await asyncio.sleep(DELAY)
    t = STATE["tick"]
    pg = int(request.query_params.get("page", 1))
    name = hotel.replace("-", " ").title()
    count = 6 + 2 * t  # two new reviews every market day
    items = []
    for k in range(count):
        rating, title, text = REVIEW_BANK[(k * 7 + len(hotel)) % len(REVIEW_BANK)]
        d = date.today() - timedelta(days=(count - k) * 3)
        items.append({"id": hashlib.md5(f"{hotel}{k}".encode()).hexdigest()[:10], "rating": rating, "title": title, "text": text,
                      "who": REVIEWERS[(k + len(hotel)) % len(REVIEWERS)], "date": d, "trip": ["Couple", "Family", "Business", "Solo", "Friends"][k % 5]})
    if sort == "newest":
        items.sort(key=lambda x: x["date"], reverse=True)
    elif sort == "lowest":
        items.sort(key=lambda x: x["rating"])
    avg = round(sum(x["rating"] for x in items) / len(items), 1)
    dist = {s: sum(1 for x in items if x["rating"] == s) for s in range(5, 0, -1)}
    per = 5
    pages = max(1, -(-len(items) // per))
    pg = max(1, min(pg, pages))
    shown = items[(pg - 1) * per: pg * per]
    cards = "".join(f"""<article class="card review" data-review-id="{x['id']}" style="padding:18px;margin-bottom:12px">
<div class="row between"><div class="row"><span style="width:40px;height:40px;border-radius:50%;background:var(--tint);color:var(--brand);display:grid;place-items:center;font-weight:800">{x['who'][0]}</span>
<div><b class="reviewer">{x['who']}</b><div class="muted small"><span class="trip-type">{x['trip']}</span> trip · <time datetime="{x['date'].isoformat()}">{x['date'].strftime('%d %b %Y')}</time></div></div></div>
<span class="review-rating badge {'green' if x['rating'] >= 4 else 'amber' if x['rating'] == 3 else 'red'}">{x['rating']}/5</span></div>
<h3 class="review-title" style="margin:12px 0 4px;font-size:17px">{escape(x['title'])}</h3><p class="review-text" style="margin:0;color:#394452">{escape(x['text'])}</p></article>""" for x in shown)
    bars = "".join(f'<div class="row" style="gap:8px;flex-wrap:nowrap"><span style="width:14px">{s}</span><div style="flex:1;height:8px;border-radius:4px;background:#eef2f7"><div style="height:8px;border-radius:4px;background:var(--brand);width:{dist[s] * 100 // len(items)}%"></div></div><span class="muted small" style="width:26px">{dist[s]}</span></div>' for s in dist)
    qp = {"sort": sort}
    pager = "".join(f'<span class="current">{p}</span>' if p == pg else f'<a href="?{urlencode({**qp, "page": p})}">{p}</a>' for p in range(1, pages + 1))
    if pg < pages:
        pager += f'<a class="next" href="?{urlencode({**qp, "page": pg + 1})}">Next ›</a>'
    body = f"""<div class="container"><div class="grid" style="grid-template-columns:1.2fr 2fr;gap:22px;align-items:start">
<aside class="card" style="padding:0;position:sticky;top:80px"><div class="img" style="aspect-ratio:16/9">{scene('hotel', name)}</div><div class="body">
<h1 style="margin:0;font-size:24px">{escape(name)}</h1><div class="row" style="margin:10px 0"><b class="overall-score" style="font-size:40px;color:var(--brand)">{avg}</b>
<div>{stars(avg)}<div class="muted"><span class="review-count">{len(items)}</span> reviews</div></div></div>{bars}</div></aside>
<div><form id="review-sort" class="toolbar"><h2 style="margin:0">Guest reviews</h2><label class="row" style="gap:8px;font-weight:600">Sort
<select id="sort" name="sort" onchange="this.form.submit()">{''.join(f'<option value="{v}" {"selected" if v == sort else ""}>{l}</option>' for v, l in [("newest", "Newest first"), ("lowest", "Lowest rating"), ("relevant", "Most relevant")])}</select></label></form>
{cards}<div class="pagination">{pager}</div></div></div></div>"""
    return shell(request, "stayverdict", f"{name} reviews", body, attrs=f'data-hotel="{escape(name)}"', active="Hotels")


# ============================================================================ TravelSafe advisories
ADVISORIES = [("Thailand", 1, "Exercise normal precautions. Monsoon flooding possible in the south.", "Visa on arrival, 30 days"),
              ("United Arab Emirates", 1, "Exercise normal precautions. Summer heat advisories in effect.", "Visa on arrival for eligible passports"),
              ("Indonesia (Bali)", 2, "Exercise increased caution near Mount Agung due to volcanic activity.", "e-VoA, 30 days"),
              ("Sri Lanka", 2, "Exercise increased caution. Fuel shortages may affect transport.", "ETA required before travel"),
              ("Maldives", 1, "Exercise normal precautions.", "Free visa on arrival, 30 days"),
              ("Nepal", 2, "Exercise increased caution on trekking routes during monsoon.", "Visa not required for Indian citizens"),
              ("Singapore", 1, "Exercise normal precautions.", "Visa required, apply online")]
LEVELS = {1: ("Level 1: Exercise normal precautions", "green"), 2: ("Level 2: Exercise increased caution", "amber"),
          3: ("Level 3: Reconsider travel", "red"), 4: ("Level 4: Do not travel", "red")}


@router.get("/advisories", response_class=HTMLResponse)
async def advisories(request: Request):
    await asyncio.sleep(DELAY)
    t = STATE["tick"]
    cards = []
    for i, (country, lvl, summary, visa) in enumerate(ADVISORIES):
        updated = date.today() - timedelta(days=10 + i)
        if t >= 1 and country.startswith("Indonesia"):
            lvl, summary, updated = 3, "Reconsider travel to areas near Mount Agung; flights from Denpasar may be disrupted by ash.", date.today() - timedelta(days=1)
        if t >= 2 and country == "Sri Lanka":
            lvl, summary, updated = 1, "Exercise normal precautions. Transport services have returned to normal.", date.today()
        if t >= 3 and country == "Singapore":
            visa, updated = "Visa-free transit up to 96 hours", date.today()
        label, colour = LEVELS[lvl]
        cards.append(f"""<article class="card advisory" data-country="{escape(country)}" style="padding:18px;margin-bottom:12px;border-left:6px solid {'#16a34a' if colour == 'green' else '#f59e0b' if colour == 'amber' else '#dc2626'}">
<div class="row between"><h3 class="country" style="margin:0;font-size:19px">{escape(country)}</h3><span class="level badge {colour}">{label}</span></div>
<p class="summary" style="margin:10px 0 8px">{escape(summary)}</p><div class="row small"><span>🛂 <span class="visa-rule">{escape(visa)}</span></span>
<span class="muted">Updated <time class="updated" datetime="{updated.isoformat()}">{updated.strftime('%d %b %Y')}</time></span></div></article>""")
    body = f"""<div class="container"><div class="card" style="padding:18px 20px;margin-bottom:18px;background:#fff7ed;border-color:#fed7aa">
<b>⚠ Demo data.</b> <span class="muted">These advisories are fictional and exist to test change monitoring. Always check official government sources.</span></div>
<div class="toolbar"><h1 style="margin:0">Travel advisories</h1><span class="muted">{len(cards)} destinations · sorted A–Z</span></div>{''.join(sorted(cards, key=lambda c: c.split('data-country="')[1]))}</div>"""
    return shell(request, "travelsafe", "Travel advisories", body, active="Advisories", consent="none")


# ============================================================================ directory
SITES = [("skyroam", "/mock/travel", "Online travel agency: flights and hotels with full booking flows", "beach"),
         ("tripnova", "/mock/offers/tripnova", "Competitor holiday packages with changing prices and promotions", "backwaters"),
         ("skyroam", "/mock/campaign/summer-sale", "Campaign landing page whose headline, copy and CTA change", "heritage"),
         ("staybay", "/mock/hotels/goa", "Hotel rate pages; the Goa page is redesigned every third day", "hotel"),
         ("partnerhub", "/mock/partners", "Supplier portal publishing operational and policy notices", "city"),
         ("wanderlytics", "/mock/trends", "Destination demand dashboard", "mountains"),
         ("indirail", "/mock/rail", "Train search with class-wise seat availability", "train"),
         ("explorely", "/mock/activities/goa", "Tours and activities with filters and pagination", "activity"),
         ("stayverdict", "/mock/reviews/sea-breeze-resort", "Hotel reviews; new reviews appear each day", "forest"),
         ("travelsafe", "/mock/advisories", "Country travel advisories and visa rules", "island")]


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def directory(request: Request):
    tiles = "".join(f"""<a class="card" href="{url}" style="text-decoration:none;color:inherit"><div class="img">{scene(art, key + url)}</div>
<div class="body"><div class="row"><span class="logo"><span class="mark" style="background:{BRANDS[key]['brand']};width:30px;height:30px"></span></span><b style="font-size:17px">{BRANDS[key]['name']} {BRANDS[key]['suffix']}</b></div>
<div class="muted" style="margin-top:6px">{desc}</div><div class="small" style="margin-top:6px;color:{BRANDS[key]['brand']}">{url}</div></div></a>""" for key, url, desc, art in SITES)
    body = f"""<section class="hero"><div class="art">{panorama('city', 'dir')}</div><div class="in" style="padding-bottom:60px">
<h1>Demo websites</h1><p class="lead">Fictional travel sites bundled with the Web Ops Agent so every workflow can run safely, offline, without touching real businesses. Market day {STATE['tick']}.</p></div></section>
<div class="container"><div class="grid g3">{tiles}</div></div>"""
    return shell(request, "wanderlytics", "Demo websites", body, consent="none")
