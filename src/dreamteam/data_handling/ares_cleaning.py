import pandas as pd

path = 'src/dreamteam/data/ares_H4R.xlsx'

def clean_ares_data(path:str) -> None:
    data = pd.read_excel(path, skiprows=2)

    #clean zugnummer from text
    data["Zug"] = data["Zug"].str.extract(r'(\d+)').astype(int)

    #retrieve start and end date from the column "Datum ab - bis" and convert to datetime
    data["start_date"]= pd.to_datetime(data['Datum ab - bis'].str.split(' - ').str[0], format='%d.%m.%Y', errors='coerce')
    data["end_date"]= pd.to_datetime(data['Datum ab - bis'].str.split(' - ').str[1].fillna(data["start_date"]), format='%d.%m.%Y', errors='coerce')

    #retrieve start and end station from the column "Station von - nach"
    data["start_station"]= data['Station von - nach'].str.split(' - ').str[0]
    data["end_station"]= data['Station von - nach'].str.split(' - ').str[1].fillna(data["start_station"])

    #change Abteile to list
    data["Abteile"] = data["Abteile"].str.split(',').apply(lambda x: [i.strip() for i in x] if isinstance(x, list) else [])
    #change Plätze/Sektoren to list
    data["Plätze/Sektoren"] = data["Plätze/Sektoren"].str.split(',').apply(lambda x: [i.strip() for i in x] if isinstance(x, list) else [])

    #select relevant columns and save to csv
    final_data = data[["Gespeichert","Zug", "Wagen", "Abteile", "Plätze/Sektoren", "start_date", "end_date", "start_station", "end_station", "Bemerkung", "Zusatzbemerkung", "Grund der Sperre"]]
    final_data.to_csv('src/dreamteam/data/ares_cleaned.csv', index=False)

if __name__ == "__main__":
    clean_ares_data(path)