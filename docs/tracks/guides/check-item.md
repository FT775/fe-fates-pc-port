# Five-minute check: a new item

What you are doing: starting a new game and looking for an extra sword in Chapter 1, then taking the mod out. About 5 minutes plus the prologue. Your old save is not the check. Start a new game.

1. In the port folder, run:
   `python tools/mods/mods.py example-item`
2. Then:
   `python tools/mods/mods.py install`
   If it stops, copy the error.
3. Start Fire Emblem Fates in Zakuro. Begin a new game. Play the prologue. Chapter 1 is shared, so the route does not matter.
4. In Chapter 1, before you move, open the avatar's items.
5. You should see a second sword named **Example Sword** next to the Bronze Sword, same icon. Its help line should say it is a Bronze Sword copy with 5 more might, added by the ExampleItem mod. Its might should be 5 higher, and equipping it should show an attack 5 higher than the Bronze Sword.
6. Write down what you saw. Close the game. Run:
   `python tools/mods/mods.py uninstall`
7. Start a new game again. The Example Sword should be gone.

Tell us if the sword was there, if the name was blank, or if Chapter 1 crashed. A crash or a blank name is a useful result, not a failure you have to fix.
