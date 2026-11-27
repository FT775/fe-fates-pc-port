# Grok on the round-71 Esc window wording (track page, 2026-11-24)

The one round-71 page consult (facts only, no game data). Question as sent (build/r71/page/grok_query.md), then
Grok's words unchanged (session lines left out). Used in patch 0032 (`rando_page.rs`: the Next New Game part).

## Question

> Round 71, track page (Fire Emblem Fates PC port, the randomizer window in the Esc menu). Your round-70 answers are being built as you said: a "Next New Game" part under "This run" with the same rows and sections as the New Game page, no Start, buttons "Keep for next New Game", "Defaults", "Randomize everything", the grey line "These never change the game you are playing." at its top, and the one-line note "Randomize everything turned on N settings. This run lists them after Start." with a fixed two-line help line. Five small wording/behaviour calls left; answer each in 1-2 lines, plain words, facts only (no game data needed).
> 
> 1. Keep or live? Proposal: changes in the Next New Game part are a draft. Keep saves them (to the same file the New Game page remembers, and the next New Game page opens with them, even with Randomizer off). Closing the window without Keep throws the draft away. OK, or should every change count at once with no Keep button?
> 2. While the draft differs from what is kept, the part's note says "Not kept yet: press Keep for next New Game." After Keep: "Kept for the next New Game." OK, or other words?
> 3. "This run" today ends with the grey line "The settings are chosen when a New Game's mode is picked. Changing them never changes a game already started." With the new part below it, proposal: drop that line whenever the Next New Game part is shown (its own grey line says the same), keep it when the part cannot show. OK?
> 4. A test run without a data folder cannot save anything. Proposal: the Keep button is grey and the note says "No data folder: nothing can be kept." OK, or other words?
> 5. The help line when no setting is pointed at stays "Point at a setting to see what it changes." The full text of a long help line shows when the pointer rests on it (it is cut to two lines with "..."). OK?

## Answer

1. Keep the draft. A change that saves the moment you touch it will rewrite the next game while someone is only looking. Closing without Keep throws the draft away.

2. Those words are right. "Not kept yet: press Keep for next New Game." Then "Kept for the next New Game."

3. Drop the old grey line when the Next New Game part is on screen. Two lines that say the same thing look like a mistake. Keep the old line only when that part cannot show.

4. Grey the Keep button, and say "No data folder: nothing can be kept."

5. Yes. The resting line stays "Point at a setting to see what it changes." A long help line is cut to two lines with "...", and the full text shows when the pointer rests on it.
