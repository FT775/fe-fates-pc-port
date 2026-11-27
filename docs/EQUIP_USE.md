# May this unit hold this item (Fates): Unit::CanItemEquip

**In plain words.** This batch (docs/tracks/REWRITE_ORDER3.md batch 1) rewrites the game's answer
to "may this unit hold this weapon or staff". The game asks it everywhere: the item and equip
menus, trades, the unit screen, preparations, every fight forecast, the AI, and the castle.
A weapon-lock or class mod can be checked against it. It cannot change an answer: that needs a
table edit, or a writer. The batch's second function, "may this unit use this item now"
(`Unit::CanItemUse`), is not rewritten. Section 4 says why.

Status 2026-11-16 (batch `equip_use`). **UNVERIFIED** in the project's sense:

- **1 readable override** (`src/readable/equip_use/equip_use.c`, registry and target rows added):
  `unit_can_equip_item`.

It matches the game's own ARM code on made-up cases (several seeds): the same answer, the same
guest calls in the same order with the same arguments, and the same number of bytes read from
unmapped memory. The planted bugs are in section 5; the results, with tier 2, in section 6. It has not been in a live
compare yet. A separate capture step does that. Nothing changes in the game.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-16) [high unless marked]. No table values or game text are copied here. The names the game
looks up are described in English, not copied.

---

## 1. The question (override)

**`Unit::CanItemEquip(const unit::Item*, bool, bool) const`** (0x0052C634, 3,352 bytes,
`unit_can_equip_item`). Arguments: the unit, the carried item, "staffs allowed" and "check the
unit's own rank". The answer is 1 (yes) or 0 (no).

```
record = unit::Item::ToData(item)                              through the guest
kind   = ItemSubKind::Get(record.weapon_kind).kind (signed byte +1)
no  when "staffs allowed" is 0 and kind = 6 (staff)
no  when kind >= 8 (not a wielded kind; a negative kind goes on)
rank:
  "check own rank" set:  reach = min(unit.weapon_exp[kind], GetWeaponExpLimit(unit, kind))   signed
  else:                  reach = GetWeaponExpLimit(unit, kind)
  no  when reach < record.weapon_rank (the weapon experience the item needs)
stone: ItemSubKind::Get asked again; kind byte 7 (dragonstone / beaststone):
  no  when Job::CanEquipFromSubKind(unit.job, record.weapon_kind) = 0
"only for" items, only when the record's ItemFlag word has one of the nine bits (one cached OR):
  avatar only          the unit's flag bits (unit | Person | class) have the avatar PersonFlag bit,
                       and with state bit 28 the Person is a download one (Person::IsDownload)
  dark-mage line only  GetCategory has the dark-mage category bit, or the unit has the skill that
                       opens dark tomes to other classes (IsEquipSkill)
  male only            no when IsFemale says yes
  female only          no when IsFemale says no
  Takumi, Ryoma, Leo, Xander, Ophelia only   as "avatar only", each with its own PersonFlag bit
"no warp" units: the unit's flag bits have the "no warp" PersonFlag bit, ItemSubKind::Get (third
  time) says staff, and the record's use number is the rescue or the draw staff's: no
yes otherwise
```

Every test reads what it needs again, as the game does: the record's ItemFlag word is read once for
the "any only for" test and the avatar test, then again for each later test; the unit's three flag
words and its Person and class pointers are read again for each test that needs them. The readable
code does the same, so an unmapped or "torn" record or unit gives the same count of unmapped reads.
The Person handed to `IsDownload` is the one read for that test's flag words.

**Reach.** 71 direct (ARM BL) calls in the game (menus, trade, equip, the unit screen, the AI, the castle,
`Unit::ItemEquip`, `Unit::WeaponBuildup`, `Unit::CanItemUse` and more). Three older overrides call
it through the guest: `unit_held_item_index`, `unit_can_cannon_item` and `ai_has_heal_rod`. Any
route with a fight or an item menu should meet it [med: not yet run live]. No chapter is added.

## 2. The one-time caches

The game fills 21 caches of its own the first time the function runs, each behind a guard word
(0x006D9804 to 0x006D9854, 4 bytes apart). Each looks a name up in a data table and keeps a number
or a bit:

| What | Kept as | Where |
|---|---|---|
| the dark-mage class line (JobCategory) | u16, 1 << number | 0x006D9670 |
| the skill that opens dark tomes (EquipSkill record +0x10) | s16 | 0x006D9672 |
| the rescue and draw staffs (ItemUse) | u16 each | 0x006D9674, 0x006D9676 |
| avatar, Takumi, Ryoma, Leo, Xander, Ophelia, "no warp" (PrivateSkill) | u64 PersonFlag bit each | 0x006D9B10 .. 0x006D9B40 |
| "only for" avatar, dark-mage line, male, female, Takumi, Ryoma, Leo, Xander, Ophelia (ItemSkill) | u64 ItemFlag bit each | 0x006D9B48 .. 0x006D9B88 |
| the nine "only for" bits ORed | u64 | 0x006D9B90 |

