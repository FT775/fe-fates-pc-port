# The drop flag 0x8000 (round 64, goal 5)

**In plain words.** Round 62 left weapons whose item flag bit 0x8000 is set out of the tougher-bosses forge,
because that bit was read as "the enemy drops this item". Nobody had shown it. Round 64 shows it in a robot game:
an enemy whose weapon has the bit gives that weapon to the player when it is killed ("You got Iron Club"); the same
enemy with the bit taken away gives nothing; an enemy of the same class with the same weapon and no bit gives
nothing; and that enemy with the bit put on gives the weapon. So the bit is the drop, and **the rule stays**:
drops are never forged or upgraded (tools/randomizer/weapons.py `forgeable`, `DROP_BIT`; only its comment changed).
Fates and Seal seeds are byte-identical.

## Where the bit comes from (facts, docs/rando/MISC.md 2)
- DisposUnit `item_N_flags` bit 0 is the mark in the tables. `Unit::SetDisposItem` 003D8C38 turns it into
  unit::Item+0x2 bit 15 (0x8000), the "item word 2" the robot reads.
- `map::SequenceBattle` `ProcSequence::ItemDrop` 0035C548 tests that bit on the loser's items.
- In memory the drop-marked weapon also has its name slot cleared (word 2 0xC000), while the same weapon on an
  ordinary enemy has name slot 1 (0x4001); docs/rando/BOSS_MIGHT.md explains why the name slot matters for might.

## The robot proof (one headless job, randomizer off, cheat pokes in the job's own copy only)
Job `dc-bt-A008-off` (Birthright chapter 8, base save picked by chapsel; frozen round-62b robot side:
boot-server 1b8b2593, capture library 610f791d, sha checked and written in the result; 70 s; no window).
From one memory slot taken on the turn-1 map, Corrin kills four times. Each kill uses bosskill's attack: the target's
HP is poked to 1 and Corrin's move bonus to 60. Corrin had a free item slot, so no convoy question came.

| Kill | Target (A008) | Target's Iron Club, word 2 | Poke | Corrin gained | Screen after the kill |
|---|---|---|---|---|---|
| flag_as_laid | Oni at 13,8 (the table marks its Iron Club) | 0xC000 (bit set) | none | Iron Club (item 113) | "You got Iron Club" |
| flag_cleared | the same Oni | 0x4000 | bit 0x8000 cleared | nothing | no message |
| plain_as_laid | Oni at 3,11 (same class, same weapon, no mark) | 0x4001 | none | nothing | no message |
| plain_flag_set | the same Oni | 0xC001 | bit 0x8000 set | Iron Club (item 113) | "You got Iron Club" |

Every target died. The bit alone decides the drop, both ways.

- Result: build/r64/checks/robot/pjobs/dc-bt-A008-off/result.json (steps.dropcheck.variants).
- Verdict: build/r64/checks/verdicts.json, "drop_flag/bt A008": PASS (`python build/r64/checks/judge64.py`).
- Pictures side by side: build/r64/checks/review/drop_flag_A008.png. The reviewer opened it: the message and Iron
  Club in Corrin's 4th slot in the two "bit set" kills, and no message and no new item in the other two. **SEEN.**
- Also consistent: round 63's A018 Leo and A025 Iago kills stopped at "send an item to the convoy?" (full
  inventory), which is this drop arriving.

## Review (round 64)
- SEEN by the reviewer in drop_flag_A008.png: with the bit as laid Corrin gets "You got Iron Club" and it lands in
  her items; with the bit poked off on the same Oni she gets nothing; the plain Oni gives nothing, and with the bit
  poked on it gives "You got Iron Club". The owner's ok is still needed (F-037).
- The proof ran with the randomizer off only. That is enough to prove what the bit means.
- The weapons.py diff changes only the DROP_BIT comment, so seeds stay byte-identical by inspection. The re-made
  Fates `r63fboss1` and the smoke step's Fates all1 run are byte-identical after this edit (docs/rando/SEAL_BOSSES.md,
  Review).

## How (driver)
`build/r64/checks/robot/p64.py` (round 63's p63.py with this round's folders) adds `drop_check`, used when a
bosskill job has the key `dropcheck` (`flag_xy`, `plain_xy`, `attacker`, `iids`). It reads the target's and the
attacker's items before and after each kill, keeps the screens until the player phase is steady, and takes shots
`drop_<kill>_battle`, `_sN` (each new screen) and `_after`.
