# Live day-ahead wind forecast for Denmark

Every morning before the 12:00 day-ahead gate, this repository receives my forecast of the next day's hourly wind
power in Denmark's four wind zones: offshore and onshore, in DK1 (west) and DK2 (east). Each forecast is committed
before the day it covers begins. After the day ends, it is scored against Energinet's measured output and against
Energinet's own day-ahead forecast.

How it works: several weather models (ECMWF IFS and its AI model AIFS, DMI HARMONIE, DWD ICON, and others) forecast
the wind at 34 points around Danish wind farms. For each model, a gradient-boosted mapping turns that weather into
power. It was trained on each model's forecasts as they were issued a day earlier, so the lead time matches a real
day-ahead decision.

- `forecasts/<day>.json`: the forecast for that day, with the time it was issued
- `SCOREBOARD.md` and `scores.csv`: accuracy of each source on each finished day
- `train.py`, `forecast.py`, `score.py`: the full pipeline

Data: Open-Meteo (CC BY 4.0), Energinet Energi Data Service, DMI.
