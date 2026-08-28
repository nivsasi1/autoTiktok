#!/usr/bin/env python3
"""Measure how many local businesses in an area actually need a website.

This answers the one question that decides whether the lead-gen product is
worth building: out of the businesses you could sell to in a given city, what
share have no site at all, a dead site, a social page standing in for a site,
or a site bad enough to be worth replacing.

It samples rather than enumerates. A few hundred businesses pin the percentage
to within a couple of points, which is all a go/no-go needs, and keeps a run
inside the Places API free tier instead of scraping a whole city.
"""

import argparse
import csv
import math
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests

try:                                  # keeps the script runnable standalone,
    from dotenv import load_dotenv    # outside the repo's virtualenv
    load_dotenv()
except ModuleNotFoundError:
    pass

PLACES_URL = "https://places.googleapis.com/v1/places:searchNearby"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# Fields we need live in the Enterprise SKU (websiteUri, rating, phone); the
# rest ride along free. Asking for less would cost less but tells us nothing.
FIELD_MASK = ",".join(
    "places." + f
    for f in (
        "id displayName formattedAddress nationalPhoneNumber websiteUri "
        "rating userRatingCount businessStatus primaryType location googleMapsUri"
    ).split()
)

# Places types worth selling a website to: somebody walks in, books, or orders.
# Deliberately excludes what a website can't help (atm, bus_stop) and the
# categories that are chains by nature.
BUSINESS_TYPES = [
    "restaurant", "cafe", "bakery", "bar", "meal_takeaway",
    "hair_salon", "barber_shop", "beauty_salon", "nail_salon", "spa",
    "clothing_store", "shoe_store", "jewelry_store", "furniture_store",
    "home_goods_store", "florist", "pet_store", "book_store",
    "hardware_store", "electronics_store", "gift_shop", "bicycle_store",
    "sporting_goods_store", "optician", "pharmacy",
    "dentist", "doctor", "physiotherapist", "veterinary_care",
    "lawyer", "accounting", "real_estate_agency", "insurance_agency",
    "travel_agency", "gym", "plumber", "electrician", "painter",
    "moving_company", "car_repair", "car_wash",
]

# A websiteUri on one of these is a social page, not a website. It still means
# the owner accepted they need a web presence — which makes them a warmer lead
# than someone with nothing, not a colder one.
SOCIAL_HOSTS = (
    "facebook.com", "fb.com", "fb.me", "instagram.com", "wa.me",
    "whatsapp.com", "tiktok.com", "linktr.ee", "linkedin.com",
    "youtube.com", "t.me", "telegram.me", "waze.com", "pinterest.com",
)

# Google shut business.site down in 2024, so every one of these is dead by now
# and the owner may not know. Highest-intent lead in the whole dataset.
DEAD_BY_DEFAULT_HOSTS = ("business.site", "negocio.site", "page.link")

PARKED_MARKERS = (
    "domain is for sale", "buy this domain", "this domain may be for sale",
    "parkingcrew", "sedoparking", "domain parking", "afternic",
    "under construction", "coming soon", "site is under maintenance",
    "האתר בבנייה", "אתר בהקמה", "בקרוב", "האתר אינו זמין",
)

UA = "Mozilla/5.0 (compatible; leadscan/1.0; +local market research)"


@dataclass
class Place:
    place_id: str
    name: str
    category: str
    address: str
    phone: str
    maps_url: str
    website: str
    rating: float
    reviews: int
    lat: float
    lng: float
    verdict: str = ""
    http_status: str = ""
    load_ms: int = 0
    https_ok: bool = False
    mobile_ok: bool = False
    score: int = 0
    notes: str = ""


# ---------------------------------------------------------------- geography

def geocode_city(city: str, key: str) -> tuple[float, float, float, float]:
    """Return the city's viewport as (south, west, north, east)."""
    r = requests.get(GEOCODE_URL, params={"address": city, "key": key}, timeout=20)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "OK" or not data.get("results"):
        raise SystemExit(f"geocode failed for {city!r}: {data.get('status')} "
                         f"{data.get('error_message', '')}")
    vp = data["results"][0]["geometry"]["viewport"]
    return (vp["southwest"]["lat"], vp["southwest"]["lng"],
            vp["northeast"]["lat"], vp["northeast"]["lng"])


