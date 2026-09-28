"""SkyRoam Travel: a fictional online travel agency the agent can operate end to end.

Flights: search -> results (non-stop filter, sort) -> traveller details (pre-ticked insurance) -> review -> confirm
Hotels:  search -> results (free-cancellation filter, sort, pagination) -> hotel page (room types,
         pre-ticked airport pickup) -> guest details -> review -> confirm
A blocking cookie overlay must be accepted first. Prices move with the shared market clock.
Nothing here charges money; airlines and hotels are fictional.
"""
import asyncio
import hashlib
import time
from datetime import date, timedelta
from html import escape
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from mock_sources.kit import panorama, scene, scene_for, seeded, shell, stars
from mock_sources.router import STATE

router = APIRouter(prefix="/mock/travel", tags=["demo-travel-site"])
BOOKINGS: list[dict] = []
AIRLINES = [("Aurora Air", "AU", "#e11d48"), ("Monsoon Airways", "MW", "#0891b2"), ("Deccan Jet", "DJ", "#7c3aed"),
            ("Sahyadri Air", "SY", "#16a34a"), ("Coastline", "CL", "#ea580c")]
DELAY = 0.5
CITIES = ["Pune", "Mumbai", "Delhi", "Goa", "Bengaluru", "Jaipur", "Kochi", "Chennai", "Kolkata", "Dubai", "Singapore", "Bali"]


def page(request, title, body, **kw):
    return shell(request, "skyroam", title, body, consent="overlay", **kw)


def steps_bar(active, labels=("Search", "Select", "Details", "Review", "Confirmed")):
    return '<div class="steps-bar">' + "".join(f'<span class="{"on" if i <= active else ""}">{i + 1}. {l}</span>' for i, l in enumerate(labels)) + "</div>"


# ============================================================================ home
@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    d = (date.today() + timedelta(days=14)).isoformat()
    dl = "".join(f'<option value="{c}">' for c in CITIES)
    pop = [("Goa", "Beaches and shacks", "₹ 3,299"), ("Jaipur", "Forts and palaces", "₹ 2,899"), ("Dubai", "Skyline and souks", "₹ 11,499"),
           ("Manali", "Snow and cafés", "₹ 4,499"), ("Kochi", "Backwaters", "₹ 3,899"), ("Bali", "Villas and temples", "₹ 18,999"),
           ("Leh", "High passes", "₹ 7,999"), ("Mumbai", "City lights", "₹ 2,499")]
    tiles = "".join(f"""<a class="card" href="/mock/travel/hotels?city={c.lower()}" style="text-decoration:none;color:inherit"><div class="img">{scene(scene_for(c), c, c)}</div>
<div class="body"><div class="row between"><b>{c}</b><span class="muted">from <b style="color:#18212b">{p}</b></span></div><div class="muted">{s}</div></div></a>""" for c, s, p in pop)
    body = f"""<section class="hero"><div class="art">{panorama('beach', 'home')}</div><div class="in">
<h1>Where to next?</h1><p class="lead">Compare 500+ airlines and 40,000 hotels. Free cancellation on most stays.</p></div></section>
<div class="container" style="padding-top:0"><div class="searchbox">
<div class="tabs"><a class="on" href="/mock/travel">✈ Flights</a><a href="/mock/travel/hotels?city=goa">🏨 Hotels</a><a href="/mock/rail">🚆 Trains</a><a href="/mock/activities/goa">🎟 Activities</a></div>
<form id="flight-search" action="/mock/travel/flights" method="get"><datalist id="cities">{dl}</datalist>
<div class="fields"><div class="field"><label for="from">From</label><input id="from" name="from" list="cities" placeholder="City or airport" required autocomplete="off"></div>
<div class="field"><label for="to">To</label><input id="to" name="to" list="cities" placeholder="City or airport" required autocomplete="off"></div>
<div class="field"><label for="date">Departure</label><input id="date" name="date" type="date" value="{d}" required></div>
<div class="field"><label for="pax">Travellers</label><select id="pax" name="pax">{''.join(f'<option value="{n}">{n} adult{"s" if n > 1 else ""}</option>' for n in range(1, 7))}</select></div>
<div class="field"><button id="search" class="btn lg" type="submit" style="width:100%">Search flights</button></div></div></form></div>
<div class="grid g4" style="margin-top:22px">
<div class="card" style="padding:16px"><b>🔒 Secure payments</b><div class="muted">PCI-compliant checkout</div></div>
<div class="card" style="padding:16px"><b>↩ Easy cancellations</b><div class="muted">Refunds in 3–5 days</div></div>
<div class="card" style="padding:16px"><b>💬 24×7 support</b><div class="muted">Chat, call or email</div></div>
<div class="card" style="padding:16px"><b>🏷 Price match</b><div class="muted">Found it cheaper? Tell us</div></div></div>
<div class="section-title"><h2>Popular destinations</h2><a href="/mock/offers/skyroam">See holiday packages →</a></div>
<div class="grid g4">{tiles}</div></div>"""
    return page(request, "Cheap flights, hotels and holidays", body, active="Flights")


