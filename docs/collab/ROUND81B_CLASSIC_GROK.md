# Round 81b: Grok on the Classic bug (2026-11-25, 23:58 EST)

## The question (facts only, no game data)

QUESTION FOR GROK (creative lead) - ROUND 81b: THE CLASSIC BUG. Facts only, no game data. Plain words, under 300 words please.

Found in round 81: if a player starts a New Game on Normal + Classic, our in-game randomizer and Nuzlocke never start.
The game plays un-randomized, silently. Casual, Phoenix and Hard + Casual work. Hard + Classic was not tried.
Cause: our "New Game began" detector watches a settings word that the game happens not to change on Normal + Classic.
Round 81 added a reliable hook on the game's own "start from the beginning" step (used for the new New Game defaults).

Two ways, the owner asked about both:
 1. Real fix: the randomizer also listens to that hook, so Classic just works. One engine build; same page, nothing new to learn.
 2. A randomizer setting instead (for example a "Classic" choice on the randomizer page, the player picks Casual in the game,
    and our existing Nuzlocke-style permadeath lock makes fallen units stay gone). Also one engine build (a new page row).

Questions:
 a. Which would you do, and why, in two or three sentences for a non-technical owner?
 b. Do Fates randomizer / Nuzlocke players expect to pick Classic in the game's own menu?
 c. Anything to add alongside (for example a warning line if the randomizer ever does not start)?

## Grok's answer

Do the real fix. The player already picked Classic on the game's own screen. The randomizer missed that start. Make it listen to the same start step the new defaults already use, so Classic just works. A second Classic on the randomizer page, which tells them to pick Casual and then fakes the deaths, is two switches for one choice. They will disagree, and the player will not know which one won.

Fates players expect to pick Classic in the game's own menu. That is the normal screen. Nuzlocke players expect it there too, because that is the mode where a death sticks.

Add one warning, not a new mode. If the randomizer was on and a New Game started without the seed, say so in one line: "This New Game did not use your seed." Then they know to stop, instead of playing an ordinary game by mistake.

