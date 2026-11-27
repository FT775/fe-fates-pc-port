# May this staff be used on that unit (Fates): `Rod::CanUseTarget`

**In plain words.** Before the game lets a unit use a staff on another unit, and while the enemy
AI weighs where to use one, it asks: does this staff do anything to that unit? A healing staff
only works on an ally who has lost HP. Rescue (and its enemy-side twin, draw) only works when the
map and the unit allow it to be moved. The stat-lowering staff only works when it would lower a
stat further than it already is. Freeze, silence and curse only work on a unit that does not have
that state already, and silence only on a unit that uses magic. This batch
(docs/tracks/REWRITE_ORDER4.md row 4, round 22) rewrites that one question. It stores nothing: it
only reads. The callers (`Rod::Use`, the staff action, and `Rod::CanUseDisvalueRange`, the AI's
staff check) are unchanged.

Status 2026-11-17 (round 22 batch `rod_target`), **UNVERIFIED** in the project's sense:

- **1 readable override** (`src/readable/rod_target/rod_target.c`, registry and target rows added):
  `rod_can_use_target`.

It gives the same answers as the game's own ARM code on made-up cases (two seeds and long runs),
with the same guest calls in the same order and the same unmapped reads; the planted bugs and the
tier-2 result are in section 4. Live compare (round 22 integrate, library built 2026-11-17T18:22:15,
already FRESH, no rebuild): `r22-cap-rod_target`, 8 real-play routes (bt-ch4, bt-ch5, bt-ch7, bt-ch8,
bt-ch17, cq-ch6, cq-ch7, rv-ch7): **119 records, 112 match, 7 gave up (cold first call), 0 bad**; met on
7 routes (not on bt-ch4); every final memory hash equal to the route's earlier runs. Cheat routes
(`r22-capc-readers`): met on cheat-family and cheat-skill-proc, 0 bad. Status stays UNVERIFIED until
the owner's call. Nothing changes in the game.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-17) [high unless marked]. No table values or game text are copied here: the thirteen
names are ID labels (SPID_, IUID_, SEID_), given here in English.

---

## 1. What it decides

**`map::ItemHelper::Rod::(anonymous)::CanUseTarget(const Unit*, int, Unit*)`** (0x0034AC30, 2,184
bytes with its literal pool: r0 the staff's user, r1 the user's item slot, r2 the target).

```
first time only (thirteen one-time caches, each behind a C++ guard word, asked in this order):
  no move   = 1 << index of the PrivateSkill "no move"       (guard 0x006D74C0, u64 at 0x006D7550)
  no warp   = 1 << index of the PrivateSkill "no warp"       (guard 0x006D74BC, u64 at 0x006D7558)
  the ItemUse numbers of heal, heal all, rescue, draw, weakness, freeze, silence, curse
                                    (guards 0x006D74B8 .. 0x006D749C, u16 at 0x006D7450 .. 0x006D745E)
  the EquipSkill numbers of status resistance, status immunity, negative chain
                                    (guards 0x006D7498 .. 0x006D7490, s16 at 0x006D7460 .. 0x006D7464)

item = user + 0x108 + 4 * slot               (the slot is not range-checked)
staff is X  means  unit::Item::ToData(item)'s byte +0x1B == the cached u16 of X
                   (ToData is asked again for every test; all 16 bits are compared)
if no target: 0
if Force::IsAllied(target.force, Situation.force_index):
  heal:      Unit::GetMHPImpl(target, 1, 0, 0) > target HP (s8 at +0xF3)
  heal all:  the same
  rescue:    movable(target)
  otherwise: 0
else:
  weakness:  amounts = the 8 bytes ItemData +0x40 (extra_data, hp first), signed
             target has status immunity:   all 0
             else target has resistance:   amounts 1..7 halved (rounding down; hp kept)
             user has negative chain:      1 if any amount 1..7 > 0
             else:                         1 if any amount 1..7 > target.debuff of that stat
  draw:      movable(target)
  freeze:    target.conditions[0] bit 1 (0x02) clear
  silence:   magic(target) and target.conditions[0] bit 3 (0x08) clear
  curse:     target.conditions[0] bit 5 (0x20) clear
  otherwise: 0

movable(t): Situation.flags bit 27 (0x08000000) clear [low for what the bit means], and
            (t.private_flags | t.person.flags | t.job.flags) has neither the "no move" nor the
            "no warp" bit (all 64 bits)
magic(t):   Unit::GetWeaponExp(t, 5) > 0, or GetWeaponExp(t, 6) > 0 (signed), or for slot 0..4
            in order: Item::IsMagic(ToData(t's item)) and Unit::CanItemEquip(t, item, 1, 1)
answers are 1 or 0
```

Details that matter for matching the game exactly:

- The staff number is a u16 cache compared with the record's byte: a cached number above 0xFF
  never matches. The first number that matches decides, so when two cached numbers are equal the
  test order wins (allied: heal, heal all, rescue; other: weakness, draw, freeze, silence, curse).
