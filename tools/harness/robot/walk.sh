#!/bin/sh
# walk.sh SRC DST "DIR:FRAMES DIR:FRAMES ..." : hold directions, full-res shot at end
cd "$(dirname "$0")/../../.."
src=$1; dst=$2; shift 2
f=$(cat build/harness/robot/states/$src.frame)
W=$(python -c "
import sys
f=$f+10; out=[]
for seg in sys.argv[1].split():
    d,n=seg.split(':'); n=int(n)
    if d=='WAIT': f+=n; continue
    for t in range(f,f+n,6): out.append(f'{t}:{d}')
    f+=n+10
print(','.join(out)); open('build/harness/robot/walk_end','w').write(str(f))
" "$*")
e=$(cat build/harness/robot/walk_end)
python tools/harness/robot/auto.py $dst $src --press "$W" --to $((e+20)) >/dev/null
python tools/harness/robot/probe.py c6w $((e+30)) "0:A" $((e+22)) --load $dst --scale 1 --markers 2>&1 | grep -o "castle__[A-Za-z_@0-9]*\|[0-9]* [A-Za-z_]*__[A-Za-z_@0-9]*" | sort -u | head -12
cp build/harness/shots/c6w/checkpoints.png build/harness/robot/last.png
