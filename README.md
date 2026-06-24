# Nightvision

This is an App that helps the people responsible for night trains to check if the ARES booking system is in sync with the timetable data of different train compainies (SBB, ÖBB and DB) and if these timetables are consistent to each other.


# Installation

We use uv as a package manager. You can install the package with "uv venv" and then "venv sync" once venv is installed.

# Data Folder:
Data is placed in the folder "data", which is included in the .gitignore file of the repository so no data should be commited to the repo!

Input Data:

## ASES-Sperrliste
ASES blocklist (Sperrrliste): Export from the ASES system showing the trains / train stops that are blocked for bookings in the system. It is used in the form of an Excel-File that is manually exported from the system

## Train list
List of the relevant night trains including information of train numbers, train category. This list is used to query for the relevant trains from the databases and to add additional information to the trains


