#!/bin/sh
# br.sh SRC DST : copy a look-ahead chain state (bin, frame, inputs) in build/harness/robot/states/, to go back later
cd "$(dirname "$0")/../../../build/harness/robot/states" && for e in bin frame inputs; do cp "$1.$e" "$2.$e"; done
