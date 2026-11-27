# Who a visited castle can add (Fates): castle::JoinSequence

**In plain words.** When you enter your castle, the game looks up a small list file
(castle/castle_join.bin.lz) of characters who can come and ask to join. Each entry names a
character, up to three chapters and up to three building types. A character is offered when no
unit of that character is in your army yet, when at least one of the chapters is cleared (or the
entry names none), and when at least one of the building types is built (or the entry names none).
At most six are offered at once. The game then plays the join scene for them.

This batch (docs/tracks/REWRITE_ORDER2.md batch 7) reads that decision. The function that makes it
is **not a reader**: it loads the file into memory, stores the result into its caller's list and
frees the file. So there is no override here, only a **helper** that gives the same answer without
loading, storing or freeing anything. Nothing changes in the game, and nothing here can make a
character join.

Status 2026-11-16 (round 12 batch `castle_join`), **UNVERIFIED** in the project's sense:

- **0 readable overrides.**
- **1 helper** (F-017): `castle_join_offer` (`src/readable/castle_join/castle_join.c`, registry row
  `0x00451DF4`, kind helper). It gives the same answers as the game's own ARM code on made-up cases
  (two seeds), with the same guest calls in the same order and the same unmapped reads; the planted
  bugs are in section 5.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-16) [high unless marked]. No table values or game text are copied here.

---

## 1. What the game does: `castle::JoinSequence::GetJoinPersonList` (0x00451DF4)

Its only caller is `castle::CastleSeq::InitEnterEventJoin` (0x0049BCB0), which then hands the list
to `JoinSequence::Create`. Argument: a `castle::JoinPersonList_t*` (six Person pointers, then a
count word at +24).

```
list is 0                                  -> return 0 (nothing else)
list.count = 0                             (a store into the caller's list)
open castle/castle_join.bin.lz            (ArchiveFile on the stack: a heap load)
table = 0 when the file or its body word (+0x70) is 0, else body + 0x20
for each record i while i < table.count (signed, read again after every record):
    record = table + 4 + 32 * i
    UnitPool::GetFromPerson(record.person_label, forces 0x59) is not 0  -> skip (already in the army)
    chapter condition: the three labels at +8, +12, +16
        all 0 -> met
        else  -> castle::cut::IsCleared(label) for each in turn (0 labels too); the first yes -> met;
                 none -> skip
    building condition: the three words at +20, +24, +28
        all -1 -> met
        else  -> for each in turn: Castle::Get, Castle::GetData, then
                 BuildingDispos::IsBuilt(data's dispos (+4), the word's low byte sign-extended, 3, 0);
                 the first yes -> met; none -> skip
    person = Person::Get(record.person_label)
    if list.count is not 6: list[count] = person, count + 1     (a store into the caller's list)
    found = 1                                                   (also when the list was full)
free the file                              (FileBase::Free)
return found
```

The force mask 0x59 is forces 0, 3, 4 and 6 [low for which forces those are]. The rank 3 passed to
IsBuilt is compared with a byte of the building's record [low for what it means: perhaps the
building's level]. `IsCleared` is 1 when the chapter's map spot has state 2. The record's first word
(+0) is not read.

## 2. Why it is not a reader, and what the helper does instead

GetJoinPersonList stores into the caller's list (its count first, then each Person), and it loads
and frees a file on the heap. A replay of it is not safe (a load is not idempotent), and the stores
are game state. So it gets no override (F-017, F-021: readers only).

