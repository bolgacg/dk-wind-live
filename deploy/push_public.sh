#!/bin/bash
# laptop cron: mirror gene's live record to github.com/bolgacg/dk-wind-live (Bo approved the push, 29 Oct 2026).
# Fast-forward only; commits are authored on gene as Bo; refuses to push if any commit message mentions AI tooling.
cd /home/bolgac/projects/dk-wind-blend/live-public || exit 1
git pull -q --ff-only origin master || exit 1; git fetch -q github
if git log --format=%B github/main..HEAD 2>/dev/null | grep -qiE "claude|co-authored|anthropic|session"; then
  echo "$(date -u +%FT%TZ) REFUSED: AI mention in unpushed commits"; exit 1
fi
[ -z "$(git log github/main..HEAD --oneline 2>/dev/null)" ] && exit 0
git push -q github HEAD:main && echo "$(date -u +%FT%TZ) pushed $(git rev-parse --short HEAD)" \
  && echo "$(date +%FT%T%z)  push       bolgacg/dk-wind-live  main $(git rev-parse --short HEAD) (cron, Bo approved 29 Oct)" >> ~/.claude/outward-actions.log
