# Does this carried item add its bonus (Fates): `Unit::IsItemEnhanceHave`

**In plain words.** Some items give a bonus just by being carried. Before the game adds that bonus
(to a stat, or to movement for one special bow), it asks: does this item really count for this
unit? The item must have the "bonus while carried" mark. The caller can also ask it to count the
Fujin Yumi and the Brynhildr. An item made "only for" one of six people (the avatar, Takumi, Ryoma,
Leo, Xander, Ophelia) counts at once in that person's hands. Any other item counts if its sub-kind is
exactly kind 8, or else if the unit could equip it. This batch (docs/tracks/REWRITE_ORDER4.md row 5,
round 23) rewrites that one question. It stores nothing: it only reads. The callers are unchanged.

Status 2026-11-17 (round 23 batch `item_enhance`), **UNVERIFIED** in the project's sense:

- **1 readable override** (`src/readable/item_enhance/item_enhance.c`, registry and target rows
  added): `unit_item_enhance_have`.

It gives the same answers as the game's own ARM code on made-up cases (fourteen seeds and long
runs), with the same guest calls in the same order and the same unmapped reads. The planted bugs and
the tier-2 result are in section 4. Live compare: not done here (a separate capture step does that).
Nothing changes in the game.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-17) [high unless marked]. No table values or game text are copied here. The fifteen ID labels
(SPID_, ISID_) are described in English.

---

## 1. What it decides

**`Unit::IsItemEnhanceHave(const unit::Item*, bool) const`** (0x0052FB98, 2,500 bytes with its two
literal pools: r0 the unit, r1 one of its unit::Items, r2 the bool).

```
first time only (sixteen one-time caches, each behind a C++ guard word, asked in this order,
guards 0x006D9894 going down one word to 0x006D9858; every value a u64):
  1 << the PrivateSkill (PersonFlag) number of: avatar, Takumi, Ryoma, Leo, Xander, Ophelia
                                                    (0x006D9B98, BA0, BA8, BB0, BB8, BC0)
  1 << the ItemSkill (ItemFlag) number of: bonus while carried, Fujin Yumi, Brynhildr
                                                    (0x006D9BC8, BD0, BD8)
  1 << the ItemSkill number of: only for the avatar, Takumi, Ryoma, Leo, Xander, Ophelia
                                                    (0x006D9BE0, BE8, BF0, BF8, C00, C08)
  the six "only for" bits ORed                      (0x006D9C10)

data   = unit::Item::ToData(item)
wanted = bonus while carried | (bool != 0 ? Fujin Yumi | Brynhildr : 0)    (the bool: whole word)
flags  = data's ItemFlag word (u64 at +0)
if flags & wanted == 0:              answer 0
if flags & (the six "only for" bits ORed) != 0:
  for each owner in order avatar, Takumi, Ryoma, Leo, Xander, Ophelia:
    (flags read again from data for every owner after the first)
    if flags has the owner's "only for" bit and
       (unit.private_flags | person.flags | class.flags) has the owner's PersonFlag bit:
      if unit.state_flags bit 28 is clear:              answer 1
      if Person::IsDownload(unit.person) != 0:          answer 1
      (otherwise go on with the next owner)
if ItemSubKind::Get(data.weapon_kind, signed byte +0x1A).kind (u8 at +1) == 8:   answer 1
answer Unit::CanItemEquip(unit, item, 1, 1), as it is        (a tail branch, B)
```

Details that matter for matching the game exactly:

- An owner's item that its owner does NOT hold is not answered 0: the game goes on to the
  sub-kind and equip tests. So does an owner's item held by a unit with state bit 28 and a Person
  that is not a download one.
- The combined mask is a cache of its own, read as it is. It is not rebuilt from the six parts.
- The unit's three flag words, the person and class pointers and state_flags are read again for
  every owner tested. The record's flag word is read again for every owner after the first. Only
  the number of unmapped bytes is compared, and the readable code reads the same bytes.
- `Person::IsDownload`'s answer and the bool are tested as whole words.
- Kind 8 is the first kind number that `Unit::CanItemEquip` never allows ("kinds 8 and up are not
  wielded", docs/EQUIP_USE.md) [low for what kind 8 holds].
- State bit 28 is the same bit CanItemEquip tests for its "royal only" items (equip_use.h
  `EU_UNIT_DOWNLOAD_ONLY`) [low for what the bit means].

## 2. Why it is a reader

The body's only stores are into its own sixteen caches (one `stm` each, the first time it runs,
after a `PrivateSkill::Get` or `ItemSkill::Get` and `__aeabi_llsl`) and its own stack (it pushes
r0-r2). The readable code never stores. While any of the sixteen guard words is cold, it gives up at
entry, before it reads or calls anything else, so the game's own code runs and fills the caches
exactly as before. The three guest callees are readable overrides already and store nothing outside
their own one-time caches (`item_to_data`, `person_is_download`, `item_subkind_record`). Each is a
guest call, in the game's order, with the game's arguments. The battle note's "12 caches" was a
count from the outside. The body has sixteen guard words.

