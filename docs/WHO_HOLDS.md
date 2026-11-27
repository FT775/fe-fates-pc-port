# May this class hold this kind of weapon (Fates): `Job::CanEquipFromSubKind`

**In plain words.** Before the game lets a unit hold a weapon, it asks whether the unit's class
may hold that kind of weapon at all. For a sword, lance, axe, dagger, bow, tome or staff the answer
is simple: the class may, if its weapon-rank cap for that kind is not 0. Dragonstones and
beaststones have a rule each, on what the class is (dragon blood, beast, monster, human shape, a
class that transforms, and which side it comes from). This batch (docs/tracks/REWRITE_ORDER4.md
row 2, round 21) rewrites that one question. It stores nothing: it only reads. The callers
(`Unit::CanItemEquip`, the unit screen's weapon-rank line and the game's own) are unchanged.

Status 2026-11-17 (round 21 batch `who_holds`), **UNVERIFIED** in the project's sense:

- **1 readable override** (`src/readable/who_holds/who_holds.c`, registry and target rows added):
  `who_holds_can_equip_subkind`.

It gives the same answers as the game's own ARM code on made-up cases (two seeds), with the same
guest call and the same unmapped reads; the planted bugs and the tier-2 result are in section 4.
Not yet in a live compare: a separate capture step rebuilds the capture library and compares the
override in real play. Nothing changes in the game.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-17) [high unless marked]. No table values or game text are copied here: the five category
names are ID names (JCID_), given here in English.

---

## 1. What it decides

**`Job::CanEquipFromSubKind(ItemSubKind::Type) const`** (0x00524420, 174 words with its literal
pool: r0 the class record, r1 the weapon sub-kind number).

```
first time only (five one-time caches, each behind a C++ guard word, asked in this order):
  dragon    = 1 << index of the JobCategory ID "manakete"   (guard 0x006D39D0, u16 at 0x006D3994)
  beast     = 1 << index of "laguz"                          (guard 0x006D39CC, u16 at 0x006D3996)
  monster   = 1 << index of "mamono"                         (guard 0x006D39C8, u16 at 0x006D3998)
  humanoid  = 1 << index of "hitogata"                       (guard 0x006D39C4, u16 at 0x006D399A)
  transform = 1 << index of "henshin"                        (guard 0x006D39C0, u16 at 0x006D399C)

record = ItemSubKind::Get(sub)              (sub passed as the full word)
kind   = record's kind byte (+1), read signed
if kind != 7:
  return class.max_weapon_exp[kind] != 0     (the byte at class + 0x44 + kind; kind is not range-checked)
stones (kind 7), on the class's category word (class + 0x1A, u16):
  sub 14: dragon and not transform
  sub 15: beast
  sub 16: dragon and transform
  sub 17: monster and not humanoid
  sub 18: humanoid and class origin (+0x74) == 2 (Nohr side)
  sub 19: humanoid and class origin == 1 (Hoshido side)
  any other sub: no
answers are 1 or 0
```

Details that matter for matching the game exactly:

- The stone switch is the game's jump table on `sub - 14` compared unsigned with 6: only the full
  word 14 .. 19 takes a rule. A sub-kind whose low byte is 14 .. 19 but whose word is not
  (0x10E, -242) answers 0 when its record says stone. The readable `switch` on the full word does
  the same.
- For a stone, the game reads the cache first, then the class's category word once, and tests the
  same word against a second cache. The readable code keeps that order (helper `first_has`).
- A kind byte 0x80 .. 0xFF is negative: the cap byte is read before the class record (class + 0x44
  - 128 .. class + 0x43). A kind 8 .. 127 reads past the eight caps. The readable code adds the
  signed kind exactly as the game does.

## 2. Why it is a reader

The body's only stores are into its own five caches (the `strh` after each name lookup, the first
time it runs) and its own stack (push/pop). The readable code never stores: while any of the five
guard words is cold it gives up at entry, before it reads or calls anything else, so the game's
own code runs and fills the caches exactly as before. The one call, `ItemSubKind::Get`, is a
readable override already (item_subkind_record, triangle batch). Not here, and why:

- **They store or build** (Grok's row: "do not"): the buy action, `Unit::ItemEquip` (writes the
  unit's item list), `Unit::CanItemUse` (builds a ClassChangeEnumerator on its stack,
  docs/EQUIP_USE.md section 4).