def tile_centers(bbox, radius_m: int) -> list[tuple[float, float]]:
    """Grid the bbox into circle centers spaced so the circles barely overlap."""
    south, west, north, east = bbox
    step_lat = (radius_m * 1.5) / 111_320
    mid_lat = math.radians((south + north) / 2)
    step_lng = (radius_m * 1.5) / (111_320 * max(math.cos(mid_lat), 0.01))

    centers = []
    lat = south
    while lat <= north:
        lng = west
        while lng <= east:
            centers.append((lat, lng))
            lng += step_lng
        lat += step_lat
    return centers


# ------------------------------------------------------------- places fetch

def search_tile(lat: float, lng: float, radius_m: int, key: str,
                types: list[str]) -> list[dict]:
    body = {
        "includedTypes": types,
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {"center": {"latitude": lat, "longitude": lng},
                       "radius": float(radius_m)}
        },
    }
    headers = {"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELD_MASK,
               "Content-Type": "application/json"}

    for _ in range(len(types)):  # bounded: each retry drops one bad type
        r = requests.post(PLACES_URL, json=body, headers=headers, timeout=30)
        if r.status_code == 200:
            return r.json().get("places", [])
        if r.status_code == 400 and "included_type" in r.text.lower():
            # The type table shifts between API versions; drop what it rejects
            # rather than making the caller guess which name went stale.
            bad = re.findall(r"'([a-z_]+)'", r.text)
            keep = [t for t in body["includedTypes"] if t not in bad]
            if len(keep) == len(body["includedTypes"]):
                break
            print(f"  ! dropping unsupported types: {sorted(set(bad))}", file=sys.stderr)
            body["includedTypes"] = keep
            continue
        raise SystemExit(f"Places API {r.status_code}: {r.text[:400]}")
    return []


def to_place(p: dict) -> Place | None:
    if p.get("businessStatus") not in (None, "OPERATIONAL"):
        return None  # closed for good; not a lead
    loc = p.get("location", {})
    return Place(
        place_id=p.get("id", ""),
        name=p.get("displayName", {}).get("text", ""),
        category=p.get("primaryType", ""),
        address=p.get("formattedAddress", ""),
        phone=p.get("nationalPhoneNumber", ""),
        maps_url=p.get("googleMapsUri", ""),
        website=(p.get("websiteUri") or "").strip(),
        rating=float(p.get("rating") or 0),
        reviews=int(p.get("userRatingCount") or 0),
        lat=float(loc.get("latitude") or 0),
        lng=float(loc.get("longitude") or 0),
    )


def collect(bbox, radius_m, sample, max_calls, key) -> tuple[list[Place], int]:
    centers = tile_centers(bbox, radius_m)
    random.shuffle(centers)          # sample the city evenly, not west-to-east
    seen: dict[str, Place] = {}
    calls = 0

    for lat, lng in centers:
        if len(seen) >= sample or calls >= max_calls:
            break
        raw = search_tile(lat, lng, radius_m, key, BUSINESS_TYPES[:50])
        calls += 1
        for p in raw:
            place = to_place(p)
            if place and place.place_id not in seen:
                seen[place.place_id] = place
        print(f"\r  tiles {calls}/{max_calls}  businesses {len(seen)}",
              end="", flush=True)
    print()
    return list(seen.values())[:sample], calls


# --------------------------------------------------------- website grading

def grade(place: Place) -> None:
    url = place.website
    if not url:
        place.verdict = "NO_SITE"
        return

    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if any(host == h or host.endswith("." + h) for h in SOCIAL_HOSTS):
        place.verdict = "SOCIAL_ONLY"
        place.notes = host
        return
    if any(host.endswith(h) for h in DEAD_BY_DEFAULT_HOSTS):
        place.verdict = "DEAD"
        place.notes = "retired Google site builder"
        return

    started = time.monotonic()
    try:
        r = requests.get(url, timeout=12, allow_redirects=True,
                         headers={"User-Agent": UA})
    except requests.RequestException as exc:
        place.verdict = "DEAD"
        place.notes = type(exc).__name__
        return
    place.load_ms = int((time.monotonic() - started) * 1000)
    place.http_status = str(r.status_code)
    place.https_ok = r.url.startswith("https://")

    if r.status_code >= 400:
        place.verdict = "DEAD"
        return

    html = r.text[:200_000]
    low = html.lower()
    if any(m in low for m in PARKED_MARKERS):
        place.verdict = "PARKED"
        return

    place.mobile_ok = 'name="viewport"' in low or "name='viewport'" in low
    slow = place.load_ms > 4000
    if not place.mobile_ok or slow or not place.https_ok:
        place.verdict = "WEAK"
        place.notes = ",".join(filter(None, [
            "" if place.mobile_ok else "no-mobile",
            "slow" if slow else "",
            "" if place.https_ok else "no-https",
        ]))
    else:
        place.verdict = "HEALTHY"


