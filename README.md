# Lead Finder — Bright Data Version

Find Swedish local businesses without websites using Bright Data's SERP API to scrape Google Maps. ~100x cheaper than Google Places API.

## How it works

```
1. Search Google Maps via Bright Data SERP API
   "bilverkstad Kalmar" → scrapes Google Maps → returns 20 businesses with full data
   
2. Check website field
   Bright Data returns website URL directly in search results — no separate API call needed
   
3. (Optional) Firecrawl verification
   Double-check "no website" candidates with a web search to catch false positives
   
4. Output CSV
   Sorted by review count — highest reviews = best leads
```

## Cost comparison

| Method | Cost per 1,000 businesses | Full Sweden (290 cities × 3 niches) |
|--------|--------------------------|--------------------------------------|
| Google Places API | ~$49 (search + details) | ~$164 |
| **Bright Data** | **~$1.50** | **~$1.30** |

## Setup

```bash
# No dependencies beyond Python 3.10+ and firecrawl CLI

# Firecrawl (for optional verification step)
npm install -g firecrawl-cli
firecrawl login --browser

# Bright Data
# 1. Sign up at brightdata.com
# 2. Create a SERP API zone
# 3. Get your API key from the zone's Overview tab
```

## Usage

```bash
# Basic — 290 Swedish municipalities × default niches
export BRIGHTDATA_API_KEY="your-key"
python3 lead_finder_brightdata.py --output leads.csv

# Custom niches and cities
python3 lead_finder_brightdata.py \
  --cities-file municipalities.txt \
  --niches bilverkstad snickare städfirma \
  --output leads.csv

# Dry run — see cost estimate without running
python3 lead_finder_brightdata.py \
  --cities-file municipalities.txt \
  --niches-file niches.txt \
  --dry-run

# Skip Firecrawl verification (faster, more false positives)
python3 lead_finder_brightdata.py --skip-firecrawl --output raw_leads.csv
```

## Output

CSV with columns:

| Column | Description |
|--------|-------------|
| Name | Business name |
| Address | Full address |
| Phone | Phone number |
| Rating | Google rating (1-5) |
| Reviews | Number of Google reviews |
| Category | Google Maps category |
| Search Query | The query that found this business |
| Verified | Verification status |

## Files

| File | What |
|------|------|
| `lead_finder_brightdata.py` | Main script |
| `municipalities.txt` | All 290 Swedish municipalities (from SCB) |
| `niches.txt` | 155 business niches organized by tier |

## Bright Data API

Uses the SERP API direct access method:
- Endpoint: `POST https://api.brightdata.com/request`
- Auth: `Authorization: Bearer <API_KEY>`
- Zone: your SERP API zone name
- URL: `https://www.google.com/maps/search/{query}?gl=se&hl=sv&brd_json=1`

Docs: https://docs.brightdata.com/scraping-automation/serp-api/introduction