- `Unit::IsEquipSkill`'s argument is the cached s16, sign-extended (`ldrsh`).
- In `movable`, the game reads the person and class pointers, the three flag words and the "no
  move" bit before its first test, and the "no warp" bit only when the first test passed. The
  readable code reads the same bytes (the order of reads inside one test cannot change an answer:
  only the number of unmapped bytes is compared, and it is the same).
- `Situation` is read through the pointer at 0x006D7ED0 (`G_Situation`) once for the army byte
  and again inside `movable`, as the game does; the game does not test it for 0.
- The weakness amounts are copied by the game into an 8-byte buffer on its own stack and changed
  there; the readable code uses a local array, so it never writes guest memory.

## 2. Why it is a reader

The body's only stores are into its own thirteen caches (each `strh` / `stm` after a name lookup,
the first time it runs) and its own stack (push/pop and the 8-byte amounts buffer). The readable
code never stores: while any of the thirteen guard words is cold it gives up at entry, before it
reads or calls anything else, so the game's own code runs and fills the caches exactly as before.
The seven callees are readable overrides already and store nothing (`item_to_data`,
`force_is_allied`, `unit_max_hp`, `unit_has_skill`, `unit_weapon_exp`, `item_is_magic`,
`unit_can_equip_item`); each is a guest call, in the game's order, with the game's arguments.
There is no tail branch in this function, so the round-10 lesson (docs/MOVE.md) does not apply to
its calls.