# ============================================================================ flights
def flights_for(frm: str, to: str, day: str):
    t = STATE["tick"]
    base = 3200 + int(hashlib.md5(f"{frm}{to}".lower().encode()).hexdigest(), 16) % 5200
    out = []
    for i in range(8):
        r = seeded(frm.lower(), to.lower(), day, i)
        name, code, colour = AIRLINES[i % len(AIRLINES)]
        dep_h = 5 + i * 2 + r.randint(0, 1)
        dur = r.choice([95, 110, 125, 150, 185, 240])
        stops = 0 if i % 3 != 2 else 1
        if stops:
            dur += 90
        drift = 1 + seeded(frm, to, day, i, t).choice([0, 0, -0.06, 0.04, 0.11, -0.13]) if t else 1
        fare = round(base * (0.8 + 0.1 * (i % 5)) * (1.15 if stops == 0 else 0.9) * drift, -1)
        arr = dep_h * 60 + dur
        out.append({"id": f"{code}{200 + i * 17}-{day.replace('-', '')}", "airline": name, "code": code, "colour": colour,
                    "flight_no": f"{code}-{200 + i * 17}", "depart": f"{dep_h % 24:02d}:{(i * 7) % 60:02d}",
                    "arrive": f"{(arr // 60) % 24:02d}:{arr % 60:02d}", "duration": f"{dur // 60}h {dur % 60}m", "stops": stops, "fare": fare,
                    "refundable": i % 2 == 0, "meal": i % 3 == 0})
    return out


