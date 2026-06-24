import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def combine_data(
    path_ares: Path,
    path_fahrplan_zuege_sbb: Path,
    path_fahrplan_zuege_oebb: Path,
    path_fahrplan_zuege_db: Path,
    path_fahrplan_zueglaeufe_sbb: Path,
    path_fahrplan_zueglaeufe_oebb: Path,
    path_fahrplan_zueglaeufe_db: Path,
    path_output_zuege: Path,
    path_output_zuglaeufe: Path,
    path_train_list: Path,
) -> None:
    """Read in and combine timetable data, ARES data and train list with additional information and write result tables used in the UI

    Args:
        path_ares (Path): Path to ARES data
        path_fahrplan_zuege_sbb (Path): Path to sbb train data
        path_fahrplan_zuege_oebb (Path): Path to ÖBB train data
        path_fahrplan_zuege_db (Path): Path to DB train data
        path_fahrplan_zueglaeufe_sbb (Path): Path to sbb train run data
        path_fahrplan_zueglaeufe_oebb (Path): Path to ÖBB train run data
        path_fahrplan_zueglaeufe_db (Path): Path to DB train run data
        path_output_zuege (Path): Path to output train data
        path_output_zuglaeufe (Path): Path to output train run data
        path_train_list (Path): Path to train list data

    Returns:
        pd.DataFrame: A tuple containing the combined train data
        pd.DataFrame: Combined train run data.
    """
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

    for fahrplan_df in (
        data_fahrplan_zueglaeufe_sbb,
        data_fahrplan_zueglaeufe_oebb,
        data_fahrplan_zueglaeufe_db,
    ):
        fahrplan_df["HaltID"] = fahrplan_df["HaltID"].astype(str).str.strip()

    data_fahrplan_zueglaeufe_sbb["Datum_Start"] = data_fahrplan_zueglaeufe_sbb.groupby(
        "ReiseID"
    )["Datum"].transform("min")
    data_fahrplan_zueglaeufe_oebb["Datum_Start"] = (
        data_fahrplan_zueglaeufe_oebb.groupby("ReiseID")["Datum"].transform("min")
    )
    data_fahrplan_zueglaeufe_db["Datum_Start"] = data_fahrplan_zueglaeufe_db.groupby(
        "ReiseID"
    )["Datum"].transform("min")

    train_list = pd.read_csv(path_train_list, sep=";", encoding="utf-8")
    train_list["Zugnummer"] = (
        train_list["Gattung"].astype(str).str.strip()
        + " "
        + train_list["Flügel"].astype(str).str.strip()
    )

    train_list = train_list[["Gruppierung", "Zugnummer", "Kategorie"]].drop_duplicates()

    data_fahrplan_zuege_joined, data_fahrplan_zueglaeufe_joined = combine_fahrplan_data(
        data_fahrplan_zuege_sbb=data_fahrplan_zuege_sbb,
        data_fahrplan_zueglaeufe_sbb=data_fahrplan_zueglaeufe_sbb,
        data_fahrplan_zuege_oebb=data_fahrplan_zuege_oebb,
        data_fahrplan_zueglaeufe_oebb=data_fahrplan_zueglaeufe_oebb,
        data_fahrplan_zuege_db=data_fahrplan_zuege_db,
        data_fahrplan_zueglaeufe_db=data_fahrplan_zueglaeufe_db,
        train_list=train_list,
    )

    data_fahrplan_zueglaeufe_joined = check_consitency_fahrplan(
        data_fahrplan_zueglaeufe_joined=data_fahrplan_zueglaeufe_joined,
    )

    data_zuege_joined, data_zueglaeufe_joined = combine_data_zuege(
        data_ares=data_ares,
        data_fahrplan_zuege=data_fahrplan_zuege_joined,
        data_fahrplan_zueglaeufe=data_fahrplan_zueglaeufe_joined,
    )

    data_zuege_joined.to_csv(path_output_zuege, index=False, sep=";")
    data_zueglaeufe_joined[
        [
            "Datum_Start",
            "Gruppierung",
            "Kategorie",
            "Zugnummer",
            "Halt",
            "Datum_sbb",
            "an_sbb",
            "ab_sbb",
            "Datum_db",
            "an_db",
            "ab_db",
            "Datum_oebb",
            "an_oebb",
            "ab_oebb",
            "Konsistenz_Fahrplan",
            "Konsistenz_Detail",
            "ARES_info",
        ]
    ].to_csv(path_output_zuglaeufe, index=False, sep=";")

    logger.info(
        f"Combined data saved to {path_output_zuege} and {path_output_zuglaeufe}"
    )


