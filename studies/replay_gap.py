"""Fill the gap between the 2026 test (ends 18 Oct) and the first live forecast (31 Oct): J4catDK as the 10:30 run
would have made it, with the live models (trained on data up to 18 Oct, so these days are unseen), the archived
day-ahead weather runs and DKcast's export cut into the feed format. Labelled "replayed" on the page, never "live".

Usage: DKCAST_FEED=<scratch dir> python3 live/studies/replay_gap.py 2026-10-19 2026-10-27
  ->  reports/replay_gap.csv (hour_utc, zone, j4catdk, cap); days already in the file are kept
For days past the weather archive: --api fetches the same day-before runs from Open-Meteo's previous-runs API, and
DKCAST_EXPORT points at projects-5a's backfill (same format as the export, made the same way)."""
import os, sys, time, urllib.parse
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import BLEND, LIVE, LIVE_MODELS, POINTS, ROOT, ZONES, capacity_proxy, get_json, realtime_actuals
from train import load_weather
import forecast


def api_weather(model, d0, d1):
    """The runs issued the day before (_previous_day1), as in the archive the models were trained on."""
    names = list(POINTS)
    q = urllib.parse.urlencode({"latitude": ",".join(str(POINTS[p][0]) for p in names),
                                "longitude": ",".join(str(POINTS[p][1]) for p in names),
                                "hourly": "wind_speed_100m_previous_day1,wind_direction_100m_previous_day1", "models": model,
                                "wind_speed_unit": "ms", "timezone": "GMT", "start_date": d0, "end_date": d1})
    d = get_json(f"https://previous-runs-api.open-meteo.com/v1/forecast?{q}")
    sp, di = {}, {}
    for p, loc in zip(names, d):
        h = loc["hourly"]
        t = pd.to_datetime(h["time"]).tz_localize("UTC")
        sp[p] = pd.Series(h["wind_speed_100m_previous_day1"], index=t, dtype=float)
        di[p] = pd.Series(h["wind_direction_100m_previous_day1"], index=t, dtype=float)
    return pd.DataFrame(sp), pd.DataFrame(di)


def main():
    d0, d1 = sys.argv[1], sys.argv[2]
    feed = Path(os.environ["DKCAST_FEED"])
    feed.mkdir(parents=True, exist_ok=True)
    exp = pd.read_parquet(os.environ.get("DKCAST_EXPORT", ROOT / "experiments" / "results" / "dkcast_wind_export_points.parquet"))
    exp["time"] = pd.to_datetime(exp.time).dt.tz_localize("UTC")
    if "--api" in sys.argv:
        w0, w1 = f"{pd.Timestamp(d0) - pd.Timedelta(days=1):%Y-%m-%d}", f"{pd.Timestamp(d1) + pd.Timedelta(days=1):%Y-%m-%d}"
        weather = {}
        for m in BLEND:
            time.sleep(6)  # Open-Meteo counts each of the 34 locations as a call
            weather[m] = api_weather(LIVE_MODELS[m], w0, w1)
    else:
        weather = {m: load_weather(LIVE_MODELS[m]) for m in BLEND}
    act = realtime_actuals(f"{pd.Timestamp(d0) - pd.Timedelta(days=65):%Y-%m-%d}", f"{pd.Timestamp(d1) + pd.Timedelta(days=1):%Y-%m-%d}")
    cap = capacity_proxy(act)  # known the day before, as live
    rows = []
    for d in pd.date_range(d0, d1).strftime("%Y-%m-%d"):
        day = pd.Timestamp(d).date()
        start = pd.Timestamp(d, tz="Europe/Copenhagen").tz_convert("UTC")
        hours = pd.date_range(start, pd.Timestamp(day + pd.Timedelta(days=1), tz="Europe/Copenhagen").tz_convert("UTC"),
                              freq="h", inclusive="left")
        cut = exp[exp.time.isin(hours)].copy()
        cut["time"] = cut.time.dt.tz_convert(None)
        cut.to_parquet(feed / f"dkcast_wind_{day}.parquet")
        frames = {m: (sp.reindex(hours), di.reindex(hours)) for m, (sp, di) in weather.items()}
        cap_now = cap[cap.index < start].iloc[-1]  # the newest value known before the day, like the 10:30 run
        try:
            out = forecast.j4_forecast(frames, hours, cap_now, day)
        except forecast.FeedNotReady as e:
            print(d, "feed not ready:", e, flush=True)
            continue
        for z in ZONES:
            for h, v in out[z].items():
                rows.append(dict(hour_utc=f"{h:%Y-%m-%dT%H:%M}", zone=z, j4catdk=round(float(v), 1), cap=round(float(cap_now[z]), 1)))
        print(d, "ok", round(sum(out[z].sum() for z in ZONES)), "MWh", flush=True)
    out, f = pd.DataFrame(rows), LIVE / "reports" / "replay_gap.csv"
    if f.exists() and len(out):
        old = pd.read_csv(f)
        out = pd.concat([old[~old.hour_utc.isin(out.hour_utc)], out])
    out.sort_values(["hour_utc", "zone"]).to_csv(f, index=False)


if __name__ == "__main__":
    main()