- **The callers**: `Unit::CanItemEquip` (unit_can_equip_item, docs/EQUIP_USE.md) and
  `GameInfoViewer::GetWeaponLevelKind` (weapon_level_view_kind, docs/WEAPON_LEVEL_VIEW.md) already
  call this function through `guest_call2`; that call now reaches this override. When this
  override gives up nested (a cold cache), its own entry runs the original for that call
  (include/readable/fe_guest.h, FE_ENTRY): the caller's answer does not change. Neither caller's
  folder was edited.

**Reach.** A preparations or fight route that already met the equip check (Grok: one route); the
separate capture step picks it. No chapter is added.

## 3. Checks

**Host differential test:** `python src/readable/who_holds/tests/who_holds_diff.py`
(weapon_level_view_diff.py's method: the ARM interpreter src/readable/battle/tests/arm_mini.py on
extracted/text.bin against the readable C built with the host gcc; r0, unmapped reads and the
ordered list of guest calls with their argument registers; nested give-ups and guest writes
flagged). `ItemSubKind::Get` is answered by one table on both sides and listed. While a guard is
cold the original reaches the guard routine before any other read (arm_mini raises "cold guard")
and the readable code must give up at entry. The made-up states are random test values, never game
data, and often outside what the game uses: unmapped class pointers and records, a class whose caps
and origin are on an unmapped page (its category mapped), record kinds past 7 and negative,
sub-kinds negative, huge and with a stone number in the low byte only, cache bits 0, two bits, the
same bit twice or 0xFFFF, origin bytes past 2, one guard cold or several.

**Planted bugs** (`--plant`, 24): the cache test dropped, or with one guard missing (two
plants); `ItemSubKind::Get` read directly instead of called; the sub-kind passed as its low byte;
the kind read unsigned or from the wrong byte; the stone kind 6, or the stone test `<`; the cap
byte read without the kind, compared with 1, or with the kind clamped to 0 .. 7; the stone table
from 13; rule 14's transform test inverted; rule 15 on the dragon bit; rule 16's second test
dropped; rule 17 on transform instead of humanoid; the Nohr origin 3; rule 19's origin `>=`; rule
19's humanoid test dropped; other stone sub-kinds answering 1; the category read as a byte; a
cache read from the wrong word; the second test on the low byte only.

Not planted, because they cannot change an answer: the order of the cache read and the class's
category read (the caches are always mapped, so only the class read can fault, once either way);
the 1-or-0 form of the answer (the game's `mov r0,#1` / `mov r0,#0` and the C comparison give the
same word).

**Tier 2** (`tools/readable/verify.py`): section 4.

## 4. Results (2026-11-17)

- Host test, seed 20261117, 300 cases, with `--plant`: **300 cases, 0 mismatches, 24/24 planted bugs
  caught**. Paths met: every stone rule both ways (14..19 each answered 1 and 0), other stone
  sub-kinds, caps 0 and not 0, kinds past 7 and negative, 51 cold give-ups at entry; 37 cases with
  unmapped reads.
- Host test, seed 7, with `--plant`: **300 cases, 0 mismatches, 24/24 planted bugs caught**.
- Host test, seed 7, 1500 cases: **1,500 cases, 0 mismatches** (222 cold give-ups at entry; 188
  cases with unmapped reads).
- Tier 2 (`python tools/readable/verify.py --out build/readable/verify_who_holds --only
  0x00524420`; library build 352 s): **1 GAVE-UP, 0 MISMATCH** (`readable-verify: OK`). GAVE-UP:
  the five caches are cold in verify's made-up memory, so the readable code gave up at entry and
  only the fallback ran: proves nothing either way (as `weapon_level_view_kind`). No classifier
  change. This run left out `src/readable/strike/` (the row 1 batch, running at the same time, was
  not registered yet and stage.py refuses an unregistered marker); the scratch wrapper changed
  only which folders were walked, nothing in the repo.
- `python tools/readable/check.py --selftest` (real tree, strike registered by then): readable OK
  (lint 288 rows 0 problems, 54 sources, host 146/146, capture 568/568, undo 554/554, self-test
  27/27 broken inputs, verify pipeline 28/28).
- `python tools/harness/gen_stubs.py --check`: OK (254 overrides, 62 guard users; this row carries
  the guard tag: the body calls the guard routine 0x00302C6C).
- Callers seen in the readable layer: unit_can_equip_item (src/readable/equip_use/equip_use.c) and
  weapon_level_view_kind (src/readable/weapon_level_view/weapon_level_view.c), both through
  `guest_call2`; not edited.