**`castle_join_offer(ctx, file, out)`** starts after the load: `file` is the loaded file (the
pointer the game's ArchiveFile holds). It runs the loop above with the same guest calls, in the
game's order, with the game's arguments, and puts the count and the Persons into `out` in host
memory. It returns 1 when any record qualified (also past the sixth), else 0. It loads, frees and
stores nothing in the guest.

`UnitPool::GetFromPerson` can reach `Person::IsDownload` (through `Unit::IsUnique`, for a unit with
state bit 28), whose readable override gives up while its one-time cache is cold. A give-up inside a
guest call counts as a mismatch, so the helper asks that cache's guard (0x006D3B3C) first and gives
up while it is cold, before reading anything. That can be earlier than the game would reach it (an
empty table never calls GetFromPerson); the host test allows exactly that early give-up.

What the helper is for: knowing who the castle would offer, from a copy of the join file, without
pressing yes. A mod that adds castle recruits can check its file against the game's own rule. It
cannot make anyone join.

What it does not do: the game frees the file before it returns, so no loaded copy stays in memory
for a live compare to read. The helper needs a file the caller loaded; that is why it has no live
(capture) check and no tier-2 run (both work on overrides only).

## 3. The guest calls (each read on 2026-11-16, with what it calls; none stores outside its own stack)

| Call | What it does |
|---|---|
| `UnitPool::GetFromPerson(const char*, unsigned)` 0x004F5E74 | Person::Get, then the first unique unit of that Person in a force of the mask (Unit::IsUnique, readable `unit_is_unique`); 0 if none |
| `castle::cut::IsCleared(const char*)` 0x00469D34 | 0 for 0; Chapter::Get, Spot::Get, Spot::GetData; 1 when the spot's state byte is 2 |
| `Castle::Get` 0x0044544C | the castle object (a global word) |
| `Castle::GetData` 0x0044545C | one of three records of the castle object, by its kind |
| `castle::BuildingDispos::IsBuilt(EventType, int, const char*)` 0x00455610 | walks the placed buildings; GetDataByUniqueIndex, IsStatue, strcmp only when the name is not 0 (here it is 0) |
| `Person::Get(const char*)` 0x0044A6DC | IdentHash::GetSurely, a hash lookup; since round 27 the override `person_record_by_name` (docs/PERSON_RECORD.md), so this guest call reaches readable code |

## 4. Not here, and why

- **`castle::JoinSequence::Create`** (0x00451F94): the join scene (a new process, the message file,
  a scene object). Not a reader.
- **The load and the stores** of GetJoinPersonList itself (section 2).
- **The castle "!" join talk, `JoinSeq::Join`, `MI_Join`, `AfterBattleSequence::MI_JoinUnit`**: the
  scene and menus that add the unit. They store into the army.
- **The building level-up menu and the spa talk**: other batches (REWRITE_ORDER2 says so).
- **No route** reaches the castle join talk: a castle "!" talk was tried and not reached, and no
  piece is added to grind one (REWRITE_ORDER2 batch 7).

## 5. Checks

**Host differential test:** `python src/readable/castle_join/tests/castle_join_diff.py`
(weapon_rank_diff.py's method: the ARM interpreter src/readable/battle/tests/arm_mini.py on
extracted/text.bin against the readable C built with the host gcc; the whole ordered list of guest
calls with their argument registers, unmapped reads, nested give-ups and guest writes). The ARM side
runs the whole of GetJoinPersonList. Its file load is answered on the ARM side only: the
ArchiveFile constructor puts the case's file pointer into the stack object (and must be asked for
the join file's name), and FileBase::Free does nothing; those two calls are not listed, because the
helper never makes them. The expected result is what the original stores into the list (count and
Persons) and its return value, folded into one number (FNV-1a); the original may write nothing else
outside its stack. The six other callees are answered by one table on both sides; GetFromPerson
raises "cold guard" while the download cache is cold. The made-up states are random test values,
never game data, and often outside what the game uses (a file of 0, a body of 0, unmapped files and
bodies, a table that runs onto an unmapped page, a mapped page 0, counts that are 0, negative or past
six Persons taken, building words of -1, 0x80, 0x1FF or negative, chapter labels of 0, Persons and
GetData answers of 0 or unmapped). The test prints which paths the cases met.

**Planted bugs** (`--plant`, 20): the cache asked first; the file and body tests; the signed count;
the record offset; the army skip and its force mask; the order of the two conditions; "any of
three" against "all three"; 0 chapter labels skipped; only the first entry tested for "none" (both
lists); Castle::Get/GetData asked once; the building byte passed whole and zero-extended; the rank;
the dispos offset; Person::Get replaced by a direct read; the list cap; the count returned instead of
1. One planted bug was dropped as an equivalent mutant ("found only while the list has room": the
list is full only after six Persons were taken, so found is already 1).

## 6. Results (2026-11-16)

- Host test, seed 20261117 (the default), 300 cases, with `--plant`: **300 cases, 0 mismatches,
  20/20 planted bugs caught** (plants on 300 cases of seed 20261118). Paths met: 0 Persons taken 144,
  1 to 6 taken 140, more than 6 taken (list full) 7, chapter asked 146, building asked 144, no table
  (file or body 0 or unmapped) 80, table onto an unmapped page 35, page 0 mapped 9, cases with
  unmapped reads 101, cold cache 9 (both gave up), allowed early give-ups 2.
- Host test, seed 7, with `--plant`: **300 cases, 0 mismatches, 20/20 planted bugs caught**.
- Host test, seed 7, 1500 cases: **1,500 cases, 0 mismatches** (68 cold, 40 allowed early give-ups;
  63 with the list full, 128 torn tables, 57 with page 0 mapped).
- Tier 2 (`tools/readable/verify.py`): **not applicable**. It runs overrides only, and this batch has
  none. No classifier change.
- Live compare: not applicable for the same reason (a helper is never entered in the game).
- Capture step (round 13, session `r13-cap-castle_join`, 2026-11-16): **not applicable, and not a
  failure.** It ran nothing and made no session: `castle_join_offer` has no row in
  config/harness/targets.csv, so `parallel.py --only castle_join_offer` stops ("not a readable
  override") before any route starts. Nothing came out bad. The reader was looked at again and
  kept as it is (nothing to fix; it stays registered as a helper), and every host gate was run
  again on 2026-11-16 with the same results as above. It stays UNVERIFIED (host-tested only). A live
  check would need GetJoinPersonList itself captured, which stores into game state and so is out
  of scope while the rewrite is readers only.
- `python tools/readable/check.py --selftest`: readable OK (lint 276 rows 0 problems, 47 sources,
  host 146/146, capture 568/568, undo 554/554, self-test 27/27 broken inputs, verify pipeline 28/28).
  `python tools/harness/gen_stubs.py --check`: OK (241 overrides at the time of the run; none of
  them this batch's).
