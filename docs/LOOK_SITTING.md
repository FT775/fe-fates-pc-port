# Your 30-minute sitting: four looks, one at a time

Prepared 2026-11-16 (round 16, Grok's NEXT_R16 rank 4). This clock is yours: it is not part of any
round, and no round waits on it. Do it whenever you like, all at once or in pieces.

**In plain words.** Four short looks at changes we have made but nobody has seen in a window yet.
Each one is one page with the exact commands. Do them **in this order, one change at a time**: take
each one out before starting the next, so if something looks odd we know which change did it.
**Do not save the game during the sitting** (or save only into a spare slot). Your saves, Zakuro
settings and other mods are not touched by any of the tools.

| # | Look | Page | Install | Time |
|---|---|---|---|---|
| 1 | Screen extras (60 fps battles, faster battles, 16:9) | docs/EXTRAS.md, section 1 | nothing is installed into the game's data; you copy one cheat file yourself and switch it on in Zakuro's Cheats window | about 5 min |
| 2 | One renamed name: Jakob shows as **Jacques** | docs/LOOK_TEXT.md | `python tools/mods/look_text.py install` | about 5 min |
| 3 | The stat tables: one edit in each table, plus one castle edit | docs/LOOK_STEP4.md | `python tools/mods/look_step4.py install` | 10-15 min |
| 4 | One portrait swapped: Jakob shows **Felicia's face** | docs/LOOK_PORTRAIT.md | `python tools/mods/look_portrait.py install` | about 5 min |

Total about 25-30 minutes. If you only have 10, do 1 and 2; they are the shortest.

## The order, step by step

Use one save of your own for all four: one where **Jakob is in your army** and you can reach **My
Castle** (for look 3, ideally a save where the dining hall can cook).

1. **Screen extras (about 5 min).** Follow docs/EXTRAS.md section 1. Turn the switches on one at a
   time in a battle. Turn them all off again when done (off is the original game).
   *Write down:* for each switch, "on: looked smoother / faster / wider: yes or no", and anything odd.
2. **Renamed name (about 5 min).** Follow docs/LOOK_TEXT.md: install, load the save, look at Jakob's
   name in the unit list and his status screen.
   *Write down:* "army list: Jacques yes/no, status: yes/no, conversation: yes/no/not tried".
   *Then take it out:* quit the game, `python tools/mods/mods.py uninstall`, then
   `python tools/mods/mods.py disable LookText`.
3. **Stat tables (10-15 min).** Follow docs/LOOK_STEP4.md (its table of five lines).
   *Write down:* one answer per line, for example "1 yes, 2 yes, 3 showed 14, 4 yes, 5 not tried".
   *Then take it out:* quit the game, `python tools/mods/mods.py uninstall`, then
   `python tools/mods/mods.py disable LookStep4` (so it is not installed again with the portrait).
4. **Portrait (about 5 min).** Follow docs/LOOK_PORTRAIT.md: install, load the save, look at Jakob in
   a conversation and on his status screen.
   *Write down:* "conversation: Felicia's face yes/no, talk window yes/no, status screen yes/no/no
   picture there", and whether anything looked garbled.
   *Then take it out:* quit the game, `python tools/mods/mods.py uninstall`, then
   `python tools/mods/mods.py disable LookPortrait`.

At the end, `python tools/mods/mods.py list` should show the look mods as **off**, and
`python tools/mods/mods.py status` should say nothing is installed. Start the game once more: it
should be the original game.

## What to send back

Four short lines, one per look, in your own words. "Not tried" is a fine answer, and so is "crashed
when ...": each answer tells us something real. After that you decide what the step percents do; the
tools do not change them.
