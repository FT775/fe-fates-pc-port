# Grok on the round-70 page choices (track swap, 2026-11-24)

Copied by the round-70 integrate step from build/r70/swap/ (gitignored) so the answers are kept. Grok's words
unchanged; the session lines are left out. Used in docs/rando/FULL_SWAP_PLAN.md (sections 4-6).

## Question 1

> Round 70 (desk work, Fire Emblem Fates PC port randomizer page). Three small player-facing choices; answer each in 1-3 lines, plain words. Facts only, no game data needed.
> 1. Growth view in Preparations (Pick Units screen). On the battle map the growth view toggles with Select (Tab on keyboard). In Preparations the game uses Select itself, and our code read shows no Preparations menu reads the Y button (Y is free there). Proposal: Y toggles growths in Preparations, Select/Tab stays the key on the map; the bottom-screen Growths button works in both. OK, or would fans expect something else?
> 2. Share code. The seed box takes 1-32 letters/digits/-/_. A code holding every setting plus the seed would be about 25-30 characters and fragile in that box. Proposal: a separate one-line "Share code" field with Copy and Paste buttons under the seed row; pasting fills every row and the seed; a code from another page version is refused with a plain message. OK, or paste into the seed box?
> 3. "Randomize everything" now writes a 4-line list into the one-line help line. Proposal: one line "Randomize everything turned on 23 settings (This run lists them after Start)." and the help line keeps a fixed 2-line height so buttons never jump. OK?
> Also: two preset buttons later (round 74). Your names for them, and one line each on what goes in (Light / Wild were the draft words).

## Answer 1

1. Y in Preparations is the right key. Select is already taken there, and fans expect Select only on the map stat page, where it already works. The bottom-screen Growths button covers both, so say "Y in Preparations, Select on the map" in the help line.

2. Use a separate Share code field with Copy and Paste. The seed box is for a seed, and a 25-character settings code pasted there will be mistaken for one. Refuse a code from another page version in one plain sentence.

3. Yes. One line, and a fixed two-line help height so the buttons do not jump. "Randomize everything turned on 23 settings. This run lists them after Start."

Presets: **Light** turns on classes, growths, and join stats, keeps royals and the face, and leaves enemies, Nuzlocke, and the full swap off. **Wild** also turns on enemy classes, enemy weapons, music, and a within-route shuffle, still keeps the face, and still leaves Nuzlocke and the full swap off.


## Question 2

> One more for round 70 (the roadmap listed it as your question for round 71). The Esc menu's Randomizer window today shows only "This run" (read only). Round 71 adds the next New Game's settings there. Proposal: under "This run", a "Next New Game" part with the SAME rows and sections as the New Game page (same help line), no Start button, buttons "Keep for next New Game", "Defaults", "Randomize everything", and one grey line "These never change the game you are playing." Kept in the same file the page already uses. Same form as the title page, or a shorter one (which rows)? 1-3 lines.

## Answer 2

Use the same rows as the New Game page. A shorter list will hide a switch they set at the title, and they will think it was lost. No Start button. The grey line "These never change the game you are playing" stays at the top of that part, not the bottom.

