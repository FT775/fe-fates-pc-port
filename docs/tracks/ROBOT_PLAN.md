# Test robot plan — one Birthright campaign

ELI5 / ETA: This is the list of what the automatic player must reach, and how we know it got there. Nothing is built. The robot cannot start until the graphics card is free and the headless program exists. That is not tonight's picture and map work.

Status 2026-11-11. Design only. Scope already agreed: one campaign, Birthright, Normal, the easier death rule (Casual). Not three campaigns. Not Lunatic.

What the robot can actually do today, from docs/HARNESS.md: the fake tests pass. Nothing has run on Fates. A real run needs Zakuro's headless program, a save backup, and a route whose button timings have been found. The one route on file is a title screen copied from Awakening and marked unverified. Do not use those frame numbers.

## Rules

- Every headless run needs the graphics card. Awakening holds it until that work is paused. Fates headless does not start before then.
- Finding the buttons is the expensive part. It is done in short pieces, from scratch savestates, on the card. Once a piece has a recording, replaying that recording still needs the card (it is still the headless program) but it does not need the buttons found again, and it does not need you.
- A new route stops when it adds no functions. Do not raise the depth limit. Three failed rebuilds of one piece, or four hours on one piece, means skip that piece and keep the last good save.
- Capture only a run that wins or opens a feature. A failed piece does not need a full compare.
- Stop the campaign when the feature list below has each been opened once, even if functions remain. Do not clear later chapters to go looking.
- If a menu is not on the save, write "not here" and stop that family. Do not start Conquest or Revelation to find it.
- Your time for this plan: zero. A 30–45 minute session is only if the robot cannot open the list. That ask is not now.

## Order

The exit is a screen marker or a memory read. Frame numbers are blank until a run finds them. No game text is stored in the route file; the check names the screen, not a sentence from the game.

| # | Reach | Exit check | Card |
|---|---|---|---|
| 0 | Title, twice, same inputs | The two savestate hashes match. An update beside the ROM is refused before this run. | First find, then replay |
| 1 | New game, Normal, Casual | The difficulty byte and the death-rule byte equal the values a reading names for those two settings. Those values stay blank until the reading. Do not guess them. | First find, then replay |
| 2 | Shared prologue, one battle, forecast opened once | Chapter progress is still before the route split. A battle screen was up. A forecast screen was up. | First find, then replay |
| 3 | Route choice: Birthright | The route byte is the Birthright value the route tool already proved (folder A, not B or C). The next chapter file is under A. | First find, then replay |
| 4 | Early Birthright, only until the rows below open | Each row is "opened once" or "not here". Do not add a chapter whose only job is more map. | First find, then replay |
| 5 | Shop | Shop screen marker, once | Replay of 4, if 4 already opened it; else one more piece |
| 6 | Armory | Armory screen marker, once | same |
| 7 | Forge | Forge screen marker, once | same |
| 8 | Convoy | Convoy screen marker, once | same |
| 9 | One support | Support list or one support scene, once. If the only path is a petting scene, write "not reached" and skip. Do not rewrite that scene. | same |
| 10 | One dragon vein | The vein command was used on a marked tile, once. The effect is not checked. | same |
| 11 | One Attack Stance follow-up | A battle log or a memory read shows the ally strike happened, not only that an ally stood next door | same |
| 12 | One Guard Stance pair | A pair occupied one tile, once. A block is a bonus, not required | same |

Rows 5–8 are My Castle entry points. If the castle is not open when the early chapters already have a shop, do not hunt the castle. Write "not here" for the ones that are missing.

## What this plan does not do

- Conquest, Revelation, Lunatic, the revive-next-turn rule, child paralogues, amiibo, the petting scenes, the castle renderer.
- A route whose only job is event-only readers. Those wait for a later capture, if you ever do one.
- A second campaign because a menu was missing.

## When it can start

After tonight's picture and map work, and only when the card is free. The first run is row 0, not a chapter clear. Rows 1–12 are the feature list, early to mid December if row 0 is honest and we do not triple the campaign. If row 0's title timings are nothing like the copied Awakening ones, say so in the first session and do not pretend the copy worked.
