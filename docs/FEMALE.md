# Is this unit, or this person, female (Fates): `Unit::IsFemale` and `Person::IsFemale`

**In plain words.** Some items may only be held by men or only by women, and a child's growth
takes from the mother's or the father's side. To decide, the game asks one of two questions: "is
this unit female" (a unit on the map or in the army) or "is this person female" (a character's
fixed record). Both answers come from one flag bit, the PersonFlag "female". For a person, only the
person's own flag word counts. For a unit, three flag words count: the unit's own, its person's and
its class's, so a class flag can make a unit female too. This batch (docs/tracks/REWRITE_ORDER4.md
row 3, round 22) rewrites those two questions. They store nothing: they only read. The callers
(`Unit::CanItemEquip`, the growth code and the game's own) are unchanged.

Status 2026-11-17 (round 22 batch `female`), **UNVERIFIED** in the project's sense:

- **2 readable overrides** (`src/readable/female/female.c`, registry and target rows added):
  `female_unit_is_female`, `female_person_is_female`.

They give the same answers as the game's own ARM code on made-up cases (two seeds), with the same
unmapped reads and no guest call; the planted bugs and the tier-2 result are in section 4. Live
compare: the capture step (`r22-cap-female`, bt-ch4, library rebuilt 18:22) gave 45 records, 43 match,
2 cold give-ups, 0 bad, memory 18ca52e007f5179e = every earlier bt-ch4 run; round 22 integrate replayed
it offline (0 bad) and played the 4 cheat routes live (`r22-capc-readers`: both readers met, 0 bad).
Status stays UNVERIFIED until the owner's call. Nothing changes in the game.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-17) [high unless marked]. No table values or game text are copied here: the flag's name is
an ID name (SPID_), given here in English.

---

## 1. What they decide

**`Unit::IsFemale(void) const`** (0x00533938, 41 words with its literal pool: r0 the unit).

```
first time only (one cache, behind a C++ guard word):
  female = 1 << index of the PersonFlag ID "female"     (guard 0x006D97EC, u64 at 0x006D9AF0)

flags = unit.private_flags (+0x00, u64)
      | unit.person (+0x9C) -> PersonData.flags (+0x00, u64)
      | unit.job    (+0xA0) -> JobData.flags    (+0x00, u64)
return (flags & female) != 0          (1 or 0)
```

**`Person::IsFemale(void) const`** (0x0053ED90, 31 words with its literal pool: r0 the Person
record).

```
first time only:
  female = 1 << index of the PersonFlag ID "female"     (guard 0x006D3B2C, u64 at 0x006D3B70)

return (person.flags (+0x00, u64) & female) != 0      (1 or 0)
```

Details that matter for matching the game exactly:

- `Unit::IsFemale` does **not** call `Person::IsFemale`: it reads the three words itself and keeps
  a cache of its own. The two caches hold the same bit in the game, but the readable code reads
  each function's own cache, as the game does (a plant that swaps them is caught).
- The bit is a 64-bit mask: the test covers both halves of each word. Unmapped pointers read as 0
  (the unit, its person or class pointer): the readable code reads the same bytes, so the same
  number of unmapped bytes.
- The answer is the game's `movne r0,#1` / `moveq r0,#0`: 1 or 0, never the raw bits.
- `Job::IsFemale` (0x00524AF4, the class alone, the same shape on JobData.flags) exists, but it is
  not in Grok's row and was not rewritten here.

## 2. Why they are readers

Each body's only stores are into its own cache (the `strd` after the name lookup, the first time it
runs) and its own stack (push/pop). The readable code never stores: while its guard word is cold it
gives up at entry, before it reads anything else, so the game's own code runs, calls
`PrivateSkill::Get` and the 64-bit shift, and fills the cache exactly as before. Once the cache is
filled neither body calls anything. Not here, and why:

