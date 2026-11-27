# The class record for a class number (Fates): `Job::Get(unsigned short)`

**In plain words.** Every class (Hoshido Noble, Wyvern Rider, ...) has one fixed record in the game
data: its name, base stats, growths, skills and so on. Most of the game keeps a class as a pointer
to that record, but some places (saves, the arena, the castle, the class-change screen) keep only
its number. `Job::Get(unsigned short)` turns a class number into the record. The game can have more
than one block of class records loaded (the main game data, and any block added later), so it walks
a short list of loaded blocks and picks the first block whose numbers cover the one asked. A number
that no block holds does not give "nothing": it gives the first record of the first block. This
batch (docs/tracks/REWRITE_ORDER5.md row 2, round 25) rewrote that lookup in readable C. It only
reads. The callers (the class-change reader, the castle, the arena, the save code and the rest of
the game) are unchanged.

Status 2026-11-17 (round 25 batch `job_record`), **UNVERIFIED** in the project's sense, and **a
helper, not an override**:

- **1 readable helper** (`src/readable/job_record/job_record.c`, registry row kind `helper`, no
  target row): `job_record_get`.

It gives the same answers as the game's own ARM code on made-up cases (two seeds), with the same
unmapped reads and no guest call; 18/18 planted bugs are caught (section 4). **It was written as an
override and then stood down to a helper**, by the batch's stop rule (the `UnitPool::Get` lesson):
tier 2 could not pick its address, because the function before it in the code runs on into it
(section 2). So the game keeps running its own `Job::Get`, nothing is built into the capture
library for it, and there is nothing to capture. Readable code that needs a class record may call
`job_record_get` directly, as `unit_pool_force` is used. Nothing changes in the game.

Everything below was read in the game's ARM code (objdump of extracted/text.bin, read only,
2026-11-17) [high unless marked]. No table values or game text are copied here.

---

## 1. What it answers

**`Job::Get(unsigned short)`** (0x00341AA4, 26 words with its one-word literal pool: r0 the class
number).

```
node = *(0x006D39A0)                        (literal 0x006D3990 + 0x10: the first list node)
if node != 0:
  repeat:
    block = node[+0x0]                      (the block header)
    first = u16 block[+0x20]                (record 0's class number, job_number, header + 8 + 0x18)
    if number >= first                      (signed, the whole 32-bit register)
       and first + u16 block[+0x6] > number (the block's record count; signed):
         record = node[+0x0] + 8 + (number - first) * 0x80     (the node's block read again)
         if record != 0: return record
         stop walking                       (an address of 0: fall back)
    node = node[+0x8]                       (the next node)
  until node == 0
return *(first node) + 8                    (the first block's record 0; with an empty list the
                                             block word is read from address 0)
```

Details that matter for matching the game exactly:

- The compares are **signed 32-bit on the whole register**, not on 16 bits. Callers pass a 16-bit
  number, so the upper half is normally 0, but the readable code does not assume it (a plant that
  cuts the number to 16 bits is caught).
- The fallback reads **the first node's** block (the game keeps the first node in r12), not the
  last node walked.
- **An empty list** (the word at 0x006D39A0 is 0) reads the block word from address 0: the answer
  is whatever is there plus 8 (8 and four unmapped bytes in made-up memory). The readable code
  makes the same read.
- **A record address of 0** (`adds` / `bne`) falls back too. It can only happen on made-up memory (a
  block at the very top of the address space); the host test places one there.
- In the in-range path the game reads the node's block word a second time. The readable code makes
  the same read. It cannot change an answer: the node's word was already read once just before (a
  4-aligned word is mapped or unmapped as a whole), and with an unmapped node the walk never reaches
  that path (an unmapped block reads first 0 and count 0, so no number is in range).
- Nothing is cached and nothing is called: the body never gives up.
- `Job::Get(const char*)` (0x00341A3C, the lookup by ID label: a hash lookup through
  0x006DCB44 and a tail branch) is a different function and is not part of this batch.

## 2. Why it is a reader, and whether its address can be checked

