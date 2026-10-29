#!/bin/bash
# gene: run one live job (forecast|score) with the venv, log to ~/dk-wind-live/logs/
# after scoring, rebuild the league data for the public page and commit it
cd ~/dk-wind-live/live || exit 1
mkdir -p ../logs
echo "=== $(date -u +%FT%TZ) $1" >> ../logs/$1.log
../.venv/bin/python $1.py >> ../logs/$1.log 2>&1
if [ "$1" = score ]; then
  ../.venv/bin/python league.py --live-scores scores.csv >> ../logs/league.log 2>&1 \
    && mkdir -p docs && cp site/index.html site/data.json docs/ \
    && git add docs && git commit -qm "league update $(date -u +%F)" >> ../logs/league.log 2>&1
fi
exit 0