- **No spouse or child rule** (Grok's row: "do not"). Nothing in either body asks about family;
  `unit::Family::GetGrow` and `ParentSingle::GetGrow` (family_grow, src/readable/unit/) ask
  `Person::IsFemale` and choose a side; they were not edited, and no rule about who marries whom
  was guessed.
- **The callers**: `Unit::CanItemEquip` (unit_can_equip_item, docs/EQUIP_USE.md, "male only" and
  "female only" items) calls `Unit::IsFemale` through `guest_call1`; the growth code
  (src/readable/unit/growth_rates.c, docs/GROWTH.md) calls `Person::IsFemale` through
  `guest_call1`. Those calls now reach these overrides. When an override gives up nested (a cold
  cache), its own entry runs the original for that call (include/readable/fe_guest.h, FE_ENTRY):
  the caller's answer does not change. Neither caller's folder was edited.

**Reach.** Any preparations screen already recorded (Grok: one route); the separate capture step
picks it. No chapter is added, none to meet a child.

## 3. Checks

**Host differential test:** `python src/readable/female/tests/female_diff.py` (who_holds_diff.py's
method: the ARM interpreter src/readable/battle/tests/arm_mini.py on extracted/text.bin against the
readable C built with the host gcc; r0, unmapped reads and the ordered list of guest calls, none
expected; nested give-ups and guest writes flagged). While a guard is cold the original reaches the
guard routine before any other read (arm_mini raises "cold guard") and the readable code must give
up at entry. The made-up states are random test values, never game data, and often outside what the
game uses: unmapped unit, person and class pointers (0 and others), records whose high flag word is
on an unmapped page, a unit whose person and class pointers are unmapped, cached bits in either half
of the word, 0, two bits or every bit, each function's cache different from the other's or the same,
guard words cold or hot with other bits set.

**Planted bugs** (`--plant`, 19). `Unit::IsFemale`: the cache test dropped; the wrong guard word;
the other function's cache; only the cache's low word; the unit's own word, the person's or the
class's left out; the unit's word read as 32 bits; the person's word read through the class
pointer; every cached bit required; the raw bits answered; the answer inverted. `Person::IsFemale`:
the cache test dropped; the wrong guard word; the other function's cache; only the cache's low word;
the person's word read as 32 bits; read from the wrong offset; the answer inverted.

Not planted, because they cannot change an answer: the order of the reads (the caches are always
mapped; an unmapped read counts the same bytes in any order and gives 0 either way); the 1-or-0 form
of a correct comparison.

**Tier 2** (`tools/readable/verify.py`): section 4.

## 4. Results (2026-11-17)

- Host test, seed 20261117, 300 cases per function, with `--plant`: **600 cases, 0 mismatches,
  19/19 planted bugs caught**. Paths met: `Unit::IsFemale` answered 1 with the bit from the unit's
  own word, the person's, the class's and each pair and all three, and 0; 27 cold give-ups at entry;
  78 cases with unmapped reads. `Person::IsFemale` answered 1 (89) and 0; 29 cold give-ups; 36 cases
  with unmapped reads. No guest call listed on either side.
- Host test, seed 7, with `--plant`: **600 cases, 0 mismatches, 19/19 planted bugs caught**.
- Host test, seed 7, 1500 cases per function: **3,000 cases, 0 mismatches** (134 and 150 cold
  give-ups at entry).
- Tier 2 (`python tools/readable/verify.py --out build/readable/verify_female --only
  0x00533938,0x0053ED90`; library build 338 s): **2 GAVE-UP, 0 MISMATCH** (`readable-verify: OK`).
  GAVE-UP: both caches are cold in verify's made-up memory, so the readable code gave up at entry and
  only the fallback ran: proves nothing either way (as `who_holds_can_equip_subkind`); shadow pass:
  readable r0 = game r0 for both. No classifier change. This run left out `src/readable/rod_target/`
  (the row 4 batch, running at the same time, was not registered yet and stage.py refuses an
  unregistered marker); the scratch wrapper changed only which folders were walked, nothing in the
  repo.
- `python tools/readable/check.py --selftest`: readable OK (lint 290 rows 0 problems, 55 sources,
  host 146/146, capture 568/568, undo 554/554, self-test 27/27 broken inputs, verify pipeline 28/28),
  run through the same kind of scratch wrapper hiding `src/readable/rod_target/` (unregistered, see
  above); on the plain tree it fails only on that folder's missing registry row.
- `python tools/harness/gen_stubs.py --check`: OK (256 overrides, 64 guard users; both rows carry
  the guard tag: each body calls the guard routine 0x00302C6C).
- Callers' host tests unchanged: `equip_use_diff.py` 300 cases 0 mismatches; `growth_diff.py`
  7,900 cases 0 mismatches.