The body stores nothing: it has no stack frame, no push and no store instruction (26 words:
loads, compares, arithmetic, branches, `bx lr` and the literal). The list it walks is
changed only by `Job::Load` (0x00341B8C) and `Job::Free` (0x00341B0C), which are not here.

**The fall-through (the `UnitPool::Get` lesson).** `castle::CastleButler::GetJob` (0x00341A50,
21 words) ends with `pop {r4, lr}` and a no-op at 0x00341AA0 and then runs on into 0x00341AA4
instead of calling it: the same shape as `map::Mind::GetTradeUnit` falling into `UnitPool::Get`,
whose override was taken out because tier 2 could not pick the address (docs/MOVE.md section 6).
Checked before going on:

- In 3dsrecomp's generated code (the round 22 verify library, build/readable/verify/lib/entries.c
  and code110.c) 0x00341AA4 is a function of its own (`f_00341AA4`, entry-table rows 0x00341AA4,
  0x00341AB4, 0x00341AF0, 0x00341AFC, 0x00341B04). `f_00341A50` leaves through it on both paths:
  its tail branch at 0x00341A6C is `CALL(f_00341AA4)`, and its fall-through after the no-op at
  0x00341AA0 sets the target 0x00341AA4 and goes through the dispatcher (`recomp_call`, which looks
  the address up in the entry table). The hand run on the holder below reached the override from
  that caller on at least one of the two paths [high for "reached", not checked which path].
