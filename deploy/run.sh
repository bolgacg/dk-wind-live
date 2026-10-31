#!/bin/bash
# gene: run one live job (forecast|score|today) with the venv, log to ~/dk-wind-live/logs/
# after scoring or forecasting, rebuild the league data for the public page and commit it
cd ~/dk-wind-live/live || exit 1
mkdir -p ../logs
echo "=== $(date -u +%FT%TZ) $1" >> ../logs/$1.log
../.venv/bin/python $1.py >> ../logs/$1.log 2>&1
if [ "$1" = score ] || [ "$1" = forecast ]; then  # forecast too, so the health line shows the new forecast
  ../.venv/bin/python league.py --live-scores hourly_scores.csv >> ../logs/league.log 2>&1 \
    && ../.venv/bin/python export_summary.py >> ../logs/league.log 2>&1 \
    && { ../.venv/bin/python timeline.py >> ../logs/league.log 2>&1; true; } \
    && mkdir -p docs && cp site/*.html site/*.json site/*.js site/*.css docs/ \
    && git add docs && git commit -qm "league update $(date -u +%F)" >> ../logs/league.log 2>&1
fi
if [ "$1" = today ]; then  # provisional running score of the day in progress, hourly
  ../.venv/bin/python export_summary.py >> ../logs/today.log 2>&1
  ../.venv/bin/python timeline.py >> ../logs/today.log 2>&1
  mkdir -p docs && cp site/today.json site/summary.json site/timeline.json docs/ && git add docs/today.json docs/summary.json docs/timeline.json site/today.json site/summary.json site/timeline.json \
    && git commit -qm "provisional score $(date -u +%FT%H:00Z)" >> ../logs/today.log 2>&1
fi
exit 0
