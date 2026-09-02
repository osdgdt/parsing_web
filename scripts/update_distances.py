#!/usr/bin/env python3
"""One-time (manually run) script: geocode the reference point and a list of
candidate comuni via OpenStreetMap Nominatim, compute straight-line distance
from the reference point, and write comuni.json with everything within
INCLUDE_RADIUS_KM. Not scheduled - comuni coordinates don't change over time,
re-run manually only if the reference point or radius changes.

Nominatim usage policy: max ~1 request/second, requires an identifying
User-Agent (the stock library UA is explicitly rejected) - both honored below.
"""
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "parsing-web-lavoro-brescia/1.0 (one-time comuni distance script; contact: osdgdt github repo)"
REQUEST_DELAY_S = 1.1
INCLUDE_RADIUS_KM = 22  # generous buffer over the real 20km filter, applied client-side
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "comuni.json"

# Structured query pinpoints the actual residential quartiere (a plain free-text
# search for "quartiere Giuseppe Cesare Abba, Brescia" incorrectly resolves to an
# unrelated historic-center memorial for the person, ~3-4km off).
REFERENCE_QUERY = {
    "street": "Via Prima Quartiere Giuseppe Cesare Abba",
    "city": "Brescia",
    "postalcode": "25127",
    "country": "Italia",
}
REFERENCE_EXPECTED_POSTCODE = "25127"

CANDIDATE_COMUNI = [
    # (key, label) - key must stay in sync with anything already used in data.json
    ("brescia", "Brescia"),
    ("rezzato", "Rezzato"),
    ("botticino", "Botticino"),
    ("san-zeno-naviglio", "San Zeno Naviglio"),
    ("castenedolo", "Castenedolo"),
    ("bagnolo-mella", "Bagnolo Mella"),
    ("mazzano", "Mazzano"),
    ("concesio", "Concesio"),
    ("bovezzo", "Bovezzo"),
    ("collebeato", "Collebeato"),
    ("nuvolento", "Nuvolento"),
    ("nuvolera", "Nuvolera"),
    ("nave", "Nave"),
    ("caino", "Caino"),
    ("villa-carcina", "Villa Carcina"),
    ("sarezzo", "Sarezzo"),
    ("lumezzane", "Lumezzane"),
    ("gussago", "Gussago"),
    ("cellatica", "Cellatica"),
    ("rodengo-saiano", "Rodengo-Saiano"),
    ("ospitaletto", "Ospitaletto"),
    ("castegnato", "Castegnato"),
    ("passirano", "Passirano"),
    ("roncadelle", "Roncadelle"),
    ("castel-mella", "Castel Mella"),
    ("travagliato", "Travagliato"),
    ("torbole-casaglia", "Torbole Casaglia"),
    ("berlingo", "Berlingo"),
    ("flero", "Flero"),
    ("poncarale", "Poncarale"),
    ("capriano-del-colle", "Capriano del Colle"),
    ("azzano-mella", "Azzano Mella"),
    ("borgosatollo", "Borgosatollo"),
    ("ghedi", "Ghedi"),
    ("montichiari", "Montichiari"),
    ("paitone", "Paitone"),
    ("serle", "Serle"),
    ("virle-treponti", "Virle Treponti"),
    ("prevalle", "Prevalle"),
]


def nominatim_get(params):
    url = NOMINATIM_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def geocode_reference():
    params = dict(REFERENCE_QUERY)
    params["format"] = "jsonv2"
    params["addressdetails"] = "1"
    results = nominatim_get(params)
    if not results:
        print("ERRORE: geocoding del punto di riferimento non ha restituito risultati.", file=sys.stderr)
        sys.exit(1)
    best = results[0]
    postcode = best.get("address", {}).get("postcode", "")
    if postcode != REFERENCE_EXPECTED_POSTCODE:
        print(
            f"ERRORE: il punto di riferimento trovato ha CAP '{postcode}', "
            f"atteso '{REFERENCE_EXPECTED_POSTCODE}'. Non procedo per non ancorare "
            "tutte le distanze a un punto sbagliato. Risultato grezzo: "
            f"{json.dumps(best, ensure_ascii=False)}",
            file=sys.stderr,
        )
        sys.exit(1)
    return float(best["lat"]), float(best["lon"])


def geocode_comune(label):
    results = nominatim_get({
        "q": f"{label}, Provincia di Brescia, Italia",
        "format": "jsonv2",
        "addressdetails": "1",
        "limit": "5",
    })
    for r in results:
        addr = r.get("address", {})
        if r.get("category") == "boundary" and addr.get("county") == "Brescia":
            return float(r["lat"]), float(r["lon"])
    # Fall back to the first boundary-ish result if the strict filter finds nothing
    for r in results:
        if r.get("category") in ("boundary", "place"):
            return float(r["lat"]), float(r["lon"])
    return None


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def main():
    print("Geocodifica del punto di riferimento (quartiere Giuseppe Cesare Abba)...")
    ref_lat, ref_lon = geocode_reference()
    print(f"  -> {ref_lat}, {ref_lon}")
    time.sleep(REQUEST_DELAY_S)

    results = []
    for key, label in CANDIDATE_COMUNI:
        print(f"Geocodifica {label}...")
        coords = geocode_comune(label)
        if coords is None:
            print(f"  -> ATTENZIONE: nessun risultato utile per '{label}', saltato.", file=sys.stderr)
            time.sleep(REQUEST_DELAY_S)
            continue
        lat, lon = coords
        dist = round(haversine_km(ref_lat, ref_lon, lat, lon), 1)
        print(f"  -> {lat}, {lon}  ({dist} km)")
        if dist <= INCLUDE_RADIUS_KM:
            results.append({"key": key, "label": label, "lat": lat, "lon": lon, "distanceKm": dist})
        else:
            print(f"  -> escluso, oltre {INCLUDE_RADIUS_KM} km")
        time.sleep(REQUEST_DELAY_S)

    results.sort(key=lambda r: r["distanceKm"])
    OUTPUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nScritto {OUTPUT_PATH} con {len(results)} comuni entro {INCLUDE_RADIUS_KM} km.")


if __name__ == "__main__":
    main()
