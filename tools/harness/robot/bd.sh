#!/bin/sh
# bd.sh CHAIN [-e] [-m] : look run at a chain's state + board with level, exp, stats, items (bd.py; -e enemies too, -m terrain)
# Budget: probe.py goes through robot/budget.py (resources.json priority, one look-ahead at a time, APPDATA below
# build/); a look-ahead loads a savestate, which parallel.py runs cannot, so it is not a parallel.py job.
cd "$(dirname "$0")/../../.."
f=$(cat build/harness/robot/states/$1.frame)
python tools/harness/robot/probe.py look $((f+12)) "0:A" $((f+2)) --load $1 --save ${AUTO_SAVE:-bt-ch8-support} --markers --dump 0x006D7000,16384 --scale 1 >/dev/null 2>&1
cp build/harness/shots/look/checkpoints.png build/harness/robot/look.png
PYTHONIOENCODING=utf-8 python tools/harness/robot/bd.py look $2 | cut -c1-${W:-70}
[ "$3" = "-m" ] && PYTHONIOENCODING=utf-8 python tools/harness/robot/units.py look -m | tail -20
