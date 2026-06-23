import pandas as pd
import os
import yaml
import requests

# Load all sheets from the Excel file into a dictionary of DataFrames
all_trains = pd.read_csv("./data/NJ_List.csv", delimiter=";", header=0)
unique_combinations = all_trains[["Gattung", "Stamm"]].drop_duplicates()



url = "https://apis.deutschebahn.com/db/apis/ris-journeys/v2/find"




# Load the configuration from the YAML file
with open("config.yaml", "r") as file:
    config = yaml.safe_load(file)

for index, row in unique_combinations.iterrows():

        querystring = {"date":"2026-06-22","journeyNumber":row["Stamm"],"category":row["Gattung"]}
        headers = {
            "db-client-id": os.environ.get("DB_CLIENT_ID",""),
            "db-api-key": os.environ.get("DB_CLIENT_KEY","")
        }
        response = requests.get(url, headers=headers, params=querystring)
        response= response.json()
        if response.get("journeys"):
            train = response["journeys"][0]["train"]["name"]
            df = pd.DataFrame(response["journeys"][0]["stops"])