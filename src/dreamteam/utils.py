from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
import re
import unicodedata

import pandas as pd


def _strip_accents(value: str) -> str:
    value = value.replace("ß", "ss")
    value = unicodedata.normalize("NFKD", value)
    return "".join(char for char in value if not unicodedata.combining(char))


def _normalize_station_name(name: str) -> str:
    normalized = _strip_accents(name.strip().lower())
    normalized = re.sub(r"\([^)]*\)", " ", normalized)
    normalized = normalized.replace("bahnhof", " ")
    normalized = re.sub(r"\bhbf\b", " ", normalized)
    normalized = normalized.replace("/donau", " ")
    normalized = normalized.replace("wörther see", "worthersee").replace(
        "wörthersee", "worthersee"
    )
    normalized = normalized.replace("centraal", "central").replace(
        "centrale", "central"
    )
    normalized = normalized.replace("st. ", "st ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _canonical_station_name(*names: str) -> str:
    candidates: list[str] = []
    for name in names:
        if not name:
            continue
        candidate = re.sub(r"\s*\([^)]*\)", "", name).strip()
        candidate = candidate.replace(" Bahnhof", "")
        candidate = re.sub(r"\s+", " ", candidate)
        if candidate:
            candidates.append(candidate)

    if not candidates:
        return ""

    return sorted(set(candidates), key=lambda value: (len(value), value.lower()))[0]


def _name_similarity(left: str, right: str) -> float:
    left_normalized = _normalize_station_name(left)
    right_normalized = _normalize_station_name(right)
    if not left_normalized or not right_normalized:
        return 0.0
    if left_normalized == right_normalized:
        return 1.0

    left_tokens = set(left_normalized.split())
    right_tokens = set(right_normalized.split())
    union = left_tokens | right_tokens
    token_score = len(left_tokens & right_tokens) / len(union) if union else 0.0
    sequence_score = SequenceMatcher(None, left_normalized, right_normalized).ratio()
    return 0.55 * sequence_score + 0.45 * token_score


def _parse_minutes(value: str) -> int | None:
    value = (value or "").strip()
    if not value or ":" not in value:
        return None

    try:
        hours, minutes = value.split(":", 1)
        return int(hours) * 60 + int(minutes)
    except ValueError:
        return None


def _row_minutes(row: pd.Series) -> int | None:
    departure = _parse_minutes(str(row.get("ab", "") or ""))
    if departure is not None:
        return departure
    return _parse_minutes(str(row.get("an", "") or ""))


def create_station_name_mapping(
    data_fahrplan_zueglaeufe_sbb: pd.DataFrame,
    data_fahrplan_zueglaeufe_oebb: pd.DataFrame,
    data_fahrplan_zueglaeufe_db: pd.DataFrame,
) -> pd.DataFrame:
    """
    Create a conservative station name mapping from the three Zulauf tables.

    The mapping keeps only station names that are lexically similar enough to
    represent the same place. Time information is used only as a tie-breaker
    for near-identical candidates.
    """

    source_frames = {
        "sbb": data_fahrplan_zueglaeufe_sbb,
        "oebb": data_fahrplan_zueglaeufe_oebb,
        "db": data_fahrplan_zueglaeufe_db,
    }

    unique_halts = {
        source: sorted(
            {str(value).strip() for value in frame["Halt"].dropna().tolist()}
        )
        for source, frame in source_frames.items()
        if "Halt" in frame.columns
    }

    train_time_index: dict[str, dict[str, list[tuple[str, int]]]] = {
        source: defaultdict(list) for source in source_frames
    }
    for source, frame in source_frames.items():
        if "Halt" not in frame.columns:
            continue
        for _, row in frame.iterrows():
            train_number = str(row.get("Zugnummer", "") or "").strip()
            halt = str(row.get("Halt", "") or "").strip()
            minutes = _row_minutes(row)
            if train_number and halt and minutes is not None:
                train_time_index[source][train_number].append((halt, minutes))

    def timing_hint_score(
        source_left: str, source_right: str, halt_left: str, halt_right: str
    ) -> float:
        score = 0.0
        seen = 0
        left_trains = set(train_time_index[source_left])
        right_trains = set(train_time_index[source_right])

        for train_number in left_trains & right_trains:
            left_times = [
                minutes
                for halt, minutes in train_time_index[source_left][train_number]
                if halt == halt_left
            ]
            right_times = [
                minutes
                for halt, minutes in train_time_index[source_right][train_number]
                if halt == halt_right
            ]
            if not left_times or not right_times:
                continue

            seen += 1
            smallest_difference = min(
                abs(left_time - right_time)
                for left_time in left_times
                for right_time in right_times
            )
            smallest_difference = min(smallest_difference, 1440 - smallest_difference)
            if smallest_difference <= 3:
                score += 1.0
            elif smallest_difference <= 8:
                score += 0.6
            elif smallest_difference <= 15:
                score += 0.25

        if not seen:
            return 0.0

        return min(1.0, score / seen)

    def best_match(
        source_left: str, source_right: str, halt_left: str
    ) -> tuple[str, str, float]:
        candidates: list[tuple[str, float]] = []
        for halt_right in unique_halts.get(source_right, []):
            similarity = _name_similarity(halt_left, halt_right)
            if similarity >= 0.82:
                candidates.append((halt_right, similarity))

        if not candidates:
            return "", "", 0.0

        ranked_candidates: list[tuple[float, float, float, str]] = []
        for halt_right, similarity in candidates:
            timing_score = timing_hint_score(
                source_left, source_right, halt_left, halt_right
            )
            final_score = 0.8 * similarity + 0.2 * timing_score
            ranked_candidates.append(
                (final_score, similarity, timing_score, halt_right)
            )

        ranked_candidates.sort(reverse=True)
        best_score, best_similarity, best_timing, best_halt = ranked_candidates[0]
        if len(ranked_candidates) > 1 and (best_score - ranked_candidates[1][0]) < 0.03:
            return "", "", 0.0

        method = "name_similarity"
        if best_similarity >= 0.98:
            method = "normalized_exact"
        elif best_timing >= 0.4:
            method = "name_plus_timing"

        return best_halt, method, best_score

    mapping_rows: list[dict[str, str]] = []
    for source_halt in unique_halts.get("oebb", []):
        matched_sbb, method_sbb, score_sbb = best_match("oebb", "sbb", source_halt)
        matched_db, method_db, score_db = best_match("oebb", "db", source_halt)

        present_values = [
            value for value in [source_halt, matched_sbb, matched_db] if value
        ]
        if len(present_values) < 2:
            continue
        if len(set(present_values)) == 1:
            continue

        pair_similarities = []
        if source_halt and matched_sbb:
            pair_similarities.append(_name_similarity(source_halt, matched_sbb))
        if source_halt and matched_db:
            pair_similarities.append(_name_similarity(source_halt, matched_db))
        if matched_sbb and matched_db:
            pair_similarities.append(_name_similarity(matched_sbb, matched_db))

        if not pair_similarities or max(pair_similarities) < 0.82:
            continue

        if matched_sbb and matched_db:
            average_score = (score_sbb + score_db) / 2
        else:
            average_score = score_sbb or score_db

        confidence = (
            "high"
            if average_score >= 0.92
            else ("medium" if average_score >= 0.86 else "low")
        )

        mapping_rows.append(
            {
                "oebb_halt": source_halt,
                "sbb_halt": matched_sbb,
                "db_halt": matched_db,
                "standardized_halt": _canonical_station_name(
                    source_halt, matched_sbb, matched_db
                ),
                "match_method_sbb": method_sbb,
                "match_method_db": method_db,
                "confidence": confidence,
            }
        )

    mapping_df = pd.DataFrame(mapping_rows)
    if not mapping_df.empty:
        mapping_df = mapping_df.sort_values(
            by=["standardized_halt", "oebb_halt"], kind="stable"
        ).reset_index(drop=True)

    return mapping_df
