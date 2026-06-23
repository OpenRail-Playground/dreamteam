import logging
import re
import unicodedata
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def _normalize_station_name(value: str) -> str:
    value = value.replace("ß", "ss")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.strip().lower()
    value = re.sub(r"\([^)]*\)", " ", value)
    value = value.replace("bahnhof", " ")
    value = re.sub(r"\bhbf\b", " ", value)
    value = value.replace("/donau", " ")
    value = value.replace("wörther see", "worthersee").replace(
        "wörthersee", "worthersee"
    )
    value = value.replace("centraal", "central").replace("centrale", "central")
    value = value.replace("st. ", "st ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def apply_station_name_mapping(
    data_fahrplan_zueglaeufe: pd.DataFrame,
    station_name_mapping: pd.DataFrame | Path,
    mapping_column: str,
) -> pd.DataFrame:
    """
    Consolidates values in the `Halt` column to a common station name using
    the prepared mapping table.
    """
    if isinstance(station_name_mapping, pd.DataFrame):
        mapping_df = station_name_mapping.copy()
    else:
        mapping_df = pd.read_csv(station_name_mapping, sep=";", encoding="utf-8")

    target_column = None
    for candidate in ("common_halt", "standardized_halt"):
        if candidate in mapping_df.columns:
            target_column = candidate
            break

    if target_column is None:
        raise KeyError("Mapping target column not found in station mapping")

    lookup_df = mapping_df[[mapping_column, target_column]].copy()
    lookup_df = lookup_df.dropna(subset=[mapping_column, target_column])
    lookup_df[mapping_column] = lookup_df[mapping_column].astype(str).str.strip()
    lookup_df[target_column] = lookup_df[target_column].astype(str).str.strip()
    lookup_df = lookup_df[lookup_df[mapping_column] != ""]
    lookup_df["_mapping_key"] = lookup_df[mapping_column].map(_normalize_station_name)
    lookup_df = lookup_df[["_mapping_key", target_column]].drop_duplicates(
        subset=["_mapping_key"], keep="first"
    )

    mapped = data_fahrplan_zueglaeufe.copy()
    if "Halt" in mapped.columns:
        mapped["_mapping_key"] = mapped["Halt"].where(mapped["Halt"].notna(), "")
        mapped["_mapping_key"] = (
            mapped["_mapping_key"].map(str).map(_normalize_station_name)
        )
        mapped = mapped.merge(lookup_df, how="left", on="_mapping_key")
        mapped["Halt"] = mapped[target_column].fillna(mapped["Halt"])
        mapped = mapped.drop(columns=["_mapping_key", target_column])

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
    path_station_name_mapping: Path,
    path_train_list: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:

    data_ares = pd.read_csv(path_ares, sep=";", encoding="utf-8")

    data_fahrplan_zuege_sbb = pd.read_csv(
        path_fahrplan_zuege_sbb, sep=";", encoding="utf-8"
    )
    data_fahrplan_zuege_oebb = pd.read_csv(
        path_fahrplan_zuege_oebb, sep=";", encoding="utf-8"
    )
    data_fahrplan_zuege_db = pd.read_csv(
        path_fahrplan_zuege_db, sep=";", encoding="utf-8"
    )

    data_fahrplan_zueglaeufe_sbb = pd.read_csv(
        path_fahrplan_zueglaeufe_sbb, sep=";", encoding="utf-8"
    )
    data_fahrplan_zueglaeufe_oebb = pd.read_csv(
        path_fahrplan_zueglaeufe_oebb, sep=";", encoding="utf-8"
    )
    data_fahrplan_zueglaeufe_db = pd.read_csv(
        path_fahrplan_zueglaeufe_db, sep=";", encoding="utf-8"
    )

    station_name_mapping = pd.read_csv(
        path_station_name_mapping, sep=";", encoding="utf-8"
    )

    data_fahrplan_zueglaeufe_sbb_mapped = apply_station_name_mapping(
        data_fahrplan_zueglaeufe_sbb, station_name_mapping, "sbb_halt"
    )
    data_fahrplan_zueglaeufe_oebb_mapped = apply_station_name_mapping(
        data_fahrplan_zueglaeufe_oebb, station_name_mapping, "oebb_halt"
    )
    data_fahrplan_zueglaeufe_db_mapped = apply_station_name_mapping(
        data_fahrplan_zueglaeufe_db, station_name_mapping, "db_halt"
    )

    train_list = pd.read_csv(path_train_list, sep=";", encoding="utf-8")
    train_list["Zugnummer"] = (
        train_list["Gattung"] + "_" + train_list["Flügel"].astype(str)
    )

    train_list = train_list[["Gruppierung", "Zugnummer"]].drop_duplicates()

    data_fahrplan_zuege_joined, data_fahrplan_zueglaeufe_joined = combine_fahrplan_data(
        data_fahrplan_zuege_sbb=data_fahrplan_zuege_sbb,
        data_fahrplan_zueglaeufe_sbb=data_fahrplan_zueglaeufe_sbb_mapped,
        data_fahrplan_zuege_oebb=data_fahrplan_zuege_oebb,
        data_fahrplan_zueglaeufe_oebb=data_fahrplan_zueglaeufe_oebb_mapped,
        data_fahrplan_zuege_db=data_fahrplan_zuege_db,
        data_fahrplan_zueglaeufe_db=data_fahrplan_zueglaeufe_db_mapped,
        train_list=train_list,
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

    data_zuege_joined.to_csv(path_output_zuege, index=False, sep=";")
    data_zueglaeufe_joined.to_csv(path_output_zueglaeufe, index=False, sep=";")

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
    train_list: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Combines the fahrplan data from SBB, OEBB and DB into one dataframe.
    """

    data_fahrplan_zuege_joined = (
        data_fahrplan_zuege_sbb[["Datum", "Zugnummer"]]
        .merge(
            data_fahrplan_zuege_db,
            how="outer",
            on=["Zugnummer", "Datum"],
            suffixes=("_sbb", "_db"),
        )
        .merge(
            data_fahrplan_zuege_oebb,
            how="outer",
            on=[
                "Zugnummer",
                "Datum",
            ],
            suffixes=("", "_oebb"),
        )
    )

    data_fahrplan_zueglaeufe_joined = (
        data_fahrplan_zueglaeufe_sbb[["Datum", "Zugnummer", "Halt", "an", "ab"]]
        .merge(
            data_fahrplan_zueglaeufe_db[["Datum", "Zugnummer", "Halt", "an", "ab"]],
            how="outer",
            on=["Zugnummer", "Datum", "Halt"],
            suffixes=("_sbb", "_db"),
        )
        .merge(
            data_fahrplan_zueglaeufe_oebb[["Datum", "Zugnummer", "Halt", "an", "ab"]],
            how="outer",
            on=["Zugnummer", "Datum", "Halt"],
        )
        .rename(columns={"an": "an_oebb", "ab": "ab_oebb"})
    )

    data_fahrplan_zuege_joined = data_fahrplan_zuege_joined.merge(
        train_list[["Gruppierung", "Zugnummer"]], how="left", on="Zugnummer"
    ).sort_values(by=["Zugnummer", "Datum"], ignore_index=True)
    data_fahrplan_zueglaeufe_joined = data_fahrplan_zueglaeufe_joined.merge(
        train_list[["Gruppierung", "Zugnummer"]], how="left", on="Zugnummer"
    ).sort_values(by=["Zugnummer", "Datum", "ab_oebb"], ignore_index=True)

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

    expand_ares_data(data_ares)

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
