from dreamteam.data_handling.combine_data import combine_data
from pathlib import Path

path_ares = Path("data/ares_cleaned.csv")
path_fahrplan_zuege_sbb = Path("data/sbb_data.csv")
path_fahrplan_zuege_oebb = Path("data/oebb_data.csv")
path_fahrplan_zuege_db = Path("data/db_data.csv")
path_fahrplan_zueglaeufe_sbb = Path("data/sbb_data.csv")
path_fahrplan_zueglaeufe_oebb = Path("data/oebb_data.csv")
path_fahrplan_zueglaeufe_db = Path("data/db_data.csv")
path_output_zuege = Path("data/output_zuege.csv")
path_output_zueglaeufe = Path("data/output_zueglaeufe.csv")

combine_data(
    path_ares=path_ares,
    path_fahrplan_zuege_sbb=path_fahrplan_zuege_sbb,
    path_fahrplan_zuege_oebb=path_fahrplan_zuege_oebb,
    path_fahrplan_zuege_db=path_fahrplan_zuege_db,
    path_fahrplan_zueglaeufe_sbb=path_fahrplan_zueglaeufe_sbb,
    path_fahrplan_zueglaeufe_oebb=path_fahrplan_zueglaeufe_oebb,
    path_fahrplan_zueglaeufe_db=path_fahrplan_zueglaeufe_db,
    path_output_zuege=path_output_zuege,
    path_output_zueglaeufe=path_output_zueglaeufe,
    station_name_mapping=Path("data/station_name_mapping.csv"),
)