- **But tier 2 does not pick the address**, which is what failed for `UnitPool::Get` too.
  `tools/readable/verify.py --only 0x00341AA4` (library built 414 s) said **NOT-RUN**: "0 functions
  in both passes and the build's entry table shows no holder for this address". The entry table of
  that build had 0x00341AA4 -> `override_0x00341AA4` (its own row, so the classifier's UNSAMPLED
  rule, "code held inside another function", does not apply), yet 3dsrecomp's `verify` with
  `VERIFY_ONLY=00341AA4` tested no function at all: its own list of functions to sample does not
  start one at 0x00341AA4, the target of a fall-through [med for that reason: read from the
  results, not from 3dsrecomp's code, which is not copied here].
- As extra evidence only (not a gate), `verify` was run by hand on the holder, `VERIFY_ONLY=00341A50`,
  on the same library: in the shadow pass the override was reached from the caller and its r0 matched the game's ("shadow match (1 so far, 0 mismatches)"). The shadow log still counts the holder as "1 mismatched": its only difference is "4 faults against 8" with identical registers, the A-against-2A shape check.py treats as benign in shadow mode (both sides run, so unmapped reads double) [integrate round 25, from the review]. In the readable pass r0
  matched (8) and only r1, r12 and the Z flag differed (scratch registers and flags, the ABI-ONLY
  shape). Verify's made-up memory has the list word 0, so this met only the empty-list path.
- **Decision (stop rule):** an override whose address the checker cannot pick is not kept (the
  task's rule, and what was done with `UnitPool::Get`). The marker was taken out, the registry row
  became kind `helper` (the shape of `unit_pool_force`, whose `Force::Get` falls into
  `UnitPool::GetForce` the same way), and the target row was removed. No classifier was changed.
  Turning it into an override later needs a tier-2 way to check a fall-through target (for example
  a verify pass on the holder that also requires the readable log to show the override was reached
  on more than the empty-list path); that is the owner's or the classifier owner's call.

**Callers** (not edited): 69 ARM branch sites in the code (65 `BL`, 4 tail `B`), plus the
fall-through above and any Thumb `BLX`; among them the class-change reader's guest call
(`CC_JobGet` in src/readable/class_change/class_change.h: `Job::IsHigh(Job::Get(number))`), the
arena's enemy builder (`ArenaData::CalculateEnemy`, docs/TABLES.md) and the save code. The
class-change reader calls it through `guest_call`; with no override that call still runs the game's
own code. Its host test was rerun unchanged (section 4).

**Not here** (Grok's row: "do not"): `Unit::ClassChange` and the seal stores (writers), the class
blocks' loading and freeing, and `AIValue::GetJob` (REWRITE_ORDER5: only after rows 2 and 4 are
overrides, and only if the checker can pick the address).

**Reach.** Grok's row: any fight already on disk, one route. As a helper it has no override entry,
so a capture would record nothing for it: no capture is needed or possible. No chapter is added.

## 3. Checks

**Host differential test:** `python src/readable/job_record/tests/job_record_diff.py` (the helper
is called directly by the test's C driver with the game's argument register; otherwise the female
test's method: the ARM interpreter src/readable/battle/tests/arm_mini.py on extracted/text.bin
against the readable C built with the host gcc; r0, unmapped reads and the ordered list of guest
calls, none expected; nested give-ups and guest writes flagged). The made-up states are random test
values, never game data, and often outside what the game uses: an empty list, an unmapped first
node, unmapped blocks in the list, an unmapped last link, one to five blocks in random order,
overlapping and empty blocks, first numbers and counts up to 0xFFFF, a node at the end of a mapped
page pointing at a block low in memory, a block at the top of the address space so the record
address wraps to 0, class numbers just inside and just outside each block, negative, wider than 16
bits, or with junk in the upper half. List nodes are 4-aligned, as the game's heap nodes are:
arm_mini's unaligned `LDR` rotates the word (ARMv5 style), which is not what the 3DS or 3dsrecomp
does, so a node torn across a page would test the interpreter, not the function (a first run with
such a node showed exactly that, and it was taken out).

**Planted bugs** (`--plant`, 18): the wrong list word; the empty-list test dropped; the lower range
test off by one, or unsigned; the upper range test off by one; the count ignored; the number cut to
16 bits; the wrong offset of the count, of the first number, of the next link, of the records; the
wrong record size; the index not taken from the first number; a record address of 0 answered; the
fallback answering 0, the first node's pointer itself, or the last node's block; only the first
block asked.

Not planted, because they cannot change an answer: the upper range test unsigned (it is reached
only with 0 <= first <= number, so both values are non-negative; a first run planted it and it was
not caught, as expected); dropping the second read of the node's block word (section 1); the order
of the reads (an unmapped read counts the same bytes in any order).

**Tier 2** (`tools/readable/verify.py`): section 4.

## 4. Results (2026-11-17)

- Host test, seed 20261117, 300 cases, with `--plant`: **300 cases, 0 mismatches, 18/18 planted
  bugs caught**. Paths met: a record of the first to the fifth listed block (with and without
  unmapped reads on the way), no block holds it (fallback, 126 cases, 40 more with unmapped reads),
  empty list (18), record address wraps to 0 (fallback, 11). No guest call on either side.
- Host test, seed 7, with `--plant`: **300 cases, 0 mismatches, 18/18 planted bugs caught**.
- Host test, seed 7, 1500 cases: **1,500 cases, 0 mismatches** (wrap to 0: 60; empty list: 75).
- Tier 2 (`python tools/readable/verify.py --out build/readable/verify_job_record --only
  0x00341AA4`, while the row was still an override; library build 414 s): **1 NOT-RUN, 0 MISMATCH**
  (`readable-verify: 1 problem(s)`): verify could not pick the address (section 2). By hand on the
  holder 0x00341A50: shadow match 1, 0 mismatches (the log's "1 mismatched" is only "4 faults against 8", the benign shadow shape); readable pass r0 equal, r1/r12/Z only. The row is
  now a helper, which tier 2 does not run. The scratch library (553 MB) was deleted; its logs, the
  summary and the entry-table rows were kept.
- `python tools/readable/check.py --selftest` (helper shape): readable OK (lint 298 rows 0
  problems, 60 sources, host 146/146, capture 568/568, undo 554/554, self-test 27/27 broken
  inputs, verify pipeline 28/28).
- `python tools/harness/gen_stubs.py --check` (helper shape): OK (263 overrides, 67 guard users;
  this row is not in targets.csv any more).
- Caller's host test unchanged: `class_change_diff.py` 1,500 cases, 0 mismatches.

Logs of these runs were kept under build/readable/job_record/logs/ (gitignored).
