# DK Wind Live: a live day-ahead wind power forecast for Denmark

Every morning before the 12:00 day-ahead gate, this repository receives my forecast of the next day's hourly wind
power in Denmark's four wind zones: offshore and onshore, in DK1 (west) and DK2 (east). Each forecast is committed
before the day it covers begins. After the day ends, it is scored against Energinet's measured output, against
Energinet's own day-ahead forecast and against other public weather models.

Page: [bolgacg.github.io/dk-wind-live](https://bolgacg.github.io/dk-wind-live)

## What the forecast is

Four weather models (ECMWF IFS, ECMWF AIFS, DMI HARMONIE and DWD ICON-EU) forecast the wind at 34 points around Danish
wind farms. For each model, a gradient-boosted model per zone turns that weather into power, as a share of recent
capacity. The four power forecasts are averaged with equal weight, and their disagreement sets an 80% band. Each
power model was trained on that weather model's forecasts as they were issued a day earlier, so the lead time matches
a real day-ahead decision.

## Run it yourself

Needs Python 3.11 or newer and an internet connection. No API keys.

```
git clone https://github.com/bolgacg/dk-wind-live
cd dk-wind-live
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python forecast.py      # tomorrow's forecast (the day after, if run after 12:00), into forecasts/
.venv/bin/python score.py         # scores every finished day against Energinet's measured output
.venv/bin/python league.py --live-scores scores.csv   # rebuilds site/data.json for the page
```

`forecast.py` and `score.py` commit their output into your clone, the same way this repository keeps its public
record. To retrain the power models you also need the archive of past forecasts (`train.py`, see its docstring).

## Files

- `forecasts/<day>.json`: the forecast for that day, with the time it was issued and the band
- `scores.csv`, `SCOREBOARD.md`: accuracy of each source on each finished day
- `models/`: the trained power models, one folder per weather model
- `train.py`, `forecast.py`, `score.py`, `band.py`, `league.py`: the full pipeline
- `site/`: the public page

## Data and licences

Code: MIT licence (see `LICENSE`). Weather data: [Open-Meteo](https://open-meteo.com), CC BY 4.0. Open-Meteo's free
API is for non-commercial use; commercial use needs one of their paid plans. Power data: Energinet
[Energi Data Service](https://www.energidataservice.dk). Station data: DMI.
