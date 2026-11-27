# Can this unit open a door (Fates): `Unit::CanKeyDoor`

**In plain words.** Some maps have doors. A unit may open one when it has the lock-opening skill
(the thief line's skill) or carries an item that opens doors (a key). When the map builds what a
door does, and when the enemy AI decides whether a unit may walk through doors or go and open one,
the game asks "can this unit open a door". This batch (docs/tracks/REWRITE_ORDER5.md row 5, round
26) rewrites that question. It stores nothing: it only reads, and it asks the same two questions the
game asks (does the unit have the skill; which carried item opens doors) of the game's own
functions, in the game's order. The callers are unchanged.

Status 2026-11-17 (round 26 batch `key_door`), **UNVERIFIED** in the project's sense:

- **1 readable override** (`src/readable/key_door/key_door.c`, registry and target rows added):
  `key_door_unit_can_open`.

It gives the same answers as the game's own ARM code on made-up cases (three seeds), with the same
unmapped reads and the same guest calls in the same order; the planted bugs and the tier-2 result are
in section 4. Live compare: not run here (the separate capture step does that). Status stays
UNVERIFIED until the owner's call. Nothing changes in the game.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-17) [high unless marked]. No table values or game text are copied here: the skill's name is
an ID name (SEID_), given here in English.

---

## 1. What it decides

**`Unit::CanKeyDoor(void) const`** (0x00529E20, 29 instructions and a literal pool of one address
and the inline ID name: r0 the unit).

```
first time only (one cache, behind a C++ guard word):
  skill = EquipSkill number of the ID "lock-opening skill"   (guard 0x006D98F8, s16 at 0x006D96A0;
                                                               literal 0x006D9628 + 0x2D0 and + 0x78)

if Unit::IsEquipSkill(unit, skill) != 0:   return 1        (0x0052DD04, the s16 sign-extended)
if Unit::GetItemIndexKeyDoor(unit) != -1:  return 1        (0x00530BDC, the carried slot or -1)
return 0
```

Details that matter for matching the game exactly:

- The skill number is read as a **signed** half-word (`ldrsh`) and passed sign-extended in the
  whole register (plants that read it unsigned or cut it to 8 bits are caught).
- The skill's answer is tested on the **whole register** (`cmp r0,#0`): any non-zero answer is yes,
  not only 1.
- The item's answer is compared with **-1 only** (`cmn r0,#1`): -2, 0xFFFF or 0x80000000 count as
  "has a key item", exactly as the game does; slot 0 is a real slot.
- The item is asked **only when the skill says no**: the order and the number of guest calls are
  part of the behaviour (the host test compares the call list).
- The answer is 1 or 0, never the slot.
- The body reads nothing of the unit itself; both callees read it.

**Callers** (every ARM BL to 0x00529E20 in text.bin, 4 sites, unchanged):
`map::(anonymous)::Door::BuildAttribute` (what a door does on the map),
`AIThink::ProcessingMutation`, `AIThink::GetDeployFreeMoveFlag` (the readable
`ai_deploy_free_move_flag`, src/readable/ai/ai_permission.c, not edited: it still calls this
function through a guest call, and in the game that call can now reach this override), and
`AIThink::ToDestroy`.

## 2. Why it is a reader

The body's only stores are into its own cache (the `strh` after the name lookup, the first time it
runs) and its own stack (push/pop). The readable code never stores: while the guard word is cold it
gives up at entry, before it reads or calls anything else, so the game's own code runs, calls
`EquipSkill::Get` (0x001758C4) and fills the cache exactly as before. The two callees stay the
game's own functions, called as guests exactly as the game calls them (`unit_has_skill` is already a
readable override of `Unit::IsEquipSkill`; `Unit::GetItemIndexKeyDoor` is not rewritten, its own
one-time caches are its own business). Not here, and why:

