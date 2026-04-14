#!/usr/bin/env python3
"""
Lead Finder — Bright Data version.

Uses Bright Data's SERP API to scrape Google Maps instead of the official
Google Places API. ~33x cheaper: $1.50/1,000 results vs $49/1,000 with Google.

Usage:
  export BRIGHTDATA_API_KEY="your-key"
  python3 lead_finder_brightdata.py --output leads.csv
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time
import unicodedata
import urllib.parse
import urllib.request


BRIGHTDATA_URL = "https://api.brightdata.com/request"

SKIP_DOMAINS = [
    "google.com", "facebook.com", "hitta.se", "eniro.se",
    "allabolag.se", "ratsit.se", "merinfo.se", "birthday.se",
    "linkedin.com", "instagram.com", "yelp.com", "trustpilot.com",
    "gulasidorna.se", "foretag.se", "proff.se", "118100.se",
    "hantverkskollen.se", "scanish.com", "dorunner.se",
    "sweblend.se", "cybo.com", "sverigesforetagsguide.se",
    "maptons.com", "kompass.com",
]

IGNORE_WORDS = {
    "ab", "hb", "kb", "ek", "för", "och", "the", "and", "of",
    "malmö", "malmo", "stockholm", "göteborg", "goteborg",
}

DEFAULT_CITIES = [
    "Halmstad", "Växjö", "Kristianstad", "Kalmar", "Falun", "Skellefteå",
    "Karlskrona", "Trollhättan", "Östersund", "Borlänge", "Nyköping",
    "Varberg", "Visby", "Ystad", "Lidköping", "Enköping",
]

DEFAULT_NICHES = ["bilverkstad", "snickare", "städfirma"]


def normalize(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def log(msg: str, **kwargs):
    print(msg, file=sys.stderr, **kwargs)


def firecrawl_verify(business_name: str, city: str) -> str | None:
    """Use firecrawl search to double-check if a business has a website."""
    try:
        result = subprocess.run(
            ["firecrawl", "search", f"{business_name} {city}", "--limit", "3"],
            capture_output=True, text=True, timeout=15,
        )
        name_normalized = normalize(business_name)
        name_parts = set(name_normalized.split()) | set(business_name.lower().split())
        name_parts = {p for p in name_parts if len(p) > 3 and p not in IGNORE_WORDS}

        for line in result.stdout.split("\n"):
            if "URL:" not in line and "url:" not in line:
                continue
            url_raw = line.split(":", 1)[-1].strip()
            url_lower = url_raw.lower()
            if any(d in url_lower for d in SKIP_DOMAINS):
                continue
            url_normalized = normalize(url_raw)
            if any(part in url_normalized for part in name_parts):
                return url_raw.strip()
        return None
    except Exception:
        return None


def search_brightdata(api_key: str, query: str) -> list[dict]:
    """
    Search Google Maps via Bright Data SERP API.
    Returns list of business dicts with name, address, phone, website, rating, etc.
    """
    maps_url = f"https://www.google.com/maps/search/{urllib.parse.quote(query)}?gl=se&hl=sv&brd_json=1"

    payload = json.dumps({
        "zone": "gmb_scraper",
        "url": maps_url,
        "format": "raw",
    }).encode()

    req = urllib.request.Request(
        BRIGHTDATA_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        log(f"  API error: {e}")
        return []

    businesses = []
    for r in data.get("organic", []):
        biz = {
            "name": r.get("title", ""),
            "address": r.get("address", ""),
            "phone": r.get("phone", ""),
            "website": r.get("link", ""),
            "display_link": r.get("display_link", ""),
            "rating": r.get("rating", ""),
            "reviews": r.get("reviews", 0),
            "category": "",
            "maps_url": r.get("place_id_link", ""),
        }

        cats = r.get("category", [])
        if cats:
            biz["category"] = ", ".join(c.get("title", "") for c in cats)

        businesses.append(biz)

    return businesses


def load_file_list(filepath: str) -> list[str]:
    items = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                items.append(line)
    return items


def main():
    parser = argparse.ArgumentParser(
        description="Find businesses without websites using Bright Data Google Maps API."
    )
    parser.add_argument("--output", "-o", default="leads_brightdata.csv")
    parser.add_argument("--cities", nargs="+", default=None)
    parser.add_argument("--cities-file", default=None)
    parser.add_argument("--niches", nargs="+", default=None)
    parser.add_argument("--niches-file", default=None)
    parser.add_argument("--skip-firecrawl", action="store_true")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("BRIGHTDATA_API_KEY")
    if not api_key and not args.dry_run:
        print("ERROR: Set BRIGHTDATA_API_KEY or pass --api-key", file=sys.stderr)
        sys.exit(1)

    if args.cities_file:
        cities = load_file_list(args.cities_file)
    elif args.cities:
        cities = args.cities
    else:
        cities = DEFAULT_CITIES

    if args.niches_file:
        niches = load_file_list(args.niches_file)
    elif args.niches:
        niches = args.niches
    else:
        niches = DEFAULT_NICHES

    queries = [f"{niche} {city}" for niche in niches for city in cities]
    log(f"Total queries: {len(queries)} ({len(niches)} niches x {len(cities)} cities)")

    if args.dry_run:
        cost = len(queries) * 0.0015  # $1.50 per 1000 results, ~1 request per query
        log(f"\n  --- DRY RUN ---")
        log(f"  Estimated results: ~{len(queries) * 20:,}")
        log(f"  Bright Data cost: ~${cost:.2f}")
        log(f"  Firecrawl verification: free")
        sys.exit(0)

    # Phase 1: Bright Data search
    all_businesses = {}
    total_results = 0

    for i, query in enumerate(queries):
        log(f"[{i+1}/{len(queries)}] Searching: {query}")
        results = search_brightdata(api_key, query)
        total_results += len(results)

        for biz in results:
            # Deduplicate by name + address
            key = f"{biz['name']}|{biz['address']}"
            if key not in all_businesses:
                biz["query"] = query
                all_businesses[key] = biz

        # Small delay to avoid rate limiting
        if (i + 1) % 10 == 0:
            log(f"  ... {len(all_businesses)} unique businesses so far")
            time.sleep(0.5)

    log(f"\nTotal API results: {total_results}")
    log(f"Unique businesses: {len(all_businesses)}")

    # Split by website
    no_website = []
    has_website = 0

    for biz in all_businesses.values():
        if biz["website"]:
            has_website += 1
        else:
            no_website.append(biz)

    log(f"Has website: {has_website}")
    log(f"No website (candidates): {len(no_website)}")

    # Phase 2: Firecrawl verification
    if args.skip_firecrawl:
        verified = no_website
        false_positives = 0
        log("\nSkipping Firecrawl verification")
    else:
        log(f"\n==> Verifying {len(no_website)} leads with Firecrawl...")
        verified = []
        false_positives = 0

        for biz in no_website:
            name = biz["name"]
            parts = biz["address"].split(",")
            city = parts[-1].strip().split()[-1] if parts else ""

            log(f"  Checking: {name} ({city})...", end="")
            found_url = firecrawl_verify(name, city)
            if found_url:
                log(f" FOUND WEBSITE: {found_url}")
                false_positives += 1
            else:
                log(f" confirmed no website")
                verified.append(biz)

    # Summary
    log(f"\n{'='*50}")
    log(f"FINAL RESULTS")
    log(f"{'='*50}")
    log(f"  Total businesses scanned: {len(all_businesses)}")
    log(f"  Has website: {has_website}")
    log(f"  False positives caught: {false_positives}")
    log(f"  Verified leads: {len(verified)}")
    if all_businesses:
        log(f"  Lead rate: {len(verified)/len(all_businesses)*100:.1f}%")
    log(f"\n  Bright Data cost: ~${len(queries) * 0.0015:.2f}")

    # Write CSV
    sorted_leads = sorted(verified, key=lambda x: x.get("reviews", 0), reverse=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Name", "Address", "Phone", "Rating", "Reviews",
            "Category", "Search Query", "Verified",
        ])
        for biz in sorted_leads:
            writer.writerow([
                biz["name"], biz["address"], biz["phone"],
                biz["rating"], biz["reviews"], biz["category"],
                biz["query"], "firecrawl_verified",
            ])

    log(f"\nSaved {len(sorted_leads)} leads to: {args.output}")


if __name__ == "__main__":
    main()