**The tail branch (docs/MOVE.md 9, the check for each batch).** The function ends with
`b 0x0052C634` (`Unit::CanItemEquip`, the override `unit_can_equip_item`). 3dsrecomp copies
CanItemEquip's code into this function's generated function. The capture library's `f_0052FB98`
(build/harness/lib/code201.c, built 2026-11-16, and build/harness/next/lib/code201.c, 2026-11-17)
has `case 0x0052C634u: goto L_0052C634;` in its dispatch and `goto L_0052C634;` at 0x0053054C, even
though entries.c maps 0x0052C634 to `override_0x0052C634`. So the original never enters that
override from here, and the live compare would not list it. The readable code therefore runs
`unit_can_equip_item`'s C directly, with no guest call (capability.c does the same with
`unit_max_hp`). For that reason it also asks, at entry, the 30 caches that `unit_can_equip_item`
asks before it reads anything (its 21 own, and those of GetWeaponExpLimit, IsDownload and
GetCategory; equip_use.c `caches_ready`). A cold one makes the readable code give up early. That is
safe, because the original then runs. Those caches are filled by the first equip check of a game,
long before a bonus is asked. The tier-2 build's own generated code is in section 4.

Not here, and why (Grok's row: "do not"): a new map to meet one bow, and the forge window.

**Callers in the game** (every BL/B whose target is 0x0052FB98, found in text.bin; all BL, no tail
branch): `anonymous_namespace::GetEnhanceHave` (0x0033A7B4; readable `unit_item_stat_bonus`, asks
with false), `map::BattleCalculator::CalculateAttackSingle` (0x00363930), `sortie::entrust::detail::
Score::Calculate` (0x004BC738, 0x004BC7C0), `GameHelp::(anonymous)::CreateCapabilityString`
(0x004E9438), `Unit::IsCostFree` (0x0052ACCC; readable `unit_is_cost_free`, asks with true). In the
capture library every one of the six is `reg15_ = 0x0052FB98u; CALL(f_0052FB98);`: a real call, so
the override is entered.

**Reach.** A fight already on disk (Grok: one route). The separate capture step picks it. No chapter
is added.

## 3. Checks

**Host differential test:** `python src/readable/item_enhance/tests/item_enhance_diff.py` uses the
method of rod_target_diff.py and equip_use_diff.py. The ARM interpreter
src/readable/battle/tests/arm_mini.py runs on extracted/text.bin against the readable C built with
the host gcc. Compared: r0, unmapped reads and the ordered list of guest calls with their argument
registers. Nested give-ups and guest writes are flagged. The made-up states start from
equip_use_diff.py's `base_state` (units, Persons, classes, Item and ItemSubKind records, torn
records and a torn unit, CanItemEquip's caches). The test adds this function's caches, item flag
words aimed at one of the bonus bits, owners' bits in the unit's, Person's or class's word, state
bit 28, IsDownload answers and kind 8. The original runs **on through the tail branch into
CanItemEquip's ARM code**, so the readable side's direct C call is compared with the real thing.
Both functions' callees are answered by one table on both sides and listed. CanItemEquip itself is
listed on neither side. The values are random test values, never game data, and often outside what
the game uses:

- bools 2, 0x100, 0x80000000 and 0xFFFFFFFF;
- IsDownload answers 0x100 and 0x80000000;
- a combined "only for" cache that does not match its six parts;
- owners' bits equal to CanItemEquip's own bits or not;
- unmapped units, records and sub-kinds.

Cold guards: every fourth case has exactly one guard cold. Own guards and CanItemEquip's guards
take turns, so all 16 and all 30 are made cold on every 300-case run. The readable code must then
give up before any read. A cold own guard makes the original reach the guard routine at entry. The
first time round, a CanItemEquip guard is made cold in a case with no bonus bit: the original answers
0 before the tail, so only the readable code's own test of that guard can make it give up. These
cases are counted as "early give-ups" (safe). In 10% of cases the record is the torn one (only the
low word of its flags mapped) and the item belongs to an owner past the first. A flag word read once
instead of once per owner then shows as fewer unmapped bytes.

**Planted bugs** (`--plant`, 29):

- the caches: the cache test dropped; the first or the last own guard not asked; CanItemEquip's 21
  guards not asked; the download guard not asked;
- the bonus bits: "bonus while carried" missing; the named weapons never added, or always added;
  the bool tested on its low byte; the Brynhildr bit left out; no bonus bit answered 1;
- the owners: the combined test dropped; the flag word not read again for each owner; two owners'
  pairs crossed; the last owner dropped; an owner's item that its owner does not hold answered 0;
  the Person's or the class's flag word left out; the flags cut to 32 bits;
- state bit 28 and IsDownload: the wrong bit; the bit test turned round; IsDownload not asked;
  IsDownload's answer read as a byte;
- the sub-kind: weapon_kind read unsigned; kind 7 in place of 8; the kind test dropped;
- the equip test: CanItemEquip's bools (1, 0) or (0, 1); the equip test made a guest call (the
  round-10 lesson: the live library inlines it).

