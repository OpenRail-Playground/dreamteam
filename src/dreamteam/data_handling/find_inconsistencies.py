"""
find_inconsistencies.py

Finds inconsistent train rides across one or more CSV files.

Stops are identified by HaltID, which is consistent across all sources.
Rides are grouped by ReiseID.

Usage:
    python find_inconsistencies.py sbb_data.csv oebb_data.csv db_data.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


# ------------------------------ Data classes ------------------------------

@dataclass(frozen=True)
class Stop:
    name: str
    halt_id: str
    arrival: str | None
    departure: str | None
    date: str
    source: str


@dataclass
class Ride:
    ride_id: str
    train: str
    start_date: str
    source: str
    stops: list[Stop] = field(default_factory=list)

    def stop_sequence(self) -> tuple[str, ...]:
        return tuple(s.halt_id for s in self.stops)


# -------------------------------- Loading --------------------------------

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_rides(path: Path) -> list[Ride]:
    source = path.name
    ride_map: dict[str, Ride] = {}
    rides: list[Ride] = []

    with open(path, encoding="utf-8", newline="") as f:
        sample = f.readline()
    delimiter = ";" if ";" in sample else "\t"

    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            date = row.get("Datum", "").strip()
            if not DATE_RE.match(date):
                continue
            train    = row.get("Zugnummer", "").strip()
            name     = row.get("Halt", "").strip()
            arr      = row.get("an", "").strip() or None
            dep      = row.get("ab", "").strip() or None
            reise_id = row.get("ReiseID", "").strip()
            halt_id  = row.get("HaltID", "").strip() or name

            ride_key = reise_id or f"{train}-{date}-{source}"
            if ride_key not in ride_map:
                ride = Ride(ride_id=ride_key, train=train, start_date=date, source=source)
                ride_map[ride_key] = ride
                rides.append(ride)

            ride_map[ride_key].stops.append(Stop(
                name=name, halt_id=halt_id,
                arrival=arr, departure=dep,
                date=date, source=source,
            ))
    return rides


# -------------------------------- Checks ---------------------------------

@dataclass
class Issue:
    kind: str
    primary_key: str  # Datum;Zugnummer;first_HaltID
    detail: str
    ride_ids: list[str]


def find_sequence_inconsistencies(rides: list[Ride]) -> list[Issue]:
    # Group by (Datum, Zugnummer, HaltID of first stop)
    by_key: dict[str, list[Ride]] = defaultdict(list)
    for r in rides:
        if not r.stops:
            continue
        pk = f"{r.start_date};{r.train};{r.stops[0].halt_id}"
        by_key[pk].append(r)

    issues: list[Issue] = []
    for pk, group in by_key.items():
        seqs: dict[tuple[str, ...], list[str]] = defaultdict(list)
        for r in group:
            seqs[r.stop_sequence()].append(r.ride_id)
        if len(seqs) <= 1:
            continue
        issues.append(Issue(
            kind="sequence_mismatch",
            primary_key=pk,
            detail=f"{len(seqs)} different stop sequences found",
            ride_ids=[rid for ids in seqs.values() for rid in ids],
        ))
    return issues


def find_time_inconsistencies(rides: list[Ride]) -> list[Issue]:
    issues: list[Issue] = []
    for ride in rides:
        prev_dt = None
        prev_lbl = None
        for s in ride.stops:
            for lbl, t in (("arr", s.arrival), ("dep", s.departure)):
                if t is None:
                    continue
                dt = f"{s.date} {t}"
                if prev_dt is not None and dt < prev_dt:
                    issues.append(Issue(
                        kind="time_not_monotonic",
                        primary_key=f"{ride.start_date};{ride.train};{ride.stops[0].halt_id if ride.stops else ''}",
                        detail=(f"In {ride.ride_id}: {prev_lbl} at {prev_dt} "
                                f"is after {s.name} {lbl} at {dt}"),
                        ride_ids=[ride.ride_id],
                    ))
                prev_dt, prev_lbl = dt, f"{s.name} {lbl}"
    return issues


# ---------------------------------- CLI ----------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Find inconsistent train rides across CSV files."
    )
    ap.add_argument("files", nargs="*",
                    default=["sbb_data.csv", "oebb_data.csv", "db_data.csv"],
                    help="CSV files (default: sbb_data.csv oebb_data.csv db_data.csv)")
    ap.add_argument("--data-dir", default="./data",
                    help="Directory to look for files in (default: ./data)")
    args = ap.parse_args(argv)

    data_dir = Path(args.data_dir)
    resolved_files = [
        Path(f) if Path(f).is_absolute() or "/" in f or "\\" in f else data_dir / f
        for f in args.files
    ]

    all_rides: list[Ride] = []
    for f in resolved_files:
        rides = load_rides(f)
        print(f"  {f}: {len(rides)} ride(s), "
              f"{sum(len(r.stops) for r in rides)} stop(s)")
        all_rides.extend(rides)
    print(f"Total: {len(all_rides)} ride(s)\n")

    ride_by_id = {r.ride_id: r for r in all_rides}  # noqa: F841 (reserved for future use)
    seq_issues  = find_sequence_inconsistencies(all_rides)
    time_issues = find_time_inconsistencies(all_rides)

    def print_section(title, issues):
        print(f"=== {title} ({len(issues)}) ===")
        for i, iss in enumerate(issues, 1):
            print(f"[{i}] {iss.primary_key}")
        print()

    print_section("Sequence inconsistencies", seq_issues)
    print_section("Time inconsistencies",     time_issues)

    total = len(seq_issues) + len(time_issues)
    if total == 0:
        print("✅ No inconsistencies found.")
        return 0
    print(f"⚠️  Found {total} inconsistency/inconsistencies.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

