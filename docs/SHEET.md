# The unit's status sheet (Fates): defence, resistance, HP, move and small unit questions, read from the code

**In plain words.** The battle-formula batch (docs/FORMULAS.md) rewrote five of a unit's stats
(strength, magic, skill, speed, luck) and the numbers built from them. This batch rewrites the
rest of what a unit's status sheet shows and what every fight and every move asks: **defence,
resistance, maximum HP and move**, plus a dozen small questions the game asks about a unit all
the time: which class categories it belongs to (dragon, beast, flying ...), which item it has
equipped or holds, its level as shown and its level counted from the first class, how many items
it carries, its weapon's shortest range, whom it may never attack, and whether it is unique, a
giant, invisible or capturable.

All 19 are **readers**: they store nothing (F-017). They are an idle-fill batch
(docs/collab/EFFICIENCY_AGREED.md item 2), written while the robot runs, with host builds only.

Status 2026-11-13: 19 readable overrides (`src/readable/sheet/`), all **UNVERIFIED** in the
project's sense. Every one gives the same answers as the game's own ARM code on made-up cases,
with the same guest calls in the same order and the same unmapped reads (section 6); 40 bugs
planted on purpose were all caught. Tier 2: no result difference; 3 shadow-pass read counts the
classifier does not explain yet (section 6). Not yet in a live compare: the integrator appends the
registry rows and rebuilds the capture library. Nothing changes in the game.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-13) [high unless marked]. No table values or game text are copied here; skill and flag
names are the game's ID labels (`SEID_`, `SPID_`, `JCID_`) given in English [med for the English].

---

## 1. Defence and resistance (`Unit::GetDefImpl` 0x0052A000, `Unit::GetMdefImpl` 0x0052BF6C)

The same shape as the five stats of docs/FORMULAS.md section 2, with their own numbers:

```
base  = Person.base[s] + (avatar: boon/bane) + Class.base[s] + Unit.gains[s]
        (- Unit.stat_loss[s] while state bit 30 is set)
base  = 0 if negative, else at most Unit::GetLimit(s)
```

and, when the getter is asked for the extras (its second bool; every battle number asks):

| Part | Defence | Resistance |
|---|---|---|
| Guard Stance bonus of the partner behind | yes | yes |
| equipped skills | Def+2: +2; "juuken" (the speed skill): -1; Def absorb: + the absorbed amount | Res+2: +2; Res absorb: + the absorbed amount |
| rallies and tonics (+ a condition bit, or the rally kind passed in) | +4, +2, tonic +2 (+1 with better tonics), +4 | +4, +2, tonic +2 (+1 with better tonics), +4 |
| mood bits | +2 / -1 (condition byte 5) | +2 / -1 (condition byte 6) |
| the weapon's stat bonus (the given weapon, else the equipped one) | yes | yes |
| carried-item bonuses (`GetEnhanceHave`) | yes | yes |
| debuff (only when the third bool is set) | yes | yes |

The result is clamped to 0 .. 99. No halving bit (strength and magic have one).

## 2. Maximum HP and move

**Maximum HP** (`Unit::GetMHPImpl` 0x0052A364): the same base as above for stat 0 (HP). With the
extras: a condition bit halves it (rounded toward zero), HP+5 adds 5, the HP tonic adds 5 (7 with
better tonics), and two mood bits add 2 / take 1. No weapon, no partner, no carried items, no
debuff: the third argument is not even read. Clamped to 0 .. 99.

The map's **HP window** asks the same: `HpWindowUnit::GetMaxHp` 0x0052A350 is three instructions
that fall straight into `GetMHPImpl` (with the extras, no rally), and `HpWindowUnit::GetHp`
0x00373954 reads the unit's current-HP byte (Unit +0xF3).

**Move** (`Unit::GetMovePower` 0x0052D5E4):

```
move = Class.mov + a per-unit bonus (Unit +0x12C; not while state bit 30 is set)
       - a per-unit loss (Unit +0x12D, only when above 0)
```

and with the extras:

```
+ 1 for the move rally (a condition bit, or rally kind 30)
+ the partner's class pair-up move (Class.pair_up[0] of the unit behind), when paired
+ 1 for Move+1
+ 1 for a skill labelled "amphibious", only for a unit in the class category "shooter" (ballistae)
+ half the class move for a condition bit when the unit flies, - half when it does not
- half the class move for another condition bit when the unit flies, + half when it does not
= 0 for one more condition bit
```

