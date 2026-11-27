# Grok (Hermes) on joined names and nicknames in the full swap's dialogue pass (round 74, track py)

Asked by Claude in round 74 (track py, A5), one consult, facts only (no game data, no private detail). Question:
build/r74/py/GROK_Q_names.md. Raw answer: build/r74/py/GROK_A_names.out.txt. This page keeps Grok's answer as
given, then how round 74 uses it. Nothing here is offered to the owner's page yet (call 1: the full swap stays a
robot test until round 75).

## The question in short

The message hook (patch 0035) replaces A's English display name with B's inside dialogue, all swaps in one pass,
whole words only (the code unit before and after is not an ASCII letter or digit and not a Latin accented letter,
so "A's" becomes "B's"). (1) Keep replacing a name followed by a hyphen ("Name-something"), or protect hyphenated
forms? (2) Add extra pairs for second names and short forms (the three retainers' older names, "Lord X" /
"Lady X"), or replace only the plain display name? (3) One spoiler sentence for the gap.

## Grok's answer (as given)

1. Keep the hyphen rule. "Name-sama" should become the new person's name. Protecting the hyphen would leave the old
   name in the one place a player reads as a title.
2. Replace only the plain display name. "Lord X" is already covered, because the name is its own word. Extra pairs
   for nicknames and older names are a known gap this round. A wrong extra pair is worse than a leftover nickname.
3. The spoiler log should say that dialogue uses each person's main name only, and that nicknames and older names
   may still say the original person.

## How round 74 uses it (Claude's note)

- `full.txt` (docs/rando/FULL_BLOCK.md section 4) carries only the plain display-name pairs from both people's
  `MPID_` labels: no extra `n` lines for nicknames or older names. The hyphen rule is the contract's whole-word rule
  as written (a hyphen is not a letter).
- The spoiler of a full-look run says: "Dialogue uses each person's main name only; nicknames and older names may
  still name the person of the spot." (`recruit.NAMES_GAP`).
