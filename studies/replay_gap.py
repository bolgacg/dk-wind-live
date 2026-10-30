"""Fill the gap between the 2026 test (ends 18 Oct) and the first live forecast (31 Oct): J4catDK as the 10:30 run
would have made it, with the live models (trained on data up to 18 Oct, so these days are unseen), the archived
day-ahead weather runs and DKcast's export cut into the feed format. Labelled "replayed" on the page, never "live".

Usage: J4_MODELS unset, DKCAST_FEED=<scratch dir> python3 live/studies/replay_gap.py 2026-10-19 2026-10-27
  ->  reports/replay_gap.csv (hour_utc, zone, j4catdk, cap)"""
import os, sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import BLEND, LIVE, LIVE_MODELS, ROOT, ZONES, capacity_proxy, realtime_actuals
from train import load_weather
import forecast


def main():
    d0, d1 = sys.argv[1], sys.argv[2]
    feed = Path(os.environ["DKCAST_FEED"])
    feed.mkdir(parents=True, exist_ok=True)
    exp = pd.read_parquet(ROOT / "experiments" / "results" / "dkcast_wind_export_points.parquet")
    exp["time"] = pd.to_datetime(exp.time).dt.tz_localize("UTC")
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
    pd.DataFrame(rows).to_csv(LIVE / "reports" / "replay_gap.csv", index=False)


if __name__ == "__main__":
    main()
