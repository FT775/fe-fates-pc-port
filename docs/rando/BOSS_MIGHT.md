# Tougher bosses: weapon might (round 63)

F-049 asks for **+1 / +2 / +3 weapon might, as the player sees it**, on Easy / Normal / Hard when "Tougher bosses"
is on. Round 62 gave +1 / +1 / +2 on screen (docs/rando/R62.md section 4). This round fixes that in
`tools/randomizer/weapons.py` (no engine build).

## Why round 62 was short

The game adds a forge bonus to a weapon's might in `unit::Item::GetPower` (0053B4B4): the might byte of the forge
table `ItemRefine` at (row, the weapon's forge rank). The row is **not always** `Item.refine_index` (Item+0x48):

- `Unit::SetDisposItem` (003D8C38) gives every weapon of a unit whose `Person.unit_kind` is not 1 (enemies,
  bosses, other armies) name slot 1 (unit::Item+0x2, bits 0-6).
- With name slot 1, `GetPower` reads the row from **Item+0x49** (`unknown_49`, the second forge table) instead.
- Most weapons have `refine_index` 0 or 1 (+2 might a level up to +4, then +1) and `unknown_49` 2 (+1 might a
  level, ItemRefine row 2: 1, 2, 3 ... 9).

Round 62 picked forge levels on the `refine_index` row (+2 a level, so Easy and Normal got 1 level, Hard 2), but a
boss's weapon shows the row-2 might (+1 a level). The robot's records agree: 306 of the 372 enemy items read in the
round-62 boss jobs have name slot 1 in memory; 54 of the other 66 are drop-marked (`SetDisposItem` clears the slot
for those), and 12 have neither (not looked at one by one; staves and other non-weapons get no slot).

## The rule now

- `boss_refine_row`: the row the game will use: `refine_index` for a playable person (`unit_kind` 1), else
  `unknown_49`.
- `boss_might_plan`: the fewest forge levels on top of the weapon's current rank (after a ladder step) whose added
  might on that row is at least the step (Easy 1, Normal 2, Hard 3), capped at the game's forge maximum 7.
  On row 2 the levels equal the step, so the shown might is exactly +1 / +2 / +3.
- If the forge maximum stops it, the spoiler says "stopped by the forge maximum 7" (or "already at the forge
  maximum 7: no tougher-boss might added").
- If a weapon's row cannot give exactly the step (a playable-person row, +2 a level), the spoiler says
  "+N wanted, this weapon's forge steps give M". In the made runs (Fates and Seal, 3 difficulties) no boss weapon
  needed either note: every boss weapon line reads "might +step shown".
- The guard (`check_weapons`) recomputes the same rule. Which class a boss gets is unchanged (the weapons track
  runs after the enemies track and draws from its own stream; host check below).

Spoiler line, Hard: `A014 unit 2 (boss) slot 1: forge +3 (tougher boss +3: might +3 shown)`.

## Checks

- `python -m unittest tests.test_rando_boss_might`: made-up forge rows (row 2 gives the step, the cap stops and says
  so, rows 0/1 give even steps, the row follows `unit_kind`, the round-62 rule reproduces the screen's +1/+1/+2),
  and on the game's own tables: row 2 is +1 a level, and every tougher-boss line of the made Fates runs is
  recomputed independently (row by the chapter's `PersonChapter.unit_kind`, might byte of that row at the old and
  new rank) and must equal the spoiler and the step.
- `python build/r63/might/cmp_head.py`: the same answers made with HEAD's weapons.py and with today's: every
  spoiler line outside the weapons section (boss classes included) and every non-dispos patch block are equal,
  dispos blocks edit the same offsets. Fates and Seal, `all1` (enemy and boss classes on) and `boost_on_hard`.
- Robot pairs on the round-62b build's robot side (boot-server 1b8b2593, capture library 610f791d; round 62b did
  not rebuild them), headless, one job at a time: build/r63/might/robot/pjobs/m-*; pictures side by side in
  build/r63/might/review/; verdicts in build/r63/might/verdicts.json (`python build/r63/might/judge.py`).

| Pair (off -> on, same seed) | Read on screen (unit page) | Weapon might change | Memory (rank, name slot 1) | Verdict |
|---|---|---|---|---|
| Birthright A014 Daniela, Ragnarok, Easy | Atk 26 Mag 14 -> Atk 30 Mag 17 | +1 | rank 0 -> 1, +1 | SEEN PASS |
| same, Normal | -> Atk 31 Mag 17 | +2 | rank 0 -> 2, +2 | SEEN PASS |
| same, Hard | -> Atk 32 Mag 17 | +3 | rank 0 -> 3, +3 | SEEN PASS |
| Seal R006 Chevois (Wyvern Lord), Steel Lance, Hard | the Seal unit page is the simple page: no Atk; "Steel Lance +3" shows | 10 -> 13 (from memory) | rank 0 -> 3, +3 | memory PASS, not SEEN |

  Weapon might change = (Atk - Mag) on - (Atk - Mag) off; class and weapon rank are the same, so the rank bonus
  cancels. Round 62 on the same seeds read +1 / +1 / +2 (build/r62/check/review/boss_boost_hard_bt_0.png).
  The Seal pair's first try looked at the wrong unit (PID_B013_ボス at 3,19, a unit the Seal boost does not
  reach); the one retry aimed at the two R006 bosses (Wyvern Lord 12,12 and General 6,11, both rank 0 -> 3).

## Integrate (round 63) and what is still open

- `tools/harness/rcheck.py` `judge_boost` now judges the shown might too (+1 / +2 / +3, `name_slot_might`, forge-7
  cap in `forge_capped`; selftest 57/57). Before, it counted forge levels and would have rejected the fixed Normal
  and Hard runs. docs/tests/RCHECK.md describes the new rule.
- check_all row `rando-r63-boss-might` runs `tests.test_rando_boss_might`.
- The Seal pair is **not SEEN**: the item label "Steel Lance +3" is a forge count, which a judge must not use. The
  shown might 10 -> 13 is from memory only. A SEEN pair needs one more headless robot job that switches the Seal
  unit page to the full page (TOUCH_PAGE) so Atk can be read. Not run in round 63 (the pair had used its one
  retry, and the integrate step runs no game).
- A playable-person boss (`unit_kind` 1) would use the +2-a-level row: its item label and its shown might would
  then differ, and it could only show even steps (the spoiler notes it). No such boss was in the made runs, so this
  case is covered by host tests only.

## Run ids

Run ids are the seed plus a hash of the answer, so **no run id changes**. What changes is the content of runs with
Tougher bosses on at Normal or Hard: the boss weapons' forge bytes, one level more than round 62 (Normal 1 -> 2,
Hard 2 -> 3). Checked by patch compare against build/r62/check/runs: boost_off (Fates, Seal) and boost_on_easy
(Fates) byte-identical; boost_on_normal changed. Every everything-on run with Normal/Hard and Tougher bosses on
changes the same way (e.g. r59fall1-37ec8c6e, r59sall1-3d54cbff: forge bytes only, cmp_head.py).

