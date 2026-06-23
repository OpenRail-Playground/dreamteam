import pandas as pd
from pathlib import Path

import logging

logger = logging.getLogger(__name__)


def apply_station_name_mapping(
    data_fahrplan_zueglaeufe: pd.DataFrame,
    station_name_mapping: Path,
) -> pd.DataFrame:
    """
    Consolidates values in the `Halt` column to a common station name using
    the prepared mapping table.
    """
    mapping_df = pd.read_csv(station_name_mapping, sep=";", encoding="utf-8")

    source_cols = ["oebb_halt", "sbb_halt", "db_halt"]
    lookup_records: list[tuple[str, str]] = []

    for _, row in mapping_df.iterrows():
        common_halt = row.get("common_halt")
        if pd.isna(common_halt):
            continue
        common_halt = str(common_halt).strip()
        if not common_halt:
            continue

        for col in source_cols:
            value = row.get(col)
            if pd.isna(value):
                continue
            value = str(value).strip()
            if value:
                lookup_records.append((value, common_halt))

    station_lookup = dict(lookup_records)

    mapped = data_fahrplan_zueglaeufe.copy()
    if "Halt" in mapped.columns:
        mapped["Halt"] = mapped["Halt"].map(lambda x: station_lookup.get(x, x))

    return mapped


