import os
from datetime import datetime, timedelta

import pandas as pd
import requests
import yaml

FIND_URL = "https://apis.deutschebahn.com/db/apis/ris-journeys/v2/find"
JOURNEY_URL = "https://apis.deutschebahn.com/db/apis/ris-journeys/v2/"
PLACES_URL = "https://apis.deutschebahn.com/db/apis/ris-stations/v1/stop-places/"
LAST_N_DAYS = 7


def get_headers():
    return {
        "db-client-id": os.environ.get("DB_CLIENT_ID", ""),
        "db-api-key": os.environ.get("DB_CLIENT_KEY", ""),
    }

def get_places_headers():
    return {
        "db-client-id": os.environ.get("DB_CLIENT_ID_PLACES", ""),
        "db-api-key": os.environ.get("DB_CLIENT_KEY_PLACES", ""),
    }


def fmt_time(event):
    if event is None:
        return None
    return datetime.fromisoformat(event["time"]).strftime("%H:%M")


def fmt_date(event):
    return datetime.fromisoformat(event["time"]).strftime("%Y-%m-%d")


def group_events_by_stop(events):
    stops = {}
    for event in events:
        eva = event["stopPlace"]["evaNumber"]
        if eva not in stops:
            stops[eva] = {"name": event["stopPlace"]["name"], "ARRIVAL": None, "DEPARTURE": None}
        stops[eva][event["type"]] = event
    return stops


def fetch_rows_for_journey(journey, headers, querystring, gattung, flügel):
    response = requests.get(JOURNEY_URL + journey["journeyID"], headers=headers, params=querystring)
    journey_data = response.json()
    places_header = get_places_headers()
    stops = group_events_by_stop(journey_data["events"])
    rows = []
    for stop in stops.values():
        eva_number = stop["ARRIVAL"]["stopPlace"]["evaNumber"] if stop["ARRIVAL"] else stop["DEPARTURE"]["stopPlace"]["evaNumber"]
        requested_stop = requests.get(PLACES_URL + eva_number + '/keys', headers=places_header)
        requested_stop = requested_stop.json()  # We can use this if we need more details about the stop in the future
        arrival = stop["ARRIVAL"]
        departure = stop["DEPARTURE"]
        ref = arrival if arrival else departure
        rows.append({
            "Datum":     fmt_date(ref),
            "Zugnummer": f"{gattung} {flügel}",
            "Halt":      stop["name"],
            "an":        fmt_time(arrival),
            "ab":        fmt_time(departure),
            "ReiseID":   journey["journeyID"],
            "HaltID": next((k["key"] for k in requested_stop.get("keys", []) if k["type"] == "UIC"), eva_number)
        })
    return rows


def fetch_rows_for_date(date_str, unique_combinations, headers, seen_journey_ids: set):
    rows = []
    for _, row in unique_combinations.iterrows():
        querystring = {"date": date_str, "journeyNumber": row["Flügel"], "category": row["Gattung"]}
        response = requests.get(FIND_URL, headers=headers, params=querystring).json()
        for journey in response.get("journeys", []):
            jid = journey["journeyID"]
            if jid in seen_journey_ids:
                continue
            seen_journey_ids.add(jid)
            rows.extend(fetch_rows_for_journey(journey, headers, querystring, row["Gattung"], row["Flügel"]))
    return rows


def main():
    with open("config.yaml", "r") as f:
        yaml.safe_load(f)  # reserved for future config use

    all_trains = pd.read_csv("./data/NJ_List.csv", delimiter=";", header=0)
    unique_combinations = all_trains[["Gattung", "Flügel"]].drop_duplicates()
    headers = get_headers()

    today = datetime.today()
    dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, LAST_N_DAYS + 1)]

    rows = []
    seen_journey_ids: set = set()
    for date_str in dates:
        rows.extend(fetch_rows_for_date(date_str, unique_combinations, headers, seen_journey_ids))

    pd.DataFrame(rows).to_csv("./data/db_data.csv", index=False, sep=";")


if __name__ == "__main__":
    main()