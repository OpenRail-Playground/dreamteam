"""
find_inconsistencies.py

Finds inconsistent train rides across one or more TSV files.

Input format (tab-separated, no header):
    date <TAB> train_number <TAB> stop_name <TAB> arrival <TAB> departure

Usage:
    python find_inconsistencies.py sbb_data.csv oebb_data.csv db_data.csv
    python find_inconsistencies.py *.csv --show-variants
    python find_inconsistencies.py *.csv --fuzzy-threshold 0.90
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path


# --------------------------- Name normalization ---------------------------

STRIP_TOKENS = {"bahnhof", "bhf", "station", "gare", "stazione", "hbf", "hb"}

DEFAULT_STOP_MAPPING: dict[str, str] = {
    "Spittal-Millstättersee": "Spittal-Millstättersee",
    "Spittal/Drau-Millstätter See Bahnhof": "Spittal-Millstättersee",
    "Schwarzach-St.Veit": "Schwarzach-St.Veit",
    "Schwarzach im Pongau-St.Veit Bahnhof": "Schwarzach-St.Veit",
    "Mallnitz-Obervellach": "Mallnitz-Obervellach",
    "Mallnitz-Obervellach Bahnhof": "Mallnitz-Obervellach",
    "Bad Gastein": "Bad Gastein",
    "Bad Gastein Bahnhof": "Bad Gastein",
    "Zürich HB": "Zürich HB",
    "Zurich HB": "Zürich HB",
    "Zürich Hauptbahnhof": "Zürich HB",
    "Genève": "Genève",
    "Geneva": "Genève",
    "Genf": "Genève",
}


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if unicodedata.category(c) != "Mn")


def normalize_name(name: str) -> str:
    n = _strip_accents(name).lower()
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    tokens = [t for t in n.split() if t not in STRIP_TOKENS]
    return " ".join(tokens).strip()


class StopNameResolver:
    def __init__(self, mapping=None, fuzzy_threshold=0.85):
        raw = mapping if mapping is not None else DEFAULT_STOP_MAPPING
        self._mapping = {normalize_name(k): v for k, v in raw.items()}
        for canonical in set(raw.values()):
            self._mapping.setdefault(normalize_name(canonical), canonical)
        self._fuzzy_threshold = fuzzy_threshold
        self._cache: dict[str, str] = {}

    def resolve(self, raw_name: str) -> str:
        if raw_name in self._cache:
            return self._cache[raw_name]
        norm = normalize_name(raw_name)
        if norm in self._mapping:
            result = self._mapping[norm]
        else:
            best, best_score = None, 0.0
            for known_norm, canonical in self._mapping.items():
                score = SequenceMatcher(None, norm, known_norm).ratio()
                if score > best_score:
                    best, best_score = canonical, score
            if best and best_score >= self._fuzzy_threshold:
                result = best
            else:
                result = " ".join(w.capitalize() for w in norm.split()) or raw_name
                self._mapping[norm] = result
        self._cache[raw_name] = result
        return result


# ------------------------------ Data classes ------------------------------

@dataclass(frozen=True)
class Stop:
    name: str
    raw_name: str
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
        return tuple(s.name for s in self.stops)


# -------------------------------- Loading --------------------------------

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_rides(path: Path, resolver: StopNameResolver) -> list[Ride]:
    rides: list[Ride] = []
    current: Ride | None = None
    source = path.name

    # Detect delimiter from the first line
    with open(path, encoding="utf-8", newline="") as f:
        sample = f.readline()
    delimiter = ";" if ";" in sample else "\t"

    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        for row in reader:
            cells = [c.strip() for c in row]
            while cells and cells[0] == "":
                cells.pop(0)
            if len(cells) < 3:
                continue
            cells += [""] * (5 - len(cells))
            date, train, stop_name, arr, dep = cells[:5]
            if not DATE_RE.match(date):
                continue

            prev_stop_is_terminal = (
                current is not None
                and current.stops
                and current.stops[-1].departure is None
            )
            start_new = (
                current is None
                or current.train != train
                or (arr == "" and dep != "" and prev_stop_is_terminal)
            )
            if start_new:
                current = Ride(
                    ride_id=f"{train}-{date}-{source}",
                    train=train, start_date=date, source=source,
                )
                rides.append(current)

            current.stops.append(Stop(
                name=resolver.resolve(stop_name),
                raw_name=stop_name,
                arrival=arr or None,
                departure=dep or None,
                date=date, source=source,
            ))
    return rides


# -------------------------------- Checks ---------------------------------

@dataclass
class Issue:
    kind: str
    train: str
    detail: str
    ride_ids: list[str]


def _seq_diff(a, b):
    parts = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b).get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            parts.append(f"replace {list(a[i1:i2])} -> {list(b[j1:j2])}")
        elif tag == "delete":
            parts.append(f"only in A: {list(a[i1:i2])}")
        elif tag == "insert":
            parts.append(f"only in B: {list(b[j1:j2])}")
    return "; ".join(parts) or "(identical)"


def find_sequence_inconsistencies(rides):
    by_train: dict[str, list[Ride]] = defaultdict(list)
    for r in rides:
        by_train[r.train].append(r)

    issues: list[Issue] = []
    for train, group in by_train.items():
        seqs: dict[tuple[str, ...], list[str]] = defaultdict(list)
        for r in group:
            seqs[r.stop_sequence()].append(r.ride_id)
        if len(seqs) <= 1:
            continue
        ref_seq, ref_ids = max(seqs.items(), key=lambda kv: len(kv[1]))
        for seq, ids in seqs.items():
            if seq == ref_seq:
                continue
            issues.append(Issue(
                kind="sequence_mismatch",
                train=train,
                detail=(f"Reference ({len(ref_ids)} ride(s), e.g. {ref_ids[0]}):\n"
                        f"    {list(ref_seq)}\n"
                        f"  Variant ({len(ids)} ride(s)):\n"
                        f"    {list(seq)}\n"
                        f"  Diff: {_seq_diff(ref_seq, seq)}"),
                ride_ids=ids,
            ))
    return issues


def find_time_inconsistencies(rides):
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
                        train=ride.train,
                        detail=(f"In {ride.ride_id}: {prev_lbl} at {prev_dt} "
                                f"is after {s.name} {lbl} at {dt}"),
                        ride_ids=[ride.ride_id],
                    ))
                prev_dt, prev_lbl = dt, f"{s.name} {lbl}"
    return issues


def find_name_variants(rides):
    variants: dict[str, set[str]] = defaultdict(set)
    for r in rides:
        for s in r.stops:
            variants[s.name].add(s.raw_name)
    issues = []
    for canonical, raws in sorted(variants.items()):
        if len(raws) > 1:
            issues.append(Issue(
                kind="name_variant",
                train="*",
                detail=f"{canonical!r} appears as: {sorted(raws)}",
                ride_ids=[],
            ))
    return issues


# ---------------------------------- CLI ----------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Find inconsistent train rides across TSV files."
    )
    ap.add_argument("files", nargs="*",
                    default=["sbb_data.csv", "oebb_data.csv", "db_data.csv"],
                    help="TSV files (default: sbb_data.csv oebb_data.csv db_data.csv)")
    ap.add_argument("--data-dir", default="./data",
                    help="Directory to look for files in when no path is given (default: ./data)")
    ap.add_argument("--fuzzy-threshold", type=float, default=0.85,
                    help="Similarity threshold (0..1) for fuzzy name matching")
    ap.add_argument("--show-variants", action="store_true",
                    help="Also list raw names merged into the same canonical name")
    args = ap.parse_args(argv)

    data_dir = Path(args.data_dir)
    resolved_files = [
        Path(f) if Path(f).is_absolute() or "/" in f or "\\" in f else data_dir / f
        for f in args.files
    ]

    resolver = StopNameResolver(fuzzy_threshold=args.fuzzy_threshold)

    all_rides: list[Ride] = []
    for f in resolved_files:
        rides = load_rides(Path(f), resolver)
        print(f"  {f}: {len(rides)} ride(s), "
              f"{sum(len(r.stops) for r in rides)} stop(s)")
        all_rides.extend(rides)
    print(f"Total: {len(all_rides)} ride(s)\n")

    ride_by_id: dict[str, Ride] = {r.ride_id: r for r in all_rides}

    seq_issues = find_sequence_inconsistencies(all_rides)
    time_issues = find_time_inconsistencies(all_rides)
    variant_issues = find_name_variants(all_rides) if args.show_variants else []

    def print_rows(ride: Ride) -> None:
        print(f"    {'Date':<12} {'Train':<12} {'Stop':<35} {'Arr':>5}  {'Dep':>5}")
        for s in ride.stops:
            print(f"    {s.date:<12} {ride.train:<12} {s.raw_name:<35} {s.arrival or '':>5}  {s.departure or '':>5}")

    def print_section(title, issues):
        print(f"=== {title} ({len(issues)}) ===")
        for i, iss in enumerate(issues, 1):
            print(f"\n[{i}] train={iss.train}")
            print(f"    {iss.detail}")
            for ride_id in iss.ride_ids:
                ride = ride_by_id.get(ride_id)
                if ride:
                    print(f"\n    Rows for {ride_id}:")
                    print_rows(ride)
        print()

    print_section("Sequence inconsistencies", seq_issues)
    print_section("Time inconsistencies", time_issues)
    if args.show_variants:
        print_section("Name variants merged", variant_issues)

    total = len(seq_issues) + len(time_issues)
    if total == 0:
        print("✅ No inconsistencies found.")
        return 0
    print(f"⚠️  Found {total} inconsistency/inconsistencies.")
    return 1


if __name__ == "__main__":
    main()
