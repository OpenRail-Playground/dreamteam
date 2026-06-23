"""Lädt ÖBB HAFAS Journey Daten analog zu load_db_data.py / load_sbb_data.py.

Ablauf:
1. Für jede eindeutige (Gattung, Stamm)-Kombination aus NJ_List.csv
   Endpoint 1 aufrufen:
   GET {base}/trainSearch?match=<Gattung> <Stamm>&date=YYYY-MM-DD&format=json
   -> liefert JourneyDetail[*] mit `ref` und `dayOfOperation`.
2. Pro Treffer Endpoint 2 aufrufen:
   GET {base}/journeyDetail?id=<ref>&format=json&date=YYYY-MM-DD
   -> liefert Stops mit name, arrDate/arrTime, depDate/depTime.
3. Halte werden in CSV gleichen Formats geschrieben:
   Datum;Zugnummer;Halt;an;ab  -> ./data/oebb_data.csv

Auth:
- Header `x-Gateway-APIKey` muss bei beiden Calls gesetzt sein.
- `id`-Param NICHT vorab URL-encoden (requests übernimmt das, sonst Double-Encoding -> 400).

Umgebungsvariablen (.env):
  OEBB_BASE_URL  z.B. https://api-gateway.oebb.at/gateway/Hafas-API/active
  OEBB_API_KEY   API-Gateway Key
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests


# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
QUERY_DATE = "2026-06-22"  # gleiches Datum wie DB-/SBB-Skripte

BASE_URL = os.environ.get(
    "OEBB_BASE_URL", "https://api-gateway.oebb.at/gateway/Hafas-API/active"
).rstrip("/")
API_KEY = os.environ.get("OEBB_API_KEY", "")


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------
def _fmt_time(t: str | None) -> str | None:
    if not t:
        return None
    # ÖBB liefert "HH:MM:SS" -> "HH:MM"
    return t[:5]


def _stop_event_iso(stop: dict, kind: str) -> tuple[str | None, str | None]:
    """Gibt (date, time) für 'arr' oder 'dep' eines Stops zurück."""
    date = stop.get(f"{kind}Date")
    time = stop.get(f"{kind}Time")
    return date, time


# ---------------------------------------------------------------------------
# API Calls
# ---------------------------------------------------------------------------
def fetch_train_search(
    session: requests.Session, match: str, date: str
) -> list[dict]:
    """Endpoint 1: /trainSearch -> Liste an Journey-Treffern mit `ref`."""
    url = f"{BASE_URL}/trainSearch"
    r = session.get(
        url,
        params={"match": match, "date": date, "format": "json"},
        timeout=30,
    )
    if r.status_code == 404:
        return []
    if r.status_code >= 400:
        print(f"[WARN] trainSearch '{match}' -> {r.status_code} {r.text[:200]}")
        return []
    try:
        data = r.json()
    except ValueError:
        print(f"[WARN] trainSearch '{match}' -> kein JSON")
        return []
    return data.get("JourneyDetail") or []


def fetch_journey_detail(
    session: requests.Session, ref: str, date: str | None = None
) -> dict | None:
    """Endpoint 2: /journeyDetail?id=<ref> -> Detail mit Stops."""
    url = f"{BASE_URL}/journeyDetail"
    params = {"id": ref, "format": "json"}
    if date:
        params["date"] = date
    r = session.get(url, params=params, timeout=30)
    if r.status_code >= 400:
        print(f"[WARN] journeyDetail -> {r.status_code} {r.text[:200]}")
        return None
    try:
        return r.json()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    if not API_KEY:
        raise RuntimeError("OEBB_API_KEY nicht gesetzt (siehe .env).")

    nj_list_path = Path("./data/NJ_List.csv")
    all_trains = pd.read_csv(nj_list_path, delimiter=";", header=0)
    unique_combinations = all_trains[["Gattung", "Stamm"]].drop_duplicates()

    session = requests.Session()
    session.headers.update(
        {
            "x-Gateway-APIKey": API_KEY,
            "Accept": "application/json",
        }
    )

    rows: list[dict] = []
    for _, row in unique_combinations.iterrows():
        gattung = str(row["Gattung"]).strip()
        stamm = str(row["Stamm"]).strip()
        match = f"{gattung} {stamm}"        # z.B. "NJ 470"
        zugnummer = match

        journeys = fetch_train_search(session, match, QUERY_DATE)
        # Nur Journeys, die exakt am QUERY_DATE verkehren
        journeys = [
            j for j in journeys if j.get("dayOfOperation") == QUERY_DATE
        ]
        if not journeys:
            print(f"[INFO] Keine Journeys für {match} am {QUERY_DATE}")
            continue

        for j in journeys:
            ref = j.get("ref")
            if not ref:
                continue
            detail = fetch_journey_detail(session, ref, QUERY_DATE)
            if not detail:
                continue
            stops = (detail.get("Stops") or {}).get("Stop") or []
            for stop in stops:
                arr_date, arr_time = _stop_event_iso(stop, "arr")
                dep_date, dep_time = _stop_event_iso(stop, "dep")
                ref_date = arr_date or dep_date
                rows.append(
                    {
                        "Datum": ref_date,
                        "Zugnummer": zugnummer,
                        "Halt": stop.get("name"),
                        "an": _fmt_time(arr_time),
                        "ab": _fmt_time(dep_time),
                    }
                )

    out_path = Path("./data/oebb_data.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out_path, index=False, sep=";", encoding="utf-8")
    print(f"[OK] {len(rows)} Zeilen geschrieben nach {out_path}")


if __name__ == "__main__":
    main()

