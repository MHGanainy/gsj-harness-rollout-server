#!/usr/bin/env bash
# CP-28 collection driver: serial single-episode submits, timed.
set -u
LEG="$1"; N="$2"
R=~/gsj-harness-rollout-server
PV=$R/vendor/polar/.venv/bin/python
CSV=~/cp28/timing-$LEG.csv
echo "attempt,exit,seconds" > "$CSV"
for i in $(seq 1 "$N"); do
  T0=$(date +%s)
  PYTHONPATH=$R $PV -m gsj_rollout.cli submit \
    --config ~/cp28/rollout.cp28.$LEG.yaml --case case_0001 --timestep 12 \
    --prompt-file ~/cp09prime/instruction.golden.txt \
    --task-id cp28-$LEG-a$i --timeout 900 --grace 120 \
    --out ~/cp28/out-$LEG >> ~/cp28/logs/submit-$LEG.log 2>&1
  RC=$?
  T1=$(date +%s)
  echo "$i,$RC,$((T1-T0))" >> "$CSV"
  echo "[collect.sh] $LEG attempt $i rc=$RC $((T1-T0))s"
done