@router.get("/flights", response_class=HTMLResponse)
async def flight_results(request: Request, to: str = "", pax: int = 1, nonstop: str | None = None, sort: str = "recommended"):
    await asyncio.sleep(DELAY)
    q = dict(request.query_params)
    frm, day = q.get("from", ""), q.get("date") or (date.today() + timedelta(days=14)).isoformat()
    fl = flights_for(frm, to, day)
    if nonstop:
        fl = [f for f in fl if f["stops"] == 0]
    if sort == "price":
        fl.sort(key=lambda f: f["fare"])
    elif sort == "departure":
        fl.sort(key=lambda f: f["depart"])
    base_q = {"from": frm, "to": to, "date": day, "pax": pax}
    cheapest = min((f["fare"] for f in fl), default=0)
    cards = "".join(f"""<div class="card flight-card" data-flight-id="{f['id']}" style="padding:18px 20px;margin-bottom:12px;display:grid;grid-template-columns:1.3fr 2fr 1fr auto;gap:18px;align-items:center">
<div class="row"><span style="width:40px;height:40px;border-radius:10px;background:{f['colour']};color:#fff;display:grid;place-items:center;font-weight:800">{f['code']}</span>
<div><div class="airline" style="font-weight:700">{f['airline']}</div><div class="flight-no muted">{f['flight_no']}</div></div></div>
<div class="row" style="gap:14px;flex-wrap:nowrap"><div style="text-align:center"><b class="depart" style="font-size:20px">{f['depart']}</b><div class="muted">{escape(frm[:3].upper())}</div></div>
<div style="flex:1;text-align:center"><div class="duration muted">{f['duration']}</div><div style="height:2px;background:#d6dbe2;position:relative;margin:4px 0">{'<span style="position:absolute;left:50%;top:-4px;width:10px;height:10px;border-radius:50%;background:#f59e0b"></span>' if f['stops'] else ''}</div>
<div class="stops small" style="color:{'#16a34a' if f['stops'] == 0 else '#b45309'};font-weight:700">{'Non-stop' if f['stops'] == 0 else '1 stop'}</div></div>
<div style="text-align:center"><b class="arrive" style="font-size:20px">{f['arrive']}</b><div class="muted">{escape(to[:3].upper())}</div></div></div>
<div><div class="row">{'<span class="badge green">Cheapest</span>' if f['fare'] == cheapest else ''}{'<span class="badge soft">Refundable</span>' if f['refundable'] else ''}</div>
<div class="muted small" style="margin-top:4px">{'Free meal · ' if f['meal'] else ''}15 kg check-in</div></div>
<div style="text-align:right"><div class="fare price">₹ {f['fare'] * pax:,.0f}</div><div class="muted">for {pax} traveller{'s' if pax > 1 else ''}</div>
<a class="btn select-btn" style="margin-top:8px" href="/mock/travel/book?{urlencode({**base_q, 'flight': f['id']})}">Select</a></div></div>""" for f in fl)
    hidden = "".join(f'<input type="hidden" name="{k}" value="{escape(str(v))}">' for k, v in base_q.items())
    body = f"""<div style="background:var(--brand2);color:#fff"><div class="container" style="padding:16px 24px" >
<div class="row between"><div><b style="font-size:20px">{escape(frm)} → {escape(to)}</b><div style="opacity:.85">{day} · {pax} traveller{'s' if pax > 1 else ''} · Economy</div></div>
<a class="btn ghost" href="/mock/travel" style="background:transparent;color:#fff;border-color:#fff">Modify search</a></div></div></div>
<div class="container">{steps_bar(1)}<form id="filters" action="/mock/travel/flights" method="get">{hidden}</form>
<div class="layout"><aside class="sidebar"><h4>Stops</h4>
<label><input type="checkbox" id="filter-nonstop" name="nonstop" value="1" form="filters" {'checked' if nonstop else ''} onchange="this.form.submit()"> Non-stop only</label>
<hr><h4>Airlines</h4>{''.join(f'<label><input type="checkbox" checked disabled> {a[0]}</label>' for a in AIRLINES)}
<hr><h4>Departure</h4><div class="row"><span class="chip">🌅 Morning</span><span class="chip">🌇 Evening</span></div></aside>
<div><div class="toolbar"><b>{len(fl)} flights found</b><label class="row" style="gap:8px;font-weight:600">Sort by
<select id="sort" name="sort" form="filters" onchange="this.form.submit()">{''.join(f'<option value="{v}" {"selected" if v == sort else ""}>{l}</option>' for v, l in [("recommended", "Recommended"), ("price", "Cheapest first"), ("departure", "Earliest departure")])}</select></label></div>
<div id="results">{cards or '<div class="card" style="padding:30px;text-align:center">No flights match these filters.</div>'}</div></div></div></div>"""
    return page(request, f"{frm} to {to} flights", body, attrs=f'data-route="{escape(frm)}-{escape(to)}" data-date="{day}"', active="Flights")


def _find_flight(q):
    for f in flights_for(q.get("from", ""), q.get("to", ""), q.get("date", "")):
        if f["id"] == q.get("flight"):
            return f
    return None


def _trip_card(f, q):
    return f"""<div class="card" style="padding:16px 18px;margin-bottom:16px"><div class="row between"><div class="row">
<span style="width:40px;height:40px;border-radius:10px;background:{f['colour']};color:#fff;display:grid;place-items:center;font-weight:800">{f['code']}</span>
<div><b>{f['airline']} {f['flight_no']}</b><div class="muted">{escape(q.get('from', ''))} {f['depart']} → {escape(q.get('to', ''))} {f['arrive']} · {f['duration']} · {'Non-stop' if f['stops'] == 0 else '1 stop'}</div></div></div>
<div class="muted">{q.get('date')}</div></div></div>"""