def add_datetime_min_column(data_fahrplan_zueglaeufe: pd.DataFrame) -> pd.DataFrame:
    """
    Combines each operator's date with their times to create full datetimes,
    then finds the minimum datetime across all operators and time types.
    This properly handles times spanning across dates (e.g., 23:00 on day 1 < 00:30 on day 2).

    Args:
        data_fahrplan_zueglaeufe (pd.DataFrame): The joined fahrplan data containing date and time columns for each operator.

    Returns:
        pd.DataFrame: The joined fahrplan data with a new column "datetime_min" indicating the minimum datetime across all operators and time types.
    """
    data = data_fahrplan_zueglaeufe.copy()
    datetime_columns = []

    for operator, datum_col in [
        ("sbb", "Datum_sbb"),
        ("db", "Datum_db"),
        ("oebb", "Datum_oebb"),
    ]:
        for time_type in ["ab", "an"]:
            time_col = f"{time_type}_{operator}"
            datetime_col = f"datetime_{time_type}_{operator}"

            # Only create if both columns exist
            if datum_col in data.columns and time_col in data.columns:
                data[datetime_col] = pd.to_datetime(
                    data[datum_col].astype(str) + " " + data[time_col].astype(str),
                    errors="coerce",
                )
                datetime_columns.append(datetime_col)

    # Find the minimum datetime across all operators and time types
    data["datetime_min"] = data[datetime_columns].min(axis=1)

    return data


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

    Args:
        data_fahrplan_zuege_sbb (pd.DataFrame): SBB train data
        data_fahrplan_zueglaeufe_sbb (pd.DataFrame): SBB train run data
        data_fahrplan_zuege_oebb (pd.DataFrame): OEBB train data
        data_fahrplan_zueglaeufe_oebb (pd.DataFrame): OEBB train run data
        data_fahrplan_zuege_db (pd.DataFrame): DB train data
        data_fahrplan_zueglaeufe_db (pd.DataFrame): DB train run data
        train_list (pd.DataFrame): Train list data
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

    sbb_cols = data_fahrplan_zueglaeufe_sbb[
        ["Datum_Start", "Datum", "Zugnummer", "HaltID", "Halt", "an", "ab"]
    ].rename(
        columns={
            "Datum": "Datum_sbb",
            "Halt": "Halt_sbb",
            "an": "an_sbb",
            "ab": "ab_sbb",
        }
    )

    db_cols = data_fahrplan_zueglaeufe_db[
        ["Datum_Start", "Datum", "Zugnummer", "HaltID", "Halt", "an", "ab"]
    ].rename(
        columns={"Datum": "Datum_db", "Halt": "Halt_db", "an": "an_db", "ab": "ab_db"}
    )

    oebb_cols = data_fahrplan_zueglaeufe_oebb[
        ["Datum_Start", "Datum", "Zugnummer", "HaltID", "Halt", "an", "ab"]
    ].rename(
        columns={
            "Datum": "Datum_oebb",
            "Halt": "Halt_oebb",
            "an": "an_oebb",
            "ab": "ab_oebb",
        }
    )

    data_fahrplan_zueglaeufe_joined = sbb_cols.merge(
        db_cols, how="outer", on=["Zugnummer", "Datum_Start", "HaltID"]
    ).merge(oebb_cols, how="outer", on=["Zugnummer", "Datum_Start", "HaltID"])

    data_fahrplan_zueglaeufe_joined["Halt"] = (
        data_fahrplan_zueglaeufe_joined["Halt_sbb"]
        .combine_first(data_fahrplan_zueglaeufe_joined["Halt_db"])
        .combine_first(data_fahrplan_zueglaeufe_joined["Halt_oebb"])
    )
    data_fahrplan_zueglaeufe_joined = data_fahrplan_zueglaeufe_joined.drop(
        columns=["Halt_sbb", "Halt_db", "Halt_oebb"]
    )

    data_fahrplan_zuege_joined = data_fahrplan_zuege_joined.merge(
        train_list[["Gruppierung", "Zugnummer", "Kategorie"]],
        how="left",
        on="Zugnummer",
    ).sort_values(by=["Zugnummer", "Datum"], ignore_index=True)
    data_fahrplan_zueglaeufe_joined = data_fahrplan_zueglaeufe_joined.merge(
        train_list[["Gruppierung", "Zugnummer", "Kategorie"]],
        how="left",
        on="Zugnummer",
    )

    # Add datetime_min column for proper chronological sorting
    data_fahrplan_zueglaeufe_joined = add_datetime_min_column(
        data_fahrplan_zueglaeufe_joined
    )

    data_fahrplan_zueglaeufe_joined = data_fahrplan_zueglaeufe_joined.sort_values(
        by=["Zugnummer", "Datum_Start", "datetime_min"], ignore_index=True
    ).drop(
        columns=[
            "datetime_min",
            "datetime_ab_sbb",
            "datetime_an_sbb",
            "datetime_ab_db",
            "datetime_an_db",
            "datetime_ab_oebb",
            "datetime_an_oebb",
        ]
    )

    return (data_fahrplan_zuege_joined, data_fahrplan_zueglaeufe_joined)