then never below 0 (no upper cap). Whether a unit flies or shoots comes from `Unit::GetCategory`
(section 3). What sets the two half-move bits was not traced [low guess: weather or a terrain
effect of a Conquest/Revelation map].

## 3. Class categories, items and levels

- **Categories** (`Unit::GetCategory` 0x0052B728): the class's category bits (Class +0x1A), plus
  "dragon" when the unit, its person or its class has the PersonFlag bit labelled "manakete",
  plus "beast" for the bit labelled "laguz", and minus "dragon" for the bit labelled "cannot use
  special weapons". This is what effective weapons test (docs/FORMULAS.md section 4) and what
  move asks.
- **Equipped item** (`Unit::GetItemEquipped` 0x0052EFE8, and the same code again at 0x003D5FB0):
  the carried item whose equipped flag is set (via `GetItemIndexEquipped`), or nothing.
- **Held item** (`Unit::GetItemIndexHold` 0x0052F474): the equipped item's slot, else the first
  staff the unit may wield (`Unit::CanItemEquip`), else -1. Each slot is tested in turn.
- **Item count** (`Unit::GetHasItemNum` 0x0052E594): the slot of the first empty item, else 5.
- **Shown level** (`Unit::GetShowLevel` 0x0052DC44): the level, at most 99.
- **Low level** (`Unit::GetLowLevel` 0x0052BBCC): the level, plus 20 in a class with the
  "promoted class" PersonFlag bit (the level counted from the first class).
- **Shortest range** (`Unit::GetRangeI` 0x00534474): the weapon's shortest range, except that a
  bow whose shortest range is 2 or more reaches from 1 when the unit has the skill labelled "close
  shot". The longest range (`GetRangeO`) is not in this batch (section 5).

## 4. Who may attack whom, and four yes/no questions