@router.get("/book", response_class=HTMLResponse)
async def book(request: Request):
    await asyncio.sleep(DELAY)
    q = dict(request.query_params)
    f = _find_flight(q)
    if not f:
        return page(request, "Not found", '<div class="container"><div class="card" style="padding:30px">That flight is no longer available. Search again.</div></div>')
    hidden = "".join(f'<input type="hidden" name="{k}" value="{escape(v)}">' for k, v in q.items())
    body = f"""<div class="container" style="max-width:860px">{steps_bar(2)}{_trip_card(f, q)}
<form id="passenger-form" action="/mock/travel/review" method="get" class="card" style="padding:22px">{hidden}
<h2 style="margin-top:0">Traveller details</h2><p class="muted" style="margin-top:-6px">Enter names exactly as on government ID.</p>
<div class="fields" style="grid-template-columns:repeat(3,1fr)"><div class="field"><label for="name">Full name</label><input id="name" name="name" required></div>
<div class="field"><label for="email">Email</label><input id="email" name="email" type="email" required></div>
<div class="field"><label for="phone">Mobile</label><input id="phone" name="phone" placeholder="+91"></div></div>
<div class="card" style="margin:18px 0;padding:14px 16px;background:var(--tint);border-color:transparent"><label style="display:flex;gap:10px;align-items:center;font-weight:700">
<input type="checkbox" id="insurance" name="insurance" value="1" checked style="width:18px;height:18px"> Secure my trip with travel insurance (₹ 349 per traveller)</label>
<div class="muted" style="margin-left:28px">Covers delays, lost baggage and medical emergencies.</div></div>
<button id="continue" class="btn lg" type="submit">Continue to review</button></form></div>"""
    return page(request, "Traveller details", body, active="Flights")


@router.get("/review", response_class=HTMLResponse)
async def review(request: Request):
    await asyncio.sleep(DELAY)
    q = dict(request.query_params)
    f = _find_flight(q)
    if not f:
        return page(request, "Not found", '<div class="container"><div class="card" style="padding:30px">That flight is no longer available.</div></div>')
    pax = int(q.get("pax", 1))
    ins = 349 * pax if q.get("insurance") else 0
    taxes = round(f["fare"] * pax * 0.12)
    total = f["fare"] * pax + taxes + ins
    hidden = "".join(f'<input type="hidden" name="{k}" value="{escape(v)}">' for k, v in q.items())
    body = f"""<div class="container" style="max-width:860px">{steps_bar(3)}{_trip_card(f, q)}
<div class="card" style="padding:22px"><h2 style="margin-top:0">Review and pay</h2>
<p>Traveller: <b class="traveller">{escape(q.get('name', ''))}</b> · {escape(q.get('email', ''))}</p>
<table class="tbl" style="max-width:460px"><tr><td>Base fare × {pax}</td><td style="text-align:right">₹ {f['fare'] * pax:,.0f}</td></tr>
<tr><td>Taxes and fees</td><td style="text-align:right">₹ {taxes:,.0f}</td></tr><tr><td>Travel insurance</td><td style="text-align:right" class="insurance-line">₹ {ins:,.0f}</td></tr>
<tr><td><b>Total</b></td><td style="text-align:right;font-size:22px" class="total-fare"><b>₹ {total:,.0f}</b></td></tr></table>
<form id="confirm-form" action="/mock/travel/confirm" method="post">{hidden}<input type="hidden" name="total" value="{total}"><input type="hidden" name="kind" value="flight">
<p><button id="confirm-booking" class="btn lg" type="submit">Confirm booking</button></p></form>
<p class="muted">Demo site: confirming creates a fictional booking. No payment is taken.</p></div></div>"""
    return page(request, "Review booking", body, active="Flights")