# A business with reviews is a business with customers — proven demand and
# proof the owner tends their Google listing. That, not the missing site, is
# what separates a lead worth a visit from a dead storefront.
BASE_SCORE = {"DEAD": 85, "PARKED": 80, "NO_SITE": 70, "SOCIAL_ONLY": 65,
              "WEAK": 45, "HEALTHY": 5}


def score(place: Place) -> int:
    base = BASE_SCORE.get(place.verdict, 0)
    demand = min(25, int(8 * math.log10(place.reviews + 1)))
    quality = 5 if place.rating >= 4.0 else 0
    return min(100, base + demand + quality)


# ------------------------------------------------------------------- report

def summarize(places: list[Place], calls: int, area: str) -> None:
    total = len(places)
    if not total:
        print("no businesses found — widen the area or raise --max-calls")
        return

    order = ["NO_SITE", "DEAD", "PARKED", "SOCIAL_ONLY", "WEAK", "HEALTHY"]
    counts = {v: sum(1 for p in places if p.verdict == v) for v in order}
    margin = 100 * 1.96 * math.sqrt(0.25 / total)   # worst-case 95% CI

    print(f"\n{'=' * 58}\n  {area} — {total} businesses, {calls} API calls")
    print(f"  95% confidence: ±{margin:.1f} points\n{'=' * 58}")
    for v in order:
        n = counts[v]
        bar = "█" * round(40 * n / total)
        print(f"  {v:<12} {n:>4}  {100 * n / total:>5.1f}%  {bar}")

    sellable = sum(counts[v] for v in ("NO_SITE", "DEAD", "PARKED", "SOCIAL_ONLY"))
    strong = [p for p in places if p.score >= 80]
    print(f"\n  no real website : {sellable:>4}  ({100 * sellable / total:.1f}%)")
    print(f"  + weak sites    : {sellable + counts['WEAK']:>4}  "
          f"({100 * (sellable + counts['WEAK']) / total:.1f}%)")
    print(f"  score >= 80     : {len(strong):>4}  ({100 * len(strong) / total:.1f}%)"
          "   <- what a salesperson would actually knock on\n")

    print("  top 10 leads")
    for p in sorted(places, key=lambda p: -p.score)[:10]:
        print(f"   {p.score:>3}  {p.verdict:<12} {p.reviews:>4}rev  "
              f"{p.name[:38]:<38} {p.phone}")


def write_csv(places: list[Place], path: str) -> None:
    cols = ["score", "verdict", "name", "category", "reviews", "rating",
            "phone", "address", "website", "http_status", "load_ms",
            "https_ok", "mobile_ok", "notes", "maps_url", "lat", "lng"]
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for p in sorted(places, key=lambda p: -p.score):
            w.writerow({c: getattr(p, c) for c in cols})
    print(f"\n  wrote {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--city", default="Ramat Gan, Israel")
    ap.add_argument("--sample", type=int, default=400,
                    help="stop once this many distinct businesses are found")
    ap.add_argument("--max-calls", type=int, default=60,
                    help="hard ceiling on Places API calls (cost guard)")
    ap.add_argument("--radius", type=int, default=180,
                    help="tile radius in metres; smaller = less 20-result truncation")
    ap.add_argument("--out", default="leads.csv")
    ap.add_argument("--dry-run", action="store_true",
                    help="show the plan and cost estimate, call nothing")
    args = ap.parse_args()

    key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not key:
        raise SystemExit("set GOOGLE_MAPS_API_KEY (see leadscan/README.md)")

    print(f"geocoding {args.city} ...")
    bbox = geocode_city(args.city, key)
    tiles = len(tile_centers(bbox, args.radius))
    print(f"  bbox {bbox[0]:.3f},{bbox[1]:.3f} -> {bbox[2]:.3f},{bbox[3]:.3f}"
          f"  ({tiles} tiles at {args.radius}m)")
    print(f"  sampling up to {args.max_calls} of them "
          f"(~${args.max_calls * 0.035:.2f} at list price, free under the "
          f"10k/month Places free tier)")
    if args.dry_run:
        return

    print("\nfetching businesses ...")
    places, calls = collect(bbox, args.radius, args.sample, args.max_calls, key)

    print(f"checking {len(places)} websites ...")
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(grade, places))
    for p in places:
        p.score = score(p)

    summarize(places, calls, args.city)
    write_csv(places, args.out)


if __name__ == "__main__":
    main()
