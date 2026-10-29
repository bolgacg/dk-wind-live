"""Issue the daily forecast. Target day = the next Copenhagen calendar day whose day-ahead gate (12:00 CET the day
before) has not passed. Fetches each weather model's latest forecast at the 34 points, applies the trained mapping,
snapshots Energinet's own day-ahead forecast as the bar, writes live/forecasts/<target>.json and commits it.

Usage: python3 live/forecast.py"""
import json, os, subprocess, sys, time, urllib.parse
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
# projects-5a writes dkcast_wind_<day>.parquet here by 10:30; the variable is for tests
DKCAST_FEED = Path(os.environ.get("DKCAST_FEED", Path.home() / "dk-wind-blend" / "live_feed"))


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


def day_ahead_prices(start_utc, end_utc):
    """Hourly day-ahead price per area (EUR/MWh), from Energinet's 15-minute DayAheadPrices."""
    d = get_json("https://api.energidataservice.dk/dataset/DayAheadPrices?"
                 f"start={start_utc:%Y-%m-%dT%H:%M}&end={end_utc:%Y-%m-%dT%H:%M}&timezone=UTC&limit=0"
                 "&columns=TimeUTC,PriceArea,DayAheadPriceEUR")
    df = pd.DataFrame(d["records"])
    df["t"] = pd.to_datetime(df.TimeUTC).dt.floor("h").dt.tz_localize("UTC")
    return df[df.PriceArea.isin(["DK1", "DK2"])].groupby(["t", "PriceArea"]).DayAheadPriceEUR.mean().unstack()


class FeedNotReady(Exception):
    """The DKcast feed for the target day is missing, incomplete or fails the level check. Bo's rule (29 Oct 21:30):
    J4catDK never runs without DKcast; the run waits for the next try instead."""


