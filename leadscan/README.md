# leadscan — does this market actually exist?

A one-day validation for the "sell website leads to web sellers" idea. It
samples real businesses in a city and measures what share of them have **no
website, a dead one, a social page instead of one, or one bad enough to
replace** — the number the whole business model rests on.

It is a research probe, not the product. Run it, read the percentage, decide.

## Run it

```bash
pip install requests python-dotenv
echo 'GOOGLE_MAPS_API_KEY=...' >> .env      # console.cloud.google.com
python leadscan/scan.py --city "Ramat Gan, Israel" --dry-run   # plan + cost
python leadscan/scan.py --city "Ramat Gan, Israel"
```

Enable **Places API (New)** and **Geocoding API** on the key. A default run is
~60 calls; Google's free tier covers 10k/month per SKU, so validating a few
cities costs nothing. `--max-calls` is a hard ceiling so a typo can't spend.

| flag | default | |
|---|---|---|
| `--city` | Ramat Gan, Israel | anything the Geocoding API resolves |
| `--sample` | 400 | stop after this many distinct businesses |
| `--max-calls` | 60 | cost guard |
| `--radius` | 180 | tile radius in metres |
| `--out` | leads.csv | sorted by score, opens in Excel (UTF-8 BOM) |

## What the verdicts mean

| verdict | meaning | why it matters |
|---|---|---|
| `NO_SITE` | Google lists no website | the obvious lead — and the hardest to close, since many have already said no |
| `DEAD` | domain doesn't resolve, 4xx/5xx, or a retired `business.site` | **the best lead in the file.** They already paid for a site once and may not know it's gone |
| `PARKED` | "for sale" / "בקרוב" placeholder | same as dead, plus they own the domain |
| `SOCIAL_ONLY` | the "website" is Facebook/Instagram/WhatsApp | already accepted they need a presence — warmer than nothing |
| `WEAK` | live but no mobile viewport, no HTTPS, or >4s | a redesign pitch, and they're a proven buyer |
| `HEALTHY` | mobile, HTTPS, fast | not a lead |

Score = verdict weight + a demand bonus from review count + a rating bonus.
**Review count is the point.** A shop with 300 reviews and no website has
customers and an owner who tends their listing; one with zero reviews is a
storefront that may not want to be found. Sorting by "no website" gives you a
list. Sorting by score gives you a route worth walking.

## Read the output honestly

`no real website %` is the top-line number. Compare it against the ~17–29% that
US surveys report for small businesses. Then look at `score >= 80` — that is
the real addressable count, and it is always much smaller.

Known biases, so you don't over-trust the number:

- Tiles cap at 20 results, so a dense high street is undersampled. Lower
  `--radius` if the count looks truncated.
- Google's `websiteUri` can be stale in both directions — a site the owner
  never linked reads as `NO_SITE`. Treat the figure as an upper bound.
- Businesses missing from Google Maps entirely are invisible here, and those
  skew toward exactly the offline businesses the product targets.
- One `requests.get` judges a site. It won't catch a pretty site with broken
  checkout, and a bot-blocking WAF looks like `DEAD`. Spot-check before selling.

## Before building on this

The raw list is already a commodity: Apify actors sell no-website leads at
~$2 per 1,000, Webleadr at $12 per 100, and NoWebFinder, LocalLead, Thyonix
and Grape Leads all ship the same search. Nobody is short of lists. If the
numbers here justify continuing, the defensible product is the **pitch** — a
generated mockup for that specific shop, built from its Google photos, hours
and reviews — plus territory exclusivity, not the CSV.