def expand_ares_data(data_ares: pd.DataFrame) -> pd.DataFrame:
    """
    Expands ARES entries to one row per date between start_date and end_date.

    Args:
        data_ares (pd.DataFrame): ARES data

    Returns:
        pd.DataFrame: Expanded ARES data with one row per date
    """
    data = data_ares.copy()
    data["start_date"] = pd.to_datetime(data["start_date"])
    data["end_date"] = pd.to_datetime(data["end_date"])

    data = data[data["start_date"].notna() & data["end_date"].notna()].copy()

    data["Datum"] = [
        pd.date_range(start=start, end=end, freq="D")
        for start, end in zip(data["start_date"], data["end_date"])
    ]
    data_ares_expanded = data.explode("Datum", ignore_index=True)
    data_ares_expanded["Datum"] = data_ares_expanded["Datum"].dt.strftime("%Y-%m-%d")

    return data_ares_expanded


def combine_data_zuege(
    data_ares: pd.DataFrame,
    data_fahrplan_zuege: pd.DataFrame,
    data_fahrplan_zueglaeufe: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Combines the ares data with the fahrplan data into one dataframe.

    Args:
        data_ares (pd.DataFrame): ARES data
        data_fahrplan_zuege (pd.DataFrame): Timetable train data
        data_fahrplan_zueglaeufe (pd.DataFrame): Timetable train run data

    Returns:
        pd.DataFrame: Combined train data
        pd.DataFrame: Combined train run data
    """

    data_ares_expanded = expand_ares_data(data_ares)

    data_ares_expanded["ARES_info"] = data_ares_expanded.apply(
        lambda row: (
            f"{row['start_date'].strftime('%Y-%m-%d')} - {row['end_date'].strftime('%Y-%m-%d')}, {row['start_station']} - {row['end_station']}: {row['Grund der Sperre']}"
        ),
        axis=1,
    )

    ares_train_column = (
        "Zugnummer" if "Zugnummer" in data_ares_expanded.columns else "Zug"
    )
    data_ares_expanded["train_number_clean"] = (
        data_ares_expanded[ares_train_column].astype(str).str.extract(r"(\d+)")[0]
    )
    data_ares_expanded = data_ares_expanded.rename(columns={"Datum": "Datum_Start"})

    data_fahrplan_for_merge = data_fahrplan_zueglaeufe.copy()
    data_fahrplan_for_merge["train_number_clean"] = (
        data_fahrplan_for_merge["Zugnummer"].astype(str).str.extract(r"(\d+)")[0]
    )

    data_zueglaeufe_joined = data_fahrplan_for_merge.merge(
        data_ares_expanded[["Datum_Start", "train_number_clean", "ARES_info"]],
        how="left",
        on=["Datum_Start", "train_number_clean"],
    ).drop(columns=["train_number_clean"])

    data_zuege_joined = data_fahrplan_zuege

    return data_zuege_joined, data_zueglaeufe_joined


def check_consitency_fahrplan(
    data_fahrplan_zueglaeufe_joined: pd.DataFrame,
) -> None:
    """
    Checks the consistency of the fahrplan data.

    Args:
        data_fahrplan_zueglaeufe_joined (pd.DataFrame): The joined fahrplan data

    Returns:
        pd.DataFrame: The joined fahrplan data with consistency status and detail columns.
    """

    def _same_or_both_nan(left, right) -> bool:
        if pd.isna(left) and pd.isna(right):
            return True
        if pd.isna(left) or pd.isna(right):
            return False
        return left == right

    def _format_value(value) -> str:
        return "NA" if pd.isna(value) else str(value)

    def _evaluate_times(row: pd.Series, prefix: str) -> tuple[bool, str]:
        sbb_value = row[f"{prefix}_sbb"]
        db_value = row[f"{prefix}_db"]
        oebb_value = row[f"{prefix}_oebb"]

        # Nuanced rule: if SBB time is missing, compare DB and OEBB only.
        if pd.isna(sbb_value):
            is_consistent = _same_or_both_nan(db_value, oebb_value)
            if is_consistent:
                return (
                    True,
                    f"{prefix}: SBB missing tolerated (DB=OEBB={_format_value(db_value)})",
                )
            return (
                False,
                f"{prefix}: SBB missing but DB/OEBB differ (DB={_format_value(db_value)}, OEBB={_format_value(oebb_value)})",
            )

        is_consistent = _same_or_both_nan(sbb_value, db_value) and _same_or_both_nan(
            sbb_value, oebb_value
        )
        if is_consistent:
            return True, f"{prefix}: all equal ({_format_value(sbb_value)})"
        return (
            False,
            f"{prefix}: mismatch (SBB={_format_value(sbb_value)}, DB={_format_value(db_value)}, OEBB={_format_value(oebb_value)})",
        )

    def _evaluate_row(row: pd.Series) -> pd.Series:
        an_consistent, an_detail = _evaluate_times(row, "an")
        ab_consistent, ab_detail = _evaluate_times(row, "ab")

        status = "Konsistent" if an_consistent and ab_consistent else "Nicht konsistent"
        detail = f"{an_detail}; {ab_detail}"
        return pd.Series(
            {
                "Konsistenz_Fahrplan": status,
                "Konsistenz_Detail": detail,
            }
        )

    consistency_result = data_fahrplan_zueglaeufe_joined.apply(_evaluate_row, axis=1)
    data_fahrplan_zueglaeufe_joined["Konsistenz_Fahrplan"] = consistency_result[
        "Konsistenz_Fahrplan"
    ]
    data_fahrplan_zueglaeufe_joined["Konsistenz_Detail"] = consistency_result[
        "Konsistenz_Detail"
    ]
    return data_fahrplan_zueglaeufe_joined


def main() -> None:
    path_ares = Path("data/ares_cleaned.csv")
    path_fahrplan_zuege_sbb = Path("data/sbb_data.csv")
    path_fahrplan_zuege_oebb = Path("data/oebb_data.csv")
    path_fahrplan_zuege_db = Path("data/db_data.csv")
    path_fahrplan_zueglaeufe_sbb = Path("data/sbb_data.csv")
    path_fahrplan_zueglaeufe_oebb = Path("data/oebb_data.csv")
    path_fahrplan_zueglaeufe_db = Path("data/db_data.csv")
    path_output_zuege = Path("data/output_zuege.csv")
    path_output_zuglaeufe = Path("data/output_zuglaeufe.csv")
    path_train_list = Path("data/NJ_List.csv")

    combine_data(
        path_ares=path_ares,
        path_fahrplan_zuege_sbb=path_fahrplan_zuege_sbb,
        path_fahrplan_zuege_oebb=path_fahrplan_zuege_oebb,
        path_fahrplan_zuege_db=path_fahrplan_zuege_db,
        path_fahrplan_zueglaeufe_sbb=path_fahrplan_zueglaeufe_sbb,
        path_fahrplan_zueglaeufe_oebb=path_fahrplan_zueglaeufe_oebb,
        path_fahrplan_zueglaeufe_db=path_fahrplan_zueglaeufe_db,
        path_output_zuege=path_output_zuege,
        path_output_zuglaeufe=path_output_zuglaeufe,
        path_train_list=path_train_list,
    )


if __name__ == "__main__":
    main()
