# Five-minute check: a tinted face

What you are doing: making Ryoma's normal standing portrait look blue, looking at it, then putting it back. About 5 minutes. If a step is not on the screen, stop and tell us the last line you did see.

1. Open the port folder. In a command window there, run:
   `python tools/mods/mods.py example-face`
   It tints his normal standing expression blue. You do not paint anything.
2. Then run:
   `python tools/mods/mods.py install`
   If it stops with an error, do not start the game. Copy the error. The first build can take a few seconds.
3. Start Fire Emblem Fates in Zakuro, or restart it if it was already open.
4. Go to a scene where Ryoma talks with his big standing portrait. He appears in the shared opening. A save that already has him in the army works too, for example a support conversation in My Castle. A Conquest-only save may not show him. Do not use that save for this check.
5. With his normal expression, his face and clothes should look blue. His other expressions, and his small portrait in menus, should look as usual.
6. Write down what you saw. Close the game. Run:
   `python tools/mods/mods.py uninstall`
7. Start again and look at the same portrait. The blue should be gone.

Tell us whether the big portrait was blue, whether the other expressions stayed normal, and whether uninstall put the old picture back. If the picture is garbled or empty, or the game crashes when he talks, say so. That is a useful result, not a failure you have to fix.
