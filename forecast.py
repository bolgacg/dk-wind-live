"""Issue the daily forecast. Target day = the next Copenhagen calendar day whose day-ahead gate (12:00 CET the day
before) has not passed. Fetches each weather model's latest forecast at the 34 points, applies the trained mapping,
snapshots Energinet's own day-ahead forecast as the bar, writes live/forecasts/<target>.json and commits it.

Usage: python3 live/forecast.py"""
import json, subprocess, sys, urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import lightgbm as lgb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (BLEND, CAP_WINDOW_DAYS, LEVEL, LIVE, LIVE_MODELS, POINTS, ZONES, capacity_proxy, features, get_json,
                    realtime_actuals)

CPH = ZoneInfo("Europe/Copenhagen")


def target_day(now):
    local = now.astimezone(CPH)
    d = local.date() + timedelta(days=1)
    if local.hour >= 12:
        d += timedelta(days=1)
    return d


def fetch_weather(model, level=100):
    names = list(POINTS)
    q = urllib.parse.urlencode({
        "latitude": ",".join(str(POINTS[p][0]) for p in names),
        "longitude": ",".join(str(POINTS[p][1]) for p in names),
        "hourly": f"wind_speed_{level}m,wind_direction_{level}m", "models": model, "wind_speed_unit": "ms",
        "timezone": "GMT", "forecast_days": 4})
    d = get_json(f"https://api.open-meteo.com/v1/forecast?{q}")
    sp, di = {}, {}
    for p, loc in zip(names, d):
        h = loc["hourly"]
        t = pd.to_datetime(h["time"]).tz_localize("UTC")
        sp[p] = pd.Series(h[f"wind_speed_{level}m"], index=t, dtype=float)
        di[p] = pd.Series(h[f"wind_direction_{level}m"], index=t, dtype=float)
    return pd.DataFrame(sp), pd.DataFrame(di)


def energinet_da(start_utc, end_utc):
    d = get_json("https://api.energidataservice.dk/dataset/Forecasts_Hour?"
                 f"start={start_utc:%Y-%m-%dT%H:%M}&end={end_utc:%Y-%m-%dT%H:%M}&timezone=UTC&limit=0")
    df = pd.DataFrame(d["records"])
    if df.empty:
        return {}
    df = df[df.ForecastType.isin(["Offshore Wind", "Onshore Wind"])]
    df["z"] = df.PriceArea + "_" + df.ForecastType.str.split().str[0].str.lower()
    out = {}
    for z, g in df.groupby("z"):
        g = g.sort_values("HourUTC")
        out[z] = {"hours": list(g.HourUTC), "day_ahead": [None if pd.isna(v) else float(v) for v in g.ForecastDayAhead],
                  "issued_utc": sorted(set(g.TimestampUTC))[-1] if "TimestampUTC" in g else None}
    return out


def main():
    now = datetime.now(tz=ZoneInfo("UTC"))
    day = target_day(now)
    start = pd.Timestamp(datetime(day.year, day.month, day.day, tzinfo=CPH)).tz_convert("UTC")
    end = pd.Timestamp(datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=CPH)).tz_convert("UTC")
    hours = pd.date_range(start, end, freq="h", inclusive="left")
    out_f = LIVE / "forecasts" / f"{day}.json"
    if out_f.exists() and "--force" not in sys.argv:
        print(f"{out_f} exists, skipping")
        return

    # capacity proxy from the realtime feed, last 60 days, value known at issue time
    act = realtime_actuals(f"{(now - timedelta(days=CAP_WINDOW_DAYS + 3)):%Y-%m-%d}", f"{now + timedelta(days=1):%Y-%m-%d}")
    cap_now = capacity_proxy(act).iloc[-1]

    preds, missing, mapping = {}, {}, {}
    for short, model in LIVE_MODELS.items():
        # each weather model uses its own trained mapping when one exists, else the IFS one
        mdir = LIVE / "models" / model
        if not (mdir / "meta.json").exists():
            if short not in BLEND:
                continue  # competitors only enter once they have their own mapping
            mdir = LIVE / "models" / "ecmwf_ifs025"
        boosters = {z: lgb.Booster(model_file=str(mdir / f"{z}.txt")) for z in ZONES}
        meta = json.load(open(mdir / "meta.json"))
        mapping[short] = meta["weather"]
        try:
            sp, di = fetch_weather(model, meta.get("level", 100))
        except Exception as e:
            missing[short] = str(e)
            continue
        X = features(sp, di).reindex(hours)[meta["features"]]
        if X.isna().any(axis=1).any():
            missing[short] = f"{int(X.isna().any(axis=1).sum())} of {len(hours)} hours without data"
            X = X.dropna()
            if X.empty:
                continue
        preds[short] = {z: pd.Series(np.clip(boosters[z].predict(X), 0, None) * cap_now[z], index=X.index)
                        for z in ZONES}
    # pre-registered blend: equal-weight mean of the models that delivered every hour
    full = [m for m in BLEND if m in preds and all(len(preds[m][z]) == len(hours) for z in ZONES)]
    if full:
        preds["blend"] = {z: sum(preds[m][z] for m in full) / len(full) for z in ZONES}

    rec = {"target_day_cph": str(day), "issued_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "gate_utc": str(pd.Timestamp(datetime.combine(day - timedelta(days=1), datetime.min.time(), tzinfo=CPH)
                                        .replace(hour=12)).tz_convert("UTC")),
           "hours_utc": [h.strftime("%Y-%m-%dT%H:%M") for h in hours], "capacity_proxy_mw": cap_now.round(1).to_dict(),
           "blend_members": full, "missing": missing, "mapping": mapping,
           "forecast_mw": {m: {z: [round(float(s.get(h, np.nan)), 1) if h in s.index else None for h in hours]
                               for z, s in zs.items()} for m, zs in preds.items()},
           "energinet_snapshot": energinet_da(start, end)}
    out_f.parent.mkdir(exist_ok=True)
    json.dump(rec, open(out_f, "w"), indent=1)
    tot = {m: round(sum(sum(v for v in rec["forecast_mw"][m][z] if v is not None) for z in ZONES)) for m in preds}
    print(f"issued {day} at {rec['issued_utc']}, total MWh by model: {tot}, missing: {missing}")
    # commit code and models together with the forecast, so each forecast records the exact state that made it
    subprocess.run(["git", "-C", str(LIVE), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(LIVE), "commit", "-q", "-m", f"forecast for {day}, issued {rec['issued_utc']}"],
                   check=True)


if __name__ == "__main__":
    main()
