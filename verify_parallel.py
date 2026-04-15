#!/usr/bin/env python3
"""
Parallel Firecrawl verification for lead candidates.

Splits the input CSV into N chunks and runs verification in parallel
using subprocess workers. Each worker verifies its chunk independently.

Usage:
  export FIRECRAWL_API_KEY="your-key"
  python3 verify_parallel.py --input raw_leads.csv --output verified_leads.csv --workers 10
"""

import argparse
import csv
import math
import os
import subprocess
import sys
import tempfile
import time
import unicodedata

SKIP_DOMAINS = [
    "google.com", "facebook.com", "hitta.se", "eniro.se",
    "allabolag.se", "ratsit.se", "merinfo.se", "birthday.se",
    "linkedin.com", "instagram.com", "yelp.com", "trustpilot.com",
    "gulasidorna.se", "foretag.se", "proff.se", "118100.se",
    "hantverkskollen.se", "scanish.com", "dorunner.se",
    "sweblend.se", "cybo.com", "sverigesforetagsguide.se",
    "maptons.com", "kompass.com",
]
IGNORE_WORDS = {"ab", "hb", "kb", "ek", "för", "och", "the", "and", "of"}


def normalize(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def firecrawl_verify(name, city):
    try:
        result = subprocess.run(
            ["firecrawl", "search", f"{name} {city}", "--limit", "3"],
            capture_output=True, text=True, timeout=15,
        )
        name_parts = set(normalize(name).split()) | set(name.lower().split())
        name_parts = {p for p in name_parts if len(p) > 3 and p not in IGNORE_WORDS}
        for line in result.stdout.split("\n"):
            if "URL:" not in line and "url:" not in line:
                continue
            url_raw = line.split(":", 1)[-1].strip()
            if any(d in url_raw.lower() for d in SKIP_DOMAINS):
                continue
            if any(part in normalize(url_raw) for part in name_parts):
                return url_raw.strip()
        return None
    except Exception:
        return None


def verify_chunk(chunk_file, output_file, worker_id):
    """Verify a chunk of leads and write results."""
    leads = []
    with open(chunk_file, encoding="utf-8") as f:
        leads = list(csv.DictReader(f))

    verified = []
    false_positives = 0

    for i, biz in enumerate(leads):
        name = biz["Name"]
        parts = biz["Address"].split(",")
        city = parts[-1].strip().split()[-1] if parts and biz["Address"] else ""

        print(f"  [W{worker_id}] [{i+1}/{len(leads)}] {name} ({city})...", end="", flush=True)
        found = firecrawl_verify(name, city)
        if found:
            print(f" FOUND WEBSITE: {found}")
            false_positives += 1
        else:
            print(f" confirmed no website")
            verified.append(biz)

    # Write verified leads
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Address", "Phone", "Rating", "Reviews", "Google Maps", "Category", "Search Query", "Verified"])
        for b in verified:
            writer.writerow([
                b["Name"], b["Address"], b["Phone"], b["Rating"], b["Reviews"],
                b.get("Google Maps", ""), b.get("Category", ""), b["Search Query"],
                "firecrawl_verified",
            ])

    print(f"\n  [W{worker_id}] Done: {len(verified)} verified, {false_positives} false positives")
    return len(verified), false_positives


def main():
    parser = argparse.ArgumentParser(description="Parallel Firecrawl verification")
    parser.add_argument("--input", "-i", required=True, help="Input CSV (raw leads)")
    parser.add_argument("--output", "-o", required=True, help="Output CSV (verified leads)")
    parser.add_argument("--workers", "-w", type=int, default=10, help="Number of parallel workers")
    args = parser.parse_args()

    # Load all leads
    leads = []
    with open(args.input, encoding="utf-8") as f:
        leads = list(csv.DictReader(f))

    print(f"Total candidates: {len(leads)}")
    print(f"Workers: {args.workers}")

    # Split into chunks
    chunk_size = math.ceil(len(leads) / args.workers)
    chunks = [leads[i:i + chunk_size] for i in range(0, len(leads), chunk_size)]
    actual_workers = len(chunks)

    print(f"Chunk size: ~{chunk_size}")
    print(f"Actual chunks: {actual_workers}")

    # Write chunk files
    tmpdir = tempfile.mkdtemp()
    chunk_files = []
    output_files = []

    fieldnames = ["Name", "Address", "Phone", "Rating", "Reviews", "Google Maps", "Category", "Search Query", "Verified"]

    for i, chunk in enumerate(chunks):
        chunk_file = os.path.join(tmpdir, f"chunk_{i}.csv")
        output_file = os.path.join(tmpdir, f"verified_{i}.csv")

        with open(chunk_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in chunk:
                writer.writerow({k: row.get(k, "") for k in fieldnames})

        chunk_files.append(chunk_file)
        output_files.append(output_file)

    # Launch parallel workers
    print(f"\nLaunching {actual_workers} workers...")
    processes = []

    for i in range(actual_workers):
        # Each worker is a subprocess running this same script in single-worker mode
        cmd = [
            sys.executable, __file__,
            "--input", chunk_files[i],
            "--output", output_files[i],
            "--workers", "1",
            "--_worker-id", str(i),
        ]
        p = subprocess.Popen(cmd, env={**os.environ, "_SINGLE_WORKER": "1"})
        processes.append(p)

    # Wait for all workers
    for p in processes:
        p.wait()

    # Merge results
    print(f"\nMerging results...")
    total_verified = 0

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(fieldnames)

        for output_file in output_files:
            if not os.path.exists(output_file):
                continue
            with open(output_file, encoding="utf-8") as inf:
                reader = csv.reader(inf)
                next(reader)  # skip header
                for row in reader:
                    writer.writerow(row)
                    total_verified += 1

    print(f"\nFinal: {total_verified} verified leads saved to {args.output}")

    # Cleanup
    for f in chunk_files + output_files:
        if os.path.exists(f):
            os.remove(f)
    os.rmdir(tmpdir)


# Single worker mode
if os.environ.get("_SINGLE_WORKER") == "1":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", "-i", required=True)
    parser.add_argument("--output", "-o", required=True)
    parser.add_argument("--workers", "-w", type=int, default=1)
    parser.add_argument("--_worker-id", type=int, default=0)
    args = parser.parse_args()
    verify_chunk(args.input, args.output, args._worker_id)
    sys.exit(0)


if __name__ == "__main__":
    main()
