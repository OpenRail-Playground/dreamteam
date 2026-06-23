"""Flask backend for the Fahrplan-Diskrepanz-Analyzer."""

import os
import csv
from datetime import datetime
from flask import Flask, jsonify, send_file
from pathlib import Path

app = Flask(__name__)

# Get the directory where CSV files are stored
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "sample_data"
ANALYZER_HTML = BASE_DIR / "analyzer.html"


def load_csv(filename):
    """Load a CSV file and return as list of dictionaries."""
    filepath = DATA_DIR / filename
    if not filepath.exists():
        return []
    
    data = []
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        # Detect delimiter
        sample = f.read(1024)
        f.seek(0)
        delimiter = ';' if ';' in sample else ','
        
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            data.append(row)
    
    return data


def get_trains_with_discrepancies():
    """Extract train discrepancies from Zuglaeufe.csv, enriched with route and ARES data."""
    zuglaeufe = load_csv("Zuglaeufe.csv")
    zugnummern = load_csv("Zugnummern.csv")
    ares = load_csv("ARES.csv")

    # Build route lookup: key = "Zugnummer_YYYY-MM-DD"
    # Zugnummern dates are in DD.MM.YYYY format
    route_lookup = {}
    for row in zugnummern:
        datum_str = row.get("Datum", "").strip()
        zugnummer = row.get("Zugnummer", "").strip()
        try:
            d, m, y = datum_str.split(".")
            datum_iso = f"{y}-{m}-{d}"
        except ValueError:
            datum_iso = datum_str
        route_lookup[f"{zugnummer}_{datum_iso}"] = {
            "start": row.get("Startbahnhof", "").strip(),
            "end": row.get("Zielbahnhof", "").strip()
        }

    # Build ARES remarks lookup: key = "Zug_YYYY-MM-DD" (matched by date range)
    # A single ARES entry can span start_date to end_date
    ares_by_train = {}
    for row in ares:
        zug = row.get("Zug", "").strip()
        start_date = row.get("start_date", "").strip()
        end_date = row.get("end_date", "").strip()
        bemerkung = row.get("Bemerkung", "").strip()
        if zug and start_date and bemerkung:
            if zug not in ares_by_train:
                ares_by_train[zug] = []
            ares_by_train[zug].append({
                "start_date": start_date,
                "end_date": end_date or start_date,
                "bemerkung": bemerkung
            })

    def get_ares_remarks(zugnummer, datum_iso):
        """Return ARES Bemerkung entries whose date range covers the given date."""
        remarks = []
        for entry in ares_by_train.get(zugnummer, []):
            if entry["start_date"] <= datum_iso <= entry["end_date"]:
                remarks.append(entry["bemerkung"])
        return list(dict.fromkeys(remarks))  # deduplicate, preserve order

    def detect_outlier_operators(times_by_operator):
        """Return operators whose time is a unique outlier against a shared majority."""
        value_counts = {}
        for _, value in times_by_operator.items():
            if not value:
                continue
            value_counts[value] = value_counts.get(value, 0) + 1

        if len(value_counts) <= 1:
            return []

        majority_value = None
        majority_count = 0
        for value, count in value_counts.items():
            if count > majority_count:
                majority_value = value
                majority_count = count

        if majority_count < 2:
            return []

        return [
            operator for operator, value in times_by_operator.items()
            if value and value != majority_value and value_counts.get(value, 0) == 1
        ]

    # Build discrepancies from rows where Stats_ARES != "OK"
    trains = {}
    for row in zuglaeufe:
        stats = row.get("Stats_ARES", "").strip()
        if stats == "OK":
            continue

        zugnummer = row.get("Zugnummer", "").strip()
        datum = row.get("Datum", "").strip()
        halt = row.get("Halt", "").strip()
        key = f"{zugnummer}_{datum}"

        if key not in trains:
            route = route_lookup.get(key, {})
            trains[key] = {
                "zugnummer": zugnummer,
                "datum": datum,
                "start_station": route.get("start", ""),
                "end_station": route.get("end", ""),
                "discrepancies": []
            }

        # Determine which operators are missing times for this stop
        an_sbb = row.get("an_sbb", "").strip()
        ab_sbb = row.get("ab_sbb", "").strip()
        an_oebb = row.get("an_oebb", "").strip()
        ab_oebb = row.get("ab_oebb", "").strip()
        an_db = row.get("an_db", "").strip()
        ab_db = row.get("ab_db", "").strip()

        missing = [
            op for op, has in [
                ("SBB", bool(an_sbb or ab_sbb)),
                ("ÖBB", bool(an_oebb or ab_oebb)),
                ("DB",  bool(an_db or ab_db))
            ] if not has
        ]

        mismatch_entries = []
        arrival_outliers = detect_outlier_operators({
            "SBB": an_sbb,
            "ÖBB": an_oebb,
            "DB": an_db,
        })
        for operator in arrival_outliers:
            mismatch_entries.append({
                "source": operator,
                "text": f"Halt <strong>{halt}</strong>: Mismatch in die {operator} Ankunft Zeit.",
            })

        departure_outliers = detect_outlier_operators({
            "SBB": ab_sbb,
            "ÖBB": ab_oebb,
            "DB": ab_db,
        })
        for operator in departure_outliers:
            mismatch_entries.append({
                "source": operator,
                "text": f"Halt <strong>{halt}</strong>: Mismatch in die {operator} Abfahrt Zeit.",
            })

        if mismatch_entries:
            for entry in mismatch_entries:
                trains[key]["discrepancies"].append({
                    "date": datum,
                    "halt": halt,
                    "source": entry["source"],
                    "text": entry["text"],
                    "stats": stats,
                    "ares_remarks": get_ares_remarks(zugnummer, datum)
                })
        else:
            source = ", ".join(missing) if missing else "ARES"
            if missing:
                text = (f"Halt <strong>{halt}</strong>: "
                        f"Keine Zeitdaten bei {', '.join(missing)}.")
            else:
                text = f"Halt <strong>{halt}</strong>:"

            trains[key]["discrepancies"].append({
                "date": datum,
                "halt": halt,
                "source": source,
                "text": text,
                "stats": stats,
                "ares_remarks": get_ares_remarks(zugnummer, datum)
            })

    return list(trains.values())


