# DK Wind League

A daily day-ahead forecast of Denmark's wind power, with its scores. Page: https://bolgacg.github.io/dk-wind-live/

From 7 November 2026, each day's forecast is locked with a SHA-256 hash at 10:30 and the numbers appear after 12:05, because this model will be entering competitions. The forecast covers the next day's hours in four wind zones. After the day ends, it is scored against Energinet's measured output, against Energinet's own day-ahead forecast and against forecasts from public weather models.

## Files

- `forecasts/<day>.sha256`: the hash, committed before the auction closes
- `forecasts/<day>.json`: the forecast, with the time it was issued. Check a day with `sha256sum -c <day>.sha256` inside `forecasts/`, and read the commit times of both files
- `scores.csv`, `SCOREBOARD.md`, `band_scores.csv`: the scores
- `forecast_record.csv`: forecasts issued before this repository started, with the commit each had in my earlier repository, now private
- `docs/`: the page

The model and its code are private. Copyright Bolgaç Gülen, all rights reserved; you are welcome to read and cite the forecasts. Contains data from Open-Meteo (CC BY 4.0), Energinet Energi Data Service and DMI.
