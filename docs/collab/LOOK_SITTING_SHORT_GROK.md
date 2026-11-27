# The 30-minute look, one page

This is the same sitting as `docs/LOOK_SITTING.md`. Nothing here is a new step. Do it whenever you like. No round is waiting on it. If you only have 10 minutes, do steps 1 and 2.

**Your saves.** The tools do not touch your saves, Zakuro's settings, or your other mods. The sitting page does not ask you to copy a save first. Do not save during the sitting. If you must, save only into a spare slot.

**Stop if.** If the game crashes, or a look looks odd, write that down, quit, and take that look out before you start the next one. One change at a time, so we know which one did it.

Use one save of your own where Jakob is in the army, and where you can reach My Castle. For step 3, a save where the dining hall can cook is the one the page asks for.

1. Open a battle. Turn on the screen switches one at a time: smoother battles, faster battles, then a wider picture. You should see each one do that, or not. Turn them all off again. Off is the original game. About 5 minutes. The page for the switches is `docs/EXTRAS.md`, section 1. Nothing is installed into the game's data. You copy one cheat file yourself and switch it on in Zakuro's Cheats window.

2. Install the renamed name, load the save, and open Jakob in the army list and on his status screen. You should see Jacques, or not. About 5 minutes. Then quit, take it out, and turn that look off:
   `python tools/mods/look_text.py install`
   then, after you have looked: `python tools/mods/mods.py uninstall` and `python tools/mods/mods.py disable LookText`

3. Install the stat look and follow the five lines on `docs/LOOK_STEP4.md`. Write one answer per line. About 10 to 15 minutes. Then quit, take it out, and turn that look off, so it is not still in when the face goes in:
   `python tools/mods/look_step4.py install`
   then: `python tools/mods/mods.py uninstall` and `python tools/mods/mods.py disable LookStep4`

4. Install the face, load the save, and look at Jakob in a conversation and on his status screen. You should see Felicia's face, or not, and say if a picture looked garbled. About 5 minutes. Then quit, take it out, and turn that look off:
   `python tools/mods/look_portrait.py install`
   then: `python tools/mods/mods.py uninstall` and `python tools/mods/mods.py disable LookPortrait`

5. At the end, the look list should show those looks off, and the status line should say nothing is installed. Start the game once more. It should be the original game.
   `python tools/mods/mods.py list`
   `python tools/mods/mods.py status`

**What to write in chat.** Four short lines, one per look, in your own words. "Not tried" is a fine answer. So is "crashed when ...".

- Extras: for each switch, on, and smoother or faster or wider, yes or no, and anything odd.
- Name: army list Jacques yes or no, status yes or no, conversation yes or no or not tried.
- Stats: one answer per line, such as "1 yes, 2 yes, 3 showed 14, 4 yes, 5 not tried".
- Face: conversation Felicia's face yes or no, talk window yes or no, status screen yes or no or no picture there, and whether anything looked garbled.