def j4_forecast(frames, hours, cap_now, day, use_dk=True):
    """J4catDK, my own power model (studies/e3_test.py, 2026 test 5.56% of capacity): the four blend members' winds
    side by side plus DKcast station wind, 5 seeds, then the offshore curtailment stage. use_dk=False gives J4cat, the
    same model without DKcast, issued as a separate entrant (never as a stand-in). Returns {zone: Series MW}.
    J4_MODELS (environment) points at another models folder, for the replay simulation."""
    sys.path.insert(0, str(LIVE / "studies"))
    import joint
    from e3_test import HOL26
    joint.HOLIDAYS.update(HOL26)
    X = pd.concat({m: features(*frames[m]).drop(columns=["hour", "doy"]) for m in BLEND}, axis=1)
    X.columns = [f"{m}|{c}" for m, c in X.columns]
    X = joint.add_time(X).reindex(hours)
    name = "j4catdk" if use_dk else "j4cat"
    mdir = Path(os.environ.get("J4_MODELS", LIVE / "models")) / name
    meta = json.load(open(mdir / "meta.json"))
    if use_dk:
        f = DKCAST_FEED / f"dkcast_wind_{day}.parquet"
        if not f.exists():
            raise FeedNotReady(f"no file {f.name}")
        d = pd.read_parquet(f)
        d["time"] = pd.to_datetime(d.time)
        d["time"] = d.time.dt.tz_localize("UTC") if d.time.dt.tz is None else d.time.dt.tz_convert("UTC")
        w = d.pivot_table(index="time", columns="point", values=["dk_mu", "dk_sd"])
        w.columns = [f"{a}_{b}" for a, b in w.columns]
        X = X.join(w)
        # the model was trained with DKcast sites missing (10% of 2025 hours had fewer than 20 of 22, never fewer
        # than 10), so it is only refused below what training saw; projects-5a's feed aims for all 22 x 24
        if (X.filter(like="dk_mu_").notna().sum(axis=1) < 10).any():
            raise FeedNotReady(f"{f.name} has hours with fewer than 10 of 22 sites")
        # level check (feed_check.json): the feed's daily mean within 1.5 m/s of what the members' 100 m wind implies,
        # fitted on 2025 days (residual sd 0.47 m/s)
        chk = json.load(open(mdir / "feed_check.json"))
        m100 = np.mean([frames[m][0].reindex(hours)[chk["points"]].mean().mean() for m in BLEND])
        exp_, got = chk["slope"] * m100 + chk["intercept"], X.filter(like="dk_mu_").mean().mean()
        if abs(got - exp_) > chk["threshold_ms"]:
            raise FeedNotReady(f"{f.name} level {got:.2f} m/s, expected {exp_:.2f} from the weather models")
    X = X.reindex(columns=meta["features"])
    X = X[X.drop(columns=[c for c in X if c.startswith("dk_")]).notna().all(axis=1)]  # hours with all weather inputs
    cf = pd.DataFrame({z: sum(lgb.Booster(model_file=str(mdir / f"{z}_s{k}.txt")).predict(X)
                              for k in range(meta["seeds"])) / meta["seeds"] for z in ZONES}, index=X.index).clip(0, None)
    # curtailment stage: day-ahead prices for the day before the target day are known at 10:30 that day
    p0 = hours[0] - pd.Timedelta(days=2)
    S = joint.stage2_inputs(cf, cf.index, day_ahead_prices(p0, hours[-1] - pd.Timedelta(hours=23)))[meta["stage2_features"]]
    for z in meta["offshore_stage2"]:
        ok = S.notna().all(axis=1)
        adj = pd.Series(lgb.Booster(model_file=str(mdir / f"stage2_{z}.txt")).predict(S[ok]), index=S.index[ok])
        cf[z] = (cf[z] + adj.reindex(cf.index).fillna(0)).clip(0, None)
    return {z: cf[z] * cap_now[z] for z in ZONES}


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

    preds, missing, mapping, frames = {}, {}, {}, {}
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
            time.sleep(6)  # 34 locations per request count as 34 calls; pace models under the 600-per-minute limit
            sp, di = fetch_weather(model, meta.get("level", 100))
        except Exception as e:
            missing[short] = str(e)
            continue
        if short in BLEND:
            frames[short] = (sp, di)
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
    # my own model J4catDK, the headline entrant; it never runs without DKcast (Bo, 29 Oct): if the feed is not
    # ready, this try writes nothing and the 11:00 or 11:30 try picks it up; only the last try issues without it
    j4_note = None
    if all(m in frames for m in BLEND) and (LIVE / "models" / "j4catdk" / "meta.json").exists():
        last_try = now.astimezone(CPH).hour * 60 + now.astimezone(CPH).minute >= 11 * 60 + 25
        try:
            preds["j4catdk"] = j4_forecast(frames, hours, cap_now, day)
            j4_note = "j4catdk with DKcast"
        except FeedNotReady as e:
            if not last_try:
                print(f"{now:%Y-%m-%dT%H:%MZ} DKcast feed not ready ({e}); nothing written, waiting for the next try")
                return
            missing["j4catdk"] = f"DKcast feed not ready at the last try: {e}"
        except Exception as e:
            missing["j4catdk"] = f"{type(e).__name__}: {e}"
        try:  # J4cat, the same model without DKcast: a separate entrant showing what DKcast adds
            preds["j4cat"] = j4_forecast(frames, hours, cap_now, day, use_dk=False)
        except Exception as e:
            missing["j4cat"] = f"{type(e).__name__}: {e}"
    # 80% band for total Denmark from how much the blend members disagree (band.py); only with all four members
    band_out = None
    if (LIVE / "models" / "band.json").exists() and full == BLEND:
        from band import apply
        band = json.load(open(LIVE / "models" / "band.json"))
        mem = pd.DataFrame({m: sum(preds[m][z] for z in ZONES) for m in BLEND})
        point, lo, hi = apply(band, mem, cap_total=float(cap_now[ZONES].sum()))
        band_out = {"q": band["q"], "point": [round(float(v), 1) for v in point],
                    "lo": [round(float(v), 1) for v in lo], "hi": [round(float(v), 1) for v in hi]}

    rec = {"target_day_cph": str(day), "issued_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "gate_utc": str(pd.Timestamp(datetime.combine(day - timedelta(days=1), datetime.min.time(), tzinfo=CPH)
                                        .replace(hour=12)).tz_convert("UTC")),
           "hours_utc": [h.strftime("%Y-%m-%dT%H:%M") for h in hours], "capacity_proxy_mw": cap_now.round(1).to_dict(),
           "blend_members": full, "missing": missing, "mapping": mapping, "j4_variant": j4_note,
           "forecast_mw": {m: {z: [round(float(s.get(h, np.nan)), 1) if h in s.index else None for h in hours]
                               for z, s in zs.items()} for m, zs in preds.items()},
           "band_total_mw": band_out,
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
