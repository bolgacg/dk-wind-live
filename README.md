# DK Wind League

A daily day-ahead forecast of Denmark's wind power, with its scores. Page: https://bolgacg.github.io/dk-wind-live/

Every morning before the 12:00 day-ahead auction, this repository receives my hourly forecast for the next day in four wind zones. After the day ends, it is scored against Energinet's measured output, against Energinet's own day-ahead forecast and against forecasts from public weather models.

## Files

- `forecasts/<day>.json`: each forecast, with the time it was issued
- `scores.csv`, `SCOREBOARD.md`, `band_scores.csv`: the scores
- `forecast_record.csv`: forecasts issued before this repository started, with the commit each had in my earlier repository, now private
- `docs/`: the page

The model and its code are private. Copyright Bolgaç Gülen, all rights reserved; you are welcome to read and cite the forecasts. Contains data from Open-Meteo (CC BY 4.0), Energinet Energi Data Service and DMI.