@app.route('/', methods=['GET'])
def index():
    """Serve the main analyzer HTML page."""
    if ANALYZER_HTML.exists():
        return send_file(ANALYZER_HTML, mimetype='text/html')
    return jsonify({"error": "analyzer.html not found"}), 404


@app.route('/api/discrepancies-by-train', methods=['GET'])
def discrepancies_by_train():
    """Get discrepancies grouped by train."""
    trains = get_trains_with_discrepancies()
    
    result = []
    for train in trains:
        if train["discrepancies"]:
            result.append({
                "train_id": train["zugnummer"],
                "route": f"{train['start_station']} → {train['end_station']}",
                "discrepancy_count": len(train["discrepancies"]),
                "discrepancies": train["discrepancies"]
            })
    
    return jsonify(result)


@app.route('/api/discrepancies-by-day', methods=['GET'])
def discrepancies_by_day():
    """Get discrepancies grouped by day."""
    trains = get_trains_with_discrepancies()
    
    days = {}
    for train in trains:
        if train["discrepancies"]:
            date_key = train["datum"]
            if date_key not in days:
                days[date_key] = {
                    "date": date_key,
                    "train_count": 0,
                    "trains": []
                }
            
            days[date_key]["trains"].append({
                "train_id": train["zugnummer"],
                "route": f"{train['start_station']} → {train['end_station']}",
                "discrepancies": train["discrepancies"]
            })
            days[date_key]["train_count"] = len(days[date_key]["trains"])
    
    # Sort by date and return as list
    result = sorted(days.values(), key=lambda x: x["date"], reverse=True)
    return jsonify(result)


@app.route('/api/archive', methods=['GET'])
def get_archive():
    """Get archived (resolved) discrepancies."""
    # Placeholder - could be stored in database
    return jsonify([])


@app.route('/api/dataload-history', methods=['GET'])
def dataload_history():
    """Get dataload history."""
    trains = get_trains_with_discrepancies()
    total_trains = len(set(t["zugnummer"] for t in trains))
    total_discrepancies = sum(len(t["discrepancies"]) for t in trains)
    
    return jsonify([
        {
            "id": 2451,
            "timestamp": "23.06.2026, 11:42:17",
            "triggered_by": "Automatisch (Cron)",
            "trains_checked": total_trains,
            "discrepancies_found": total_discrepancies,
            "affected_days": len(set(t["datum"] for t in trains)),
            "sources": ["NeTS-AT", "CIS", "Hafas"]
        }
    ])


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get overall statistics."""
    trains = get_trains_with_discrepancies()
    total_trains = len(set(t["zugnummer"] for t in trains))
    total_discrepancies = sum(len(t["discrepancies"]) for t in trains)
    affected_trains = len([t for t in trains if t["discrepancies"]])
    
    return jsonify({
        "total_trains": total_trains,
        "total_discrepancies": total_discrepancies,
        "affected_trains": affected_trains,
        "affected_days": len(set(t["datum"] for t in trains)),
        "last_dataload": datetime.now().strftime("%d.%m.%Y, %H:%M")
    })


if __name__ == '__main__':
    app.run(debug=True, port=5000)
