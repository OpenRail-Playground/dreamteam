# Dreamteam

This is an App that helps the people responsible for night trains to check if the ARES booking system is in sync with the timetable data of different train compainies (SBB, ÖBB and DB).


# Installation

We use uv as a package manager. You can install the package with "uv venv" and then "venv sync" once venv is installed.
# Data Folder:
This project has been initiated during the [Hack4Rail 2026](https://hack4rail.org/), a joint hackathon organised by the railway companies SBB, ÖBB, and DB in partnership with the OpenRail Association.

## API Access & Data Loading

The project fetches live timetable data from three railway APIs: **DB (Deutsche Bahn)**, **ÖBB**, and **SBB**. Each loader reads train numbers from `data/NJ_List.csv` and writes results to `data/<operator>_data.csv`.

---

### DB (Deutsche Bahn)

**Auth:** API key passed via request headers. Set the following environment variables:

| Variable | Description |
|---|---|
| `DB_CLIENT_ID` | Client ID for the RIS Journeys API |
| `DB_CLIENT_KEY` | API key for the RIS Journeys API |
| `DB_CLIENT_ID_PLACES` | Client ID for the RIS Stations API |
| `DB_CLIENT_KEY_PLACES` | API key for the RIS Stations API |

**Endpoints:**

1. `GET https://apis.deutschebahn.com/db/apis/ris-journeys/v2/find`  
   Params: `date`, `journeyNumber`, `category`  
   Finds journey IDs for a given train and date.

2. `GET https://apis.deutschebahn.com/db/apis/ris-journeys/v2/{journeyID}`  
   Fetches stop events (arrival/departure) for a specific journey.

3. `GET https://apis.deutschebahn.com/db/apis/ris-stations/v1/stop-places/{evaNumber}/keys`  
   Resolves a stop's EVA number to a UIC stop ID.

**Run:** `python -m src.dreamteam.data_handling.load_db_data`

---

### ÖBB

**Auth:** API Gateway key passed via the `x-Gateway-APIKey` header. Set:

| Variable | Description |
|---|---|
| `OEBB_API_KEY` | ÖBB API Gateway key |
| `OEBB_BASE_URL` | Base URL (default: `https://api-gateway.oebb.at/gateway/Hafas-API/active`) |
| `DB_CLIENT_ID_PLACES` | Shared with DB — used for UIC stop ID lookup |
| `DB_CLIENT_KEY_PLACES` | Shared with DB — used for UIC stop ID lookup |

**Endpoints:**

1. `GET {base}/trainSearch`  
   Params: `match` (e.g. `NJ 470`), `date`, `format=json`  
   Returns a list of journeys with a `ref` ID and `dayOfOperation`.

2. `GET {base}/journeyDetail`  
   Params: `id` (the `ref` from step 1), `date`, `format=json`  
   Returns full stop list with `arrTime`/`depTime` per stop.

> **Note:** Do not pre-encode the `id` parameter — `requests` handles encoding automatically to avoid double-encoding errors.

**Run:** `python -m src.dreamteam.data_handling.load_oebb_data`

---

### SBB

**Auth:** OAuth2 Client Credentials flow against Azure AD. An access token is fetched automatically at startup. Set:

| Variable | Description |
|---|---|
| `SBB_CLIENT_ID` | OAuth2 client ID |
| `SBB_CLIENT_SECRET` | OAuth2 client secret |
| `SBB_TOKEN_URL` | Token endpoint (default: Azure AD tenant token URL) |
| `SBB_SCOPE` | OAuth2 scope (default: `api://journey-service.int/.default`) |
| `SBB_BASE_URL` | Base URL (default: `https://journey-service-int.api.sbb.ch`) |

**Endpoints:**

1. `GET {base}/v3/vehicle-journeys/by-service/{serviceProductReference}`  
   Params: `date`  
   The `serviceProductReference` is formatted as `<Gattung> - <Nummer>` (e.g. `NJ - 470`).  
   Returns `datedVehicleJourneys[*].serviceJourney.id`.

2. `GET {base}/v3/vehicle-journeys/{id}`  
   Returns full stop-point list with `arrival.timeAimed` / `departure.timeAimed` per stop.

**Run:** `python -m src.dreamteam.data_handling.load_sbb_data`

---

### Output Format

All three loaders produce a semicolon-delimited CSV with the following columns:

| Column | Description |
|---|---|
| `Datum` | Date of operation (`YYYY-MM-DD`) |
| `Zugnummer` | Train identifier (e.g. `NJ 470`) |
| `Halt` | Stop name |
| `an` | Scheduled arrival (`HH:MM`) |
| `ab` | Scheduled departure (`HH:MM`) |
| `ReiseID` | Internal journey ID from the source API |
| `HaltID` | UIC stop identifier |

By default, data is fetched for the **next 7 days** from the current date.

---

## Install

<!-- TODO: Explain how a user can install the software -->

## License

<!-- If you decide for another license, please change it here, and exchange the LICENSE file -->

The content of this repository is licensed under the [Apache 2.0 license](LICENSE).

Data is placed in the folder "data", which is included in the .gitignore file of the repository so no data should be commited to the repo!