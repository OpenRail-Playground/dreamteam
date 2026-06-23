import pandas as pd
import os
import yaml
import requests
from datetime import datetime

# Load all sheets from the Excel file into a dictionary of DataFrames
all_trains = pd.read_csv("./data/NJ_List.csv", delimiter=";", header=0)
unique_combinations = all_trains[["Gattung", "Stamm"]].drop_duplicates()



url = "https://apis.deutschebahn.com/db/apis/ris-journeys/v2/find"
journey_url = "https://apis.deutschebahn.com/db/apis/ris-journeys/v2/"



rows = []
# Load the configuration from the YAML file
with open("config.yaml", "r") as file:
    config = yaml.safe_load(file)

for index, row in unique_combinations.iterrows():

        querystring = {"date":"2026-06-22","journeyNumber":row["Stamm"],"category":row["Gattung"]}
        headers = {
            "db-client-id": os.environ.get("DB_CLIENT_ID",""),
            "db-api-key": os.environ.get("DB_CLIENT_KEY","")
        }
        journeys_response = requests.get(url, headers=headers, params=querystring)
        journeys_response= journeys_response.json()
        if journeys_response.get("journeys"):
            journeys = journeys_response.get("journeys")
            for journey in journeys:

                journey_response = requests.get(journey_url + journey["journeyID"], headers=headers, params=querystring)
                journey_response = journey_response.json()


                # Group events by stop (evaNumber)
                stops = {}
                for event in journey_response['events']:
                    eva = event['stopPlace']['evaNumber']
                    if eva not in stops:
                        stops[eva] = {'name': event['stopPlace']['name'], 'ARRIVAL': None, 'DEPARTURE': None}
                    stops[eva][event['type']] = event

                # Build rows
                for eva, stop in stops.items():
                    arrival = stop['ARRIVAL']
                    departure = stop['DEPARTURE']

                    # Get reference event (either arrival or departure)
                    ref = arrival if arrival else departure

                    # Extract time (only time part HH:MM)
                    def fmt_time(event):
                        if event is None:
                            return None
                        return datetime.fromisoformat(event['time']).strftime('%H:%M')

                    def fmt_date(event):
                        return datetime.fromisoformat(event['time']).strftime('%Y-%m-%d')

                    rows.append({
                        'Datum':       fmt_date(ref),
                        'Zugnummer':   f"{row['Gattung']} {row['Stamm']}",
                        'Halt':        stop['name'],
                        'an':          fmt_time(arrival),
                        'ab':          fmt_time(departure),
                    })

rows_df = pd.DataFrame(rows)
rows_df.to_csv("./data/db_data.csv", index=False, sep=";")