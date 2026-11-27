#!/bin/sh
# et.sh CHAIN "MOVES" : move cursor to an empty tile, A (system menu), UP A (end turn), autopilot to next player phase
cd "$(dirname "$0")"
AUTO_SAVE=${AUTO_SAVE:-bt-castle-shop} ./st.sh $1 "$2 W20 A W40 UP A W60" 22 20 | head -1
AUTO_SAVE=${AUTO_SAVE:-bt-castle-shop} python auto.py $1 $1 --max 80 --seg 90 --stop map__SequenceHuman__anonymous_namespace__ProcSequence map__DialogYesNo ChapterFileMenu GameDialogYesNo 2>&1 | tail -1