Not here, and why (Grok's row: "do not"): `AttackTo` and the AI score bodies that call this
function (docs/AI_SCORE.md: they store; `ai_score_rod.c` stays parked), and `Random::GetValue`
(stores the generator state).

**Callers in the game** (every BL/B whose target is 0x0034AC30, found in text.bin):
`map::ItemHelper::Rod::Use` (six calls: the staff action) and `Rod::CanUseDisvalueRange` (two
calls and one tail branch: the AI's check). In the tier-2 build (section 4) every one of the nine
reaches the override: the generated code of both callers calls `override_0x0034AC30` directly,
the tail branch too (`reg15_ = 0x0034AC30u; CALL(override_0x0034AC30); RETURN();`). 3dsrecomp did
also copy the body into `CanUseDisvalueRange`'s generated function (code112.c has
`case 0x0034AC30u: goto L_0034AC30;` and a `BLOCK_TO(0x0034AC30u, ...)`), but no direct call reaches
that copy: every call and the tail branch go to the override, and entries.c maps the address to it. The lines are kept in build/readable/verify_rod_target/caller_sites.txt.

**Reach.** A route whose last coverage met a staff (Grok: at most 8; if none did, "not here").
The separate capture step picks them. No chapter is added.

## 3. Checks

**Host differential test:** `python src/readable/rod_target/tests/rod_target_diff.py`
(who_holds_diff.py's method: the ARM interpreter src/readable/battle/tests/arm_mini.py on
extracted/text.bin against the readable C built with the host gcc; r0, unmapped reads and the
ordered list of guest calls with their argument registers; nested give-ups and guest writes
flagged). The seven callees are answered by one table on both sides and listed. While a guard is
cold the original reaches the guard routine before any other read (arm_mini raises "cold guard")
and the readable code must give up at entry; every sixth case has exactly one guard cold, the
thirteen taken in turn. The made-up states are random test values, never game data, and often
outside what the game uses: staff numbers that repeat, are above 0x7F or above 0xFF; skill numbers
with bit 15 set; flag bits above 31; HP and debuff bytes above 0x7F; negative and huge weapon
experience; callee answers 0x100 and 0xFFFFFFFF; item slots past 4 and negative; the target the
same unit as the user; unmapped item records, persons, classes and Situation. Weakness cases take
one of seven set-ups (no skill, immunity twice, resistance twice, chain twice), and each set-up
often builds the state its rule turns on: no skill, only the hp amount above the hp debuff (60%) or one amount 1..3 against a debuff byte
above 0x7F (25%);
immunity, one amount that would count without it (60%); resistance, one amount 2 or 3 against a
debuff 0 (60%), else (half of the rest) one amount 0x80..0xFF against a debuff 0, which stays below
0 when halved with its sign and would count if halved unsigned; chain, only the hp amount set (1..7) with every other amount 0 or below and no
immunity (75%), so the answer is 0 only because the chain loop starts at stat 1 (ARM 0x34B288
starts at `[sp,#1]`). (Before the round-22
review the chain set-up had no such case, and a chain loop from hp was caught at 300 cases on only
3 of 7 seeds.)

**Planted bugs** (`--plant`, 42): the cache test dropped, or with one guard missing (two plants);
the no-target test dropped; the army byte from the wrong Situation field; the slot address with 2
bytes a slot; heal with `>=`, the HP byte unsigned, the max-HP arguments; heal all dropped; rescue
tested before heal; the staff number compared on its low byte only, or the record's byte read
signed; the map bit wrong; the person's or the class's flags left out; the 64-bit flags cut to 32;
the "no warp" test dropped; immunity clearing only hp; resistance halving twice, or halving without the sign; resistance asked
before immunity; the chain asked on the target; the chain test `>= 0`; the chain loop from hp (stat 0); the debuff compare from hp,
with `>=`, unsigned, or on the item's stat_bonus instead of extra_data; the skill number
zero-extended; draw dropped; the freeze, silence and curse bits; the tome kind 4; the staff
experience compared unsigned; four item slots; `Item::IsMagic` not asked; `CanItemEquip`'s second
bool 0; silence without the magic test; other enemy staffs answering 1; `Force::IsAllied`'s answer
read as a byte.

Not planted, because they cannot change an answer: halving the hp amount or not (it is never
compared); the order of reads inside one test (only the count of unmapped bytes is compared, and
the faults cannot stop the game's code); the 1-or-0 form of the answer.

**Tier 2** (`tools/readable/verify.py`): section 4.

## 4. Results (2026-11-17)

- Host test, seed 20261117, 300 cases, with `--plant`: **300 cases, 0 mismatches, 41/41 planted
  bugs caught**.
- Host test, seed 7, 300 cases, with `--plant`: **300 cases, 0 mismatches, 41/41 planted bugs
  caught**. Twelve more seeds (11, 13, 99, 5, 12, 14, 15, 16, 1, 2, 3, 4242) were also run with
  `--plant` on the final test: all 41/41. The chain-from-hp plant (added after the round-22 review)
  was caught by 2 to 17 cases on each seed; the plant caught by the fewest cases on any seed was
  the curse bit, by 1 case on seed 5 (7 on average).
  (Review history: the first version had 40 plants and no hp-only chain case; the reviewer's
  chain-from-hp plant was missed at 300 cases on 4 of 7 seeds. Giving the chain set-up a third
  share fixed that but cost cases elsewhere: the compare-from-hp and debuff-unsigned plants were
  missed once each over 14 seeds, so the final test keeps two chain shares and adds, under "no
  skill", one amount against a debuff byte above 0x7F.)
- Round 22 integrate (second review's major point): the reviewer's plant "resistance halving
  without the sign" (`(uint8_t)amount >> 1` in place of `fe_asr(amount, 1)`) was not caught on the
  default seed, because the resistance set-up used only amounts 2 and 3. Integrate added the
  negative-amount resistance case above (test only; rod_target.c/.h unchanged) and the plant as the
  42nd. Fourteen seeds (20261117, 7, 11, 13, 99, 5, 12, 14, 15, 16, 1, 2, 3, 4242) with `--plant`:
  **all 300 cases, 0 mismatches, 42/42**. (A first try that mixed the negative amounts into the 2-or-3
  choice missed the halve-twice plant on seed 1, so the 2-or-3 share was kept whole.)
- Host test, seed 7, 1,500 cases: **1,500 cases, 0 mismatches**. Seed 4242, 3,000 cases:
  **0 mismatches**. Every staff was met both allied and not, each with answers 1 and 0 where the
  rule allows.
- Tier 2 (`python tools/readable/verify.py --out build/readable/verify_rod_target --only
  0x0034AC30`; library build 346 s, at below-normal priority): **1 NOT-RUN, 0 MISMATCH**
  (`readable-verify: 1 problem(s)`). NOT-RUN is not a pass. verify tested 0 functions in both
  passes: its sampler takes the function list of 3dsrecomp's own unseeded discovery, not the build's
  (docs/ITEM.md section 6, `item_sell_price`), and that list has no function at 0x0034AC30 (the
  previous function, `CanUseDisvalueRange`, ends with a tail branch to it and its literal pool runs
  up to it) [med: the discovery was not run alone to show it]. The build itself has the override
  and every caller enters it (above). Even if verify could sample it, its made-up memory has the
  thirteen caches cold, so the readable code would give up at entry and verify would say GAVE-UP, as
  for every guard user (who_holds, strike). No classifier change. The host test and the live compare
  are the evidence. The library (551 MB) was deleted after the run; the logs are kept in
  build/readable/verify_rod_target/.
- `python tools/readable/check.py --selftest`: readable OK (lint 291 rows 0 problems, 56
  sources, host 146/146, capture 568/568, undo 554/554, self-test 27/27 broken inputs, verify
  pipeline 28/28).
- `python tools/harness/gen_stubs.py --check`: OK (257 overrides, 65 guard users; this row carries
  the guard tag: the body calls the guard routine 0x00302C6C). The count includes the row 3 batch
  (`female`), running at the same time.
- Callers in the readable layer: none active (`ai_score_rod.c` is parked and would reach this
  override through its guest call).