## Round 66: Revelation boss might SEEN (C007 Vallite)

Round 65's only Revelation pair (C017 Iago) could not show might: Fimbulvetr is a drop and drops are never forged,
and Iago's HP is at its cap on every difficulty (gap). Round 66 picked a Revelation boss whose weapon is forged and
whose HP stays below its cap on all three difficulties: **C007 Vallite (Berserker, Steel Axe, slot 1 equipped, item
flags 0, personal HP 6, cap 46)**. Other candidates were rejected from the tables and spoilers: C010 Zola, C019,
C020, C022, C023 reach the HP cap; C011 Kotaro and C016 Hans equip a drop in slot 1 (the forged weapon is slot 2,
so the shown Atk would not move).

Strict rcheck pairs, Tougher bosses off vs on, same seed and difficulty (round 65's runs r59f1boostoff{ea,no,ha}-*,
copies under build/r66/might/runs), headless robot (build/r66/might/p66.py, a copy of round 65's p64m.py; frozen
boot-server 1b8b2593 and capture library 610f791d in build/r66/might/bin), base rv-ch7-clear, cursor on the boss at
(17,3), unit page switched to the full page by touch_page. 6 jobs, all ok first try (17 s each), no log faults,
same frame 5966 on both sides. Judge: build/r66/might/judge66.py -> verdicts66.json (judge_pair on the items field,
judge_boost with round 66's cap fix and hp_cap from the tables, memory forge, and the shown might from the pictures,
review/screen66.json).

| Difficulty | Weapon | Atk off -> on | Str off -> on | shown might off -> on (Atk - Str) | HP off -> on (shown = memory) | HP want | verdict |
|---|---|---|---|---|---|---|---|
| Easy | Steel Axe -> Steel Axe +1 | 25 -> 28 | 13 -> 15 | 12 -> 13 (+1) | 26 -> 31 | >= 3 | PASS, SEEN |
| Normal | Steel Axe -> Steel Axe +2 | 25 -> 29 | 13 -> 15 | 12 -> 14 (+2) | 26 -> 34 | >= 6 | PASS, SEEN |
| Hard | Steel Axe -> Steel Axe +3 | 25 -> 30 | 13 -> 15 | 12 -> 15 (+3) | 26 -> 37 | >= 9 | PASS, SEEN |

The HP rise is the HP boost plus the story buff (+2 at C007), below the cap, so `capped` is false on all three.
Controls (host): judging the Hard ON picture as Easy, or the Easy ON picture as Normal or Hard, fails on the shown
might. Pictures: build/r66/might/pjobs/m66-rv-C007-{easy,normal,hard}-{off,on}/enemy0-5966.png; sheet
build/r66/might/review/rv_C007_might_sheet.png (OFF, Easy, Normal, Hard side by side).


Integrate review (round 66): **SEEN, all 3 pairs.** The reviewer opened the raw pictures (normal-off, hard-on) and the
sheet: the same unit, Vallite (Berserker LV1), on the same square with the same cursor. Easy shows Steel Axe +1, Atk
25 -> 28, HP 26 -> 31; Normal +2, Atk 29, HP 34; Hard +3, Atk 30, HP 37; Str 13 -> 15 on every ON picture, so the
shown might rises by +1 / +2 / +3. The 3 OFF pictures are byte-identical (sha f503a47e...), as expected: the
difficulty here is the randomizer option, not the save's difficulty (the same method as rounds 63-65). The shown
numbers in review/screen66.json were read by hand and match the pictures. Robot plus reviewer until the owner says
ok (F-037).
