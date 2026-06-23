"""Lädt SBB Journey-Service Daten analog zu load_db_data.py.

Ablauf:
1. OAuth2-Token via Client-Credentials Flow holen (Azure AD).
2. Pro eindeutiger (Gattung, Stamm)-Kombination aus NJ_List.csv die
   serviceProductReference im Format "<GATTUNG> - <NUMMER>" bauen
   (z.B. "NJ - 470") und Endpoint
   GET {base}/v3/vehicle-journeys/by-service/{ref}?date=YYYY-MM-DD aufrufen.
3. Aus der Antwort `datedVehicleJourneys[*].id` extrahieren und
   GET {base}/v3/vehicle-journeys/{id} aufrufen.
4. Halte (Stops) auslesen und als CSV nach ./data/sbb_data.csv schreiben.

Umgebungsvariablen (siehe sbb.env):
  SBB_TOKEN_URL, SBB_CLIENT_ID, SBB_CLIENT_SECRET, SBB_SCOPE, SBB_BASE_URL
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
QUERY_DATE = "2026-06-22"  # gleiches Datum wie DB-Skript

TOKEN_URL = os.environ.get(
    "SBB_TOKEN_URL",
    "https://login.microsoftonline.com/2cda5d11-f0ac-46b3-967d-af1b2e1bd01a/oauth2/v2.0/token",
)
CLIENT_ID = os.environ.get("SBB_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("SBB_CLIENT_SECRET", "")
SCOPE = os.environ.get("SBB_SCOPE", "api://journey-service.int/.default")
BASE_URL = os.environ.get(
    "SBB_BASE_URL", "https://journey-service-int.api.sbb.ch"
).rstrip("/")


# ---------------------------------------------------------------------------
# OAuth2: Access Token holen
# ---------------------------------------------------------------------------
def get_access_token() -> str:
    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError(
            "SBB_CLIENT_ID / SBB_CLIENT_SECRET nicht gesetzt (siehe sbb.env)."
        )
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": SCOPE,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Hilfsfunktionen Stops/Zeiten
# ---------------------------------------------------------------------------
def _stop_name(stop_point: dict) -> str | None:
    place = stop_point.get("place") or {}
    return place.get("name")


def _event_time(stop_point: dict, kind: str) -> str | None:
    """kind: 'arrival' oder 'departure'. SBB nutzt `timeAimed` (ISO mit TZ)."""
    ev = stop_point.get(kind) or {}
    if not isinstance(ev, dict):
        return None
    return ev.get("timeAimed") or ev.get("time") or ev.get("scheduledTime")


def _fmt_time(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%H:%M")
    except Exception:
        return iso[-8:-3] if len(iso) >= 8 else iso


def _fmt_date(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except Exception:
        return iso[:10]


# ---------------------------------------------------------------------------
# API Calls
# ---------------------------------------------------------------------------
def fetch_journey_ids(session: requests.Session, service_ref: str, date: str) -> list[str]:
    """Endpoint 1: /v3/vehicle-journeys/by-service/{serviceProductReference}?date=..."""
    url = f"{BASE_URL}/v3/vehicle-journeys/by-service/{requests.utils.quote(service_ref, safe='')}"
    r = session.get(url, params={"date": date}, timeout=30)
    if r.status_code >= 400:
        print(f"[DEBUG] GET {r.url} -> {r.status_code} {r.text[:300]}")
        return []
    data = r.json()
    dvj = data.get("datedVehicleJourneys") or data.get("DatedVehicleJourneys") or []
    ids: list[str] = []
    for entry in dvj:
        # Format: { "serviceJourney": { "id": "...", ... } }
        sj = entry.get("serviceJourney") or {}
        jid = sj.get("id") or entry.get("id")
        if jid:
            ids.append(jid)
    return ids


def fetch_journey_detail(session: requests.Session, journey_id: str) -> dict:
    """Endpoint 2: /v3/vehicle-journeys/{id}"""
    url = f"{BASE_URL}/v3/vehicle-journeys/{requests.utils.quote(journey_id, safe='')}"
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    nj_list_path = Path("./data/NJ_List.csv")
    all_trains = pd.read_csv(nj_list_path, delimiter=";", header=0)
    unique_combinations = all_trains[["Gattung", "Stamm"]].drop_duplicates()

    token = get_access_token()
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
    )

    rows: list[dict] = []
    for _, row in unique_combinations.iterrows():
        gattung = str(row["Gattung"]).strip()
        stamm = str(row["Stamm"]).strip()
        # Format: "<Kategorie> - <Nummer>"  (Leerzeichen-Bindestrich-Leerzeichen)
        service_ref = f"{gattung} - {stamm}"
        zugnummer = f"{gattung} {stamm}"

        try:
            journey_ids = fetch_journey_ids(session, service_ref, QUERY_DATE)
        except requests.HTTPError as e:
            print(f"[WARN] by-service Fehler für {service_ref}: {e}")
            continue

        if not journey_ids:
            print(f"[INFO] Keine Journeys für {service_ref} am {QUERY_DATE}")
            continue

        for jid in journey_ids:
            try:
                detail = fetch_journey_detail(session, jid)
            except requests.HTTPError as e:
                print(f"[WARN] Detail Fehler für id={jid}: {e}")
                continue

            stop_points = (
                (detail.get("serviceJourney") or {}).get("stopPoints")
                or detail.get("stopPoints")
                or []
            )
            for sp in stop_points:
                arr_iso = _event_time(sp, "arrival")
                dep_iso = _event_time(sp, "departure")
                ref_iso = arr_iso or dep_iso
                rows.append(
                    {
                        "Datum": _fmt_date(ref_iso),
                        "Zugnummer": zugnummer,
                        "Halt": _stop_name(sp),
                        "an": _fmt_time(arr_iso),
                        "ab": _fmt_time(dep_iso),
                    }
                )

    out_path = Path("./data/sbb_data.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out_path, index=False, sep=";")
    print(f"[OK] {len(rows)} Zeilen geschrieben nach {out_path}")


if __name__ == "__main__":
    main()

