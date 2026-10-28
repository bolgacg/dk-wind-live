#!/bin/bash
# gene: run one live job (forecast|score) with the venv, log to ~/dk-wind-live/logs/
cd ~/dk-wind-live/live || exit 1
mkdir -p ../logs
echo "=== $(date -u +%FT%TZ) $1" >> ../logs/$1.log
../.venv/bin/python $1.py >> ../logs/$1.log 2>&1
