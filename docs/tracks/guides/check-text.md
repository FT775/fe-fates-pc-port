# Five-minute check: a renamed name

What you are doing: making one character's name show a different spelling, then putting it back. About 5 minutes. If a step is not on the screen, stop and tell us the last line you did see.

1. Open the port folder. In a command window there, run:
   `python tools/mods/mods.py example-text`
2. Then run:
   `python tools/mods/mods.py install`
   If it stops with an error, do not start the game. Copy the error.
3. Start Fire Emblem Fates in Zakuro, or restart it if it was already open. The change is read at start.
4. Look at Ryoma's name where he appears: the shared opening, Birthright, or Revelation. It should read **Ryouma**, not Ryoma. A Conquest-only save may not show him. Do not use that save for this check.
5. Close the game. Run:
   `python tools/mods/mods.py uninstall`
6. Start the game again. The name should be Ryoma again.

Tell us: the name you saw, and whether uninstall brought the old name back. If the game crashed, say which step.
