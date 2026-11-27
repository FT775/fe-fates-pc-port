#!/bin/sh
# wk.sh CHAIN "DIR:N DIR:N W20 ..." : hold directions (N presses 6 frames apart), shot after
c=$1; shift
T=$(python -c "
import sys
out=[]
for s in sys.argv[1].split():
    if ':' in s:
        d,n=s.split(':'); out+= [d]*int(n)+['W10']
    else: out.append(s)
print(' '.join(out))" "$*")
AUTO_SAVE=${AUTO_SAVE:-bt-ch6-clear} "$(dirname "$0")/st.sh" $c "$T" 6 40