Not planted, because they cannot change an answer: reducing CanItemEquip's answer to 1 or 0 (its
ARM code answers only 0 or 1, and the test saw only those); the order of reads inside one owner test
(only the count of unmapped bytes is compared); the order of the 16 own guards (all are asked before
anything else, so any one cold gives up at entry either way).

**Tier 2** (`tools/readable/verify.py`): section 4.

## 4. Results (2026-11-17)

- Host test with `--plant`, fourteen seeds (20261117, 7, 11, 13, 99, 5, 12, 14, 15, 16, 1, 2, 3,
  4242), 300 cases each: **every seed 300 cases, 0 mismatches, 29/29 planted bugs caught**. On every
  run all 16 own guards and all 30 CanItemEquip guards were made cold alone at least once. The
  fewest cases that caught any plant on any seed: 1 for the download guard on seed 1 (certain by
  construction: its cold case answers before the tail branch), 2 for the last own guard and for the
  dropped combined "only for" test, and 3 for the first own guard and the bool tested on its low
  byte. Per-seed logs: build/readable/item_enhance/plant_s<seed>.txt.
  (Review history inside the batch: the first test missed "flag word not read again" on the default
  seed, because no case had a torn record with an owner past the first; the 10% torn-owner share
  was added. Then "IsDownload's answer as a byte" was missed on seed 13; owners' cases now set state
  bit 28 in 60% of them and answer IsDownload with 0, 1, 2, 0x100 or 0x80000000. Then the download
  guard plant was missed once, when its only cold case reached the tail and unit_can_equip_item gave
  up there too; the first round of CanItemEquip cold cases now has no bonus bit.)
- Default seed, 300 cases: 42 gave up on both sides (cold), 37 early give-ups (a CanItemEquip cache
  cold, tail not reached, the readable code gave up at entry: safe). Of the cases that did not give
  up, 97 answered 1 and 90 had unmapped reads. Paths met: no bonus bit; an owner's item at once (also after IsDownload); kind
  8; the equip test answering 1 and 0 (also after an IsDownload that said no); each with and without
  unmapped reads, for "bonus while carried", Fujin Yumi and Brynhildr.
- Long runs: seed 7, 1,500 cases: **0 mismatches**. Seed 4242, 3,000 cases: **0 mismatches**.
- Tier 2 (`python tools/readable/verify.py --out build/readable/verify_item_enhance --only
  0x0052FB98`, library build 338 s, at below-normal priority): **1 GAVE-UP, 0 MISMATCH**
  (`readable-verify: OK (1 GAVE-UP)`). verify's made-up memory has the guard words cold, so the
  readable code gave up at entry and only the fallback was tested; the interpreter and the
  recompiled original agreed (3,418 native instructions). GAVE-UP is not a pass. No classifier
  change. In that build all six callers are `CALL(override_0x0052FB98)`, and the tail branch at
  0x0053054C is still `goto L_0052C634;` (the copy of CanItemEquip inside f_0052FB98), which confirms
  section 2 in the build that carries the override. The lines are kept in
  build/readable/verify_item_enhance/caller_sites.txt. The library (542 MB) was deleted after the
  run. The logs are kept in build/readable/verify_item_enhance/.
- `python tools/readable/check.py --selftest`: readable OK (lint 296 rows 0 problems, 58 sources
  against the stub, 58 staged self-contained files, host 146/146, capture 568/568, undo 554/554,
  self-test 27/27, verify pipeline 28/28). The counts include row 6 (`volume`), running at the same
  time.
- `python tools/harness/gen_stubs.py --check`: OK (262 overrides, 66 guard users; this row carries
  the guard tag because the body calls the guard routine 0x00302C6C).
- Callers in the readable layer: `unit_item_stat_bonus` (battle2) and `unit_is_cost_free` (move)
  reach this override through their guest calls. Their host tests answer it from a table, so they
  are unchanged.
- Live compare: not done in this batch (the capture step does it: one route with a fight, Grok's
  row). Until then the status stays UNVERIFIED.