- **May not attack** (`Unit::IsDontAttack` 0x0052DC90): yes when either unit has state bit 22
  (unless the caller asks to ignore it), when the other unit's person is the one person this unit
  is told never to attack (Unit +0xF8), or when the other unit's army type is in this unit's
  "never attack" set (Unit +0x12E, one bit per army type; an army type of 32 or more never
  matches, as the game's shift gives 0).
- **Unique** (`Unit::IsUnique` 0x00533A80): no with state bit 18; yes without state bit 28; with
  it, only when the person is a downloaded (DLC) one (`Person::IsDownload`).
- **Special battle** (`Unit::IsSpecialBattle` 0x0052F234): the class is a giant (`Job::IsGiant`)
  or has its special-battle byte set; no without a class.
- **Invisible** (`Unit::IsInvisible` 0x0052C61C): bit 0 of the unit's Belong record's flags.
- **Capturable** (`Unit::CanCaptured` 0x0052AE20): the person's word +0xC is set or the Belong
  record allows it (bit 1), and the person becomes someone for the unit's class
  (`Person::GetCaptureChange`). This is Conquest's capture command.

## 5. Not this batch, and why

- `Unit::GetCapabilityImpl` 0x0052F7A0 (the stat getter by number, through a table of eight
  member-function pointers at 0x006D9CE0 in the data segment, with stat 0 going to `GetMHPImpl`),
  `GetCapabilityRating` 0x005309E0 and `GetNoWeaknessCapabilityRating` 0x00532B70 (the sum of the
  seven stats with or without debuffs): they pass a word on the guest stack to the getters, which
  `guest_call` cannot do yet (include/readable/fe_guest.h). The skill batch met the same limit.
  Round 15: all three are readers now (guest_call5 / guest_call6; docs/CAPABILITY.md).
- `Unit::GetRangeO` 0x00534510 (longest range; magic tomes with "range = magic / 2", a staff skill
  that sets 10), `GetInterferenceRodHit` 0x0053135C and `GetInterferenceRodAvoid` 0x00531D30
  (hindering staff hit and avoid): the same stack word, or they would call the battle batch's C
  stat code, which this batch does not do (efficiency rule 5: groups that do not call each other).
- `map::BattleInfo::Side::CalculateDetailDefense` 0x00349CF0 / `CalculateDetailAvoid` 0x003491F8:
  they store into the fight side (writers in this project's sense).

## 6. Checks

**Host differential test** `python src/readable/sheet/tests/sheet_diff.py` (the skill test's method
and ARM interpreter): made-up states with values outside the game's ranges on purpose (negative and
huge stat caps, bools that are not 0/1, rally kinds that are no rally, army types of 32 and more,
slots past 4), unmapped units and "torn" units whose record stops at an offset the readers read, so
a read the game skips shows as a count of unmapped reads. For each override it compares r0, the
unmapped reads and the list of guest calls with their argument registers in order; a nested give-up
is a mismatch. `unit_move`'s call to `GetCategory` runs as ARM code on one side and as the readable
override on the other.

Results 2026-11-13:

| Run | Cases | Mismatches | Planted bugs |
|---|---|---|---|
| default (`--plant`, seed 20261113, 300 per function) | 5,700 | 0 | 40/40 caught |
| long (`-n 1500 --seed 7`) | 28,500 | 0 | - |

No early give-ups in either run. Cold caches (both sides gave up at the cache) were 3 % to 15 % of
a function's cases, by design.

The test found one real fault while it was written: `hp_window_max_hp` first read the window and
then gave up on a cold HP cache, a read before the give-up. It now asks the cache first.

**Tier 2** (`tools/readable/verify.py`'s pipeline with a build/ copy of the registry plus this
batch's rows, only this batch's 19 addresses, `build/readable/verify_sheet`, below-normal priority,
library build 416 s): **1 CLEAN, 7 ABI-ONLY, 8 GAVE-UP, 3 MISMATCH**.

- GAVE-UP (defence, resistance, maximum HP, the HP window's maximum, move, categories, low level,
  shortest range): verify's made-up memory has every one-time cache cold, so the readable code
  gave up and the original ran, as in every earlier batch. Proves nothing either way; the host
  test and the live compare cover them.
- The 3 MISMATCH verdicts are all in the **shadow pass**, all a count of unmapped reads only, and in
  all three the readable pass alone (readable code against verify's interpreter) passed (ABI-ONLY)
  and the shadow log says "shadow match", 0 mismatches. The classifier's rules
  (tools/readable/check.py, "shadow surplus") do not cover these two shapes:
  - `unit_equipped_item` and `unit_equipped_item_mutable`: 10 against 40. All of the readable
    code's reads are made by its guest call to `GetItemIndexEquipped`, itself an override
    (`unit_equipped_index`); in shadow mode that call runs the callee's original AND its readable
    code, so the readable part counts twice: 10 (original, with the callee's original) + 10 (the
    callee's readable code, from the original's call) + 2 x 10 (this override's readable code) =
    40 (FE_ENTRY's shadow branch, include/readable/fe_guest.h; [med]: the counts fit, the log
    shows only the first match per function). The rule allows at most 3 x 10.
  - `unit_is_special_battle`: 25 against 34. Its callee `Job::IsGiant` fills a one-time cache by
    name the first time (many unmapped reads in verify's memory). In the readable pass the cache is
    cold, so those reads are in the 25; in the shadow pass the original filled it first, so the
    readable code's call reads only 9 more: 25 + 9 = 34. The rule wants 2 x 25 < count.
  Neither is a difference in results or guest state; they are left as MISMATCH in the verifier's
  own terms until the classifier owner (integrate) decides whether to add these two shapes.

## 7. A finding for the battle batch (not changed here)

`forecast_strikes` (src/readable/battle/formula_forecast.c, `GetSimpleTimes`) calls
`Unit::GetRangeI` through the guest without asking its one-time cache (0x006D9898) first. Once
`unit_range_min` is in the library, a cold cache there makes the inner override give up inside the
outer one (a nested give-up: harmless in play, a surplus of unmapped reads in tier 2). The cache is
filled the first time any range is asked, so a real route almost certainly never meets it cold
[med]. The fix is one more `fe_static_ready(ctx, 0x006D9898u)` in `forecast_strikes`' opening
test; that file belongs to the battle batch, so it is left to the integrator.

## 8. Where these will be met (live compare)

Expected on every Birthright, Conquest and Revelation route [med, not yet run]: defence,
resistance and maximum HP in every fight and forecast, move whenever a unit is selected, the HP
window when the cursor rests on a unit, categories in every fight (effectiveness), the shortest
range in every forecast. `unit_can_be_captured` should meet Conquest's capture command (cq-*
routes); `unit_is_special_battle` the giant fights, `unit_low_level` the experience screens. None
was run in a live compare in this batch (no robot runs: share 0).
