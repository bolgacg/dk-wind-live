"""Small summary of the frozen 2026 test, the backtest, the live days and today's forecast, for the one-page summary
that links here (projects-5a's page reads it). Run after league.py and today.py; writes site/summary.json.

The 2026 test block is copied from the one frozen run (studies/e3_test.py, 29 Oct 2026, reports/e3_test.json and the
day-block bootstrap logged in COORDINATION.md); it never changes."""
import json
from pathlib import Path

LIVE = Path(__file__).resolve().parent
TEST_2026 = {
    "period": "1 Jan to 18 Oct 2026", "hours": 6933, "days": 290,
    "nmae_pct": {"j4catdk": 5.56, "blend": 6.24, "ifs": 6.60, "energinet": 6.68},
    "nmae_pct_dk1_dk2": {"j4catdk": [5.27, 6.47], "energinet": [6.19, 8.27]},
    "skill_vs_energinet_pct": 16.8, "skill_vs_energinet_ci95": [12.6, 20.8],
    "skill_vs_ifs_pct": 15.8, "skill_vs_ifs_ci95": [12.8, 18.7],
    "days_better_than_energinet_pct": 76,
    "imbalance_eur_mwh": {"j4catdk": 3.01, "energinet": 3.33},
    "note": "one run of a frozen script, published before it ran; nMAE = mean absolute error of each area's hourly total as % of installed capacity",
}


def pick(rows, src):
    r = next((o for o in rows if o["source"] == src), None)
    return r and {k: r.get(k) for k in ("name", "nmae", "nmae_DK1", "nmae_DK2", "skill_ifs", "skill_energinet", "imb_eur_mwh", "wins")}


def main():
    D = json.load(open(LIVE / "site" / "data.json"))
    out = {"test_2026": TEST_2026, "health": D.get("health")}
    for k in ("backtest", "live"):
        if k in D:
            o = D[k]["overall"]
            out[k] = {"from": D[k]["from"], "to": D[k]["to"], "days": D[k]["days"], "sources": len(o),
                      "rank_j4catdk": next((i + 1 for i, r in enumerate(o) if r["source"] == "j4catdk"), None),
                      "j4catdk": pick(o, "j4catdk"), "energinet": pick(o, "energinet"), "ifs": pick(o, "ifs")}
    t = LIVE / "site" / "today.json"
    out["today"] = json.load(open(t)) if t.exists() else None  # today's line, measured dots and provisional ranking
    json.dump(out, open(LIVE / "site" / "summary.json", "w"), indent=1)


if __name__ == "__main__":
    main()
