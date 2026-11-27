# Five-minute check: a moved enemy

What you are doing: moving one enemy two tiles on Birthright Chapter 7, looking at him, then putting him back. About 5 minutes if you already have a save at the start of that chapter. If you do not, getting there takes longer. If a step is not on the screen, stop and tell us the last line you did see.

1. Open the port folder. In a command window there, run:
   `python tools/mods/mods.py example-map`
   It prints which enemy it moved, and from where to where. Write that line down. A picture of the map with him in the new place is at `mods/ExampleMap/maps/A007/preview.png`. Red squares are enemies. X counts columns from the left, y counts rows from the top, starting at 0.
2. Then run:
   `python tools/mods/mods.py install`
   If it stops with an error, do not start the game. Copy the error.
3. Start Fire Emblem Fates in Zakuro, or restart it if it was already open.
4. Start Birthright Chapter 7 fresh. Do not resume a suspended battle. A suspended battle may keep its own copy of the map. A save made right after choosing Birthright is enough, if it is at the start of that chapter.
5. On the first turn, that enemy should stand two tiles from where the original game puts him. Everything else should look the same. Compare with the preview picture.
6. Write down what you saw. Close the game. Run:
   `python tools/mods/mods.py uninstall`
7. Start the chapter fresh again. He should be back in the old place.

Tell us the line the first command printed, where he stood, and whether uninstall put him back. If the chapter does not load, or the enemy is missing, say so. That is a useful result, not a failure you have to fix.
