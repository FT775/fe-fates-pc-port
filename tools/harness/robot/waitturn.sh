#!/bin/sh
# waitturn.sh CHAIN x,y ... : each listed unit waits in place; prints board after
cd "$(dirname "$0")/../../.."
c=$1; shift
for u in "$@"; do python tools/harness/robot/act.py $c $u $u wait > build/harness/robot/act.out 2>&1 || { cat build/harness/robot/act.out; exit 2; }; done
cat build/harness/robot/act.out