The readable code only reads these. It gives up while any guard is cold, before reading anything
else. It also asks first the caches of the three overrides it calls that have them
(`unit_weapon_exp_limit`: 3, `person_is_download`: 1, `unit_category`: 5), so a cold one never makes
an inner override give up inside this one (the item batch's rule, docs/ITEM.md section 5). While
cold, the original runs. That is only before the game's first call of each.

## 3. Guest calls

In the game's order, with the game's arguments (docs/DECISIONS.md F-018):
`unit::Item::ToData` (item_to_data), `ItemSubKind::Get` up to three times (item_subkind_record),
`Unit::GetWeaponExpLimit` (unit_weapon_exp_limit), `Job::CanEquipFromSubKind` (who_holds_can_equip_subkind since round 21, docs/WHO_HOLDS.md),
`Person::IsDownload` up to six times (person_is_download), `Unit::GetCategory` (unit_category),
`Unit::IsEquipSkill` (unit_has_skill), `Unit::IsFemale` up to twice (female_unit_is_female since round 22, docs/FEMALE.md). Each was read:
none stores anything but a one-time cache of its own. The 64-bit shift the game uses to fill a cache
(`__aeabi_llsl`) runs only while filling, so the readable code never meets it.

## 4. Not here, and why

- **`Unit::CanItemUse`** (0x0052920C, 3,092 bytes): "may this unit use this item now" (heal, rally,
  stat boosters, seals, skill and vein scrolls). It only reads guest memory, but it cannot be written
  as a readable override with today's tools:
  - for a class-change seal it builds a `ClassChangeEnumerator` object in its own 1,040-byte stack
    frame (the unit at +0, a count at +0x404, a byte at +0x408) and has
    `ClassChangeEnumerator::Enumerate` fill it, then reads the count. The readable side would have
    to write that object into guest memory below sp and hand its address to the callee. Readable
    code may not write guest memory (the only exception is guest_call5's one stack word);
  - for a stat booster it calls `Unit::GetCapabilityImpl` with two words on the stack. guest_call5
    passes one.
  A later batch could do it with a guest_call6 and a "stack object" helper, both core changes. Its
  rally-scan part (`TstCheerFromCapabilityIndex` for units 1 to 4 tiles away) and its heal part
  would then be the readable body.
- **Anything that stores the item**: `Unit::ItemEquip`, `Unit::WeaponBuildup`, `Unit::SetDisposItem`,
  the trade and equip menus' actions. Not readers.
- **The same question for other things**: `Unit::IsItemRangeCanEquip`, `IsItemSkillCanEquip`,
  `GetItemMaxRangeCanEquip`, `GetBasicItemCanEquipForArena` call this function and are not in the
  plan row.

## 5. Checks

**Host differential test:** `python src/readable/equip_use/tests/equip_use_diff.py` (the method of
shop_price_diff.py). The ARM interpreter src/readable/battle/tests/arm_mini.py runs on
extracted/text.bin, and the readable C is built with the host gcc. Both sides compare r0, the
unmapped reads, and the whole ordered list of guest calls with their argument registers. A guest
write by the readable code is flagged as a mismatch. Every callee is answered by one table on both
sides, never by its override, so a nested give-up cannot happen in this test (the driver would flag
one, but none can arise).

Give-ups are checked both ways. The test knows which of the 30 guards (the 21 own and the 9 of the
three overrides it calls) it made cold, and requires:
- a case with any guard cold: the readable code gives up before any unmapped read ([gave up, 0
  bytes]), whatever the original did. A cold own cache makes the original reach the guard routine
  (or not, when its path never reads that cache); a cold callee cache is not seen by the original at
  all, since the table answers the callee. Cases where the original went on are counted apart as
  "early give-ups" (safe: the original runs);
- a case with every guard warm: the readable result must equal the original's. A give-up there is a
  mismatch.
Each of the 30 guards is made cold in turn (cold means bit 0 clear: mostly 0, every fourth time
0x100), so every guard is tested on every run; the test prints how many cases each guard was cold
in and fails if one never was. Until 2026-11-16 (review) any readable give-up was accepted as an
"early give-up" without checking that a guard was cold, so an override that always gave up, an extra
guard, or a callee guard left out all passed; that is fixed, and those are now planted bugs.

The made-up states are random test values, never game data, often outside what the game uses:
unmapped units, Persons, classes, records and sub-kind records; weapon kinds of 8 and up and
negative ones; bools that are not 0 or 1; a combined "only for" cache that does not match its nine
parts; experience caps of -1 and 2^31; callee answers other than 0 and 1; negative cached skill
numbers. Two case shapes are made on purpose: a staff that reaches the "no warp" test, and a weapon
with one "only for" bit. "Torn" records (only the first 4 or 8 bytes mapped) and a "torn" unit (only
its first 0x80 bytes mapped) make a read the game makes once and a copy makes twice show as more
unmapped bytes. One cold guard is chosen in about 30% of the cases, each of the 30 in turn, the
first and last of the 21 more often.

**Planted bugs** (`--plant`, 39): the first or last own guard not asked; the override always giving
up; one extra (cold) guard asked; each of the 9 callee guards left out (one plant each); the staff
and kind >= 8 tests;
a signed or unsigned kind; the rank branch, min / max, signed / unsigned, < / <=, and the experience
byte; the stone test's kind and its class argument; the "any only for" cache; the avatar test
reading the flag word again; a royal's PersonFlag test, state bit and Person re-read; the class flag
word left out; the dark-mage category and skill sign; the male and female tests; a royal's bit
swapped or one royal left out; the "no warp" bit, staff kind, the draw staff and the use byte.

**Tier 2** (`tools/readable/verify.py`): section 6.

## 6. Results (2026-11-16)

After the review fix (the give-up check above; no change to the C):
- Host test with `--plant`, seeds 20261116, 7, 11, 42, 99 and 123: **300 cases, 0 mismatches,
  39/39 planted bugs caught** on each. Seed 20261116: 73 cases gave up on both sides, 18 early
  give-ups; each own guard cold in 3 to 10 cases, each callee guard in 2. The three plants the
  reviewer found missed (always give up; extra guard 0x006D9858; the download guard left out) are
  caught: 213, 213 and 2 mismatches.
- Host test, seed 7, 1,500 cases: **0 mismatches** (356 gave up on both sides, 99 early give-ups,
  310 with unmapped reads; each callee guard cold in 11 cases, each own one in 11 to 69).
- After the fix: `python tools/readable/check.py --selftest` readable OK (lint 280 rows 0 problems,
  49 sources, host 146/146, capture 568/568, undo 554/554, self-test 27/27, verify pipeline 28/28);
  `python tools/harness/gen_stubs.py --check` OK (245 overrides, 60 guard users, 5 writers). Tier 2
  was not rerun: the C did not change, and it is UNSAMPLED for this address anyway (below).

Before the review fix (the old test, which accepted any give-up):

- Host test, seed 20261116, 300 cases, with `--plant`: **300 cases, 0 mismatches, 28/28 planted
  bugs caught** (plants on 300 cases of seed 20261117). 47 cases gave up on a cold own cache (both
  sides), 16 were early give-ups. Paths met, by the answer and the last guest call before it: no
  after GetWeaponExpLimit 50, after ItemSubKind::Get 83, after CanEquipFromSubKind 13, after
  IsDownload 13, after GetCategory 6, after IsEquipSkill 6, after IsFemale 25; yes after each of
  the seven callees (50 after the last ItemSubKind::Get).
- Host test, seed 7, with `--plant`: **300 cases, 0 mismatches, 28/28 planted bugs caught**. The
  plants were also caught on seeds 11, 42, 99 and 123 (28/28 each).
- Host test, seed 7, 1,500 cases: **1,500 cases, 0 mismatches** (219 gave up on both sides, 58
  early give-ups, 340 with unmapped reads, 5,637 guest calls listed).
- Tier 2 (`python tools/readable/verify.py --out build/readable/verify_equip_use --only 0x0052C634`;
  the verify library was built from the tree as it stood then, which took 328 s): **1 UNSAMPLED,
  0 MISMATCH** (`readable-verify: OK`). UNSAMPLED here means verify cannot pick the address: in
  3dsrecomp's discovery the function's code is held inside another generated function
  (`f_0052FB98`, per the build's lib/entries.c: the entries 0x0052C658, 0x0052C668 ... of this
  function point into it), so both passes tested 0 functions. Nothing was compared, so this proves
  nothing either way. The classifier was not changed. The host test above and the live compare
  (capture step) are the checks that count for this function.
- `python tools/readable/check.py --selftest`: readable OK (lint 280 rows 0 problems, 49 sources,
  host 146/146, capture 568/568, undo 554/554, self-test 27/27, verify pipeline 28/28).
  `python tools/harness/gen_stubs.py --check`: OK (245 overrides at the time of the run, counting
  other batches' rows added the same night).
