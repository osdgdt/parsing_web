#!/usr/bin/env python3
"""Verify that each listing's url points to a specific job ad, not a generic
search/category page. Runs on a normal GitHub Actions runner (real internet
access), unlike the Claude routine's sandbox which cannot reach these domains.

Two-phase check per listing:
  1) fast regex check against a known "specific listing" shape for that source
     (skips the HTTP call when already obviously bad)
  2) a real HTTP GET (redirects followed) to confirm the link resolves and the
     final URL still looks like a specific listing, not a generic page

A listing that fails is not removed immediately (sites sometimes rate-limit or
transiently block automated requests) - it is flagged via linkVerifyFailCount
and only removed after two consecutive failing runs.
"""
import json
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "data.json"
TIMEOUT = 10
# A realistic desktop-browser user agent, not a bot-labeled one: many job-site
# WAFs reject obviously non-browser user agents outright (observed with a
# custom UA string during testing), which would cause false-positive removals
# of perfectly valid listings. This is a link-reachability check, not content
# scraping, so presenting as an ordinary browser is appropriate here.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}
FAIL_THRESHOLD = 2

# Per-source regex for what a *specific* listing URL looks like. A URL that
# doesn't match is treated as "generic" (a search/category page) and fails
# phase 1 without even making a request. Sources with no established pattern
# yet are left out on purpose - absence of a rule is not itself a failure,
# they just always go to phase 2.
SPECIFIC_LISTING_PATTERNS = {
    "infojobs": re.compile(r"/of-i[0-9a-f]+", re.IGNORECASE),
    "subito": re.compile(r"-\d{6,}\.htm"),
    "adecco": re.compile(r"[?&]ID=[0-9a-f-]{8,}", re.IGNORECASE),
    "bakeca": re.compile(r"/\d{6,}"),
    "randstad": re.compile(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
    ),
    "linkedin": re.compile(r"/jobs/view/[^/?]*-\d+"),
}


def looks_like_specific_listing(source, url):
    pattern = SPECIFIC_LISTING_PATTERNS.get(source)
    if pattern is None:
        return True  # no rule for this source yet - don't fail it in phase 1
    return bool(pattern.search(url))


# HTTP statuses that unambiguously mean "this resource is gone" (from the
# origin server itself, not a bot-detection layer in front of it).
DEFINITELY_GONE_STATUSES = {404, 410}


def http_check(url):
    """Returns (verdict, final_url_or_error). verdict is one of:
    'valid'   - 2xx status
    'gone'    - the server itself says the resource no longer exists
    'unknown' - anything else (403/429/5xx, timeout, connection error): could
                be a WAF/bot-block on the runner's IP rather than a real
                problem with the listing, so this must NOT count as a failure
                (confirmed empirically: a plain link check from a GitHub
                Actions IP gets a 403 from at least one target site even with
                a realistic browser user agent, for a listing that is in
                fact still live)."""
    req = urllib.request.Request(url, headers=REQUEST_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            if 200 <= resp.status < 300:
                return "valid", resp.geturl()
            return "unknown", resp.geturl()
    except urllib.error.HTTPError as e:
        if e.code in DEFINITELY_GONE_STATUSES:
            return "gone", str(e)
        return "unknown", str(e)
    except Exception as e:  # network errors, timeouts, etc. - inconclusive
        return "unknown", str(e)


def verify_listing(listing):
    """Returns 'valid', 'invalid', or 'unknown' (see http_check docstring;
    'unknown' means leave the listing untouched this run)."""
    url = listing.get("url") or ""
    source = listing.get("source") or ""
    if not url:
        return "invalid"

    if not looks_like_specific_listing(source, url):
        return "invalid"

    verdict, final_url = http_check(url)
    if verdict == "unknown":
        return "unknown"
    if verdict == "gone":
        return "invalid"

    # verdict == "valid": still need the final (post-redirect) URL to look
    # like a specific listing, not a generic page the site redirected us to
    # (e.g. an expired listing bouncing to the homepage).
    if not looks_like_specific_listing(source, final_url):
        return "invalid"

    return "valid"


def main():
    if not DATA_PATH.exists():
        print(f"data.json not found at {DATA_PATH}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    listings = data.get("listings", [])

    kept = []
    changed = False
    removed_count = 0

    for listing in listings:
        verdict = verify_listing(listing)
        prev_fail_count = listing.get("linkVerifyFailCount", 0)

        if verdict == "unknown":
            # Could not conclusively check (likely a bot-block on the runner's
            # IP, not a real problem with the listing) - leave it exactly as
            # it was, don't touch the fail counter either way.
            kept.append(listing)
            continue

        if verdict == "valid":
            if prev_fail_count:
                listing.pop("linkVerifyFailCount", None)
                changed = True
            kept.append(listing)
            continue

        # verdict == "invalid"
        fail_count = prev_fail_count + 1
        if fail_count >= FAIL_THRESHOLD:
            removed_count += 1
            changed = True
            print(f"Rimosso (link non valido da {fail_count} controlli): {listing.get('title')} - {listing.get('url')}")
            continue

        listing["linkVerifyFailCount"] = fail_count
        changed = True
        print(f"Segnalato (controllo {fail_count}/{FAIL_THRESHOLD}): {listing.get('title')} - {listing.get('url')}")
        kept.append(listing)

    if not changed:
        print("Nessuna modifica necessaria.")
        return

    data["listings"] = kept
    DATA_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Aggiornato data.json: {removed_count} annunci rimossi, {len(kept)} rimasti.")


if __name__ == "__main__":
    main()