- **`Unit::IsMoveNear` and `Unit::IsEnemyInsideAttackArea`** (Grok's row: "do not"): they store a
  move image.
- **`Unit::GetItemIndexKeyDoor`** itself: not in Grok's row; it is a callee with two one-time caches
  of its own and a slot walk, left as the game's code.
- **The AI folder** (src/readable/ai/) was not edited: the AI note's guest call stays as it is.

**Reach.** An enemy-phase route already on disk, or a map with doors (Grok: one route); the
separate capture step picks it. No chapter is added. Whether a recorded route reaches it is for the
capture step to show [low: not checked here].

## 3. Checks

**Host differential test:** `python src/readable/key_door/tests/key_door_diff.py`
(job_female_diff.py's method: the ARM interpreter src/readable/battle/tests/arm_mini.py on
extracted/text.bin against the readable C built with the host gcc; r0, unmapped reads and the
ordered list of guest calls with their argument registers; nested give-ups and guest writes
flagged). The two callees are stubs whose answers each case chooses. While the guard is cold the
original reaches the guard routine before any other read or call (arm_mini raises "cold guard") and
the readable code must give up at entry. The made-up states are random test values, never game data,
and often outside what the game uses: negative, zero and large skill numbers, skill answers 0, 1, 2,
0x100, 0x80000000 and 0xFFFFFFFF, item answers -1, -2, 0 .. 5, 0xFFFF, 0x7FFFFFFF and 0x80000000,
unit pointers 0, unmapped or random, the words around the cache and the guard filled with junk,
decoy answers for a wrong skill argument or a wrong unit, guard words cold or hot with other bits
set.

**Planted bugs** (`--plant`, 18): the cache test dropped; the wrong guard word (the next word, the
word before); the wrong cache half-word (+2, or another skill's cache at 0x006D96AC); the cache read
unsigned; cut to 8 bits; the skill not asked; asked of the wrong unit; only an answer of exactly 1
taken; the item asked even when the skill said yes; the item asked first; only slots 0 and up taken
as keys; slot 0 taken as none; the raw slot answered; the answer inverted; 2 answered for the skill;
only the low half-word of the item's answer tested.

Not planted, because they cannot change an answer: the 1-or-0 form of a correct comparison; reading
the cache before or after the guard test once the guard is hot (the cache is always mapped and the
test cannot see the order of two plain reads).

**Tier 2** (`tools/readable/verify.py`): section 4.

## 4. Results (2026-11-17)

- Host test, seed 20261117, 300 cases, with `--plant`: **300 cases, 0 mismatches, 18/18 planted bugs
  caught**. Paths met: skill yes -> 1 (154); item asked -> 1 (66); item asked -> 0 (46); 34 cold
  give-ups at entry; 378 guest calls listed.
- Host test, seed 7, 300 cases, with `--plant`: **300 cases, 0 mismatches, 18/18 planted bugs
  caught** (23 cold give-ups; skill yes 132; item asked -> 1 75, -> 0 70). No case has an unmapped
  read: the body reads only its cache; the callees read the unit.
- Host test, seed 7, 1500 cases: **1,500 cases, 0 mismatches** (139 cold give-ups; skill yes 703;
  item asked -> 1 370, -> 0 288).
- Host test, seed 20261118, 300 cases: **300 cases, 0 mismatches**.
- Tier 2 (`python tools/readable/verify.py --out build/readable/verify_key_door --only
  0x00529E20`; library build 356 s, 61 staged files): **1 GAVE-UP, 0 MISMATCH**
  (`readable-verify: OK`). GAVE-UP: the cache is cold in verify's made-up memory, so the readable
  code gave up at entry and only the fallback ran: proves nothing either way (as
  `job_female_is_female`); shadow pass: no comparison logged, the fault surplus is the readable code
  run after the original (verify's host counter, not guest state). No classifier change. The library
  (543 MB) was deleted after the run; its logs are kept in build/readable/verify_key_door/.
- `python tools/readable/check.py --selftest`: readable OK (lint 300 rows 0 problems, 62 sources,
  host 146/146, capture 568/568, undo 554/554, self-test 27/27 broken inputs, verify pipeline 28/28;
  the first run stopped on the row 3 batch's then-unregistered skill_record.c, the rerun after it
  registered is green).
- Neighbours rerun with this override linked in: `ai_perm_diff.py` 5,400 cases 0 mismatches,
  `skill_diff.py` 5,100 cases 0 mismatches.
- `python tools/harness/gen_stubs.py --check`: OK (265 overrides with the row 3 batch, 68 guard users; the row carries the
  guard tag: the body calls the guard routine 0x00302C6C).