def combine_data(
    path_ares: Path,
    path_fahrplan_zuege_sbb: Path,
    path_fahrplan_zuege_oebb: Path,
    path_fahrplan_zuege_db: Path,
    path_fahrplan_zueglaeufe_sbb: Path,
    path_fahrplan_zueglaeufe_oebb: Path,
    path_fahrplan_zueglaeufe_db: Path,
    path_output_zuege: Path,
    path_output_zueglaeufe: Path,
    station_name_mapping: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:

    data_ares = pd.read_csv(path_ares, sep=",", encoding="utf-8")

    data_fahrplan_zuege_sbb = pd.read_csv(
        path_fahrplan_zuege_sbb, sep=",", encoding="utf-8"
    )
    data_fahrplan_zuege_oebb = pd.read_csv(
        path_fahrplan_zuege_oebb, sep=",", encoding="utf-8"
    )
    data_fahrplan_zuege_db = pd.read_csv(
        path_fahrplan_zuege_db, sep=",", encoding="utf-8"
    )

    data_fahrplan_zueglaeufe_sbb = pd.read_csv(
        path_fahrplan_zueglaeufe_sbb, sep=",", encoding="utf-8"
    )
    data_fahrplan_zueglaeufe_oebb = pd.read_csv(
        path_fahrplan_zueglaeufe_oebb, sep=",", encoding="utf-8"
    )
    data_fahrplan_zueglaeufe_db = pd.read_csv(
        path_fahrplan_zueglaeufe_db, sep=",", encoding="utf-8"
    )

    data_fahrplan_zueglaeufe_sbb_mapped = apply_station_name_mapping(
        data_fahrplan_zueglaeufe_sbb, station_name_mapping
    )
    data_fahrplan_zueglaeufe_oebb_mapped = apply_station_name_mapping(
        data_fahrplan_zueglaeufe_oebb, station_name_mapping
    )
    data_fahrplan_zueglaeufe_db_mapped = apply_station_name_mapping(
        data_fahrplan_zueglaeufe_db, station_name_mapping
    )

    data_fahrplan_zuege_joined, data_fahrplan_zueglaeufe_joined = combine_fahrplan_data(
        data_fahrplan_zuege_sbb=data_fahrplan_zuege_sbb,
        data_fahrplan_zueglaeufe_sbb=data_fahrplan_zueglaeufe_sbb_mapped,
        data_fahrplan_zuege_oebb=data_fahrplan_zuege_oebb,
        data_fahrplan_zueglaeufe_oebb=data_fahrplan_zueglaeufe_oebb_mapped,
        data_fahrplan_zuege_db=data_fahrplan_zuege_db,
        data_fahrplan_zueglaeufe_db=data_fahrplan_zueglaeufe_db_mapped,
    )

    check_consitency_fahrplan(
        data_fahrplan_zueglaeufe_sbb=data_fahrplan_zueglaeufe_sbb_mapped,
        data_fahrplan_zueglaeufe_db=data_fahrplan_zueglaeufe_db_mapped,
        data_fahrplan_zueglaeufe_oebb=data_fahrplan_zueglaeufe_oebb_mapped,
    )

    data_zuege_joined, data_zueglaeufe_joined = combine_data_zuege(
        data_ares=data_ares,
        data_fahrplan_zuege=data_fahrplan_zuege_joined,
        data_fahrplan_zueglaeufe=data_fahrplan_zueglaeufe_joined,
    )

    data_zuege_joined.to_csv(path_output_zuege, index=False)
    data_zueglaeufe_joined.to_csv(path_output_zueglaeufe, index=False)

    logger.info(
        f"Combined data saved to {path_output_zuege} and {path_output_zueglaeufe}"
    )


def combine_fahrplan_data(
    data_fahrplan_zuege_sbb: pd.DataFrame,
    data_fahrplan_zueglaeufe_sbb: pd.DataFrame,
    data_fahrplan_zuege_oebb: pd.DataFrame,
    data_fahrplan_zueglaeufe_oebb: pd.DataFrame,
    data_fahrplan_zuege_db: pd.DataFrame,
    data_fahrplan_zueglaeufe_db: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Combines the fahrplan data from SBB, OEBB and DB into one dataframe.
    """

    data_fahrplan_zuege_joined = data_fahrplan_zuege_sbb.merge(
        data_fahrplan_zuege_db,
        how="outer",
        on=["zugnummer", "datum"],
        suffixes=("_sbb", "_db"),
    ).merge(
        data_fahrplan_zuege_oebb,
        how="outer",
        on=[
            "zugnummer",
            "datum",
            "abfahrt",
            "ankunft",
            "abfahrtsbahnhof",
            "ankunftsbahnhof",
        ],
        suffixes=("", "_oebb"),
    )

    data_fahrplan_zueglaeufe_joined = data_fahrplan_zueglaeufe_sbb.merge(
        data_fahrplan_zueglaeufe_db,
        how="outer",
        on=["zugnummer", "datum"],
        suffixes=("_sbb", "_db"),
    ).merge(
        data_fahrplan_zueglaeufe_oebb,
        how="outer",
        on=[
            "zugnummer",
            "datum",
            "abfahrt",
            "ankunft",
            "abfahrtsbahnhof",
            "ankunftsbahnhof",
        ],
        suffixes=("", "_oebb"),
    )

    return (data_fahrplan_zuege_joined, data_fahrplan_zueglaeufe_joined)


def expand_ares_data(data_ares: pd.DataFrame) -> pd.DataFrame:
    """
    Expands the ares data by splitting the train into individual entries per date
    """
    data_ares_expanded = pd.DataFrame()
    return data_ares_expanded


def combine_data_zuege(
    data_ares: pd.DataFrame,
    data_fahrplan_zuege: pd.DataFrame,
    data_fahrplan_zueglaeufe: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Combines the ares data with the fahrplan data into one dataframe.
    """

    data_ares_expanded = expand_ares_data(data_ares)

    data_zuege_joined = data_fahrplan_zuege
    data_zueglaeufe_joined = data_fahrplan_zueglaeufe

    return data_zuege_joined, data_zueglaeufe_joined


def check_consitency_fahrplan(
    data_fahrplan_zueglaeufe_sbb: pd.DataFrame,
    data_fahrplan_zueglaeufe_oebb: pd.DataFrame,
    data_fahrplan_zueglaeufe_db: pd.DataFrame,
) -> None:
    """
    Checks the consistency of the fahrplan data.
    """

    pass
