# Five-minute check: one stat

What you are doing: making one character's Strength 10 higher, then putting it back. About 5 minutes. This is a new game look, not your existing save. Stats already stored in a save do not change.

1. In the port folder, run:
   `python tools/mods/mods.py example`
2. Then:
   `python tools/mods/mods.py install`
   If it stops, copy the error and do not start the game.
3. Start Fire Emblem Fates in Zakuro. Begin a new game. You do not need to pick a route yet if he appears in the opening. Do not use an old save: stats already stored in it stay as they were.
4. Select Ryoma and open his status page. Strength should be 10 higher than the same screen with no mod. Write down the number you see.
5. Close the game. Run:
   `python tools/mods/mods.py uninstall`
6. Start again. A new look at the same screen should show the old Strength.

Tell us the number, and whether uninstall put it back. If a later chapter shows the old number while the opening shows the new one, say so. Some chapters keep their own copy, and this check only changes the main one.