@router.post("/confirm", response_class=HTMLResponse)
async def confirm(request: Request):
    await asyncio.sleep(DELAY)
    form = {k: str(v) for k, v in (await request.form()).items()}
    kind = form.get("kind", "flight")
    name = form.get("name") or form.get("guest_name") or ""
    total = float(form.get("total") or 0)
    ref = ("SR" if kind == "flight" else "SH") + hashlib.sha1(f"{form}{time.time()}".encode()).hexdigest()[:6].upper()
    what = (f"{form.get('from')} → {form.get('to')} on {form.get('date')}" if kind == "flight"
            else f"{form.get('hotel_name')} · {form.get('room_name')} · {form.get('checkin')} for {form.get('nights')} nights")
    BOOKINGS.append({"ref": ref, "kind": kind, "what": what, "name": name, "total": total, "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    body = f"""<div class="container" style="max-width:760px">{steps_bar(4)}
<div class="card confirmation" style="padding:30px;text-align:center;border-top:6px solid #16a34a">
<div style="width:64px;height:64px;border-radius:50%;background:#dcfce7;color:#16a34a;display:grid;place-items:center;margin:0 auto 10px;font-size:34px">✓</div>
<h2 style="margin:0">Booking confirmed</h2><p class="muted">A confirmation has been sent to your email (demo).</p>
<div class="muted" style="margin-top:14px">Booking reference</div><div class="booking-ref" style="font-size:34px;font-weight:800;letter-spacing:2px">{ref}</div>
<p style="margin-top:14px">{escape(what)} · {escape(name)}</p><p>Total paid <b class="paid-total">₹ {total:,.0f}</b> (demo)</p>
<a class="btn brand" href="/mock/travel/bookings">View my trips</a></div></div>"""
    return page(request, "Booking confirmed", body, active="My trips")


@router.get("/bookings", response_class=HTMLResponse)
async def bookings(request: Request):
    rows = "".join(f"<tr><td><b>{b['ref']}</b></td><td>{'✈ Flight' if b['kind'] == 'flight' else '🏨 Hotel'}</td><td>{escape(b['what'])}</td><td>{escape(b['name'])}</td><td>₹ {b['total']:,.0f}</td><td class='muted'>{b['at']}</td></tr>" for b in reversed(BOOKINGS))
    body = f"""<div class="container"><h1 style="margin-top:0">My trips</h1><div class="card"><table class="tbl"><thead><tr><th>Ref</th><th>Type</th><th>Trip</th><th>Traveller</th><th>Total</th><th>Booked at</th></tr></thead>
<tbody>{rows or '<tr><td colspan=6 style="padding:30px;text-align:center" class="muted">No trips yet. Bookings made by the agent appear here.</td></tr>'}</tbody></table></div></div>"""
    return page(request, "My trips", body, active="My trips")


# ============================================================================ hotels
HOTEL_NAMES = ["Sea Breeze Resort", "Calangute Palms", "Fort Aguada Retreat", "Baga Bay Inn", "Candolim Courtyard", "Anjuna Hilltop",
               "Palolem Huts", "Vagator Views", "Panjim Heritage", "Colva Sands", "Morjim Retreat", "Dona Paula Suites",
               "Arambol Stay", "Benaulim Garden", "Majorda Beach House", "Old Goa Manor", "Miramar Residency", "Siolim House"]
AREAS = {"goa": ["North Goa", "South Goa", "Panjim"], "jaipur": ["Old City", "Amer", "C-Scheme"], "dubai": ["Marina", "Downtown", "Deira"],
         "manali": ["Old Manali", "Mall Road", "Solang"], "kochi": ["Fort Kochi", "Marine Drive", "Kumarakom"]}
AMENITIES = ["Pool", "Free Wi-Fi", "Breakfast", "Spa", "Gym", "Airport shuttle", "Beach access", "Rooftop bar"]


def hotels_for(city: str, checkin: str, nights: int):
    t = STATE["tick"]
    out = []
    for i, h in enumerate(HOTEL_NAMES):
        name = h if city == "goa" else f"{city.title()} {h.split()[0]} {['Hotel', 'Suites', 'Residency'][i % 3]}"
        r = seeded(city, h)
        base = r.randint(28, 160) * 100
        drift = 1 + seeded(city, h, checkin, t).choice([0, 0, 0, -0.07, 0.05, 0.12]) if t else 1
        out.append({"slug": hashlib.md5(name.encode()).hexdigest()[:8], "name": name, "area": AREAS.get(city, ["Centre", "Old town", "Riverside"])[i % 3],
                    "rating": round(3.4 + r.random() * 1.5, 1), "reviews": r.randint(80, 2400), "nightly": round(base * drift, -1),
                    "price": round(base * drift * nights, -1), "free": i % 3 != 1, "amen": r.sample(AMENITIES, 3)})
    return out


@router.get("/hotels", response_class=HTMLResponse)
async def hotels(request: Request, city: str = "goa", checkin: str | None = None, nights: int = 2, page_: int | None = None,
                 sort: str = "popular", freecancel: str | None = None):
    await asyncio.sleep(DELAY)
    pg = int(request.query_params.get("page", 1))
    checkin = checkin or (date.today() + timedelta(days=14)).isoformat()
    items = hotels_for(city, checkin, nights)
    if freecancel:
        items = [x for x in items if x["free"]]
    if sort == "price":
        items.sort(key=lambda x: x["price"])
    elif sort == "rating":
        items.sort(key=lambda x: -x["rating"])
    per = 6
    pages = max(1, -(-len(items) // per))
    pg = max(1, min(pg, pages))
    shown = items[(pg - 1) * per: pg * per]
    qp = {"city": city, "checkin": checkin, "nights": nights, "sort": sort, **({"freecancel": "1"} if freecancel else {})}
    cards = "".join(f"""<div class="card hotel-card" style="display:grid;grid-template-columns:250px 1fr 190px;margin-bottom:14px">
<div class="img" style="aspect-ratio:auto">{scene('hotel', x['name'])}</div>
<div class="body"><h3 class="hotel-name" style="margin:0 0 3px">{escape(x['name'])}</h3><div class="area muted">📍 {x['area']}</div>
<div class="row" style="margin-top:8px"><span class="badge brand" style="background:var(--brand)"><span class="rating">{x['rating']}</span></span><span class="muted">{stars(x['rating'])} · {x['reviews']:,} reviews</span></div>
<div class="row" style="margin-top:10px">{''.join(f'<span class="chip" style="padding:3px 9px;font-size:12.5px">{a}</span>' for a in x['amen'])}</div></div>
<div class="body" style="text-align:right;border-left:1px solid #edf0f4"><div class="cancel-policy badge {'green' if x['free'] else 'red'}">{'Free cancellation' if x['free'] else 'Non-refundable'}</div>
<div class="price" style="margin-top:10px">₹ {x['price']:,.0f}</div><div class="muted">{nights} nights incl. taxes</div>
<a class="btn sm brand view-btn" style="margin-top:10px" href="/mock/travel/hotel/{x['slug']}?{urlencode({'city': city, 'checkin': checkin, 'nights': nights})}">View rooms</a></div></div>""" for x in shown)
    pager = "".join(f'<span class="current">{p}</span>' if p == pg else f'<a href="?{urlencode({**qp, "page": p})}">{p}</a>' for p in range(1, pages + 1))
    if pg < pages:
        pager += f'<a class="next" href="?{urlencode({**qp, "page": pg + 1})}">Next ›</a>'
    body = f"""<div style="background:var(--brand2);color:#fff"><div class="container" style="padding:16px 24px"><div class="row between">
<div><b style="font-size:20px">Hotels in {escape(city.title())}</b><div style="opacity:.85">Check-in {checkin} · {nights} nights · 2 adults</div></div>
<a class="btn ghost" href="/mock/travel" style="background:transparent;color:#fff;border-color:#fff">Modify search</a></div></div></div>
<div class="container"><form id="hotel-filters" method="get"><input type="hidden" name="city" value="{escape(city)}"><input type="hidden" name="checkin" value="{checkin}"><input type="hidden" name="nights" value="{nights}"></form>
<div class="layout"><aside class="sidebar"><h4>Popular filters</h4>
<label><input type="checkbox" id="free-cancel" name="freecancel" value="1" form="hotel-filters" {'checked' if freecancel else ''} onchange="this.form.submit()"> Free cancellation</label>
<label><input type="checkbox" disabled> Breakfast included</label><label><input type="checkbox" disabled> Pay at hotel</label><hr>
<h4>Guest rating</h4><label><input type="checkbox" disabled> 4.5+ Excellent</label><label><input type="checkbox" disabled> 4.0+ Very good</label></aside>
<div><div class="toolbar"><b>{len(items)} stays found · page {pg} of {pages}</b><label class="row" style="gap:8px;font-weight:600">Sort by
<select id="sort" name="sort" form="hotel-filters" onchange="this.form.submit()">{''.join(f'<option value="{v}" {"selected" if v == sort else ""}>{l}</option>' for v, l in [("popular", "Popular"), ("price", "Lowest price"), ("rating", "Top rated")])}</select></label></div>
<div id="listings">{cards}</div><div class="pagination">{pager}</div></div></div></div>"""
    return page(request, f"Hotels in {city.title()}", body, attrs=f'data-city="{escape(city)}" data-stay-date="{checkin}"', active="Hotels")


def _hotel(slug, city, checkin, nights):
    return next((h for h in hotels_for(city, checkin, nights) if h["slug"] == slug), None)


def _rooms(h, nights):
    return [{"id": "std", "name": "Standard room", "desc": "Queen bed · 22 m² · city view", "price": h["price"]},
            {"id": "dlx", "name": "Deluxe room", "desc": "King bed · 30 m² · balcony · breakfast", "price": round(h["price"] * 1.25, -1)},
            {"id": "ste", "name": "Suite", "desc": "Separate living room · 48 m² · sea view · breakfast", "price": round(h["price"] * 1.7, -1)}]


@router.get("/hotel/{slug}", response_class=HTMLResponse)
async def hotel_page(slug: str, request: Request, city: str = "goa", checkin: str | None = None, nights: int = 2):
    await asyncio.sleep(DELAY)
    checkin = checkin or (date.today() + timedelta(days=14)).isoformat()
    h = _hotel(slug, city, checkin, nights)
    if not h:
        return page(request, "Not found", '<div class="container"><div class="card" style="padding:30px">Hotel not found.</div></div>')
    q = {"city": city, "checkin": checkin, "nights": nights, "hotel": slug}
    rooms = "".join(f"""<div class="card room-card" style="padding:16px 18px;margin-bottom:12px;display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center">
<div><b class="room-name" style="font-size:17px">{r['name']}</b><div class="muted">{r['desc']}</div><div class="row" style="margin-top:6px">{'<span class="badge green">Free cancellation</span>' if h['free'] else '<span class="badge red">Non-refundable</span>'}</div></div>
<div style="text-align:right"><div class="room-price price">₹ {r['price']:,.0f}</div><div class="muted">{nights} nights</div>
<a class="btn choose-room" style="margin-top:8px" href="/mock/travel/hotel-book?{urlencode({**q, 'room': r['id']})}">Reserve</a></div></div>""" for r in _rooms(h, nights))
    body = f"""<div class="container">{steps_bar(1, ("Search", "Choose room", "Guest details", "Review", "Confirmed"))}
<div class="grid" style="grid-template-columns:2fr 1fr;gap:12px;margin-bottom:18px"><div class="card"><div class="img" style="aspect-ratio:16/8">{scene('hotel', h['name'] + 'hero')}</div></div>
<div class="grid" style="gap:12px"><div class="card"><div class="img" style="aspect-ratio:16/8.3">{scene(scene_for(city), h['name'])}</div></div><div class="card"><div class="img" style="aspect-ratio:16/8.3">{scene('hotel', h['name'] + 'pool')}</div></div></div></div>
<div class="row between"><div><h1 style="margin:0">{escape(h['name'])}</h1><div class="muted">📍 {h['area']}, {city.title()} · {stars(h['rating'])} {h['rating']} ({h['reviews']:,} reviews)</div></div>
<a class="btn ghost" href="/mock/reviews/{h['name'].lower().replace(' ', '-')}">Read reviews</a></div>
<div class="row" style="margin:12px 0 20px">{''.join(f'<span class="chip">{a}</span>' for a in h['amen'])}</div>
<h2>Choose your room</h2>{rooms}</div>"""
    return page(request, h["name"], body, attrs=f'data-hotel="{escape(h["name"])}"', active="Hotels")


@router.get("/hotel-book", response_class=HTMLResponse)
async def hotel_book(request: Request, hotel: str, room: str, city: str = "goa", checkin: str | None = None, nights: int = 2):
    await asyncio.sleep(DELAY)
    checkin = checkin or (date.today() + timedelta(days=14)).isoformat()
    h = _hotel(hotel, city, checkin, nights)
    r = next((x for x in _rooms(h, nights) if x["id"] == room), None) if h else None
    if not r:
        return page(request, "Not found", '<div class="container"><div class="card" style="padding:30px">Room not available.</div></div>')
    hidden = "".join(f'<input type="hidden" name="{k}" value="{escape(str(v))}">' for k, v in dict(request.query_params).items())
    body = f"""<div class="container" style="max-width:860px">{steps_bar(2, ("Search", "Choose room", "Guest details", "Review", "Confirmed"))}
<div class="card" style="padding:16px 18px;margin-bottom:16px"><b>{escape(h['name'])}</b> · {r['name']}<div class="muted">Check-in {checkin} · {nights} nights · 2 adults</div></div>
<form id="guest-form" class="card" style="padding:22px" action="/mock/travel/hotel-review" method="get">{hidden}<h2 style="margin-top:0">Guest details</h2>
<div class="fields" style="grid-template-columns:repeat(2,1fr)"><div class="field"><label for="guest-name">Lead guest name</label><input id="guest-name" name="guest_name" required></div>
<div class="field"><label for="guest-email">Email</label><input id="guest-email" name="guest_email" type="email" required></div>
<div class="field"><label for="arrival">Arrival time</label><select id="arrival" name="arrival"><option>12:00–14:00</option><option selected>14:00–16:00</option><option>16:00–18:00</option><option>After 18:00</option></select></div>
<div class="field"><label for="requests">Special requests</label><input id="requests" name="requests" placeholder="Optional"></div></div>
<div class="card" style="margin:18px 0;padding:14px 16px;background:var(--tint);border-color:transparent"><label style="display:flex;gap:10px;align-items:center;font-weight:700">
<input type="checkbox" id="pickup" name="pickup" value="1" checked style="width:18px;height:18px"> Add airport pickup (₹ 899)</label></div>
<button id="continue" class="btn lg" type="submit">Continue to review</button></form></div>"""
    return page(request, "Guest details", body, active="Hotels")


@router.get("/hotel-review", response_class=HTMLResponse)
async def hotel_review(request: Request, hotel: str, room: str, city: str = "goa", checkin: str | None = None, nights: int = 2):
    await asyncio.sleep(DELAY)
    q = dict(request.query_params)
    checkin = checkin or (date.today() + timedelta(days=14)).isoformat()
    h = _hotel(hotel, city, checkin, nights)
    r = next((x for x in _rooms(h, nights) if x["id"] == room), None) if h else None
    if not r:
        return page(request, "Not found", '<div class="container"><div class="card" style="padding:30px">Room not available.</div></div>')
    pickup = 899 if q.get("pickup") else 0
    taxes = round(r["price"] * 0.12)
    total = r["price"] + taxes + pickup
    hidden = "".join(f'<input type="hidden" name="{k}" value="{escape(v)}">' for k, v in q.items())
    body = f"""<div class="container" style="max-width:860px">{steps_bar(3, ("Search", "Choose room", "Guest details", "Review", "Confirmed"))}
<div class="card" style="padding:22px"><h2 style="margin-top:0">Review your stay</h2><p><b>{escape(h['name'])}</b> · {r['name']} · check-in {checkin} · {nights} nights</p>
<p>Lead guest: <b>{escape(q.get('guest_name', ''))}</b> · {escape(q.get('guest_email', ''))} · arriving {escape(q.get('arrival', ''))}</p>
<table class="tbl" style="max-width:460px"><tr><td>Room ({nights} nights)</td><td style="text-align:right">₹ {r['price']:,.0f}</td></tr>
<tr><td>Taxes</td><td style="text-align:right">₹ {taxes:,.0f}</td></tr><tr><td>Airport pickup</td><td style="text-align:right">₹ {pickup:,.0f}</td></tr>
<tr><td><b>Total</b></td><td style="text-align:right;font-size:22px" class="total-fare"><b>₹ {total:,.0f}</b></td></tr></table>
<form action="/mock/travel/confirm" method="post">{hidden}<input type="hidden" name="total" value="{total}"><input type="hidden" name="kind" value="hotel">
<input type="hidden" name="hotel_name" value="{escape(h['name'])}"><input type="hidden" name="room_name" value="{r['name']}">
<p><button id="confirm-booking" class="btn lg" type="submit">Confirm booking</button></p></form>
<p class="muted">Demo site: no payment is taken.</p></div></div>"""
    return page(request, "Review stay", body, active="Hotels")
