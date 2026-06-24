"""extract_endpoints.py

Reads the merged train-stop CSVs (db_data.csv, oebb_data.csv, sbb_data.csv)
and produces a summary CSV with one row per (Datum, Zugnummer) containing
only the start and end stop with their corresponding times.

Output: ./data/endpoints.csv
Columns: Datum;Zugnummer;StartHalt;Abfahrt;EndHalt;Ankunft
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

SOURCE_FILES = [
    (Path("./data/db_data.csv"),   "DB"),
    (Path("./data/oebb_data.csv"), "OEBB"),
    (Path("./data/sbb_data.csv"),  "SBB"),
]

OUTPUT_FILE = Path("./data/endpoints.csv")


def load_sources(paths: list[tuple[Path, str]]) -> pd.DataFrame:
    frames = []
    for p, anbieter in paths:
        if p.exists():
            df = pd.read_csv(p, delimiter=";", header=0, dtype=str)
            df["Anbieter"] = anbieter
            frames.append(df)
        else:
            print(f"[WARN] {p} not found, skipping.")
    if not frames:
        raise FileNotFoundError("No source CSV files found.")
    return pd.concat(frames, ignore_index=True)


def extract_endpoints(df: pd.DataFrame) -> pd.DataFrame:
    # Normalize: empty strings -> NaN
    df["an"] = df["an"].replace("", pd.NA)
    df["ab"] = df["ab"].replace("", pd.NA)

    rows = []
    for reise_id, group in df.groupby("ReiseID", sort=False):
        group = group.reset_index(drop=True)
        first = group.iloc[0]

        start_rows = group[group["ab"].notna()]
        end_rows   = group[group["an"].notna()]

        if start_rows.empty or end_rows.empty:
            continue

        rows.append(
            {
                "Datum":      first["Datum"],
                "Zugnummer":  first["Zugnummer"],
                "StartHalt":  start_rows.iloc[0]["Halt"],
                "StartHaltID": start_rows.iloc[0]["HaltID"],
                "Abfahrt":    start_rows.iloc[0]["ab"],
                "EndHalt":    end_rows.iloc[-1]["Halt"],
                "EndHaltID":  end_rows.iloc[-1]["HaltID"],
                "Ankunft":    end_rows.iloc[-1]["an"],
                "Anbieter":   first["Anbieter"],
            }
        )

    result = pd.DataFrame(rows, columns=["Datum", "Zugnummer", "StartHalt", "StartHaltID", "Abfahrt", "EndHalt", "EndHaltID", "Ankunft", "Anbieter"])
    return result.sort_values(["Datum", "Zugnummer", "StartHaltID", "Anbieter"]).reset_index(drop=True)


def main() -> None:
    df = load_sources(SOURCE_FILES)
    endpoints = extract_endpoints(df)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    endpoints.to_csv(OUTPUT_FILE, index=False, sep=";", encoding="utf-8")
    print(f"[OK] {len(endpoints)} rows written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
