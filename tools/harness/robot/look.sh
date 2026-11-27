#!/bin/sh
# look.sh CHAIN : dump units + full-res shot at the chain's state
cd "$(dirname "$0")/../../.."
f=$(cat build/harness/robot/states/$1.frame)
python tools/harness/robot/probe.py look $((f+12)) "0:A" $((f+2)) --load $1 --markers --dump 0x006D7000,16384 --scale 1 >/dev/null 2>&1
PYTHONIOENCODING=utf-8 python tools/harness/robot/units.py look | grep -v "^force[3-7]"
python -c "import json;r=json.load(open('build/harness/runs/look/run.json'));[print(k,v['current']) for k,v in r['markers'].items()]"
cp build/harness/shots/look/checkpoints.png build/harness/robot/look.png
